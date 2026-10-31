"""Data containers for memories."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

KINDS = ("fact", "preference", "episode", "plan", "summary")

KIND_LABELS = {
    "fact": "事实",
    "preference": "喜好",
    "episode": "经历",
    "plan": "计划",
    "summary": "归纳",
}


@dataclass
class Memory:
    id: int
    kind: str
    content: str
    keywords: list[str] = field(default_factory=list)
    importance: float = 0.5
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_access_at: float | None = None
    access_count: int = 0
    status: str = "active"
    superseded_by: int | None = None
    source_ids: list[int] = field(default_factory=list)

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    def age_days(self, now: float | None = None) -> float:
        now = now if now is not None else time.time()
        return max(0.0, (now - self.created_at) / 86400.0)

    def idle_days(self, now: float | None = None) -> float:
        now = now if now is not None else time.time()
        anchor = self.last_access_at or self.created_at
        return max(0.0, (now - anchor) / 86400.0)

    def preview(self, length: int = 60) -> str:
        text = " ".join(self.content.split())
        return text if len(text) <= length else text[: length - 1] + "…"


@dataclass
class Retrieved:
    memory: Memory
    score: float
    relevance: float
