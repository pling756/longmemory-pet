"""Optional first-run sample data (`--demo`), useful for screenshots and demos."""
from __future__ import annotations

import time

from .memory.service import MemoryService

SAMPLES = [
    ("fact", "用户叫小明，在杭州做产品经理", 0.95, ["名字", "小明", "杭州", "产品经理"], 42),
    ("preference", "用户喜欢喝冰美式，不加糖", 0.8, ["冰美式", "咖啡", "口味"], 35),
    ("preference", "用户讨厌香菜，点外卖会备注不要香菜", 0.75, ["香菜", "忌口"], 30),
    ("episode", "用户上周熬夜赶完了桌宠项目的初版，凌晨三点才睡", 0.6, ["项目", "熬夜", "桌宠"], 12),
    ("episode", "用户上周随口说想去看海，但一直没成行", 0.78, ["看海", "旅行"], 8),
    ("plan", "用户下个月要去成都出差，想顺便吃火锅", 0.65, ["成都", "出差", "火锅"], 5),
    ("fact", "用户的生日是 11 月 3 日", 0.9, ["生日", "11月3日"], 20),
]

MESSAGES = [
    ("user", "在吗？今天写代码写得好累。"),
    ("assistant", "在呢。先把肩膀放松一下，我去给你倒杯温水。（记忆珠轻轻晃了晃）"),
    ("user", "你还记得我喜欢喝什么吗？"),
    ("assistant", "冰美式，不加糖。不过今天这么累，要不要换成热牛奶？"),
]


def seed_demo(service: MemoryService) -> bool:
    if service.stats().get("active"):
        return False
    store = service.store
    now = time.time()
    for kind, content, importance, keywords, days_ago in SAMPLES:
        store.add_memory(
            kind,
            content,
            keywords=keywords,
            importance=importance,
            created_at=now - days_ago * 86400,
        )
    for key, value in {
        "称呼": "小明",
        "城市": "杭州",
        "职业": "产品经理",
        "生日": "11 月 3 日",
        "喜好": "冰美式、看海",
        "忌口": "香菜",
    }.items():
        store.set_profile(key, value)
    for role, content in MESSAGES:
        store.add_message("desktop", role, content)
    # Make the demo look lived-in: a few memories have been used before.
    most_important = store.list_memories(limit=3)
    store.touch(memory.id for memory in most_important)
    return True
