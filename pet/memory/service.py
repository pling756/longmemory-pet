"""Facade used by the chat engine and the UI."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .consolidator import ConsolidationResult, Consolidator
from .extractor import ExtractedMemory, build_extractor
from .models import Memory
from .retriever import RetrievalResult, Retriever
from .store import MemoryStore
from .tokenize import similarity


@dataclass
class RecallResult:
    items: RetrievalResult
    touched: list[int] = field(default_factory=list)
    budget_chars: int = 1600

    @property
    def context(self) -> str:
        return self.items.as_context(self.budget_chars)

    @property
    def ids(self) -> list[int]:
        return self.items.ids


@dataclass
class StoreResult:
    created: list[Memory] = field(default_factory=list)
    reinforced: list[Memory] = field(default_factory=list)
    profile_updated: list[str] = field(default_factory=list)


class MemoryService:
    def __init__(
        self,
        store: MemoryStore,
        llm,
        *,
        recall_budget_chars: int = 1600,
        max_memories_per_turn: int = 4,
        dedupe_threshold: float = 0.82,
        consolidate_threshold: int = 24,
        force_heuristic: bool = False,
    ):
        self.store = store
        self.llm = llm
        self.recall_budget_chars = recall_budget_chars
        self.max_memories_per_turn = max_memories_per_turn
        self.dedupe_threshold = dedupe_threshold
        self.retriever = Retriever(store)
        self.extractor = build_extractor(
            llm,
            max_items=max_memories_per_turn,
            force_heuristic=force_heuristic,
        )
        self.consolidator = Consolidator(
            store, llm, threshold=consolidate_threshold
        )

    # ---------------------------------------------------------------- recall
    def recall(self, query: str, budget_chars: int | None = None) -> RecallResult:
        budget = budget_chars or self.recall_budget_chars
        result = self.retriever.retrieve(query, budget_chars=budget)
        if result.ids:
            self.store.touch(result.ids)
        return RecallResult(items=result, touched=result.ids, budget_chars=budget)

    # ---------------------------------------------------------------- write
    def remember_turn(
        self,
        user_text: str,
        assistant_text: str = "",
        *,
        source_ids: list[int] | None = None,
    ) -> StoreResult:
        extraction = self.extractor.extract(user_text, assistant_text)
        result = StoreResult()
        current_profile = self.store.profile()
        for item in extraction.memories[: self.max_memories_per_turn]:
            stored, reinforced = self._store_one(item, source_ids or [])
            if stored is not None:
                result.created.append(stored)
            if reinforced is not None:
                result.reinforced.append(reinforced)

        for key, value in extraction.profile.items():
            current = current_profile.get(key)
            if current == value:
                continue
            self.store.set_profile(key, value)
            result.profile_updated.append(key)
        return result

    def _store_one(
        self, item: ExtractedMemory, source_ids: list[int]
    ) -> tuple[Memory | None, Memory | None]:
        if item.importance < 0.15 or len(item.content) < 2:
            return None, None
        duplicate: Memory | None = None
        best = 0.0
        for candidate in self.store.dedupe_candidates(item.kind, limit=200):
            score = similarity(item.content, candidate.content)
            if score > best:
                best = score
                duplicate = candidate
        if duplicate is not None and best >= self.dedupe_threshold:
            self.store.reinforce(duplicate.id, item.importance)
            return None, self.store.get_memory(duplicate.id)

        memory_id = self.store.add_memory(
            item.kind,
            item.content,
            keywords=item.keywords,
            importance=item.importance,
            source_ids=source_ids,
        )
        return self.store.get_memory(memory_id), None

    # ----------------------------------------------------------- maintenance
    def maybe_consolidate(self, force: bool = False) -> ConsolidationResult:
        if not force and not self.consolidator.auto_due():
            return ConsolidationResult()
        return self.consolidator.run(force=force)

    def decay(self) -> int:
        return self.consolidator.decay()

    def forget(self, memory_id: int) -> None:
        self.store.delete_memory(memory_id)

    # ---------------------------------------------------------------- reads
    def search(self, query: str, limit: int = 200) -> list[Memory]:
        query = (query or "").strip()
        if not query:
            return self.store.list_memories(limit=limit)
        ids: list[int] = []
        relevance = dict(self.store.search_fts(query, limit=limit))
        if not relevance:
            relevance = dict(self.store.search_like(query, limit=limit))
        ids.extend(relevance.keys())
        memories = self.store.get_memories(ids)
        ordered = sorted(
            memories.values(),
            key=lambda m: (relevance.get(m.id, 0.0), m.importance, m.created_at),
            reverse=True,
        )
        return ordered[:limit]

    def recent_messages(self, limit: int = 12) -> list[dict]:
        return self.store.recent_messages(limit=limit)

    def stats(self) -> dict:
        return self.store.stats()

    def profile(self) -> dict[str, str]:
        return self.store.profile()

    @staticmethod
    def today_stamp(ts: float | None = None) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts or time.time()))
