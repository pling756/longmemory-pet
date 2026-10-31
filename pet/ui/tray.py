"""System tray entry point."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .theme import make_tray_icon


class PetTray(QSystemTrayIcon):
    show_pet_requested = Signal()
    chat_requested = Signal()
    memory_requested = Signal()
    click_through_toggled = Signal(bool)
    quit_requested = Signal()

    def __init__(self, pet_name: str, click_through: bool = False, parent=None):
        super().__init__(make_tray_icon(), parent)
        self.pet_name = pet_name
        self.setToolTip(f"{pet_name} · 长记忆桌宠")

        menu = QMenu()
        show_action = QAction(f"显示 {pet_name}", menu)
        show_action.triggered.connect(lambda: self.show_pet_requested.emit())
        menu.addAction(show_action)

        chat_action = QAction("聊天", menu)
        chat_action.triggered.connect(lambda: self.chat_requested.emit())
        menu.addAction(chat_action)

        memory_action = QAction("记忆库", menu)
        memory_action.triggered.connect(lambda: self.memory_requested.emit())
        menu.addAction(memory_action)
        menu.addSeparator()

        self.click_action = QAction("鼠标穿透", menu)
        self.click_action.setCheckable(True)
        self.click_action.setChecked(click_through)
        self.click_action.toggled.connect(self.click_through_toggled)
        menu.addAction(self.click_action)
        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(lambda: self.quit_requested.emit())
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self._menu = menu
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_pet_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.chat_requested.emit()

    def set_click_through(self, enabled: bool) -> None:
        self.click_action.blockSignals(True)
        self.click_action.setChecked(enabled)
        self.click_action.blockSignals(False)

    def update_tooltip(self, text: str) -> None:
        self.setToolTip(f"{self.pet_name} · {text}")
