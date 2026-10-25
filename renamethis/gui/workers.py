"""Execução em segundo plano (QThread) — o worker nunca mexe na interface;
ele só emite sinais, que o Qt entrega na thread principal."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot


class Worker(QObject):
    progress = Signal(int, int)
    finished = Signal(object)

    def __init__(self, fn: Callable[[Callable[[int, int], None]], Any]) -> None:
        super().__init__()
        self._fn = fn
        self._last_pct = -1

    def _report(self, done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 100
        if pct != self._last_pct:  # evita inundar a interface com sinais
            self._last_pct = pct
            self.progress.emit(done, total)

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn(self._report)
        except Exception as exc:  # o núcleo já reverte; aqui só repassamos o erro
            result = exc
        self.finished.emit(result)


def start_worker(
    parent: QObject,
    fn: Callable[[Callable[[int, int], None]], Any],
    on_progress: Callable[[int, int], None],
    on_finished: Callable[[Any], None],
) -> tuple[QThread, Worker]:
    thread = QThread(parent)
    worker = Worker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
