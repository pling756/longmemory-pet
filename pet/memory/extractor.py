"""Turn a conversation turn into durable memories.

Two implementations share one output shape:
* LLMExtractor   - asks a chat model for strict JSON, falls back to heuristics.
* HeuristicExtractor - regex rules, used for offline/mock mode and as a safety net.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..llm import LLMError, MockLLM, extract_json
from .models import KINDS

PROFILE_KEYS = ("称呼", "城市", "职业", "生日", "喜好", "忌口", "目标")

SYSTEM_PROMPT = """你是一个长期记忆整理器。从一轮对话中提取值得长期记住的信息。

规则：
1. 只提取用户主动透露的、未来仍然有用的信息。不要提取寒暄、宠物的回复、一次性的情绪。
2. kind 只能是 fact / preference / episode / plan：
   - fact：稳定事实（名字、城市、职业、家庭、重要关系）
   - preference：喜好或厌恶（食物、音乐、习惯）
   - episode：发生过的具体事情（截止日期、旅行、吵架、看病）
   - plan：未来计划
3. content 用第三人称陈述，简洁（<=40 字），不要编造。
4. importance 0~1：姓名/住址/重要关系 0.9；长期喜好 0.7；近期经历 0.5；琐事 0.25。
5. keywords 给 2~5 个检索词。
6. profile 只填写最稳定的键（称呼、城市、职业、生日、喜好、忌口、目标），没有就省略。
7. 最多 4 条；没有值得记的就返回空数组。

只输出 JSON，不要解释：
{"memories":[{"kind":"fact","content":"用户叫小明","importance":0.9,"keywords":["名字","小明"]}],"profile":{"称呼":"小明"}}"""


@dataclass
class ExtractedMemory:
    kind: str
    content: str
    importance: float = 0.5
    keywords: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    memories: list[ExtractedMemory] = field(default_factory=list)
    profile: dict[str, str] = field(default_factory=dict)


class ExtractionError(RuntimeError):
    pass


class LLMExtractor:
    def __init__(self, llm, fallback: "HeuristicExtractor", max_items: int = 4):
        self.llm = llm
        self.fallback = fallback
        self.max_items = max_items

    def extract(self, user_text: str, assistant_text: str = "") -> Extraction:
        prompt = (
            f"用户说：{user_text}\n"
            f"宠物回复：{assistant_text}\n\n"
            "请提取值得长期记住的信息，只输出 JSON。"
        )
        settings = getattr(self.llm, "settings", None)
        extract_model = getattr(settings, "extract_model", "") or None
        extract_tokens = int(getattr(settings, "extract_max_tokens", 500) or 500)
        try:
            reply = self.llm.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=extract_tokens,
                model=extract_model,
            )
            data = extract_json(reply)
            if not isinstance(data, dict) or "memories" not in data:
                raise ExtractionError("模型没有返回约定的 JSON")
            return self._parse(data)
        except (LLMError, ExtractionError, ValueError) as exc:
            print(f"[memory] 模型抽取失败，改用规则抽取：{exc}")
            return self.fallback.extract(user_text, assistant_text)

    def _parse(self, data: dict) -> Extraction:
        result = Extraction()
        raw_memories = data.get("memories")
        if isinstance(raw_memories, list):
            for raw in raw_memories[: self.max_items]:
                if not isinstance(raw, dict):
                    continue
                kind = str(raw.get("kind", "")).strip().lower()
                content = _clean(str(raw.get("content", "")))
                if kind not in KINDS or not content:
                    continue
                keywords = raw.get("keywords") or []
                if isinstance(keywords, str):
                    keywords = [keywords]
                keywords = [
                    _clean(str(k)) for k in keywords if _clean(str(k))
                ][:6]
                try:
                    importance = float(raw.get("importance", 0.5))
                except (TypeError, ValueError):
                    importance = 0.5
                result.memories.append(
                    ExtractedMemory(
                        kind=kind,
                        content=content[:120],
                        importance=max(0.15, min(1.0, importance)),
                        keywords=keywords,
                    )
                )
        profile = data.get("profile")
        if isinstance(profile, dict):
            for key, value in profile.items():
                key = str(key).strip()
                value = _clean(str(value))
                if key in PROFILE_KEYS and value:
                    result.profile[key] = value[:80]
        return result


class HeuristicExtractor:
    """Cheap rules that still make the framework feel alive offline."""

    _NAME = re.compile(r"(?:我叫|我的名字是|叫我)([\u4e00-\u9fffA-Za-z0-9_]{1,12})")
    _CITY = re.compile(
        r"我住在([\u4e00-\u9fff]{2,10})"
        r"|我在([\u4e00-\u9fff]{2,10})(?:工作|生活|上班|读书|上学)"
    )
    _LIKE = re.compile(r"我(?:很|最|超)?(?:喜欢|爱|偏爱)([^，。！？,.!?\n]{1,24})")
    _DISLIKE = re.compile(r"我(?:很|最|超)?(?:不喜欢|讨厌|受不了|怕)([^，。！？,.!?\n]{1,24})")
    _BIRTHDAY = re.compile(r"我(?:的)?生日(?:是|在)?([0-9年月日/\.\-]{2,15})")
    _PLAN = re.compile(r"我(?:明天|后天|下周|下个月|准备|打算)([^，。！？,.!?\n]{2,30})")
    _REMEMBER = re.compile(
        r"(?:记住|帮我记(?:一下)?|别忘记|不要忘记)[，,:：\s]*(.{2,60})"
    )

    def extract(self, user_text: str, assistant_text: str = "") -> Extraction:
        text = (user_text or "").strip()
        result = Extraction()
        seen: set[str] = set()

        def add(kind: str, content: str, importance: float, keywords: list[str]) -> None:
            content = _clean(content)
            if not content or content in seen:
                return
            seen.add(content)
            result.memories.append(
                ExtractedMemory(
                    kind=kind,
                    content=content[:120],
                    importance=importance,
                    keywords=keywords[:6],
                )
            )

        if match := self._NAME.search(text):
            name = match.group(1)
            add("fact", f"用户叫{name}", 0.95, ["名字", name])
            result.profile["称呼"] = name

        if match := self._CITY.search(text):
            city = match.group(1) or match.group(2)
            if city not in {"这里", "家里", "公司", "学校", "上班", "外面"}:
                add("fact", f"用户住在{city}", 0.8, ["城市", city])
                result.profile["城市"] = city

        if (match := self._LIKE.search(text)) and _statement(match.group(1)):
            thing = match.group(1)
            add("preference", f"用户喜欢{thing}", 0.72, ["喜欢", thing])
            result.profile.setdefault("喜好", thing)

        if (match := self._DISLIKE.search(text)) and _statement(match.group(1)):
            thing = match.group(1)
            add("preference", f"用户不喜欢{thing}", 0.75, ["讨厌", thing])
            result.profile.setdefault("忌口", thing)

        if match := self._BIRTHDAY.search(text):
            day = match.group(1)
            add("fact", f"用户生日是{day}", 0.9, ["生日", day])
            result.profile["生日"] = day

        if (match := self._REMEMBER.search(text)) and _statement(match.group(1)):
            thing = match.group(1)
            add("fact", f"用户希望记住：{thing}", 0.85, ["提醒", thing[:8]])
            result.profile.setdefault("目标", thing[:40])

        if (match := self._PLAN.search(text)) and _statement(match.group(1)):
            thing = match.group(1)
            add("plan", f"用户计划{thing}", 0.6, ["计划", thing[:8]])

        if not result.memories and len(text) >= 14 and any(
            marker in text for marker in ("今天", "昨天", "刚才", "最近", "刚刚")
        ):
            add("episode", f"用户提到：{text[:58]}", 0.3, ["近况"])

        return result


def build_extractor(llm, max_items: int = 4, force_heuristic: bool = False):
    heuristic = HeuristicExtractor()
    if force_heuristic or isinstance(llm, MockLLM):
        return heuristic
    return LLMExtractor(llm, heuristic, max_items=max_items)


def _statement(thing: str) -> bool:
    """Reject questions such as '我喜欢喝什么吗' captured by a greedy regex."""
    return not any(
        marker in thing for marker in ("什么", "怎么", "哪", "吗", "呢", "？", "?")
    )


def _clean(text: str) -> str:
    text = (text or "").strip().strip('"').strip("'").strip()
    return re.sub(r"\s+", " ", text)
