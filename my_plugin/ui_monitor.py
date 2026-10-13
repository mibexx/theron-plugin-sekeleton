"""The panel “Agents at work” (next to the cockpit and the THERON page) and the live-log window – desktop app only.

A panel's factory gets ``view``: ``view.context`` says what the page shows (here ``run_id``), ``view.on_context``
calls back when that changes. Reading ``ctx.runs`` is fast (local database), so the panel simply refreshes every
few seconds on the UI thread.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class WorkersPanel(QWidget):
    def __init__(self, view):
        super().__init__()
        self.view, self.ctx = view, view.ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self.workers = QLabel()
        self.workers.setWordWrap(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("mono")
        live = QPushButton(self.ctx.tr("Live log in a window"))
        live.setObjectName("ghost")
        live.clicked.connect(self.open_window)
        for w in (self.workers, self.log, live):
            lay.addWidget(w)
        view.on_context(lambda context: self.refresh())     # another task shown
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()

    def refresh(self) -> None:
        run_id = self.view.context.get("run_id")
        if not run_id:
            self.workers.setText(self.ctx.tr("No task open."))
            self.log.setPlainText("")
            return
        lines = []
        for w in self.ctx.runs.workers(run_id):
            since = int((time.time() - w["started"]) / 60)
            note = f"\n   {w['status_note']}" if w.get("status_note") else ""
            lines.append(f"▶ {w['agent']} · {since} min{note}")
        self.workers.setText("\n".join(lines) or self.ctx.tr("No agent is working right now."))
        self.log.setPlainText("\n".join(self.ctx.runs.log(run_id, last=40)))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def open_window(self) -> None:
        run_id = self.view.context.get("run_id")
        if run_id:
            self.ctx.ui.open_window(self.ctx.tr("Live log"), lambda view: LiveLog(view, run_id), id=f"log-{run_id}",
                                    width=760, height=520)


class LiveLog(QWidget):
    """A window of its own: the log of one task, live (ctx.runs.watch) – new lines come from the plugins' thread and
    are handed to the UI thread with ctx.ui.call."""

    def __init__(self, view, run_id: int):
        super().__init__()
        self.ctx = view.ctx
        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText("\n".join(self.ctx.runs.log(run_id, last=200)))
        lay.addWidget(self.text)
        self.watch = self.ctx.runs.watch(lambda ev: self.ctx.ui.call(self.add, ev["line"]), run_id=run_id)
        self.destroyed.connect(lambda *_: self.watch.cancel())

    def add(self, line: str) -> None:
        if line:
            self.text.appendPlainText(line)
