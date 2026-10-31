"""Prompt assembly and the chat turn lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import AppConfig
from ..llm import ChatModel
from ..memory.models import Memory
from ..memory.service import MemoryService, StoreResult

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

MEMORY_RULES = """【使用记忆的方式】
- 上面是你真实记得的事情，可以自然地提起，像老朋友那样，不要逐条复述。
- 只使用和当前话题相关的记忆；不确定的事不要编造。
- 如果用户问“你还记得吗”，优先根据上面的记忆回答；没有就坦白说没记住。
- 不要提到“记忆库”“检索”“系统提示”这些词。"""


@dataclass
class ChatResult:
    reply: str
    used: list[Memory] = field(default_factory=list)
    context: str = ""
    user_message_id: int | None = None


class ChatEngine:
    def __init__(self, config: AppConfig, llm: ChatModel, memory: MemoryService):
        self.config = config
        self.llm = llm
        self.memory = memory
        self.session_id = "desktop"

    # --------------------------------------------------------------- prompt
    def build_system_prompt(self, recall_context: str, profile: dict[str, str]) -> str:
        persona = self.config.persona.replace("{pet_name}", self.config.pet_name)
        persona = persona.replace("{user_name}", self.config.user_name or "你")
        now = datetime.now()
        stamp = f"{now:%Y-%m-%d %H:%M}（{WEEKDAYS[now.weekday()]}）"

        profile_lines = [f"- {key}：{value}" for key, value in list(profile.items())[:12]]
        memory_block = recall_context or "（暂时没有相关的长期记忆）"
        profile_block = "\n".join(profile_lines) or "（还不了解，慢慢认识）"

        return (
            f"{persona}\n\n"
            f"现在时间：{stamp}\n\n"
            f"【关于用户】\n{profile_block}\n\n"
            f"【你记得的事】\n{memory_block}\n\n"
            f"{MEMORY_RULES}\n\n"
            "回复要求：口语化、简短，1~3 句；除非用户要求，不要列清单，不要用 Markdown。"
        )

    def history_for_model(self, limit: int | None = None) -> list[dict[str, str]]:
        limit = limit or self.config.memory.recent_turns * 2
        rows = self.memory.recent_messages(limit=limit)
        return [
            {"role": row["role"], "content": row["content"]}
            for row in rows
            if row["role"] in {"user", "assistant"}
        ]

    # ---------------------------------------------------------------- turns
    def respond(self, user_text: str) -> ChatResult:
        user_text = user_text.strip()
        if not user_text:
            return ChatResult(reply="（歪头）你想说什么呀？")

        user_message_id = self.memory.store.add_message(
            self.session_id, "user", user_text
        )
        recall = self.memory.recall(user_text)
        system = self.build_system_prompt(recall.context, self.memory.profile())
        messages = [{"role": "system", "content": system}]
        messages.extend(self.history_for_model())

        reply = self.llm.chat(messages)
        reply = (reply or "").strip()
        if not reply:
            reply = "（发呆中）……你刚刚说什么？"
        self.memory.store.add_message(self.session_id, "assistant", reply)

        return ChatResult(
            reply=reply,
            used=[item.memory for item in recall.items.items],
            context=recall.context,
            user_message_id=user_message_id,
        )

    def remember(self, user_text: str, reply: str, source_ids: list[int] | None = None) -> StoreResult:
        return self.memory.remember_turn(
            user_text, reply, source_ids=source_ids or []
        )

    def greeting(self) -> str:
        profile = self.memory.profile()
        stats = self.memory.stats()
        name = profile.get("称呼") or self.config.user_name
        parts: list[str] = []
        if name:
            parts.append(f"{name}，你回来啦。")
        else:
            parts.append(f"嗨，我是{self.config.pet_name}，一只住在你桌面上的记忆光灵。")
        if stats.get("active"):
            parts.append(f"记忆珠里收着 {stats['active']} 束光，我都好好记着呢。")
        else:
            parts.append("跟我说说话吧，我会把每一束光都收好。")
        return "".join(parts)

    def status_line(self) -> str:
        stats = self.memory.stats()
        mode = "离线模式" if self.config.mock else self.config.llm.model
        return f"{mode} · {stats['active']} 条记忆 · {stats['messages']} 条对话"
