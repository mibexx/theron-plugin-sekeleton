# Pages & settings UI

Theron's desktop app is built with **PySide6** (Qt 6). A plugin's UI is made of ordinary PySide6 widgets. UI exists
only in the desktop app – always check `ctx.ui.available`, and import PySide6 only inside that branch: a slave and the
headless Docker image don't have it.

```python
def register(ctx):
    if ctx.ui.available:
        from .pages import BoardPage            # imports PySide6
        ctx.ui.add_page(ctx.tr("Board"), BoardPage, icon="▦")
```

## Navigation pages

`ctx.ui.add_page(title, factory, *, icon="", id="")`

- `title` – the navigation entry (shown in capitals, after Theron's own pages).
- `factory(ctx)` – returns the page's `QWidget`. Theron calls it once, when the window is built, on the UI thread. A
  class whose constructor takes `ctx` works as a factory.
- `icon` – one character shown before the title.

If the factory raises or returns something else than a `QWidget`, the page shows the error instead and the traceback
goes to the plugin's log.

```python
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget


class BoardPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        title = QLabel(ctx.tr("Board").upper())
        title.setObjectName("h1")
        self.cards = QListWidget()
        refresh = QPushButton(ctx.tr("Refresh"))
        refresh.setObjectName("primary")
        refresh.clicked.connect(self.refresh)
        for w in (title, self.cards, refresh):
            lay.addWidget(w)

    def refresh(self):
        future = self.ctx.spawn(load_cards, self.ctx)              # background
        future.add_done_callback(lambda f: self.ctx.ui.call(self.show_cards, f.result() or []))

    def show_cards(self, cards):                                   # UI thread
        self.cards.clear()
        self.cards.addItems([c["name"] for c in cards])
```

## Threads – the one rule

Widgets may only be touched on the **UI thread**. Page factories, button handlers and the settings page run there.
Everything else – schedules, events, `ctx.spawn`, nodes – runs elsewhere. From there, hand UI updates over with
`ctx.ui.call(fn, *args)`. And never block the UI thread: run network calls with `ctx.spawn`.

## Settings UI

Most plugins need no code: the `[[settings]]` in `plugin.toml` become a dialog (Settings → Plugins → *Settings …*).
For more – a “Test connection” button, an OAuth login, a preview – add a widget below the generated fields:

```python
class ConnectionTest(QWidget):
    def __init__(self, ctx):
        ...

    def save(self):          # optional – called when the user clicks Save (after the fields are stored)
        ...

ctx.ui.settings_page(ConnectionTest)
```

If `save()` raises, Theron shows the error and keeps the dialog open.

## Notifications and links

- `ctx.notify(text, level)` – a toast bottom right (works from any thread).
- `ctx.ui.open_url(url)` – opens the browser, e.g. for an OAuth login.

## Theron's look

Theron styles every widget with its HUD theme automatically. Object names for special looks:

| Widget | `setObjectName(...)` | Look |
|---|---|---|
| `QLabel` | `"h1"` | page title |
| `QLabel` | `"h2"` | section title (small capitals) |
| `QLabel` | `"dim"` | secondary text |
| `QLabel` | `"mono"` | monospace |
| `QPushButton` | `"primary"` | main action |
| `QPushButton` | `"ghost"` | quiet action |
| `QPushButton` | `"danger"` | destructive action |

Theron's colours: background `#02070d`, cyan `#00e5ff`, green `#3dffb0`, amber `#ffb648`, red `#ff4f6d`.
