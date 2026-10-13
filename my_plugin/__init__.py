"""My Plugin – a Theron plugin.

Theron calls ``register(ctx)`` once at start. Everything the plugin brings is registered here through ``ctx`` –
the plugin API (https://theron.mibexx.de/docs-plugins.html#en-pl-api). Delete what you don't need: every part
below is independent of the others.
"""

from . import events, nodes, tools
from .integrations.sync import TaskListSync
from .integrations.trello import TrelloAdapter


def register(ctx):
    # 1. Integration: two-way sync of a Theron task list with a Trello board (integrations/)
    sync = TaskListSync(ctx, TrelloAdapter(ctx))
    ctx.on_start(lambda: ctx.log(f"{ctx.name} {ctx.version} running on {ctx.host}"))
    ctx.schedule(max(1, int(ctx.settings.get("sync_minutes") or 5)) * 60, sync.run_if_configured, first=15)

    # 2. Process nodes for the editor (nodes.py)
    nodes.register(ctx, sync)

    # 3. A tool every Claude agent can use while it works (tools.py)
    tools.register(ctx)

    # 4. Reacting to what happens in Theron (events.py)
    events.register(ctx, sync)

    # 5. UI: a navigation entry and extra settings – desktop app only (pages.py, settings_page.py)
    if ctx.ui.available:   # PySide6 exists only there (not on a slave / in the headless Docker image)
        from . import pages, settings_page
        ctx.ui.add_page(ctx.tr("My Plugin"), lambda c: pages.SyncPage(c, sync), icon="⬢")
        ctx.ui.settings_page(lambda c: settings_page.ConnectionTest(c, sync))
