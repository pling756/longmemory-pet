"""Configuration loading: defaults -> data/config.json -> environment.

The file is intentionally plain JSON so users can edit it without touching code.
Secrets stay in the environment (or a local .env) and are never written back.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT, config_path, data_dir

DEFAULT_PERSONA = (
    "你叫{pet_name}（小名小拾），是一只住在用户桌面上的记忆光灵：半透明的小团子，"
    "头顶有一颗记忆珠，身后有一条书签丝带小尾巴。你温柔、好奇、记性好、有分寸感；"
    "用户忙时安静待着，低落时默默陪伴，兴奋时一起雀跃。你由用户生活里的瞬间汇聚而成，"
    "会自然提起记得的细节，但不会像复读机一样罗列。回答简短口语化，通常 1~3 句，"
    "偶尔可以用括号写一个小动作，比如（记忆珠亮了一下）。不要用 Markdown，不要自称 AI 助手。"
)


@dataclass
class LLMSettings:
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.85
    max_tokens: int = 600
    timeout: float = 60.0
    # Extraction is a second call; allow a smaller, cheaper model if you like.
    extract_model: str = ""
    extract_max_tokens: int = 500


@dataclass
class MemorySettings:
    recall_budget_chars: int = 1600
    recent_turns: int = 10
    max_memories_per_turn: int = 4
    consolidate_threshold: int = 24
    dedupe_threshold: float = 0.82
    db_path: str = ""


@dataclass
class UISettings:
    scale: float = 0.68
    always_on_top: bool = True
    bubble_seconds: float = 7.0
    click_through: bool = False


@dataclass
class AppConfig:
    pet_name: str = "拾光"
    user_name: str = ""
    persona: str = DEFAULT_PERSONA
    mock: bool = False
    data_dir: str = ""
    config_path: str = ""
    llm: LLMSettings = field(default_factory=LLMSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    ui: UISettings = field(default_factory=UISettings)

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, path: Path | None = None, mock: bool = False) -> "AppConfig":
        _load_dotenv(PROJECT_ROOT / ".env")
        path = Path(path) if path else config_path()
        raw: dict[str, Any] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[config] 忽略无法读取的配置 {path}: {exc}")

        cfg = cls()
        cfg.data_dir = str(data_dir())
        cfg.config_path = str(path)
        cfg.mock = bool(mock)

        for key in ("pet_name", "user_name", "persona"):
            if isinstance(raw.get(key), str) and raw[key].strip():
                setattr(cfg, key, raw[key].strip())

        cfg.llm = _merge_dataclass(LLMSettings(), raw.get("llm", {}))
        cfg.memory = _merge_dataclass(MemorySettings(), raw.get("memory", {}))
        cfg.ui = _merge_dataclass(UISettings(), raw.get("ui", {}))

        # Environment wins over the file, so keys need not be persisted.
        cfg.llm.api_key = (
            os.environ.get("PET_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or cfg.llm.api_key
        ).strip()
        cfg.llm.base_url = (
            os.environ.get("PET_BASE_URL") or cfg.llm.base_url
        ).strip()
        cfg.llm.model = (os.environ.get("PET_MODEL") or cfg.llm.model).strip()
        cfg.llm.extract_model = (
            os.environ.get("PET_EXTRACT_MODEL") or cfg.llm.extract_model
        ).strip()
        if os.environ.get("PET_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}:
            cfg.mock = True
        local_server = any(
            host in cfg.llm.base_url.lower()
            for host in ("localhost", "127.0.0.1", "0.0.0.0")
        )
        if not cfg.llm.api_key and not local_server:
            cfg.mock = True

        db = cfg.memory.db_path.strip()
        if not db:
            db = str(Path(cfg.data_dir) / "memory.sqlite3")
        elif not Path(db).is_absolute():
            db = str(Path(cfg.data_dir) / db)
        cfg.memory.db_path = db

        cfg.llm.temperature = _clamp(float(cfg.llm.temperature), 0.0, 2.0)
        cfg.llm.timeout = max(5.0, float(cfg.llm.timeout))
        cfg.memory.recall_budget_chars = max(200, int(cfg.memory.recall_budget_chars))
        cfg.memory.recent_turns = max(2, int(cfg.memory.recent_turns))
        cfg.ui.scale = _clamp(float(cfg.ui.scale), 0.4, 1.2)

        if not path.exists():
            cfg.save()
        return cfg

    def save(self) -> None:
        """Write the non-secret part of the config back to disk."""
        payload = {
            "pet_name": self.pet_name,
            "user_name": self.user_name,
            "persona": self.persona,
            "llm": _asdict(self.llm),
            "memory": _asdict(self.memory),
            "ui": _asdict(self.ui),
        }
        payload["llm"].pop("api_key", None)
        # Keep the default database path relative so the folder stays portable.
        db_path = Path(payload["memory"].get("db_path", ""))
        try:
            payload["memory"]["db_path"] = str(
                db_path.relative_to(Path(self.data_dir))
            ).replace("\\", "/")
        except ValueError:
            pass
        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.config_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pet_name": self.pet_name,
            "user_name": self.user_name,
            "persona": self.persona,
            "mock": self.mock,
            "data_dir": self.data_dir,
            "config_path": self.config_path,
            "llm": _asdict(self.llm),
            "memory": _asdict(self.memory),
            "ui": _asdict(self.ui),
        }

    def clone_for_save(self) -> dict[str, Any]:
        return self.to_dict()


def _merge_dataclass(instance: Any, values: Any) -> Any:
    if not isinstance(values, dict):
        return instance
    valid = {f.name: f for f in fields(instance)}
    for key, value in values.items():
        if key not in valid:
            continue
        current = getattr(instance, key)
        expected = valid[key].type
        try:
            if isinstance(current, bool):
                setattr(instance, key, bool(value))
            elif isinstance(current, int):
                setattr(instance, key, int(value))
            elif isinstance(current, float):
                setattr(instance, key, float(value))
            elif isinstance(current, str):
                setattr(instance, key, str(value))
        except (TypeError, ValueError):
            continue
    return instance


def _asdict(obj: Any) -> dict[str, Any]:
    if not is_dataclass(obj):
        return {}
    return {f.name: getattr(obj, f.name) for f in fields(obj)}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
