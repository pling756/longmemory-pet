"""Offscreen visual smoke test + screenshots.

    python tests/visual_smoke.py

Writes PNGs into .shots/ and prints basic assertions. On Windows the font
directory hint lets the offscreen platform use system fonts.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".deps"))
sys.path.insert(0, str(ROOT))

SHOTS = ROOT / ".shots"
SHOTS.mkdir(exist_ok=True)
DATA = ROOT / "data" / "preview"
DATA.mkdir(parents=True, exist_ok=True)
for stale in DATA.glob("memory.sqlite3*"):
    try:
        stale.unlink()
    except OSError:
        pass
try:
    (DATA / "config.json").unlink()
except OSError:
    pass

os.environ["LONGMEM_PET_HOME"] = str(DATA)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import PetController  # noqa: E402
from pet.config import AppConfig  # noqa: E402

BACKGROUND_TOP = "#F2ECE2"
BACKGROUND_BOTTOM = "#DCD4C8"


def paint_background(image: QImage) -> QPainter:
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 0, image.height())
    gradient.setColorAt(0.0, QColor(BACKGROUND_TOP))
    gradient.setColorAt(1.0, QColor(BACKGROUND_BOTTOM))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(QColor(255, 255, 255, 40))
    for x in range(0, image.width(), 46):
        painter.drawLine(x, 0, x, image.height())
    return painter


def save_widget(widget, name: str, pad: int = 18) -> Path:
    pixmap = widget.grab()
    image = QImage(pixmap.width() + pad * 2, pixmap.height() + pad * 2,
                   QImage.Format.Format_ARGB32)
    painter = paint_background(image)
    painter.drawPixmap(pad, pad, pixmap)
    painter.end()
    path = SHOTS / name
    image.save(str(path))
    return path


def save_pet_scene(controller: PetController, name: str = "pet.png") -> Path:
    pet = controller.pet
    bubble = pet.bubble
    rects = [QRect(pet.mapToGlobal(QPoint(0, 0)), pet.size())]
    if bubble.isVisible():
        rects.append(QRect(bubble.mapToGlobal(QPoint(0, 0)), bubble.size()))
    union = rects[0]
    for rect in rects[1:]:
        union = union.united(rect)
    margin = 24
    size = union.size()
    image = QImage(size.width() + margin * 2, size.height() + margin * 2,
                   QImage.Format.Format_ARGB32)
    painter = paint_background(image)
    if bubble.isVisible():
        painter.drawPixmap(
            bubble.mapToGlobal(QPoint(0, 0)) - union.topLeft() + QPoint(margin, margin),
            bubble.grab(),
        )
    painter.drawPixmap(
        pet.mapToGlobal(QPoint(0, 0)) - union.topLeft() + QPoint(margin, margin),
        pet.grab(),
    )
    painter.end()
    path = SHOTS / name
    image.save(str(path))
    return path


def main() -> int:
    app = QApplication([])
    config = AppConfig.load(mock=True)
    controller = PetController(app, config, no_tray=True)
    controller.start(demo=True)
    QTest.qWait(900)
    app.processEvents()

    assert controller.pet.isVisible(), "pet should be visible"
    assert controller.service.stats()["active"] >= 7, "demo memories seeded"

    controller.open_chat()
    QTest.qWait(120)
    controller.chat.add_message("user", "今天开会被否了，有点沮丧。")
    controller.chat.add_message(
        "assistant", "先别急着否定自己呀。要不要去楼下买杯冰美式，边走边跟我说说？"
    )
    controller.chat.set_status(controller.engine.status_line())
    controller.open_memory()
    QTest.qWait(260)
    app.processEvents()

    controller.pet.say("今天也辛苦啦，我陪着你。", 60000)
    QTest.qWait(120)
    generated = [
        save_pet_scene(controller),
        save_widget(controller.chat, "chat.png"),
        save_widget(controller.memory_window, "memory.png"),
    ]
    print("screenshots:", ", ".join(str(p.relative_to(ROOT)) for p in generated))
    print("chat size:", controller.chat.size())
    print("memory rows:", controller.memory_window.table.rowCount())

    controller.send_message("你还记得我喜欢喝什么吗？")
    QTest.qWait(2500)
    app.processEvents()
    assert controller.chat._message_count >= 8, "reply should be appended"
    assert controller.service.stats()["messages"] >= 6, "messages persisted"
    recalled = controller.service.recall("我喜欢喝什么").items.items
    assert recalled, "recall should return the coffee preference"
    print("recall:", [(item.memory.content, round(item.score, 2)) for item in recalled[:3]])
    print("ok")
    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
