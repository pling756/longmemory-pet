"""Manual real-desktop check: shows the pet for a few seconds and grabs it.

    python tests/live_gui.py

This exercises the Windows platform plugin (opacity animation, topmost window,
tray off) instead of the offscreen platform used by visual_smoke.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SHOTS = ROOT / ".shots"
SHOTS.mkdir(exist_ok=True)
DATA = ROOT / "data" / "live-preview"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["LONGMEM_PET_HOME"] = str(DATA)

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import PetController  # noqa: E402
from pet.config import AppConfig  # noqa: E402


def compose(rects, widgets, path: Path) -> None:
    union = rects[0]
    for rect in rects[1:]:
        union = union.united(rect)
    margin = 20
    image = QImage(union.width() + margin * 2, union.height() + margin * 2,
                   QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 0, image.height())
    gradient.setColorAt(0, QColor("#EFE9E0"))
    gradient.setColorAt(1, QColor("#D9D2C6"))
    painter.fillRect(image.rect(), gradient)
    for rect, widget in zip(rects, widgets):
        painter.drawPixmap(rect.topLeft() - union.topLeft() + QPoint(margin, margin),
                           widget.grab())
    painter.end()
    image.save(str(path))
    print("saved", path, image.size())


def main() -> int:
    app = QApplication([])
    config = AppConfig.load(DATA / "config.json", mock=True)
    controller = PetController(app, config, no_tray=True)
    controller.start(demo=True)
    QTest.qWait(1400)
    app.processEvents()

    pet_rect = QRect(controller.pet.mapToGlobal(QPoint(0, 0)), controller.pet.size())
    bubble = controller.pet.bubble
    bubble_rect = QRect(bubble.mapToGlobal(QPoint(0, 0)), bubble.size())
    print("bubble visible:", bubble.isVisible(), "opacity:", bubble.windowOpacity())
    compose([pet_rect, bubble_rect], [controller.pet, bubble], SHOTS / "live-pet.png")

    controller.open_chat()
    controller.open_memory()
    QTest.qWait(600)
    controller.chat.grab().save(str(SHOTS / "live-chat.png"))
    controller.memory_window.grab().save(str(SHOTS / "live-memory.png"))
    print("chat:", controller.chat.size(), "memory:", controller.memory_window.size())
    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
