"""Memory inspector: profile, search, importance, forgetting and consolidation."""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..memory.models import KIND_LABELS
from ..memory.service import MemoryService
from .theme import (
    BORDER,
    INK,
    LAVENDER_DARK,
    LAVENDER_SOFT,
    MUTED,
    PAPER,
    font,
)

KIND_ORDER = ("fact", "preference", "episode", "plan", "summary")
KIND_COLORS = {
    "fact": "#7C9A92",
    "preference": "#D98E8E",
    "episode": "#C89A6B",
    "plan": "#8C8FC0",
    "summary": "#9A8C7C",
}


class MemoryWindow(QWidget):
    consolidate_requested = Signal()
    memory_changed = Signal()

    def __init__(self, service: MemoryService, pet_name: str = "拾光", parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.service = service
        self.pet_name = pet_name
        self.resize(790, 640)
        self._drag_origin: QPoint | None = None
        self._rows: list = []

        shell = QVBoxLayout(self)
        shell.setContentsMargins(14, 14, 14, 14)
        self.panel = QFrame(self)
        self.panel.setObjectName("memPanel")
        self.panel.setStyleSheet(
            f"QFrame#memPanel {{ background: {PAPER}; border: 1px solid {BORDER};"
            "border-radius: 18px; }"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 9)
        shadow.setColor(QColor(50, 35, 90, 55))
        self.panel.setGraphicsEffect(shadow)
        shell.addWidget(self.panel)

        outer = QVBoxLayout(self.panel)
        outer.setContentsMargins(22, 16, 22, 18)
        outer.setSpacing(12)

        header = QWidget(self.panel)
        header.setFixedHeight(46)
        head = QHBoxLayout(header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)

        dot = QLabel("◈", header)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setFixedSize(34, 34)
        dot.setStyleSheet(
            f"background: {LAVENDER_SOFT}; color: {LAVENDER_DARK}; border-radius: 17px;"
            "font-size: 16px;"
        )
        head.addWidget(dot)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(f"{pet_name} 的记忆库", header)
        title.setFont(font(13, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {INK};")
        self.subtitle = QLabel("", header)
        self.subtitle.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        head.addStretch(1)

        close = QToolButton(header)
        close.setText("×")
        close.setStyleSheet(
            "QToolButton { font-size: 18px; color: #9C8574; padding-bottom: 3px;"
            " background: transparent; border: none; }"
            "QToolButton:hover { background: #FBE3DC; color: #C0604F; }"
        )
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setAutoRaise(True)
        close.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self.hide)
        head.addWidget(close)
        outer.addWidget(header)

        profile_card = QFrame(self.panel)
        profile_card.setObjectName("profileCard")
        profile_card.setStyleSheet(
            f"QFrame#profileCard {{ background: #F7F4FF; border: 1px solid #E7E1F7;"
            "border-radius: 12px; }"
        )
        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(14, 10, 14, 10)
        profile_layout.setSpacing(4)
        profile_title = QLabel("关于 TA", profile_card)
        profile_title.setStyleSheet(f"color: {MUTED}; font-size: 11px; border: none;")
        self.profile_label = QLabel("还没有稳定的画像，多聊几次就会有了。", profile_card)
        self.profile_label.setWordWrap(True)
        self.profile_label.setStyleSheet(f"color: {INK}; font-size: 12px; border: none;")
        profile_layout.addWidget(profile_title)
        profile_layout.addWidget(self.profile_label)
        outer.addWidget(profile_card)

        toolbar = QWidget(self.panel)
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(8)

        self.search = QLineEdit(toolbar)
        self.search.setPlaceholderText("搜一条记忆，比如：咖啡 / 杭州 / 项目")
        self.search.setFixedHeight(34)
        self.search.textChanged.connect(self._on_search)
        tools.addWidget(self.search, 1)

        self.kind = QComboBox(toolbar)
        self.kind.addItem("全部类型", "")
        for kind in KIND_ORDER:
            self.kind.addItem(KIND_LABELS[kind], kind)
        self.kind.setFixedHeight(34)
        self.kind.currentIndexChanged.connect(self.refresh)
        tools.addWidget(self.kind)

        self.forget_button = QPushButton("忘记", toolbar)
        self.forget_button.setFixedHeight(34)
        self.forget_button.setStyleSheet(
            f"QPushButton {{ background: #FFF0EA; color: #B46355; border: 1px solid #F0D5CC;"
            "border-radius: 12px; padding: 0 14px; font-weight: 500; }"
            "QPushButton:hover { background: #FBE3DC; }"
        )
        self.forget_button.setEnabled(False)
        self.forget_button.clicked.connect(self._forget)
        tools.addWidget(self.forget_button)

        self.consolidate_button = QPushButton("整理记忆", toolbar)
        self.consolidate_button.setFixedHeight(34)
        self.consolidate_button.setStyleSheet(
            f"QPushButton {{ background: {LAVENDER_DARK}; color: white; border: none;"
            "border-radius: 12px; padding: 0 14px; font-weight: 600; }"
            "QPushButton:hover { background: #7B72C9; }"
            "QPushButton:disabled { background: #E4DFF2; color: #A9A2BF; }"
        )
        self.consolidate_button.clicked.connect(self._consolidate)
        tools.addWidget(self.consolidate_button)
        outer.addWidget(toolbar)

        self.empty = QLabel(
            "还没有记忆。去和 TA 聊聊天，名字、喜好、计划都会被慢慢记住。",
            self.panel,
        )
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"color: {MUTED}; font-size: 12px; padding: 18px;")
        outer.addWidget(self.empty)

        self.table = QTableWidget(0, 5, self.panel)
        self.table.setHorizontalHeaderLabels(["类型", "内容", "重要度", "时间", "命中"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(46)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 74)
        self.table.setColumnWidth(2, 74)
        self.table.setColumnWidth(3, 118)
        self.table.setColumnWidth(4, 58)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(self._show_detail)
        outer.addWidget(self.table, 1)

        self.footer = QLabel("", self.panel)
        self.footer.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        outer.addWidget(self.footer)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(240)
        self._search_timer.timeout.connect(self.refresh)

        self.refresh()

    # ------------------------------------------------------------------ API
    def refresh(self) -> None:
        query = self.search.text().strip()
        kind = self.kind.currentData()
        if query:
            rows = self.service.search(query, limit=300)
            if kind:
                rows = [memory for memory in rows if memory.kind == kind]
        else:
            rows = self.service.store.list_memories(kind=kind or None, limit=300)
        self._rows = rows
        self._fill_table(rows)
        self._fill_profile()
        stats = self.service.stats()
        self.footer.setText(
            f"{stats['active']} 条活跃记忆 · {stats['archived']} 条已归档 · "
            f"{stats['messages']} 条对话 · 数据库 {stats['db_kb']} KB"
        )
        self.subtitle.setText(
            f"{stats['active']} 条记忆，其中 {stats.get('by_kind', {}).get('episode', 0)} 条经历"
        )
        self.empty.setVisible(not rows)
        self.table.setVisible(bool(rows))
        self.forget_button.setEnabled(False)

    def show_result(self, result) -> None:
        self.consolidate_button.setEnabled(True)
        self.consolidate_button.setText("整理记忆")
        self.refresh()
        if getattr(result, "changed", False):
            QMessageBox.information(self, "整理完成", result.describe())
        else:
            QMessageBox.information(self, "整理完成", "暂时没有足够旧的片段可以归纳。")

    def show_error(self, message: str) -> None:
        self.consolidate_button.setEnabled(True)
        self.consolidate_button.setText("整理记忆")
        QMessageBox.warning(self, "整理失败", message)

    # ------------------------------------------------------------- internals
    def _fill_table(self, rows) -> None:
        self.table.setRowCount(0)
        for row_index, memory in enumerate(rows):
            self.table.insertRow(row_index)
            kind_item = QTableWidgetItem(memory.kind_label)
            kind_item.setForeground(QColor(KIND_COLORS.get(memory.kind, INK)))
            kind_item.setFont(font(9, QFont.Weight.DemiBold))
            kind_item.setData(Qt.ItemDataRole.UserRole, memory.id)

            content = QTableWidgetItem(memory.preview(46))
            content.setToolTip(
                f"{memory.content}\n\n关键词：{'、'.join(memory.keywords) or '无'}"
            )

            importance = QTableWidgetItem(f"{memory.importance:.2f}")
            importance.setForeground(
                QColor("#C07A55" if memory.importance >= 0.7 else MUTED)
            )
            importance.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            stamp = time.strftime("%m-%d %H:%M", time.localtime(memory.created_at))
            time_item = QTableWidgetItem(stamp)
            time_item.setForeground(QColor(MUTED))

            hits = QTableWidgetItem(str(memory.access_count))
            hits.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            hits.setForeground(QColor(MUTED))

            for column, item in enumerate(
                (kind_item, content, importance, time_item, hits)
            ):
                self.table.setItem(row_index, column, item)

    def _fill_profile(self) -> None:
        profile = self.service.profile()
        if not profile:
            self.profile_label.setText("还没有稳定的画像，多聊几次就会有了。")
            return
        order = ["称呼", "城市", "职业", "生日", "喜好", "忌口", "目标"]
        parts = [f"{key}：{profile[key]}" for key in order if key in profile]
        parts += [f"{key}：{value}" for key, value in profile.items() if key not in order]
        self.profile_label.setText("　·　".join(parts))

    def _on_search(self) -> None:
        self._search_timer.start()

    def _selection_changed(self) -> None:
        self.forget_button.setEnabled(bool(self.table.selectedItems()))

    def _forget(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 1)
        if item is None:
            return
        memory_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        label = item.text()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("忘记这条记忆？")
        box.setText(f"「{label}」\n\n忘记之后就找不回来了，确定吗？")
        forget_button = box.addButton("忘记", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("算了", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not forget_button:
            return
        self.service.forget(int(memory_id))
        self.refresh()
        self.memory_changed.emit()

    def _consolidate(self) -> None:
        self.consolidate_button.setEnabled(False)
        self.consolidate_button.setText("整理中…")
        self.consolidate_requested.emit()

    def _show_detail(self, row: int, column: int) -> None:
        item = self.table.item(row, 1)
        if item is None:
            return
        memory = self._rows[row] if row < len(self._rows) else None
        if memory is None:
            return
        QMessageBox.information(
            self,
            "记忆详情",
            f"{memory.content}\n\n类型：{memory.kind_label}\n"
            f"重要度：{memory.importance:.2f}\n"
            f"创建：{time.strftime('%Y-%m-%d %H:%M', time.localtime(memory.created_at))}\n"
            f"最近用到：{time.strftime('%Y-%m-%d %H:%M', time.localtime(memory.last_access_at)) if memory.last_access_at else '还没用过'}\n"
            f"命中次数：{memory.access_count}\n"
            f"关键词：{'、'.join(memory.keywords) or '无'}",
        )

    # ------------------------------------------------------------- behaviour
    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        super().showEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 72:
            self._drag_origin = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        super().mouseReleaseEvent(event)
