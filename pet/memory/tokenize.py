"""Dependency-free tokenizer for Chinese + English.

SQLite's unicode61 tokenizer treats a whole run of CJK characters as one token,
which makes substring search useless. We index overlapping bigrams instead
("长记忆" -> "长记 记忆"), mirroring the same segmentation on the query side.
"""
from __future__ import annotations

import re

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_WORD = re.compile(r"[A-Za-z0-9_]+")
_SPACE = re.compile(r"\s+")


def tokens(text: str, *, keep_full_cjk: bool = True) -> list[str]:
    text = (text or "").lower()
    out: list[str] = []
    for match in _CJK.finditer(text):
        run = match.group(0)
        if len(run) == 1:
            out.append(run)
            continue
        if keep_full_cjk and len(run) <= 8:
            out.append(run)
        out.extend(run[i : i + 2] for i in range(len(run) - 1))
    out.extend(_WORD.findall(text))
    # Stable de-duplication.
    seen: set[str] = set()
    result: list[str] = []
    for token in out:
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def search_text(*parts: str) -> str:
    """Build the whitespace-joined text stored in the FTS column."""
    return " ".join(tokens(" ".join(p for p in parts if p), keep_full_cjk=True))


def match_query(query: str, limit: int = 28) -> str:
    toks = tokens(query, keep_full_cjk=False)[:limit]
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in toks)


_INTENTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("我是谁", "我叫什么", "我的名字", "怎么称呼", "记得我"), ("名字", "叫")),
    (("住哪", "哪里人", "哪个城市", "我在哪"), ("住", "城市")),
    (("喜欢", "爱吃", "爱喝", "想喝", "想吃", "口味"), ("喜欢", "讨厌")),
    (("讨厌", "不喜欢", "忌口", "不能吃"), ("讨厌", "不喜欢")),
    (("生日", "纪念日"), ("生日",)),
    (("计划", "打算", "明天", "下周", "下个月", "这个月", "安排", "日程"), ("计划", "打算")),
)


def expand_query(query: str) -> str:
    """Add domain words for common questions ("我是谁" -> "名字 叫").

    Pure lexical retrieval cannot know that "我是谁" should reach the memory
    "用户叫小明"; a tiny intent table bridges that gap without an embedding model.
    """
    additions: list[str] = []
    for triggers, terms in _INTENTS:
        if any(trigger in query for trigger in triggers):
            additions.extend(terms)
    return " ".join([query, *additions]) if additions else query


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(a: str, b: str) -> float:
    return jaccard(set(tokens(a, keep_full_cjk=False)), set(tokens(b, keep_full_cjk=False)))


def plain_terms(text: str, limit: int = 12) -> list[str]:
    """Human-ish terms for LIKE fallback, longest first."""
    text = (text or "").strip()
    if not text:
        return []
    terms = [t for t in _WORD.findall(text.lower()) if len(t) >= 2]
    for match in _CJK.finditer(text):
        run = match.group(0)
        if len(run) <= 2:
            terms.append(run)
        else:
            terms.append(run)
            terms.extend(run[i : i + 2] for i in range(len(run) - 1))
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            unique.append(term)
    unique.sort(key=len, reverse=True)
    return unique[:limit]
