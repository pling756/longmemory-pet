"""A small speech bubble that floats next to the pet."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QWidget

from .theme import BORDER, INK, PAPER, font

MAX_WIDTH = 268
PAD_X = 16
PAD_TOP = 12
TAIL = 16


class SpeechBubble(QWidget):
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.label = QLabel(self)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setFont(font(10))
        self.label.setStyleSheet(f"color: {INK}; background: transparent;")

        self.tail_up = False
        self._text = ""
        self._duration = 7000
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.fade_out)
        self._anim: QPropertyAnimation | None = None
        self._opacity = 1.0

    # ------------------------------------------------------------------ API
    def show_message(self, text: str, anchor: QRect, duration: int | None = None) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._text = text
        self._duration = duration or 7000
        self.label.setText(text)
        self._layout_for(text)
        self._place(anchor)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade(1.0, 150)
        self._timer.start(self._duration)

    def follow(self, anchor: QRect) -> None:
        if not self.isVisible():
            return
        self._place(anchor)

    def hide_now(self) -> None:
        self._timer.stop()
        self.hide()

    def fade_out(self) -> None:
        self._timer.stop()
        self._fade(0.0, 220, hide=True)

    # -------------------------------------------------------------- geometry
    def _layout_for(self, text: str) -> None:
        metrics = QFontMetrics(self.label.font())
        lines = text.splitlines() or [""]
        longest = max(metrics.horizontalAdvance(line) for line in lines)
        width = max(120, min(MAX_WIDTH, longest + 6))
        self.label.setFixedWidth(width)
        height = max(metrics.height(), self.label.heightForWidth(width))
        self.label.setFixedSize(width, height)
        self.resize(width + PAD_X * 2, height + PAD_TOP + TAIL + 6)

    def _place(self, anchor: QRect) -> None:
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() - 2
        self.tail_up = False
        if y < area.top() + 4:
            y = anchor.bottom() + 2
            self.tail_up = True
        x = max(area.left() + 6, min(x, area.right() - self.width() - 6))
        y = max(area.top() + 4, min(y, area.bottom() - self.height() - 4))
        self.move(QPoint(x, y))
        self._position_label()

    def _position_label(self) -> None:
        top = PAD_TOP + (TAIL if self.tail_up else 0)
        self.label.move(PAD_X, top)

    def _fade(self, target: float, msec: int, hide: bool = False) -> None:
        if self._anim:
            self._anim.stop()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(msec)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if hide:
            anim.finished.connect(self.hide)
        self._anim = anim
        anim.start()

    # --------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        body = QRectF(4, 3, self.width() - 8, self.height() - 8)
        radius = 14.0
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)

        cx = self.width() / 2
        tail = QPainterPath()
        if self.tail_up:
            tail.moveTo(cx - 9, body.top() + 1)
            tail.lineTo(cx, 1)
            tail.lineTo(cx + 9, body.top() + 1)
        else:
            tail.moveTo(cx - 9, body.bottom() - 1)
            tail.lineTo(cx, self.height() - 2)
            tail.lineTo(cx + 9, body.bottom() - 1)
        tail.closeSubpath()
        shape = path.united(tail)

        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(6, 0, -1):
            painter.setBrush(QColor(60, 50, 100, 6))
            offset = QRectF(shape.boundingRect().translated(0, index * 0.7))
            painter.drawRoundedRect(offset, radius + index * 0.4, radius + index * 0.4)

        painter.setBrush(QColor(PAPER))
        painter.setPen(QPen(QColor(BORDER), 1.2))
        painter.drawPath(shape)

        self._position_label()

    # ------------------------------------------------------------- behaviour
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self.fade_out()
        event.accept()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._fade(1.0, 80)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._timer.start(min(self._duration, 2600))
