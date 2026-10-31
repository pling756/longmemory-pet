"""Configuration precedence and secret handling."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pet.config import AppConfig  # noqa: E402

KEYS = (
    "PET_API_KEY",
    "OPENAI_API_KEY",
    "PET_BASE_URL",
    "PET_MODEL",
    "PET_MOCK",
)


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in KEYS}
        for key in KEYS:
            os.environ.pop(key, None)
        self.path = ROOT / "data" / "config-test.json"
        try:
            self.path.unlink()
        except OSError:
            pass

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        try:
            self.path.unlink()
        except OSError:
            pass

    def test_without_key_falls_back_to_mock(self) -> None:
        cfg = AppConfig.load(self.path)
        self.assertTrue(cfg.mock)

    def test_key_switches_to_online(self) -> None:
        os.environ["PET_API_KEY"] = "sk-test"
        cfg = AppConfig.load(self.path)
        self.assertFalse(cfg.mock)
        self.assertEqual(cfg.llm.api_key, "sk-test")

    def test_local_server_allows_empty_key(self) -> None:
        os.environ["PET_BASE_URL"] = "http://localhost:11434/v1"
        cfg = AppConfig.load(self.path)
        self.assertFalse(cfg.mock)
        self.assertEqual(cfg.llm.base_url, "http://localhost:11434/v1")

    def test_key_is_never_written_to_disk(self) -> None:
        os.environ["PET_API_KEY"] = "sk-secret-value"
        cfg = AppConfig.load(self.path)
        cfg.save()
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("sk-secret-value", text)
        self.assertNotIn("api_key", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
