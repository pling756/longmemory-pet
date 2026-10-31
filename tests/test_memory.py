"""Unit tests for the memory kernel (no Qt required).

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pet.config import AppConfig  # noqa: E402
from pet.core.chat import ChatEngine  # noqa: E402
from pet.llm import MockLLM  # noqa: E402
from pet.memory.consolidator import Consolidator  # noqa: E402
from pet.memory.service import MemoryService  # noqa: E402
from pet.memory.store import MemoryStore  # noqa: E402
from pet.memory.tokenize import match_query, tokens  # noqa: E402


class MemoryKernelTest(unittest.TestCase):
    def setUp(self) -> None:
        # A plain file inside data/ avoids tempfile's restrictive directory ACL
        # on Windows sandboxes; each test gets a unique database.
        self.db_path = ROOT / "data" / f"test-{self._testMethodName}.sqlite3"
        self._remove_db()
        self.store = MemoryStore(self.db_path)
        self.llm = MockLLM()
        self.service = MemoryService(
            self.store, self.llm, force_heuristic=True, consolidate_threshold=8
        )

    def tearDown(self) -> None:
        self._remove_db()

    def _remove_db(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(self.db_path) + suffix).unlink()
            except OSError:
                pass

    # ------------------------------------------------------------- tokenizer
    def test_cjk_bigrams_make_substring_search_work(self) -> None:
        assert "记忆" in tokens("长记忆桌宠")
        assert match_query("长记忆") != ""
        assert "长记" in match_query("长记忆")

    # --------------------------------------------------------------- extract
    def test_profile_and_fact_recall(self) -> None:
        self.service.remember_turn(
            "我叫小明，我喜欢喝冰美式，我住在杭州，我下个月要去成都", "好呀"
        )
        profile = self.service.profile()
        self.assertEqual(profile.get("称呼"), "小明")
        self.assertEqual(profile.get("城市"), "杭州")
        self.assertIn("冰美式", profile.get("喜好", ""))

        name_hits = self.service.recall("我是谁").items.items
        self.assertTrue(name_hits)
        self.assertEqual(name_hits[0].memory.content, "用户叫小明")

        city_hits = self.service.recall("我住哪").items.items
        self.assertEqual(city_hits[0].memory.content, "用户住在杭州")

        coffee_hits = self.service.recall("我想喝点什么").items.items
        self.assertEqual(coffee_hits[0].memory.content, "用户喜欢喝冰美式")

        plan_hits = self.service.recall("下个月有什么安排").items.items
        self.assertTrue(any("成都" in hit.memory.content for hit in plan_hits))

    def test_duplicate_is_reinforced_not_duplicated(self) -> None:
        self.service.remember_turn("我叫小明", "记住了")
        self.service.remember_turn("我叫小明", "记住了")
        facts = [
            memory
            for memory in self.store.list_memories(kind="fact")
            if memory.content == "用户叫小明"
        ]
        self.assertEqual(len(facts), 1)
        self.assertGreaterEqual(facts[0].access_count, 1)

    def test_questions_do_not_become_memories(self) -> None:
        result = self.service.remember_turn("你还记得我喜欢喝什么吗？", "冰美式呀")
        self.assertEqual(result.created, [])
        contents = [memory.content for memory in self.store.list_memories()]
        self.assertFalse(any("希望记住" in content for content in contents))

    def test_low_importance_is_dropped(self) -> None:
        result = self.service.remember_turn("嗯", "嗯嗯")
        self.assertEqual(result.created, [])

    # --------------------------------------------------------------- storage
    def test_fts_search_and_messages(self) -> None:
        ids = [
            self.store.add_memory("preference", "用户喜欢喝冰美式", keywords=["咖啡"]),
            self.store.add_memory("fact", "用户养了一只猫叫年糕", keywords=["猫"]),
        ]
        hits = dict(self.store.search_fts("咖啡"))
        self.assertIn(ids[0], hits)
        self.assertNotIn(ids[1], hits)

        self.store.add_message("desktop", "user", "你好")
        self.store.add_message("desktop", "assistant", "在呢")
        rows = self.store.recent_messages(limit=10)
        self.assertEqual([row["role"] for row in rows], ["user", "assistant"])

    def test_access_reinforces_memory(self) -> None:
        self.store.add_memory("preference", "用户喜欢冰美式", keywords=["咖啡", "冰美式"])
        self.service.recall("冰美式")
        memory = self.store.list_memories()[0]
        self.assertEqual(memory.access_count, 1)
        self.assertIsNotNone(memory.last_access_at)

    # ------------------------------------------------------------- lifecycle
    def test_consolidation_archives_old_episodes(self) -> None:
        old = time.time() - 30 * 86400
        for index in range(10):
            self.store.add_memory(
                "episode",
                f"用户第{index}天在做一个桌宠项目，遇到了不少问题",
                importance=0.5,
                created_at=old + index,
                keywords=["项目", "桌宠"],
            )
        consolidator = Consolidator(self.store, self.llm, threshold=5, min_age_days=7)
        result = consolidator.run()
        self.assertGreater(result.created, 0)
        self.assertEqual(result.archived, 10)
        self.assertEqual(self.store.stats()["by_kind"].get("episode", 0), 0)
        self.assertGreaterEqual(self.store.stats()["by_kind"].get("summary", 0), 1)
        self.assertTrue(result.describe())

    def test_decay_archives_forgotten_low_value_memory(self) -> None:
        very_old = time.time() - 200 * 86400
        self.store.add_memory(
            "episode", "用户随口说了一句今天有点热", importance=0.2, created_at=very_old
        )
        self.store.add_memory("fact", "用户叫小明", importance=0.95, created_at=very_old)
        archived = self.store.decay()
        self.assertEqual(archived, 1)
        active = [memory.content for memory in self.store.list_memories()]
        self.assertIn("用户叫小明", active)
        self.assertNotIn("用户随口说了一句今天有点热", active)

    # ------------------------------------------------------------------ chat
    def test_chat_reply_uses_retrieved_memory(self) -> None:
        self.service.remember_turn("我叫小明，我喜欢喝冰美式", "记住啦")
        engine = ChatEngine(AppConfig(mock=True), self.llm, self.service)
        result = engine.respond("你还记得我喜欢喝什么吗？")
        self.assertIn("冰美式", result.reply)
        self.assertTrue(result.used)
        self.assertEqual(len(self.store.recent_messages(limit=10)), 2)

    def test_greeting_mentions_known_name(self) -> None:
        self.service.remember_turn("我叫小明", "记住啦")
        engine = ChatEngine(AppConfig(mock=True), self.llm, self.service)
        self.assertIn("小明", engine.greeting())


if __name__ == "__main__":
    unittest.main(verbosity=2)
