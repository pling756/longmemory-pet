"""Long-memory desktop pet - entry point.

    python app.py                 # use data/config.json + .env
    python app.py --mock          # offline, no API key needed
    python app.py --demo          # seed sample memories on first run
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Wheels unpacked next to the app (see README) are picked up automatically.
_DEPS = ROOT / ".deps"
if _DEPS.exists() and str(_DEPS) not in sys.path:
    sys.path.insert(0, str(_DEPS))

from PySide6.QtCore import QLockFile, QPoint, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from pet.config import AppConfig  # noqa: E402
from pet.core.chat import ChatEngine  # noqa: E402
from pet.demo import seed_demo  # noqa: E402
from pet.llm import build_client  # noqa: E402
from pet.memory.service import MemoryService  # noqa: E402
from pet.memory.store import MemoryStore  # noqa: E402
from pet.paths import data_dir  # noqa: E402
from pet.ui.chat_window import ChatWindow  # noqa: E402
from pet.ui.memory_window import MemoryWindow  # noqa: E402
from pet.ui.pet_window import PetWindow  # noqa: E402
from pet.ui.theme import apply_app_style, make_tray_icon  # noqa: E402
from pet.ui.tray import PetTray  # noqa: E402
from pet.ui.worker import ChatTask, ConsolidateTask  # noqa: E402

CLICK_PHRASES = [
    "（记忆珠晃了晃）",
    "我在呢。",
    "戳我干嘛呀，我正在整理今天的记忆。",
    "要不要聊会儿天？",
    "今天也辛苦啦。",
]


def _bubble_text(text: str, limit: int = 120) -> str:
    """Keep the floating bubble compact; the full reply stays in chat."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="长记忆桌宠")
    parser.add_argument("--mock", action="store_true", help="强制离线模式，不调用模型")
    parser.add_argument("--demo", action="store_true", help="首次运行时写入示例记忆")
    parser.add_argument("--config", type=str, default="", help="配置文件路径")
    parser.add_argument("--data-dir", type=str, default="", help="数据目录")
    parser.add_argument("--no-tray", action="store_true", help="不创建托盘图标")
    args, qt_args = parser.parse_known_args(argv)
    return args, qt_args


class PetController:
    def __init__(self, app: QApplication, config: AppConfig, no_tray: bool = False):
        self.app = app
        self.config = config
        self.no_tray = no_tray
        self._busy = False
        self._chat_task = None
        self._consolidation_task = None
        self._consolidating = False
        self._status_timer = QTimer()
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._reset_status)

        self.store = MemoryStore(config.memory.db_path)
        self.llm = build_client(config.llm, force_mock=config.mock)
        self.service = MemoryService(
            self.store,
            self.llm,
            recall_budget_chars=config.memory.recall_budget_chars,
            max_memories_per_turn=config.memory.max_memories_per_turn,
            dedupe_threshold=config.memory.dedupe_threshold,
            consolidate_threshold=config.memory.consolidate_threshold,
            force_heuristic=config.mock,
        )
        self.engine = ChatEngine(config, self.llm, self.service)

        self.pet = PetWindow(config.pet_name, config.ui.scale, config.ui.always_on_top)
        self.chat = ChatWindow(config.pet_name)
        self.memory_window = MemoryWindow(self.service, config.pet_name)
        self.tray: PetTray | None = None
        self._chat_placed = False
        self._memory_placed = False

        self._wire()
        self.chat.set_status(self.engine.status_line())

    # ------------------------------------------------------------- lifecycle
    def start(self, demo: bool = False) -> None:
        if demo:
            seed_demo(self.service)
            self.chat.set_status(self.engine.status_line())
        self.service.decay()
        self._update_memory_level()

        self.pet.show()
        self.pet.move_to_corner()
        self._setup_tray()
        self._apply_click_through(self.config.ui.click_through, quiet=True)
        QTimer.singleShot(650, self._greet)

    def shutdown(self) -> None:
        self.pet.speak_hidden()
        self.chat.hide()
        self.memory_window.hide()
        self.pet.hide()
        if self.tray:
            self.tray.hide()
        self.app.quit()

    def _greet(self) -> None:
        self.pet.react("hello")
        self.pet.say(
            self.engine.greeting(),
            int(self.config.ui.bubble_seconds * 1000 + 2000),
        )

    def _setup_tray(self) -> None:
        if self.no_tray or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = PetTray(
            self.config.pet_name, click_through=self.config.ui.click_through
        )
        self.tray.show_pet_requested.connect(self.show_pet)
        self.tray.chat_requested.connect(self.open_chat)
        self.tray.memory_requested.connect(self.open_memory)
        self.tray.click_through_toggled.connect(self._apply_click_through)
        self.tray.quit_requested.connect(self.shutdown)
        self.tray.update_tooltip(self.engine.status_line())
        self.tray.show()

    # --------------------------------------------------------------- wiring
    def _wire(self) -> None:
        self.pet.clicked.connect(self._on_pet_clicked)
        self.pet.chat_requested.connect(self.open_chat)
        self.pet.menu_requested.connect(self._show_pet_menu)
        self.chat.message_submitted.connect(self.send_message)
        self.chat.memory_requested.connect(self.open_memory)
        self.memory_window.consolidate_requested.connect(self._consolidate)
        self.memory_window.memory_changed.connect(self._refresh_status)

    # ------------------------------------------------------------- commands
    def show_pet(self) -> None:
        self.pet.show()
        self.pet.raise_()
        self.pet.react("hello")
        self.pet.say("我在这儿。", 2600)

    def open_chat(self) -> None:
        self.chat.ensure_history(self.service.recent_messages(limit=30))
        if not self._chat_placed:
            self._place_window(self.chat)
            self._chat_placed = True
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()
        self.pet.speak_hidden()

    def open_memory(self) -> None:
        if not self._memory_placed:
            self._place_window(self.memory_window)
            self._memory_placed = True
        self.memory_window.refresh()
        self.memory_window.show()
        self.memory_window.raise_()
        self.memory_window.activateWindow()
        self.pet.speak_hidden()

    def send_message(self, text: str) -> None:
        text = text.strip()
        if not text or self._busy:
            return
        self._busy = True
        self.chat.add_message("user", text)
        self.chat.set_busy(True)
        self.chat.set_status("正在组织语言…")
        self.pet.react("thinking")

        task = ChatTask(self.engine, text)
        task.signals.replied.connect(self._on_reply)
        task.signals.remembered.connect(self._on_remembered)
        task.signals.consolidate_due.connect(self._on_consolidate_due)
        task.signals.failed.connect(self._on_failed)
        task.signals.done.connect(self._on_done)
        self._chat_task = task
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(task)

    # -------------------------------------------------------------- replies
    def _on_reply(self, result) -> None:
        self.chat.add_message("assistant", result.reply)
        # Keep the input locked until extraction finishes, but drop the
        # "thinking" bubble now that the visible answer has arrived.
        self.chat.hide_thinking()
        duration = int(
            max(
                3500,
                min(
                    15000,
                    self.config.ui.bubble_seconds * 1000 + len(result.reply) * 90,
                ),
            )
        )
        self.pet.react("excited" if result.used else "happy")
        self.pet.say(_bubble_text(result.reply), duration)
        if result.used:
            self.chat.set_status(f"想起了 {len(result.used)} 条相关记忆")
            self._status_timer.start(4200)
        else:
            self.chat.set_status(self.engine.status_line())

    def _on_remembered(self, stored) -> None:
        self._update_memory_level()
        if stored.created:
            self._refresh_status()
            if self.memory_window.isVisible():
                self.memory_window.refresh()
            if self.tray:
                self.tray.update_tooltip(self.engine.status_line())

    def _on_consolidate_due(self) -> None:
        """Run background consolidation without holding up the next message."""
        if self._consolidating:
            return
        self._consolidating = True
        task = ConsolidateTask(self.service, force=False)
        task.signals.finished.connect(self._on_auto_consolidated)
        task.signals.failed.connect(self._on_auto_consolidate_failed)
        self._consolidation_task = task
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(task)

    def _on_auto_consolidated(self, result) -> None:
        self._consolidating = False
        self._consolidation_task = None
        if result.changed:
            self._on_consolidated(result)

    def _on_auto_consolidate_failed(self, message: str) -> None:
        self._consolidating = False
        self._consolidation_task = None
        logging.warning("auto consolidation failed: %s", message)

    def _on_consolidated(self, result) -> None:
        self._update_memory_level()
        if self.memory_window.isVisible():
            self.memory_window.refresh()
        if result.created:
            self.chat.set_status(f"整理出了 {result.created} 条长期记忆")
            self._status_timer.start(5000)
            if self.tray:
                self.tray.update_tooltip(self.engine.status_line())

    def _on_failed(self, message: str) -> None:
        self.chat.add_message(
            "assistant", "呜…我这边连不上大脑了。检查一下 API Key 或网络，再来找我？"
        )
        self.chat.set_busy(False)
        self.chat.set_status(f"连接失败：{message[:80]}")
        self.pet.react("aggrieved")
        self.pet.say("呜…脑袋有点晕，等会儿再聊？", 6000)
        self._busy = False

    def _on_done(self) -> None:
        self._busy = False
        self._chat_task = None
        self.chat.set_busy(False)

    def _reset_status(self) -> None:
        if not self._busy:
            self.chat.set_status(self.engine.status_line())

    def _refresh_status(self) -> None:
        self.chat.set_status(self.engine.status_line())
        if self.tray:
            self.tray.update_tooltip(self.engine.status_line())

    def _update_memory_level(self) -> None:
        count = int(self.service.stats().get("active", 0))
        if count <= 0:
            level = 0
        elif count < 3:
            level = 1
        elif count < 6:
            level = 2
        elif count < 11:
            level = 3
        elif count < 21:
            level = 4
        else:
            level = 5
        self.pet.set_memory_level(level)

    # ------------------------------------------------------------ behaviour
    def _on_pet_clicked(self) -> None:
        self.pet.say(random.choice(CLICK_PHRASES), 2600)

    def _pet_action(self, action: str, text: str) -> None:
        self.pet.react(action)
        self.pet.say(text, 3600)

    def _show_pet_menu(self, position: QPoint) -> None:
        menu = QMenu()
        chat_action = QAction("聊天", menu)
        chat_action.triggered.connect(self.open_chat)
        menu.addAction(chat_action)

        memory_action = QAction("记忆库", menu)
        memory_action.triggered.connect(self.open_memory)
        menu.addAction(memory_action)
        menu.addSeparator()

        pet_action = QAction("摸摸头", menu)
        pet_action.triggered.connect(
            lambda: self._pet_action("happy", "好舒服～你的手我记住啦。")
        )
        menu.addAction(pet_action)

        hello_action = QAction("打个招呼", menu)
        hello_action.triggered.connect(
            lambda: self._pet_action("hello", "嗨～我是拾光。今天也想听听你的事。")
        )
        menu.addAction(hello_action)

        sleep_action = QAction("睡一觉", menu)
        sleep_action.triggered.connect(
            lambda: self._pet_action("sleep", "那我眯一会儿…你的事我都好好记着呢。")
        )
        menu.addAction(sleep_action)
        menu.addSeparator()

        through_action = QAction("鼠标穿透", menu)
        through_action.setCheckable(True)
        through_action.setChecked(self.config.ui.click_through)
        through_action.toggled.connect(self._apply_click_through)
        menu.addAction(through_action)

        if self.tray is not None:
            hide_action = QAction("隐藏", menu)
            hide_action.triggered.connect(self.pet.hide)
            menu.addAction(hide_action)

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.shutdown)
        menu.addAction(quit_action)
        menu.exec(position)

    def _apply_click_through(self, enabled: bool, quiet: bool = False) -> None:
        self.config.ui.click_through = bool(enabled)
        if self.tray:
            self.tray.set_click_through(enabled)
        currently = bool(
            self.pet.windowFlags() & Qt.WindowType.WindowTransparentForInput
        )
        if bool(enabled) != currently:
            position = self.pet.pos()
            self.pet.setWindowFlag(
                Qt.WindowType.WindowTransparentForInput, bool(enabled)
            )
            self.pet.show()
            self.pet.move(position)
        self.config.save()
        if quiet:
            return
        if enabled:
            self.pet.say("鼠标穿透已开启，从托盘菜单可以关掉。", 5000)
        else:
            self.pet.say("嗯，又能戳到我了。", 2600)

    def _consolidate(self) -> None:
        if self._consolidating:
            return
        self._consolidating = True
        task = ConsolidateTask(self.service, force=True)
        task.signals.finished.connect(self._on_manual_consolidated)
        task.signals.failed.connect(self._on_manual_consolidate_failed)
        self._consolidation_task = task
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(task)

    def _on_manual_consolidated(self, result) -> None:
        self._consolidating = False
        self._consolidation_task = None
        self.memory_window.show_result(result)

    def _on_manual_consolidate_failed(self, message: str) -> None:
        self._consolidating = False
        self._consolidation_task = None
        self.memory_window.show_error(message)

    def _place_window(self, window) -> None:
        screen = self.pet.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        pet_rect = self.pet.frameGeometry()
        x = pet_rect.left() - window.width() - 18
        y = pet_rect.bottom() - window.height() + 30
        if x < area.left() + 10:
            x = (area.width() - window.width()) // 2 + area.left()
        if y < area.top() + 10:
            y = area.top() + 10
        if y + window.height() > area.bottom():
            y = area.bottom() - window.height() - 10
        window.move(x, y)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    args, qt_args = parse_args(argv)
    if args.data_dir:
        os.environ["LONGMEM_PET_HOME"] = str(Path(args.data_dir).resolve())

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("LongMemPet")
    app.setQuitOnLastWindowClosed(False)
    apply_app_style(app)
    app.setWindowIcon(make_tray_icon())

    config = AppConfig.load(Path(args.config) if args.config else None, mock=args.mock)
    log_path = Path(config.data_dir) / "app.log"
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        encoding="utf-8",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    lock = QLockFile(str(Path(config.data_dir) / "pet.lock"))
    lock.setStaleLockTime(30000)
    if not lock.tryLock(200):
        QMessageBox.information(
            None,
            config.pet_name,
            f"{config.pet_name} 已经在桌面上跑着了。\n如果看不到它，请从系统托盘里找找。",
        )
        return 0

    controller = PetController(app, config, no_tray=args.no_tray)
    controller.start(demo=args.demo)
    logging.info("pet started (mock=%s, model=%s)", config.mock, config.llm.model)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
