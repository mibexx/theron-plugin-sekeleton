# Troubleshooting

## Where to look

| What | Where |
|---|---|
| The plugin's log | Settings → Plugins → select the plugin → *Log*, or `plugin-data/<id>/plugin.log` in Theron's data folder |
| Loading state and errors | Settings → Plugins (● loaded, ○ off, ✖ error, ! doesn't fit), or `theron plugin list` |
| Details of a package | `theron plugin info FILE` |
| A slave / the Docker worker | its console output (`docker logs …`): `[plugins] <id> <version>: loaded` and the plugin's log lines |

## Common problems

**The plugin doesn't show up after installing.** Theron loads plugins at start – restart it. Check that it is switched
on in Settings → Plugins.

**“plugin.toml is missing” / “the package '…/__init__.py' is missing”.** The package must have `plugin.toml` at its root
(or in its single top folder), and `entry` must name a folder with an `__init__.py`.

**“folder '…' doesn't match its id”.** Don't rename folders in `plugins/` by hand – install packages instead.

**“needs plugin API 2” / “needs Theron 0.15.0 or newer”.** The plugin was built for another Theron. Update Theron (or
use an older release of the plugin).

**“signature invalid”.** A file was changed after signing – often a stray file that was packed (check
`.theronignore`) or an edit after `--sign`. Pack and sign again.

**`ModuleNotFoundError` for a library.** There is no `pip` inside Theron. Vendor pure-Python libraries into `lib/`
(`pip install --target lib PACKAGE`). Libraries with native code (C extensions) can't be used.

**`ModuleNotFoundError: No module named 'PySide6'` on a slave / in Docker.** UI code may only be imported inside
`if ctx.ui.available:`.

**`ImportError: attempted relative import …` / the package's own name can't be imported.** Theron imports the
package under a name of its own; use relative imports inside it (`from .client import Client`).

**Events don't arrive.** They are delivered only in the app and on a slave, after `app.started` – not in
`theron execute` runs. Your own changes through `ctx.tasklists` don't come back to you (`include_own=True` changes that).

**A schedule doesn't run.** Same as events – and the minimum interval is 5 seconds. Check `job.last_error`.

**A node says “plugin missing”.** The process runs on a machine (e.g. a slave) where the plugin isn't installed or is
switched off – install it there.

**`ctx.ui.call` raises “no app window here”.** Only the desktop app has a UI; check `ctx.ui.available`.

**The UI freezes.** Something blocks the UI thread – move network calls and long work into `ctx.spawn`.

**Theron doesn't start because of a plugin.** Start it with `--no-plugins` (macOS: `open -a Theron --args --no-plugins`;
or `THERON_NO_PLUGINS=1`) and switch the plugin off in Settings → Plugins. A plugin that crashed Theron while loading is
switched off automatically at the next start.
