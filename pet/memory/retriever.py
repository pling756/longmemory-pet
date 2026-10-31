"""Hybrid recall: lexical relevance + recency + importance + reinforcement.

The retriever deliberately stays explainable. Every memory gets a score made of
four bounded parts, then an MMR pass keeps the injected context diverse.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .models import Memory, Retrieved
from .store import MemoryStore
from .tokenize import expand_query, jaccard, tokens

RECALL_MARKERS = (
    "记得",
    "上次",
    "之前",
    "最近",
    "刚刚",
    "以前",
    "还记得",
    "上次说",
    "好累",
    "难过",
    "开心",
    "压力",
    "烦",
)

HALF_LIFE_DAYS = {
    "fact": 240.0,
    "preference": 365.0,
    "episode": 12.0,
    "plan": 30.0,
    "summary": 120.0,
}
WEIGHTS = {
    "relevance": 0.55,
    "recency": 0.18,
    "importance": 0.17,
    "access": 0.10,
}
MMR_LAMBDA = 0.78


@dataclass
class RetrievalResult:
    items: list[Retrieved]
    profile: dict[str, str]

    @property
    def ids(self) -> list[int]:
        return [item.memory.id for item in self.items]

    def as_context(self, max_chars: int = 1600) -> str:
        if not self.items:
            return ""
        lines: list[str] = []
        used = 0
        for item in self.items:
            memory = item.memory
            stamp = time.strftime("%Y-%m-%d", time.localtime(memory.created_at))
            line = f"- [{memory.kind_label}] {memory.content}（{stamp}）"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines)


class Retriever:
    def __init__(self, store: MemoryStore):
        self.store = store

    def retrieve(
        self,
        query: str,
        *,
        budget_chars: int = 1600,
        max_items: int = 12,
        now: float | None = None,
    ) -> RetrievalResult:
        now = now if now is not None else time.time()
        query = (query or "").strip()
        profile = self.store.profile()

        expanded = expand_query(query)
        lexical = self.store.search_fts(expanded, limit=80)
        if not lexical:
            lexical = self.store.search_like(expanded, limit=60)

        relevance: dict[int, float] = {}
        if lexical:
            scores = [score for _, score in lexical]
            if len(lexical) == 1:
                relevance[lexical[0][0]] = 0.85
            else:
                best, worst = min(scores), max(scores)
                span = worst - best
                for memory_id, score in lexical:
                    relevance[memory_id] = (
                        0.5 if span <= 1e-9 else (worst - score) / span
                    )

        # Recent context helps a lexical hit ("上次那个项目" -> recent episode).
        # Without any hit or an explicit recall cue we stay silent instead of
        # dumping unrelated recent memories into every prompt.
        wants_recall = any(marker in query for marker in RECALL_MARKERS)
        if lexical or wants_recall:
            for memory in self.store.recent_memories(limit=6, days=10):
                relevance.setdefault(memory.id, 0.16)

        memories = self.store.get_memories(list(relevance))
        scored: list[Retrieved] = []
        for memory_id, rel in relevance.items():
            memory = memories.get(memory_id)
            if not memory or memory.status != "active":
                continue
            recency = 0.5 ** (memory.age_days(now) / HALF_LIFE_DAYS.get(memory.kind, 60.0))
            access = min(1.0, math.log1p(memory.access_count) / math.log1p(6))
            final = (
                WEIGHTS["relevance"] * rel
                + WEIGHTS["recency"] * recency
                + WEIGHTS["importance"] * memory.importance
                + WEIGHTS["access"] * access
            )
            # A brand-new trivial episode should not outrank a durable fact.
            if rel < 0.1 and memory.kind in {"episode"}:
                final *= 0.7
            if final >= 0.12:
                scored.append(Retrieved(memory=memory, score=final, relevance=rel))

        if not scored:
            return RetrievalResult(items=[], profile=profile)

        scored.sort(key=lambda item: item.score, reverse=True)
        selected = self._mmr(scored, budget_chars)
        return RetrievalResult(items=selected, profile=profile)

    @staticmethod
    def _mmr(candidates: list[Retrieved], budget_chars: int) -> list[Retrieved]:
        selected: list[Retrieved] = []
        used_chars = 0
        pool = candidates[:24]
        token_sets = {
            item.memory.id: set(tokens(item.memory.content)) for item in pool
        }
        while pool and len(selected) < 12:
            best_index = 0
            best_value = -1.0
            for index, item in enumerate(pool):
                if selected:
                    overlap = max(
                        jaccard(token_sets[item.memory.id], token_sets[chosen.memory.id])
                        for chosen in selected
                    )
                else:
                    overlap = 0.0
                value = MMR_LAMBDA * item.score - (1 - MMR_LAMBDA) * overlap
                if value > best_value:
                    best_value = value
                    best_index = index
            item = pool.pop(best_index)
            cost = len(item.memory.content) + len(item.memory.keywords) * 4 + 8
            if selected and used_chars + cost > budget_chars:
                continue
            selected.append(item)
            used_chars += cost
        return selected
