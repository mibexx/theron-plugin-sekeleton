# Concepts & lifecycle

## Where plugins live

| Path (inside Theron's data folder) | What |
|---|---|
| `plugins/<id>/` | the installed plugin: `plugin.toml`, the package, `lib/`, `i18n/`, `SIGNATURE.json` … |
| `plugin-data/<id>/` | the plugin's own folder (`ctx.data_dir`) and its log `plugin.log` |

Theron's data folder: macOS `~/Library/Application Support/Theron`, Windows `%APPDATA%\Theron`, Linux
`~/.local/share/theron`, the headless Docker image `/data` – or wherever `THERON_DATA` points.

Settings, the on/off state and `ctx.storage` live in Theron's database. Updating a plugin keeps all of them and
`plugin-data/<id>/`; removing it keeps them too unless the user chooses “remove with its data” (`--purge`).

## Hosts

The same plugin runs in different kinds of Theron processes. `ctx.host` tells which one:

| `ctx.host` | Process | Loaded | Started (schedules, `on_start`, events) | UI |
|---|---|---|---|---|
| `desktop` | the Theron app | ✔ | ✔ | ✔ `ctx.ui.available` |
| `desktop` | the app controlling a slave (Settings → Slave) | ✔ (nodes for the editor) | – the slave runs everything | ✔ |
| `slave` | `theron --listen` and the headless Docker worker | ✔ | ✔ | – |
| `cli` | `theron execute …` (a single console run) | ✔ | – | – |
| – | `theron plugin …`, `theron config …` and the other console commands | – | – | – |

So:

- **Nodes and agent tools** work wherever a process runs (app, slave, console run).
- **Schedules, `on_start`/`on_stop` and events** run only in long-running processes (app, slave) – a sync doesn't run
  twice because a console run happens to start.
- **Pages and settings UI** exist only in the desktop app. PySide6 is not available on a slave or in Docker – import
  UI code inside `if ctx.ui.available:`.

A process runs where its task runs: if the app controls a slave, the slave executes the nodes, so the plugin has to be
installed on the slave.

## Loading

At start, before the window opens, Theron:

1. reads every `plugins/*/plugin.toml` (a folder whose name differs from its `id` is an error),
2. skips plugins that are switched off, don't fit this Theron (`theron_api`, `min_theron`) or whose signature is
   invalid,
3. adds the plugin's `lib/` to the import path,
4. imports the package named by `entry` as the module `theron_plugins.<id with _>` – relative imports inside the
   package work, absolute imports of the package's own name don't,
5. calls `register(ctx)`.

`register` should only register things and return quickly. Don't do network calls there; use `ctx.on_start` or a
schedule. Everything that the plugin registers is visible immediately (nodes in the editor's palette, pages in the
navigation).

If importing or `register` raises, Theron logs the traceback, forgets everything the plugin had registered so far,
marks it as **error** in Settings → Plugins and continues with the next plugin.

If Theron itself crashes while a plugin is loading (a native crash, an endless loop the user kills), the marker file
`plugins/<id>/.loading` is still there at the next start; Theron then switches the plugin off and shows
“Theron quit while loading this plugin”.

## Starting and stopping

When the app window is shown (or the slave listens), Theron calls every `ctx.on_start` callback, starts the schedules
and emits `app.started`. When Theron quits it emits `app.stopping`, cancels schedules and calls the `ctx.on_stop`
callbacks (waiting up to 5 seconds in total).

All of this runs on one background thread with its own asyncio event loop (“theron-plugins”), shared by all plugins.
Async callbacks run on that loop – never block it (no `time.sleep`, no synchronous network calls in `async def`);
plain functions run in a worker thread and may block.

Process nodes run on Theron's engine loop, agent tools inside the agent's turn; both may be async or plain as well.

## Changes need a restart

Installing, updating, switching on/off and removing take effect after Theron restarts. The app offers the restart
when the settings dialog closes. Python modules can't be unloaded reliably, so there is no hot reload.

## Safe mode

`THERON_NO_PLUGINS=1` (environment) or `--no-plugins` (app or `theron --listen … --no-plugins`) start Theron without
loading any plugin – e.g. to switch off one that breaks the start.

## Versions and compatibility

- `theron_api` – the plugin API the plugin is written for. This Theron offers API **1**. A plugin for another API
  version is shown as “doesn't fit this Theron version” and not loaded.
- `min_theron` – optional: the oldest Theron release the plugin needs (e.g. for an API addition).
- `version` – the plugin's own version; any format with numbers (`1.4.2`) is fine. Installing a plugin with an `id`
  that is already installed replaces it, whatever the version.

Additions within API 1 (new methods, new events) are documented with the Theron version that introduced them. Plugin
API 1 was introduced with Theron 0.14.0.
