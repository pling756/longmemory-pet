"""拾光: the transparent, always-on-top memory spirit.

The character is a QPainter port of the interactive SVG design. Keeping it in
QPainter (instead of static images) lets the eyes follow the cursor, the tail
wag, the arm wave and the memory orb brighten as long-term memory grows.
"""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .bubble import SpeechBubble
from .theme import (
    BELLY,
    CORAL,
    GOLD,
    INDIGO,
    LAVENDER,
    LAVENDER_DARK,
    LAVENDER_LIGHT,
    MINT,
    ORB_BLUE,
    ORB_LIGHT,
    PINK,
)

BASE_W = 400
BASE_H = 470
CX = 200.0
BODY_CY = 300.0


class PetWindow(QWidget):
    clicked = Signal()
    chat_requested = Signal()
    menu_requested = Signal(QPoint)

    def __init__(self, pet_name: str = "拾光", scale: float = 0.68,
                 always_on_top: bool = True):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.pet_name = pet_name
        self.scale = max(0.4, min(1.2, scale))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setFixedSize(round(BASE_W * self.scale), round(BASE_H * self.scale))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(f"{pet_name} · 双击聊天，右键菜单")

        self.bubble = SpeechBubble()
        self.bubble.clicked.connect(self.chat_requested)

        self._phase = 0.0
        self._blink_until = 0.0
        self._next_blink = time.monotonic() + random.uniform(2.0, 4.5)
        self._bounce_start = -10.0
        self._wave_until = 0.0
        self._face = "happy"
        self._face_until = 0.0
        self._memory_level = 0
        self._orb_flash = 0.0
        self._gaze_x = 0.0
        self._gaze_y = 0.0
        self._gaze_target_x = 0.0
        self._gaze_target_y = 0.0

        self._press_global: QPoint | None = None
        self._origin: QPoint | None = None
        self._dragging = False

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------ API
    def say(self, text: str, duration: int | None = None) -> None:
        rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
        self.bubble.show_message(text, rect, duration)

    def speak_hidden(self) -> None:
        self.bubble.hide_now()

    def bounce(self) -> None:
        self._bounce_start = time.monotonic()

    def hop(self) -> None:
        self.bounce()

    def react(self, action: str) -> None:
        """Small, expressive state machine used by the controller."""
        now = time.monotonic()
        hold = 0.0
        if action in {"poke", "surprised"}:
            self._face = "surprised"
            hold = 1.25
            self.bounce()
        elif action in {"hello", "wave"}:
            self._face = "excited"
            self._wave_until = now + 1.35
            hold = 2.3
        elif action == "feed":
            self._face = "excited"
            hold = 2.0
            self.bounce()
            self._orb_flash = 1.0
        elif action == "sleep":
            self._face = "sleepy"
            hold = 20.0
        elif action == "thinking":
            self._face = "thinking"
            hold = 25.0
        elif action == "aggrieved":
            self._face = "aggrieved"
            hold = 4.0
        elif action == "excited":
            self._face = "excited"
            hold = 1.8
        elif action == "happy":
            self._face = "happy"
            hold = 1.4
        else:
            self._face = "happy"
        self._face_until = now + hold if hold else 0.0

    def set_memory_level(self, level: int) -> None:
        level = max(0, min(5, int(level)))
        if level > self._memory_level:
            self._orb_flash = max(self._orb_flash, 0.8)
        self._memory_level = level

    def reposition_bubble(self) -> None:
        if self.bubble.isVisible():
            rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            self.bubble.follow(rect)

    def move_to_corner(self) -> None:
        screen = self.screen() or self.windowHandle().screen()
        area = screen.availableGeometry()
        x = area.right() - self.width() - 28
        y = area.bottom() - self.height() - 6
        self.move(max(area.left(), x), max(area.top(), y))

    # ------------------------------------------------------------- animation
    def _tick(self) -> None:
        now = time.monotonic()
        self._phase += 0.065
        if self._face_until and now >= self._face_until:
            self._face = "happy"
            self._face_until = 0.0
        if self._face in {"happy", "excited", "surprised"} and now >= self._next_blink:
            self._blink_until = now + 0.13
            self._next_blink = now + random.uniform(2.6, 6.0)
        if (
            self.isVisible()
            and self._face != "sleepy"
            and QGuiApplication.platformName() != "offscreen"
        ):
            cursor = QCursor.pos()
            center = self.mapToGlobal(
                QPoint(round(CX * self.scale), round(BODY_CY * self.scale))
            )
            self._gaze_target_x = max(
                -1.0, min(1.0, (cursor.x() - center.x()) / (self.width() * 0.6))
            )
            self._gaze_target_y = max(
                -1.0, min(1.0, (cursor.y() - center.y()) / (self.height() * 0.5))
            )
        self._gaze_x += (self._gaze_target_x - self._gaze_x) * 0.12
        self._gaze_y += (self._gaze_target_y - self._gaze_y) * 0.12
        if self._orb_flash > 0:
            self._orb_flash = max(0.0, self._orb_flash - 0.025)
        self.update()

    def _bounce_offset(self) -> float:
        elapsed = time.monotonic() - self._bounce_start
        if 0 <= elapsed <= 0.45:
            return math.sin(elapsed / 0.45 * math.pi) * 15
        return 0.0

    def _wave_angle(self) -> float:
        remain = self._wave_until - time.monotonic()
        if remain <= 0:
            return 0.0
        progress = 1.0 - remain / 1.35
        return -20.0 * math.sin(progress * math.tau * 2)

    # ---------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.scale, self.scale)

        self._draw_shadow(painter)

        bob = math.sin(self._phase * 1.1) * 2.4
        painter.save()
        # Pseudo-3D lean + breathing, like the HTML demo's perspective tilt.
        painter.translate(CX, BODY_CY)
        painter.rotate(-self._gaze_x * 1.8)
        painter.scale(1.0 - abs(self._gaze_x) * 0.012,
                      1.0 - abs(self._gaze_y) * 0.008)
        painter.translate(-CX, -BODY_CY)
        painter.translate(0, bob - self._bounce_offset())
        breathe = 1.0 + 0.01 * math.sin(self._phase * 0.9)
        painter.translate(CX, BODY_CY)
        painter.scale(1.0, breathe)
        painter.translate(-CX, -BODY_CY)

        self._draw_sparkles(painter)
        self._draw_tail(painter)
        self._draw_feet(painter)
        self._draw_arms(painter)
        self._draw_body(painter)
        self._draw_sprout(painter)
        self._draw_face(painter)
        self._draw_orb(painter)
        painter.restore()

    def _draw_shadow(self, painter: QPainter) -> None:
        gradient = QRadialGradient(QPointF(200, 440), 96)
        gradient.setColorAt(0.0, QColor(60, 50, 100, 85))
        gradient.setColorAt(1.0, QColor(60, 50, 100, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(104, 427, 192, 26))

    def _star(self, cx: float, cy: float, size: float) -> QPainterPath:
        path = QPainterPath(QPointF(cx, cy - size))
        for dx, dy in ((0.24, -0.24), (1, 0), (0.24, 0.24),
                       (0, 1), (-0.24, 0.24), (-1, 0), (-0.24, -0.24)):
            path.lineTo(QPointF(cx + dx * size, cy + dy * size))
        path.closeSubpath()
        return path

    def _draw_sparkles(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        sparkles = (
            (52, 120, 11, GOLD, 0.0),
            (352, 150, 9, PINK, 1.7),
            (60, 300, 7.5, ORB_LIGHT, 3.1),
        )
        for cx, cy, size, color, offset in sparkles:
            pulse = 0.45 + 0.35 * (0.5 + 0.5 * math.sin(self._phase * 1.4 + offset))
            qcolor = QColor(color)
            qcolor.setAlphaF(pulse)
            painter.setBrush(qcolor)
            painter.drawPath(self._star(cx, cy, size))

    def _draw_tail(self, painter: QPainter) -> None:
        speed = 0.45 if self._face == "sleepy" else 0.9
        angle = -3.0 + math.sin(self._phase * speed) * 7.0
        painter.save()
        painter.translate(295, 258)
        painter.rotate(angle)
        painter.translate(-295, -258)
        path = QPainterPath(QPointF(295, 258))
        path.quadTo(347, 246, 371, 270)
        path.quadTo(349, 268, 333, 280)
        path.quadTo(352, 288, 368, 305)
        path.quadTo(330, 296, 295, 292)
        path.closeSubpath()
        painter.setBrush(QColor(MINT))
        painter.setPen(QPen(QColor(INDIGO), 5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        painter.restore()

    def _draw_feet(self, painter: QPainter) -> None:
        painter.setBrush(QColor(LAVENDER))
        painter.setPen(QPen(QColor(INDIGO), 5))
        painter.drawEllipse(QRectF(142, 379, 40, 26))
        painter.drawEllipse(QRectF(218, 379, 40, 26))

    def _draw_arms(self, painter: QPainter) -> None:
        pen = QPen(QColor(INDIGO), 5)
        painter.setBrush(QColor(LAVENDER))
        painter.setPen(pen)
        painter.drawEllipse(QRectF(298, 253, 28, 38))
        painter.save()
        painter.translate(102, 272)
        painter.rotate(self._wave_angle())
        painter.translate(-102, -272)
        painter.drawEllipse(QRectF(74, 253, 28, 38))
        painter.restore()

    def _draw_body(self, painter: QPainter) -> None:
        body = QRectF(96, 202, 208, 196)
        clip = QPainterPath()
        clip.addEllipse(body)
        painter.save()
        painter.setClipPath(clip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(LAVENDER))
        painter.drawEllipse(body)
        painter.setBrush(QColor(LAVENDER_LIGHT))
        painter.drawEllipse(QRectF(92, 198, 152, 128))
        painter.setBrush(QColor(LAVENDER_DARK))
        painter.drawEllipse(QRectF(162, 282, 168, 124))
        painter.setBrush(QColor(BELLY))
        painter.drawEllipse(QRectF(140, 274, 120, 124))

        # A soft radial sheen on the upper-left sells the glassy volume.
        sheen = QRadialGradient(QPointF(148, 236), 155)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 72))
        sheen.setColorAt(0.55, QColor(255, 255, 255, 18))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sheen)
        painter.drawEllipse(body)
        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(INDIGO), 6))
        painter.drawEllipse(body)

    def _draw_sprout(self, painter: QPainter) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(INDIGO), 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        stem = QPainterPath(QPointF(200, 204))
        stem.quadTo(197, 196, 200, 192)
        painter.drawPath(stem)

        painter.setPen(QPen(QColor(INDIGO), 3, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QColor(MINT))
        leaf = QPainterPath(QPointF(200, 202))
        leaf.quadTo(196, 192, 200, 185)
        leaf.quadTo(204, 192, 203, 202)
        leaf.closeSubpath()
        painter.drawPath(leaf)

        leaf2 = QPainterPath(QPointF(200, 204))
        leaf2.quadTo(188, 199, 181, 189)
        leaf2.quadTo(195, 191, 200, 204)
        leaf2.closeSubpath()
        painter.drawPath(leaf2)

    # ---------------------------------------------------------------- face
    def _draw_face(self, painter: QPainter) -> None:
        face = self._face
        blink = time.monotonic() < self._blink_until and face != "sleepy"
        gx = self._gaze_x * 8
        gy = self._gaze_y * 5

        if face == "sleepy":
            self._draw_sleepy_face(painter)
            return
        if face == "surprised":
            self._draw_surprised_face(painter, blink, gx, gy)
            return
        if face == "thinking":
            self._draw_thinking_face(painter, gx, gy)
            return
        if face == "aggrieved":
            self._draw_aggrieved_face(painter, gx, gy)
            return
        self._draw_happy_face(painter, face == "excited", blink, gx, gy)

    def _draw_eye(self, painter: QPainter, cx: float, cy: float,
                  rx: float, ry: float, gx: float, gy: float, blink: bool) -> None:
        if blink:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(INDIGO), 5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            path = QPainterPath(QPointF(cx - rx * 0.8 + gx, cy - 2 + gy))
            path.quadTo(cx + gx, cy + ry * 0.35 + gy, cx + rx * 0.8 + gx, cy - 2 + gy)
            painter.drawPath(path)
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(INDIGO))
        painter.drawEllipse(QRectF(cx - rx + gx, cy - ry + gy, rx * 2, ry * 2))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(cx - rx * 0.35 + gx, cy - ry * 0.55 + gy,
                                   rx * 0.42, ry * 0.28))
        painter.drawEllipse(QRectF(cx - rx * 0.62 + gx, cy + ry * 0.12 + gy,
                                   rx * 0.18, ry * 0.14))

    def _draw_blush(self, painter: QPainter, big: bool = False) -> None:
        color = QColor(CORAL)
        color.setAlphaF(0.9 if big else 0.8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        rx, ry = (18, 11) if big else (16, 9)
        painter.drawEllipse(QRectF(128 - rx, 330 - ry, rx * 2, ry * 2))
        painter.drawEllipse(QRectF(272 - rx, 330 - ry, rx * 2, ry * 2))

    def _draw_happy_face(self, painter: QPainter, excited: bool,
                         blink: bool, gx: float, gy: float) -> None:
        self._draw_blush(painter, big=excited)
        if excited:
            self._draw_eye(painter, 163, 290, 21, 27, gx, gy, blink)
            self._draw_eye(painter, 237, 290, 21, 27, gx, gy, blink)
            mouth = QPainterPath(QPointF(180, 324))
            mouth.quadTo(200, 352, 220, 324)
            mouth.quadTo(200, 338, 180, 324)
            mouth.closeSubpath()
            painter.setBrush(QColor(CORAL))
            painter.setPen(QPen(QColor(INDIGO), 4, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(mouth)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(GOLD))
            painter.drawPath(self._star(318, 190, 14))
        else:
            self._draw_eye(painter, 163, 292, 19, 24, gx, gy, blink)
            self._draw_eye(painter, 237, 292, 19, 24, gx, gy, blink)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(INDIGO), 5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            smile = QPainterPath(QPointF(186, 330))
            smile.quadTo(200, 342, 214, 330)
            painter.drawPath(smile)

    def _draw_surprised_face(self, painter: QPainter, blink: bool,
                             gx: float, gy: float) -> None:
        self._draw_blush(painter)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(INDIGO), 3.5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        left_brow = QPainterPath(QPointF(144, 254))
        left_brow.quadTo(163, 244, 182, 254)
        right_brow = QPainterPath(QPointF(218, 254))
        right_brow.quadTo(237, 244, 256, 254)
        painter.drawPath(left_brow)
        painter.drawPath(right_brow)

        self._draw_eye(painter, 163, 292, 22, 26, gx, gy, blink)
        self._draw_eye(painter, 237, 292, 22, 26, gx, gy, blink)

        painter.setBrush(QColor(INDIGO))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(189, 327, 22, 26))

        painter.setFont(QFont("Microsoft YaHei UI", 28, QFont.Weight.Bold))
        painter.setPen(QColor("#D85A30"))
        painter.drawText(QPointF(306, 210), "!")

    def _draw_thinking_face(self, painter: QPainter, gx: float, gy: float) -> None:
        self._draw_blush(painter)
        self._draw_eye(painter, 163, 294, 18, 23, -7 + gx, -7 + gy, False)
        self._draw_eye(painter, 237, 294, 18, 23, -7 + gx, -7 + gy, False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(INDIGO), 4.5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        mouth = QPainterPath(QPointF(192, 336))
        mouth.quadTo(200, 340, 208, 336)
        painter.drawPath(mouth)
        painter.setFont(QFont("Microsoft YaHei UI", 24, QFont.Weight.Bold))
        painter.setPen(QColor(GOLD))
        painter.drawText(QPointF(310, 218), "?")

    def _draw_aggrieved_face(self, painter: QPainter, gx: float, gy: float) -> None:
        self._draw_blush(painter)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(INDIGO), 3.5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        left_brow = QPainterPath(QPointF(146, 270))
        left_brow.quadTo(163, 260, 180, 254)
        right_brow = QPainterPath(QPointF(220, 254))
        right_brow.quadTo(237, 260, 254, 270)
        painter.drawPath(left_brow)
        painter.drawPath(right_brow)

        self._draw_eye(painter, 163, 296, 18, 23, gx, gy, False)
        self._draw_eye(painter, 237, 296, 18, 23, gx, gy, False)

        tear = QPainterPath(QPointF(152, 318))
        tear.quadTo(144, 330, 152, 336)
        tear.quadTo(160, 330, 152, 318)
        painter.setBrush(QColor(ORB_LIGHT))
        painter.setPen(QPen(QColor("#0C447C"), 2))
        painter.drawPath(tear)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(INDIGO), 4.5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        mouth = QPainterPath(QPointF(186, 340))
        mouth.quadTo(200, 330, 214, 340)
        painter.drawPath(mouth)

    def _draw_sleepy_face(self, painter: QPainter) -> None:
        self._draw_blush(painter)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(INDIGO), 5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        left = QPainterPath(QPointF(146, 292))
        left.quadTo(163, 307, 180, 292)
        right = QPainterPath(QPointF(220, 292))
        right.quadTo(237, 307, 254, 292)
        painter.drawPath(left)
        painter.drawPath(right)

        painter.setBrush(QColor(CORAL))
        painter.setPen(QPen(QColor(INDIGO), 3))
        painter.drawEllipse(QRectF(194, 326, 12, 16))

        now = time.monotonic()
        painter.setFont(QFont("Microsoft YaHei UI", 20, QFont.Weight.Medium))
        for x, y, offset, size in ((294, 208, 0.0, 20), (318, 182, 1.1, 16)):
            t = ((now + offset) % 2.4) / 2.4
            color = QColor(ORB_LIGHT)
            color.setAlphaF(0.35 + 0.6 * max(0.0, 1.0 - t))
            painter.setFont(QFont("Microsoft YaHei UI", size, QFont.Weight.Medium))
            painter.setPen(color)
            painter.drawText(QPointF(x, y - t * 10), "z")

    # ---------------------------------------------------------------- orb
    def _draw_orb(self, painter: QPainter) -> None:
        bob = math.sin(self._phase * 1.35) * 6
        ox = 200 + self._gaze_x * 10
        oy = 96 + bob + self._gaze_y * 6

        glow_alpha = 28 + self._memory_level * 10 + int(self._orb_flash * 60)
        glow = QRadialGradient(QPointF(ox, oy), 58)
        glow.setColorAt(0.0, QColor(55, 138, 221, min(160, glow_alpha)))
        glow.setColorAt(1.0, QColor(55, 138, 221, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(ox - 58, oy - 58, 116, 116))

        painter.setBrush(QColor(ORB_BLUE))
        painter.setPen(QPen(QColor(INDIGO), 5))
        painter.drawEllipse(QRectF(ox - 34, oy - 34, 68, 68))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ORB_LIGHT))
        painter.drawEllipse(QRectF(ox - 12, oy - 10, 24, 24))
        painter.setBrush(QColor("#EEEDFE"))
        painter.drawEllipse(QRectF(ox + 10, oy - 12, 8, 8))
        painter.setBrush(QColor("#B5D4F4"))
        painter.drawEllipse(QRectF(ox - 10, oy - 4, 10, 10))
        painter.setBrush(QColor(GOLD))
        painter.drawEllipse(QRectF(ox + 6, oy + 6, 8, 8))
        painter.setBrush(QColor(PINK))
        painter.drawEllipse(QRectF(ox - 8, oy + 10, 6, 6))

        memory_dots = (
            (12, -4, "#EEEDFE"),
            (-16, 6, "#F4C0D1"),
            (4, 22, "#FAC775"),
            (-8, -22, "#9FE1CB"),
            (15, 8, "#CECBF6"),
        )
        for index, (dx, dy, color) in enumerate(memory_dots):
            if index >= self._memory_level:
                break
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(ox + dx - 3, oy + dy - 3, 6, 6))

    # ------------------------------------------------------------- behaviour
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._origin = self.pos()
            self._dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_global is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._press_global
            if not self._dragging and delta.manhattanLength() > 5:
                self._dragging = True
                self.bubble.hide_now()
            if self._dragging and self._origin is not None:
                self.move(self._origin + delta)
            return
        center_x = CX * self.scale
        center_y = BODY_CY * self.scale
        self._gaze_target_x = max(
            -1.0, min(1.0, (event.position().x() - center_x) / (self.width() / 2))
        )
        self._gaze_target_y = max(
            -1.0, min(1.0, (event.position().y() - center_y) / (self.height() * 0.4))
        )

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if not self._dragging:
            self.react("surprised")
            self.clicked.emit()
        self._press_global = None
        self._origin = None
        self._dragging = False

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.chat_requested.emit()
            event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.menu_requested.emit(event.globalPos())
        event.accept()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._gaze_target_x = 0.0
        self._gaze_target_y = 0.0

    def moveEvent(self, event) -> None:  # noqa: N802
        self.reposition_bubble()
        super().moveEvent(event)
