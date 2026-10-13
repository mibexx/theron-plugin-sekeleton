"""A stand-in ``ctx`` that behaves like Theron's plugin API v1 – in memory, for tests.

    ctx = FakeContext.from_plugin(ROOT)            # settings defaults from plugin.toml, i18n from i18n/
    load_plugin(ctx, ROOT)                         # imports the package and calls register(ctx)
    result = await ctx.run_node("summarize", config={…}, handovers=[…])
    await ctx.emit("requirement.saved", {"id": 3, …})

Only the behaviour plugins rely on is modelled; the real API is documented at
https://theron.mibexx.de/docs-plugins.html#en-pl-api
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

STATUSES = ("open", "in_progress", "hitl", "done", "failed", "skipped", "closed")


class PluginError(RuntimeError):
    pass


async def _call(fn, *args):
    if inspect.iscoroutinefunction(fn):
        return await fn(*args)
    result = await asyncio.to_thread(fn, *args)
    return await result if inspect.isawaitable(result) else result


@dataclass
class NodeResult:
    ok: bool
    text: str = ""
    tasklist_id: int | None = None


class FakeNodeRun:
    def __init__(self, ctx, config, handovers, task="", instructions="", project=None, tasklist_id=None):
        self.ctx = ctx
        self.config = config
        self.handovers = [{"from": h.get("from", "Agent"), "text": h.get("text", ""), "verdict": h.get("verdict", "success")}
                          for h in handovers]
        self.input = "\n\n".join(f"## {h['from']}\n{h['text']}" for h in self.handovers)
        self.task = task
        self.instructions = instructions
        self.project = project or {"id": 1, "name": "Project", "workspace": tempfile.gettempdir()}
        self.run_id = 1
        self.step_name = "step"
        self.tasklist_id = tasklist_id
        self.progress_log: list[str] = []

    def progress(self, text):
        self.progress_log.append(text)

    def success(self, text="", tasklist_id=None):
        return NodeResult(True, text, tasklist_id)

    def failure(self, text):
        return NodeResult(False, text)


class FakeResponse:
    def __init__(self, status: int, body: Any, url: str = ""):
        self.status, self.url = status, url
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {}

    @property
    def ok(self):
        return 200 <= self.status < 300

    @property
    def text(self):
        return self.content.decode()

    def json(self):
        return json.loads(self.content or b"null")

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status} {self.url}")
        return self


class FakeHttp:
    """``ctx.http`` that answers from routes: ``http.route("GET", "/boards/", lambda req: [...])`` – the first route
    whose method matches and whose text is part of the URL answers. Every request is kept in ``requests``."""

    def __init__(self):
        self.routes: list[tuple[str, str, Callable]] = []
        self.requests: list[dict] = []

    def route(self, method: str, part: str, answer: Callable | Any, status: int = 200):
        self.routes.append((method.upper(), part, answer if callable(answer) else (lambda req, a=answer: a), status))

    async def request(self, method, url, *, params=None, headers=None, json=None, data=None, timeout=None):
        req = {"method": method.upper(), "url": url, "params": dict(params or {}), "headers": headers or {},
               "json": json, "data": data}
        self.requests.append(req)
        for m, part, answer, status in self.routes:
            if m == req["method"] and part in url:
                return FakeResponse(status, answer(req), url)
        return FakeResponse(404, {"error": "no route"}, url)

    async def get(self, url, **kw):
        return await self.request("GET", url, **kw)

    async def post(self, url, **kw):
        return await self.request("POST", url, **kw)

    async def put(self, url, **kw):
        return await self.request("PUT", url, **kw)

    async def patch(self, url, **kw):
        return await self.request("PATCH", url, **kw)

    async def delete(self, url, **kw):
        return await self.request("DELETE", url, **kw)


class _Settings:
    def __init__(self, ctx, values):
        self._ctx, self._values = ctx, values

    def all(self):
        return dict(self._values)

    def get(self, key, default=None):
        value = self._values.get(key)
        return default if value in (None, "") and default is not None else value

    def __getitem__(self, key):
        return self._values.get(key)

    def __contains__(self, key):
        return key in self._values

    def set(self, key, value):
        self.update({key: value})

    def update(self, values):
        self._values.update(values)
        self._ctx._fire("settings.changed", {"name": "settings.changed", "keys": sorted(values)})

    def missing(self):
        return []

    def on_change(self, fn):
        self._ctx.events.on("settings.changed", fn)
        return fn


class _Storage:
    def __init__(self):
        self.data: dict[str, Any] = {}

    def get(self, key, default=None):
        return json.loads(json.dumps(self.data[key])) if key in self.data else default

    def set(self, key, value):
        self.data[key] = json.loads(json.dumps(value))

    def delete(self, key):
        self.data.pop(key, None)

    def items(self, prefix=""):
        return sorted((k, v) for k, v in self.data.items() if k.startswith(prefix))

    def keys(self, prefix=""):
        return [k for k, _ in self.items(prefix)]


class _Registry:
    def __init__(self, ctx):
        self._ctx = ctx
        self.items: dict[str, dict] = {}

    def register(self, kind_or_name, **kw):
        self.items[kind_or_name] = kw
        return kw


class _Events:
    def __init__(self, ctx):
        self._ctx = ctx
        self.listeners: list[tuple[str, Callable]] = []

    def on(self, name, fn=None, *, include_own=False):
        def add(f):
            self.listeners.append((name, f))
            return f
        return add(fn) if fn is not None else add


class _Ui:
    def __init__(self, ctx):
        self._ctx = ctx
        self.available = False          # set True in a test to register pages (needs PySide6)
        self.pages: list[dict] = []
        self.settings_factory = None
        self.opened: list[str] = []

    def add_page(self, title, factory, *, icon="", id=""):
        self.pages.append({"title": title, "factory": factory, "icon": icon})

    def settings_page(self, factory):
        self.settings_factory = factory

    def call(self, fn, *args):
        fn(*args)

    def open_url(self, url):
        self.opened.append(url)


class _Tasklists:
    """In memory, with the same methods and dict shapes as Theron's ctx.tasklists."""

    def __init__(self, ctx):
        self._ctx = ctx
        self.projects_ = [{"id": 1, "name": "Project", "workspace": tempfile.gettempdir()}]
        self.lists: dict[int, dict] = {}
        self.epics: dict[int, dict] = {}
        self.reqs: dict[int, dict] = {}
        self._next = 1

    def _id(self):
        self._next += 1
        return self._next

    def projects(self):
        return [dict(p) for p in self.projects_]

    def list(self, project_id=None):
        return [dict(t) for t in self.lists.values() if project_id in (None, t["project_id"])]

    def get(self, tasklist_id):
        tl = self.lists.get(tasklist_id)
        if tl is None:
            return None
        epics = [{**e, "requirements": [dict(r) for r in self.reqs.values() if r["epic_id"] == e["id"]]}
                 for e in self.epics.values() if e["tasklist_id"] == tasklist_id]
        return {**tl, "temporary": False, "epics": epics}

    def find(self, project_id, name):
        return next((dict(t) for t in self.lists.values()
                     if t["project_id"] == project_id and t["name"].lower() == name.strip().lower()), None)

    def epic(self, epic_id):
        return dict(self.epics[epic_id]) if epic_id in self.epics else None

    def requirement(self, requirement_id):
        return dict(self.reqs[requirement_id]) if requirement_id in self.reqs else None

    def create(self, project_id, name, description=""):
        tid = self._id()
        self.lists[tid] = {"id": tid, "project_id": project_id, "name": name, "description": description,
                           "process_id": None, "template": False}
        return tid

    def update(self, tasklist_id, **fields):
        self.lists[tasklist_id].update({k: v for k, v in fields.items() if k in ("name", "description", "process_id")})
        return dict(self.lists[tasklist_id])

    def delete(self, tasklist_id):
        self.lists.pop(tasklist_id, None)

    def add_epic(self, tasklist_id, name, description="", depends_on=None):
        if tasklist_id not in self.lists:
            raise PluginError(f"task list {tasklist_id} doesn't exist")
        eid = self._id()
        self.epics[eid] = {"id": eid, "tasklist_id": tasklist_id, "name": name, "description": description,
                           "status": "open", "closed": False, "depends_on": list(depends_on or []), "order": eid}
        return eid

    def update_epic(self, epic_id, **fields):
        self.epics[epic_id].update(fields)
        return dict(self.epics[epic_id])

    def delete_epic(self, epic_id):
        self.epics.pop(epic_id, None)

    def add_requirement(self, epic_id, title, description="", acceptance="", status="open", depends_on=None):
        if epic_id not in self.epics:
            raise PluginError(f"epic {epic_id} doesn't exist")
        if status not in STATUSES:
            raise PluginError(f"status '{status}'")
        rid = self._id()
        self.reqs[rid] = {"id": rid, "epic_id": epic_id, "title": title, "description": description,
                          "acceptance": acceptance, "tech_rules": "", "status": status, "result": "",
                          "depends_on": list(depends_on or []), "order": rid}
        return rid

    def update_requirement(self, requirement_id, **fields):
        if "status" in fields and fields["status"] not in STATUSES:
            raise PluginError(f"status '{fields['status']}'")
        self.reqs[requirement_id].update(fields)
        return dict(self.reqs[requirement_id])

    def delete_requirement(self, requirement_id):
        self.reqs.pop(requirement_id, None)

    # --- test helper: a change made in Theron (not by the plugin) – fires requirement.saved
    async def app_updates_requirement(self, requirement_id, **fields):
        self.reqs[requirement_id].update(fields)
        await self._ctx.emit("requirement.saved", {"id": requirement_id, "data": dict(self.reqs[requirement_id])})


class _Runs:
    def __init__(self):
        self.started: list[dict] = []

    def start(self, project_id, text, title="", process_id=None):
        self.started.append({"project_id": project_id, "text": text, "title": title})
        return len(self.started)

    def get(self, run_id):
        return None

    def list(self, project_id=None):
        return []

    def message(self, run_id, text):
        pass


class _Ai:
    def __init__(self):
        self.answer: Callable[[str, str, str], str] = lambda prompt, system, model: "YES – fake answer"
        self.prompts: list[str] = []

    async def ask(self, prompt, system="", model="haiku"):
        self.prompts.append(prompt)
        return self.answer(prompt, system, model)


class _Log:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, text):
        self.lines.append(str(text))

    def error(self, text):
        self.lines.append(f"ERROR {text}")

    def exception(self, text=""):
        self.lines.append(f"ERROR {text}")


class FakeContext:
    def __init__(self, plugin_id="my-plugin", settings=None, root: Path | None = None, language="en"):
        self.id = plugin_id
        self.name = plugin_id
        self.version = "0.0.0"
        self.dir = Path(root) if root else Path.cwd()
        self.host = "desktop"
        self.language = language
        self.theron_version = "0.14.0"
        self.api_version = 1
        self.source = f"plugin:{plugin_id}"
        self.settings = _Settings(self, dict(settings or {}))
        self.storage = _Storage()
        self.nodes = _Registry(self)
        self.tools = _Registry(self)
        self.events = _Events(self)
        self.ui = _Ui(self)
        self.tasklists = _Tasklists(self)
        self.runs = _Runs()
        self.ai = _Ai()
        self.http = FakeHttp()
        self.log = _Log()
        self.notifications: list[tuple[str, str]] = []
        self.jobs: list[dict] = []
        self.started: list[Callable] = []
        self.stopped: list[Callable] = []
        self._catalog: dict[str, str] = {}
        self.data_dir = Path(tempfile.mkdtemp(prefix=f"{plugin_id}-"))

    @classmethod
    def from_plugin(cls, root: Path, language: str = "en") -> "FakeContext":
        """Id, name, version and setting defaults from the plugin's plugin.toml; texts from i18n/<language>.json."""
        root = Path(root)
        data = tomllib.loads((root / "plugin.toml").read_text(encoding="utf-8"))
        ctx = cls(data["id"], {s["key"]: s.get("default") for s in data.get("settings", [])}, root, language)
        ctx.name, ctx.version = data.get("name", data["id"]), data["version"]
        path = root / "i18n" / f"{language}.json"
        if language != "en" and path.is_file():
            ctx._catalog = json.loads(path.read_text(encoding="utf-8"))
        return ctx

    def tr(self, text, **kwargs):
        text = self._catalog.get(text, text)
        return text.format(**kwargs) if kwargs else text

    def notify(self, text, level="info"):
        self.notifications.append((level, text))

    def schedule(self, every, fn, *, first=None):
        job = {"every": every, "fn": fn, "first": every if first is None else first}
        self.jobs.append(job)
        return job

    def on_start(self, fn):
        self.started.append(fn)
        return fn

    def on_stop(self, fn):
        self.stopped.append(fn)
        return fn

    def spawn(self, fn, *args):
        import concurrent.futures
        future = concurrent.futures.Future()
        try:
            future.set_result(asyncio.run(_call(fn, *args)))
        except Exception as exc:  # noqa: BLE001
            future.set_exception(exc)
        return future

    # ---------------------------------------------------------------- test helpers
    async def emit(self, name: str, event: dict) -> None:
        """Deliver an event like Theron does (source "app")."""
        for ev_name, fn in list(self.events.listeners):
            if ev_name in (name, "*"):
                await _call(fn, {"name": name, "source": "app", **event})

    def _fire(self, name, event):
        for ev_name, fn in list(self.events.listeners):
            if ev_name in (name, "*") and not inspect.iscoroutinefunction(fn):
                fn(event)

    async def run_node(self, kind: str, config: dict | None = None, handovers: list[dict] | None = None,
                       **kw) -> NodeResult:
        """Run a registered node like a process would (field defaults + config)."""
        spec = self.nodes.items[kind]
        cfg = {f["key"]: f.get("default") for f in spec.get("fields") or []}
        cfg.update(config or {})
        node = FakeNodeRun(self, cfg, handovers or [], **kw)
        result = await _call(spec["run"], node)
        if isinstance(result, NodeResult):
            return result
        return NodeResult(True, "" if result is None else str(result))

    async def call_tool(self, name: str, args: dict) -> str:
        return str(await _call(self.tools.items[name]["run"], args))

    async def run_jobs(self) -> None:
        """Run every scheduled job once."""
        for job in self.jobs:
            await _call(job["fn"])


def load_plugin(ctx: FakeContext, root: Path, entry: str | None = None):
    """Import the plugin's package (as Theron does: a module of its own, relative imports work) and call
    register(ctx). Returns the module."""
    root = Path(root)
    if entry is None:
        entry = tomllib.loads((root / "plugin.toml").read_text(encoding="utf-8")).get("entry") or ctx.id.replace("-", "_")
    lib = root / "lib"
    if lib.is_dir() and str(lib) not in sys.path:
        sys.path.append(str(lib))
    if "theron_plugins_test" not in sys.modules:   # the parent package, as Theron's "theron_plugins"
        parent = types.ModuleType("theron_plugins_test")
        parent.__path__ = []
        sys.modules["theron_plugins_test"] = parent
    name = f"theron_plugins_test.{entry}"
    spec = importlib.util.spec_from_file_location(name, root / entry / "__init__.py",
                                                  submodule_search_locations=[str(root / entry)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.register(ctx)
    return module
