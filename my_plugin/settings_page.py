"""Extra settings UI – shown below the fields generated from plugin.toml (Settings → Plugins → Settings …).
A ``save()`` method, if there is one, is called when the user saves."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ConnectionTest(QWidget):
    def __init__(self, ctx, sync):
        super().__init__()
        self.ctx, self.sync = ctx, sync
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        self.button = QPushButton(ctx.tr("Test connection"))
        self.button.clicked.connect(self.test)
        self.result = QLabel()
        self.result.setObjectName("dim")
        self.result.setWordWrap(True)
        lay.addWidget(self.button)
        lay.addWidget(self.result)

    def test(self) -> None:
        # note: this tests the SAVED settings – save first after changing them
        self.result.setText("…")

        async def run():
            try:
                name = await self.sync.adapter.test()
                text = self.ctx.tr("Connected as {name}", name=name)
            except Exception as exc:  # noqa: BLE001
                text = self.ctx.tr("Connection failed: {error}", error=exc)
            self.ctx.ui.call(self.result.setText, text)
        self.ctx.spawn(run)

    def save(self) -> None:
        pass   # nothing extra to store – the fields above are saved by Theron
