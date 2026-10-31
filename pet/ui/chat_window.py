"""Frameless chat panel with bubble messages."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    BORDER,
    INK,
    LAVENDER,
    LAVENDER_SOFT,
    MUTED,
    PAPER,
    font,
)


class MessageBubble(QWidget):
    def __init__(self, role: str, text: str, pet_name: str = "拾光", parent=None):
        super().__init__(parent)
        self.role = role
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 3, 12, 3)
        row.setSpacing(8)

        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMaximumWidth(282)
        label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if role == "user":
            label.setStyleSheet(
                f"background: {LAVENDER_SOFT}; color: {INK}; border: none;"
                "border-radius: 13px; padding: 9px 13px; font-size: 13px;"
            )
        else:
            label.setStyleSheet(
                f"background: #FFFFFF; color: {INK}; border: 1px solid #EAE4F8;"
                "border-radius: 13px; padding: 9px 13px; font-size: 13px;"
            )
        label.setFont(font(10))
        label.ensurePolished()
        metrics = QFontMetrics(label.font())
        longest = max(
            (metrics.horizontalAdvance(line) for line in text.splitlines()), default=0
        )
        width = min(288, max(52, longest + 30))
        label.setFixedWidth(width)
        height = label.heightForWidth(width)
        if height > 0:
            label.setMinimumHeight(height)
        self.label = label

        if role == "user":
            row.addStretch(1)
            row.addWidget(label)
        else:
            avatar = QLabel(pet_name[:1] or "团", self)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setFixedSize(26, 26)
            avatar.setStyleSheet(
                f"background: {LAVENDER}; color: white; border-radius: 13px;"
                "font-size: 11px; font-weight: 700;"
            )
            row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(label)
            row.addStretch(1)


class ChatWindow(QWidget):
    message_submitted = Signal(str)
    memory_requested = Signal()
    closed = Signal()

    def __init__(self, pet_name: str = "拾光", parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(f"和{pet_name}聊天")
        self.pet_name = pet_name
        self.resize(402, 566)
        self._drag_origin: QPoint | None = None
        self._drag_start: QPoint | None = None
        self._thinking: MessageBubble | None = None
        self._message_count = 0

        shell = QVBoxLayout(self)
        shell.setContentsMargins(14, 14, 14, 14)
        shell.setSpacing(0)

        self.panel = QFrame(self)
        self.panel.setObjectName("panel")
        self.panel.setStyleSheet(
            f"QFrame#panel {{ background: {PAPER}; border: 1px solid {BORDER};"
            "border-radius: 18px; }"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(50, 35, 90, 55))
        self.panel.setGraphicsEffect(shadow)
        shell.addWidget(self.panel)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(14, 12, 14, 14)
        panel_layout.setSpacing(10)

        header = QWidget(self.panel)
        header.setFixedHeight(48)
        head = QHBoxLayout(header)
        head.setContentsMargins(2, 0, 2, 0)
        head.setSpacing(8)

        avatar = QLabel(pet_name[:1] or "团", header)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(34, 34)
        avatar.setStyleSheet(
            f"background: {LAVENDER}; color: white; border-radius: 17px;"
            "font-size: 13px; font-weight: 700;"
        )
        head.addWidget(avatar)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel(pet_name, header)
        name.setFont(font(11, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {INK};")
        self.status = QLabel("正在连接…", header)
        self.status.setFont(font(8))
        self.status.setMaximumWidth(230)
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        titles.addWidget(name)
        titles.addWidget(self.status)
        head.addLayout(titles)
        head.addStretch(1)

        self.memory_button = QToolButton(header)
        self.memory_button.setText("记忆")
        self.memory_button.setToolTip("查看长期记忆")
        self.memory_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.memory_button.setAutoRaise(True)
        self.memory_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.memory_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.memory_button.clicked.connect(lambda: self.memory_requested.emit())
        head.addWidget(self.memory_button)

        minimize = QToolButton(header)
        minimize.setText("—")
        minimize.setToolTip("收起到托盘")
        minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        minimize.setAutoRaise(True)
        minimize.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        minimize.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        minimize.clicked.connect(self.hide)
        head.addWidget(minimize)

        close = QToolButton(header)
        close.setText("×")
        close.setToolTip("关闭")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setAutoRaise(True)
        close.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.setStyleSheet(
            "QToolButton { font-size: 18px; color: #9C8574; padding-bottom: 3px;"
            " background: transparent; border: none; }"
            "QToolButton:hover { background: #FBE3DC; color: #C0604F; }"
        )
        close.clicked.connect(self.close_clicked)
        head.addWidget(close)
        panel_layout.addWidget(header)

        self.scroll = QScrollArea(self.panel)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.body = QWidget()
        self.body.setObjectName("chatBody")
        self.body.setStyleSheet("QWidget#chatBody { background: transparent; }")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 4, 0, 4)
        self.body_layout.setSpacing(2)
        self.body_layout.addStretch(1)
        self.scroll.setWidget(self.body)
        panel_layout.addWidget(self.scroll, 1)

        input_row = QWidget(self.panel)
        input_row.setFixedHeight(46)
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 2, 0, 0)
        input_layout.setSpacing(8)

        self.input = QLineEdit(input_row)
        self.input.setPlaceholderText(f"和{pet_name}说点什么…")
        self.input.setFont(font(10))
        self.input.returnPressed.connect(self._submit)
        input_layout.addWidget(self.input, 1)

        self.send_button = QPushButton("发送", input_row)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setFixedWidth(72)
        self.send_button.clicked.connect(self._submit)
        input_layout.addWidget(self.send_button)
        panel_layout.addWidget(input_row)

    # ------------------------------------------------------------------ API
    def set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setToolTip(text)

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        self.send_button.setText("…" if busy else "发送")
        self.input.setPlaceholderText(
            f"{self.pet_name}正在想…" if busy else f"和{self.pet_name}说点什么…"
        )
        if busy:
            self.show_thinking()
        else:
            self.hide_thinking()

    def show_thinking(self) -> None:
        if self._thinking is not None:
            return
        self._thinking = MessageBubble("pet", "正在想…", self.pet_name)
        self._insert(self._thinking)
        self.scroll_to_bottom()

    def hide_thinking(self) -> None:
        if self._thinking is None:
            return
        self.body_layout.removeWidget(self._thinking)
        self._thinking.deleteLater()
        self._thinking = None

    def add_message(self, role: str, text: str) -> None:
        self._insert(MessageBubble(role, text, self.pet_name))
        self._message_count += 1
        self.scroll_to_bottom()

    def ensure_history(self, rows: list[dict]) -> None:
        if self._message_count or not rows:
            return
        for row in rows:
            if row.get("role") in {"user", "assistant"}:
                self._insert(MessageBubble(row["role"], row["content"], self.pet_name))
                self._message_count += 1
        self.scroll_to_bottom()

    def clear(self) -> None:
        self.hide_thinking()
        while self.body_layout.count() > 1:
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._message_count = 0

    def scroll_to_bottom(self) -> None:
        QTimer.singleShot(20, self._do_scroll)

    def _do_scroll(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _insert(self, widget: QWidget) -> None:
        self.body_layout.insertWidget(self.body_layout.count() - 1, widget)

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text or not self.input.isEnabled():
            return
        self.input.clear()
        self.message_submitted.emit(text)

    # ------------------------------------------------------------- behaviour
    def close_clicked(self) -> None:
        self.hide()
        self.closed.emit()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.input.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.closed.emit()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 72:
            self._drag_origin = event.globalPosition().toPoint() - self.pos()
            self._drag_start = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        self._drag_start = None
        super().mouseReleaseEvent(event)
