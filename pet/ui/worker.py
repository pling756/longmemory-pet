"""Background jobs so model calls never freeze the pet."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ..core.chat import ChatEngine


class ChatSignals(QObject):
    replied = Signal(object)        # ChatResult
    remembered = Signal(object)     # StoreResult
    consolidate_due = Signal()      # heavy work, run it in a separate task
    failed = Signal(str)
    done = Signal()


class ChatTask(QRunnable):
    def __init__(self, engine: ChatEngine, text: str):
        super().__init__()
        self.engine = engine
        self.text = text
        self.signals = ChatSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self.engine.respond(self.text)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            traceback.print_exc()
            self.signals.failed.emit(str(exc))
            self.signals.done.emit()
            return
        self.signals.replied.emit(result)
        try:
            stored = self.engine.remember(
                self.text, result.reply, [result.user_message_id or 0]
            )
            self.signals.remembered.emit(stored)
            if self.engine.memory.consolidator.auto_due():
                self.signals.consolidate_due.emit()
        except Exception:  # memory failure must not kill the conversation
            traceback.print_exc()
        finally:
            self.signals.done.emit()


class ConsolidateSignals(QObject):
    finished = Signal(object)  # ConsolidationResult
    failed = Signal(str)


class ConsolidateTask(QRunnable):
    def __init__(self, memory_service, force: bool = True):
        super().__init__()
        self.memory_service = memory_service
        self.force = force
        self.signals = ConsolidateSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self.memory_service.maybe_consolidate(force=self.force)
            self.signals.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.signals.failed.emit(str(exc))
