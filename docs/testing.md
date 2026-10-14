# Testing with the devkit

[`devkit/fake_theron.py`](../devkit/fake_theron.py) is a stand-in for Theron's plugin API: a `ctx` that keeps
everything in memory, with a fake HTTP client and a fake AI. Your plugin runs against it exactly as it registers in
Theron – no Theron installation, no restart.

```bash
pip install pytest
python -m pytest
```

## Setup

```python
from pathlib import Path
from devkit import FakeContext, load_plugin

ROOT = Path(__file__).resolve().parent.parent

def make():
    ctx = FakeContext.from_plugin(ROOT)       # id, name, version, setting defaults from plugin.toml
    module = load_plugin(ctx, ROOT)           # import the package as Theron does, call register(ctx)
    return ctx, module
```

`FakeContext.from_plugin(root, language="en")` – `language="de"` loads `i18n/de.json` for `ctx.tr`.
[`tests/conftest.py`](../tests/conftest.py) has ready fixtures (`ctx`, and `trello` with a fake board).

## What the fake offers

| Member | Fake behaviour | Test helpers |
|---|---|---|
| `ctx.settings` | dict with the manifest's defaults | `ctx.settings.update({...})` to configure |
| `ctx.storage` | dict | `ctx.storage.data` |
| `ctx.nodes` / `ctx.tools` | registries | `ctx.nodes.items`, `ctx.tools.items`; `await ctx.run_node(kind, config=, handovers=, task=, instructions=, project=, tasklist_id=)`, `await ctx.call_tool(name, args)` |
| `ctx.events` | listener list | `await ctx.emit(name, payload)` – delivers like Theron (source `"app"`) |
| `ctx.schedule`, `on_start`, `on_stop` | recorded | `ctx.jobs`, `await ctx.run_jobs()`, `ctx.started`, `ctx.stopped` |
| `ctx.spawn` | runs immediately | |
| `ctx.tasklists` | in-memory store with the same shapes | `ctx.tasklists.projects_` (one project, id 1); `await ctx.tasklists.app_updates_requirement(id, **fields)` – a change made in Theron, fires `requirement.saved` |
| `ctx.runs` | records `start()` | `ctx.runs.started` |
| `ctx.ai` | returns `ctx.ai.answer(prompt, system, model)` | set `ctx.ai.answer = lambda p, s, m: "…"`; `ctx.ai.prompts` |
| `ctx.http` | `FakeHttp` – answers from routes | `ctx.http.route("GET", "/cards", data_or_fn, status=200)`; `ctx.http.requests` |
| `ctx.ui` | `available = False`, records pages | set `ctx.ui.available = True` before `load_plugin` to test page registration (needs PySide6) |
| `ctx.chat` *(0.17)* | registries | `ctx.chat.render(kind, data)` → the block's HTML; `ctx.chat.format(text)` → the text with your formats; `await ctx.chat.click(href or name, **params)`; `ctx.chat.refreshed` (count); `ctx.chat.messages` (every `node.say`) |
| `node.ask` / `node.say` *(0.17)* | answers from `ctx.chat.answers` (a list, one by one, or `fn(question, options)`) | after `run_node`: `ctx.last_node.asked`, `ctx.last_node.said`, `ctx.last_node.progress_log` |
| `ctx.settings.add_button` *(0.17)* | recorded | `await ctx.settings.press("Test", values={...})` → what the button returns |
| node fields *(0.17)* | | `ctx.field_options(kind, key, config)` (a function is asked), `ctx.field_visible(kind, key, config)` (`show_if`), `await ctx.press_field_button(kind, key, button, config)` → (label before, result, label after) *(0.18)* |
| `ctx.log`, `ctx.notify` | recorded | `ctx.log.lines`, `ctx.notifications` |

## Examples

```python
import asyncio

def test_check_node(ctx):
    ctx.ai.answer = lambda prompt, system, model: "NO – no price in the text"
    result = asyncio.run(ctx.run_node("check", config={"rule": "contains a price"}, handovers=[{"text": "Hello"}]))
    assert not result.ok

def test_import(ctx):
    ctx.http.route("GET", "/lists", [{"id": "L1", "name": "To do"}])
    ctx.http.route("GET", "/cards", [{"id": "C1", "name": "Login", "desc": "", "idList": "L1", "closed": False}])
    ctx.settings.update({"trello_key": "k", "trello_token": "t", "trello_board": "B"})
    result = asyncio.run(ctx.run_node("trello-import"))
    assert result.ok and ctx.tasklists.get(result.tasklist_id)["epics"][0]["name"] == "To do"
```

A route answers when the method matches and its text is part of the URL; `data_or_fn` is the JSON answer or a function
`fn(request) -> answer` getting `{"method", "url", "params", "headers", "json", "data"}`.

## Limits of the fake

The devkit models what plugins rely on, not all of Theron: no real processes, no orchestrator, events only when you
emit them, no threads for `ctx.ui.call`. Before a release, install the packed plugin in Theron and try it once for real
– ideally in a separate data folder:

```bash
THERON_DATA=/tmp/theron-test theron plugin install dist/my-plugin-0.1.0.theronplugin --yes
THERON_DATA=/tmp/theron-test theron --listen 127.0.0.1:7599     # a slave – logs the plugin loading to the console
```
