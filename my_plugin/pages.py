"""A navigation entry of its own (desktop app only). Pages are PySide6 widgets; Theron builds them on the UI thread
once the window exists. Work in the background with ``ctx.spawn`` and come back to the UI with ``ctx.ui.call`` –
widgets may only be touched on the UI thread."""

from __future__ import annotations

import time

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class SyncPage(QWidget):
    def __init__(self, ctx, sync):
        super().__init__()
        self.ctx, self.sync = ctx, sync
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(14)
        title = QLabel(ctx.tr("My Plugin").upper())
        title.setObjectName("h1")              # Theron's styles: h1, h2, dim, mono …
        lay.addWidget(title)
        self.state = QLabel()
        self.state.setObjectName("dim")
        self.state.setWordWrap(True)
        lay.addWidget(self.state)
        row = QHBoxLayout()
        self.button = QPushButton(ctx.tr("Sync now"))
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.sync_now)
        row.addWidget(self.button)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.show_state()

    def show_state(self) -> None:
        if not self.sync.configured():
            self.state.setText(self.ctx.tr("Trello sync is off – set the API key, token and board in the settings."))
            return
        last = self.sync.last
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(last["time"])) if last["time"] else self.ctx.tr("never")
        text = f"{self.ctx.tr('Last sync')}: {when}"
        if last["report"]:
            r = last["report"]
            text += "\n" + self.ctx.tr("Synced: {created} new, {updated} updated",
                                       created=r["created_local"] + r["created_remote"],
                                       updated=r["updated_local"] + r["updated_remote"])
        if last["error"]:
            text += f"\n✖ {last['error']}"
        self.state.setText(text)

    def sync_now(self) -> None:
        self.button.setEnabled(False)
        future = self.ctx.spawn(self.sync.run)
        future.add_done_callback(lambda _: self.ctx.ui.call(self._done))

    def _done(self) -> None:
        self.button.setEnabled(True)
        self.show_state()


class TasklistSyncPanel(QWidget):
    """A panel next to Theron's task-list page (ctx.ui.add_panel("tasks", …)): whether the task list shown is the one
    the Trello sync uses. ``view.context`` says which list the page shows; ``view.on_context`` calls back when the user
    picks another one."""

    def __init__(self, view, sync):
        super().__init__()
        self.view, self.ctx, self.sync = view, view.ctx, sync
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        lay.addStretch(1)
        view.on_context(lambda context: self.show_for(context.get("tasklist_id")))
        self.show_for(view.context.get("tasklist_id"))

    def show_for(self, tasklist_id) -> None:
        if not tasklist_id:
            self.text.setText(self.ctx.tr("No task list selected."))
        elif tasklist_id == self.sync.tasklist_id():
            self.text.setText(self.ctx.tr("This list is synced with Trello."))
        else:
            self.text.setText(self.ctx.tr("This list isn't synced – choose it in the plugin settings."))
