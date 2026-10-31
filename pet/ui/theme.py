"""Shared palette, fonts and global stylesheet for 拾光."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication

CREAM = "#FBF8FF"
PAPER = "#FFFDFB"
INK = "#2B2350"
MUTED = "#7E7699"

INDIGO = "#26215C"
LAVENDER = "#AFA9EC"
LAVENDER_LIGHT = "#C9C4F5"
LAVENDER_DARK = "#8B82D6"
LAVENDER_SOFT = "#EEEDFE"
BELLY = "#EEEDFE"
MINT = "#5DCAA5"
ORB_BLUE = "#378ADD"
ORB_LIGHT = "#85B7EB"
CORAL = "#F0997B"
GOLD = "#BA7517"
PINK = "#ED93B1"

BORDER = "#E9E3F7"

FONT_FAMILY = "Microsoft YaHei UI"


def font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT_FAMILY, size)
    f.setWeight(weight)
    return f


def app_stylesheet() -> str:
    return f"""
    QToolTip {{
        background: {INK}; color: #FFFDFB; border: none;
        padding: 5px 8px; border-radius: 6px; font-size: 12px;
    }}
    QLineEdit {{
        background: #F7F4FF; border: 1px solid {BORDER};
        border-radius: 14px; padding: 8px 14px; color: {INK};
        selection-background-color: {LAVENDER_LIGHT};
        font-size: 13px;
    }}
    QLineEdit:focus {{ border: 1px solid {LAVENDER_DARK}; background: #FBF9FF; }}
    QPushButton {{
        background: {LAVENDER_DARK}; color: white; border: none;
        border-radius: 14px; padding: 8px 18px; font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: #7B72C9; }}
    QPushButton:disabled {{ background: #E4DFF2; color: #A9A2BF; }}
    QToolButton {{
        border: none; background: transparent; border-radius: 8px;
        color: {MUTED}; padding: 4px 8px; font-size: 13px;
    }}
    QToolButton:hover {{ background: #F1EDFF; color: {INK}; }}
    QComboBox {{
        background: #F7F4FF; border: 1px solid {BORDER}; border-radius: 10px;
        padding: 6px 10px; color: {INK}; min-width: 82px;
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {PAPER}; border: 1px solid {BORDER};
        selection-background-color: {LAVENDER_SOFT}; color: {INK};
        outline: 0;
    }}
    QTableWidget {{
        background: {PAPER}; border: 1px solid {BORDER}; border-radius: 12px;
        gridline-color: transparent; color: {INK}; font-size: 12px;
        selection-background-color: #F4F1FF; selection-color: {INK};
    }}
    QHeaderView::section {{
        background: #F7F4FF; color: {MUTED}; border: none;
        border-bottom: 1px solid {BORDER}; padding: 7px 8px; font-size: 12px;
    }}
    QTableWidget::item {{ padding: 6px; border-bottom: 1px solid #F2EEFB; }}
    QScrollBar:vertical {{
        background: transparent; width: 8px; margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: #D9D2EE; border-radius: 4px; min-height: 28px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QMenu {{
        background: {PAPER}; border: 1px solid {BORDER}; border-radius: 10px;
        padding: 6px; color: {INK}; font-size: 13px;
    }}
    QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 7px; }}
    QMenu::item:selected {{ background: {LAVENDER_SOFT}; }}
    QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
    """


def apply_app_style(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(font(10))
    app.setStyleSheet(app_stylesheet())


def make_tray_icon(size: int = 64) -> QIcon:
    """A tiny 拾光: lavender body, orb above, mint sprout."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    painter.setBrush(QColor(70, 60, 110, 45))
    painter.drawEllipse(QRectF(14, 55, 36, 6))

    # tail
    tail = QPainterPath()
    tail.moveTo(46, 45)
    tail.quadTo(60, 40, 58, 30)
    tail.quadTo(56, 24, 49, 29)
    tail.quadTo(56, 36, 44, 41)
    tail.closeSubpath()
    painter.setBrush(QColor(MINT))
    painter.setPen(QColor(INDIGO))
    painter.drawPath(tail)

    # body
    painter.setPen(QColor(INDIGO))
    painter.setBrush(QColor(LAVENDER))
    painter.drawEllipse(QRectF(12, 22, 40, 34))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BELLY))
    painter.drawEllipse(QRectF(23, 36, 18, 15))

    # sprout
    painter.setPen(QColor(INDIGO))
    painter.setBrush(QColor(MINT))
    painter.drawEllipse(QRectF(28, 16, 8, 6))
    painter.drawEllipse(QRectF(35, 19, 7, 5))

    # orb
    painter.setBrush(QColor(ORB_BLUE))
    painter.drawEllipse(QRectF(26, 2, 12, 12))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ORB_LIGHT))
    painter.drawEllipse(QRectF(28, 4, 4, 4))

    # eyes
    painter.setBrush(QColor(INDIGO))
    painter.drawEllipse(QRectF(24, 34, 3, 5))
    painter.drawEllipse(QRectF(37, 34, 3, 5))
    painter.setBrush(QColor(CORAL))
    painter.drawEllipse(QRectF(19, 41, 5, 3))
    painter.drawEllipse(QRectF(40, 41, 5, 3))
    painter.end()
    return QIcon(pixmap)
