"""Memory consolidation: fold old episodes into compact summaries and archive
the originals, so the store stays useful instead of growing forever.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..llm import LLMError, MockLLM, extract_json
from .models import Memory
from .store import MemoryStore
from .tokenize import tokens

SUMMARY_PROMPT = """你在整理一只桌宠的长期记忆。下面是一批较早的日常片段，
请把它们归纳成 1~3 条更耐久的记忆（仍然用第三人称）。

要求：
- 保留人物、地点、偏好、承诺、重要日期等长期有用的信息；
- 合并重复内容，丢弃寒暄和一次性情绪；
- content 每条 <=60 字；
- importance 0.5~0.8；keywords 2~5 个。

只输出 JSON：
{"summaries":[{"content":"...","importance":0.65,"keywords":["..."]}]}"""


@dataclass
class ConsolidationResult:
    created: int = 0
    archived: int = 0
    summaries: list[Memory] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.created > 0 or self.archived > 0

    def describe(self) -> str:
        if not self.changed:
            return "暂时没有需要整理的记忆。"
        return f"把 {self.archived} 条旧片段归纳成了 {self.created} 条长期记忆。"


class Consolidator:
    def __init__(
        self,
        store: MemoryStore,
        llm,
        *,
        threshold: int = 24,
        min_age_days: float = 7.0,
        chunk_size: int = 12,
    ):
        self.store = store
        self.llm = llm
        self.threshold = max(2, threshold)
        self.min_age_days = max(0.0, min_age_days)
        self.chunk_size = max(3, chunk_size)

    def auto_due(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        cutoff = now - self.min_age_days * 86400
        return self.store.count_active_episodes_before(cutoff) >= self.threshold

    def run(self, *, force: bool = False) -> ConsolidationResult:
        now = time.time()
        if force:
            episodes = self.store.list_memories(kind="episode", limit=36)
            episodes.sort(key=lambda memory: memory.created_at)
        else:
            cutoff = now - self.min_age_days * 86400
            if self.store.count_active_episodes_before(cutoff) < self.threshold:
                return ConsolidationResult()
            episodes = self.store.active_episodes_before(cutoff, limit=48)

        if len(episodes) < 3:
            return ConsolidationResult()

        result = ConsolidationResult()
        for start in range(0, len(episodes), self.chunk_size):
            chunk = episodes[start : start + self.chunk_size]
            if len(chunk) < 3:
                continue
            try:
                summaries = self._summarize(chunk)
            except (LLMError, ValueError) as exc:
                print(f"[memory] 归纳失败，保留原片段：{exc}")
                continue
            if not summaries:
                continue
            summary_ids: list[int] = []
            for content, importance, keywords in summaries:
                memory_id = self.store.add_memory(
                    "summary",
                    content,
                    keywords=keywords,
                    importance=importance,
                    created_at=max(memory.created_at for memory in chunk),
                    source_ids=[memory.id for memory in chunk],
                )
                summary_ids.append(memory_id)
                result.created += 1
            if summary_ids:
                anchor = summary_ids[0]
                for memory in chunk:
                    self.store.archive_memory(memory.id, superseded_by=anchor)
                    result.archived += 1
                loaded = self.store.get_memories(summary_ids)
                result.summaries.extend(loaded.values())
        return result

    def _summarize(self, chunk: list[Memory]) -> list[tuple[str, float, list[str]]]:
        if isinstance(self.llm, MockLLM):
            return _heuristic_summaries(chunk)
        listing = "\n".join(
            f"- {time.strftime('%Y-%m-%d', time.localtime(m.created_at))} {m.content}"
            for m in chunk
        )
        reply = self.llm.chat(
            [
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": listing},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        data = extract_json(reply)
        raw = data.get("summaries")
        if not isinstance(raw, list):
            raise ValueError("模型没有返回 summaries 数组")
        out: list[tuple[str, float, list[str]]] = []
        for item in raw[:3]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            try:
                importance = float(item.get("importance", 0.6))
            except (TypeError, ValueError):
                importance = 0.6
            keywords = item.get("keywords") or []
            if isinstance(keywords, str):
                keywords = [keywords]
            keywords = [str(k).strip() for k in keywords if str(k).strip()][:5]
            out.append((content[:120], max(0.45, min(0.9, importance)), keywords))
        return out

    def decay(self) -> int:
        return self.store.decay()


def _heuristic_summaries(chunk: list[Memory]) -> list[tuple[str, float, list[str]]]:
    """Offline summary: keep the most important fragments, deduplicated."""
    ranked = sorted(chunk, key=lambda m: m.importance, reverse=True)[:4]
    ranked.sort(key=lambda m: m.created_at)
    fragments: list[str] = []
    seen_terms: set[str] = set()
    for memory in ranked:
        signature = set(tokens(memory.content, keep_full_cjk=False))
        if signature and len(signature & seen_terms) / len(signature) > 0.8:
            continue
        seen_terms |= signature
        fragments.append(memory.content)
    if not fragments:
        return []
    content = "那段时间里，" + "；".join(f.rstrip("。") for f in fragments[:3]) + "。"
    keywords = ["回顾"]
    for memory in ranked[:3]:
        keywords.extend([k for k in memory.keywords if k not in keywords][:1])
    importance = min(0.8, max(0.5, sum(m.importance for m in chunk) / len(chunk) + 0.08))
    return [(content[:150], importance, keywords[:5])]
