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
import re
import sys
import tempfile
import time
import types
from dataclasses import dataclass, field
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
    outputs: list = field(default_factory=list)   # named outputs: where the process goes on


def norm_ports(raw) -> list[dict]:
    """Like Theron: ["a", "b"] or [{"id", "label"}] → [{"id", "label"}] (unique ids of letters, digits, - and _)."""
    if isinstance(raw, (str, dict)) or not isinstance(raw, (list, tuple)):
        raise PluginError("ports: a list")
    out, seen = [], set()
    for p in raw:
        p = {"id": p} if isinstance(p, str) else dict(p)
        if not re.match(r"^[A-Za-z0-9_-]{1,40}$", str(p.get("id") or "")) or p["id"] in seen:
            raise PluginError(f"ports: bad or doubled id {p.get('id')!r}")
        seen.add(p["id"])
        out.append({"id": p["id"], "label": str(p.get("label") or p["id"])})
    return out


def node_ports(spec: dict, config: dict) -> dict:
    """The ports a registered node has for ``config`` – as Theron's editor works them out."""
    def resolve(value):
        if value is None or value in ("success_failure", "success"):
            return []
        return norm_ports(value(config) if callable(value) else value)
    return {"inputs": resolve(spec.get("inputs")), "outputs": resolve(spec.get("outputs", "success_failure"))}


class FakeNodeRun:
    def __init__(self, ctx, config, handovers, task="", instructions="", project=None, tasklist_id=None,
                 inputs=None, outputs=None):
        self.ctx = ctx
        self.config = config
        if inputs:   # named inputs: {"code": [hand-overs], "docs": [...]} – handovers are all of them together
            handovers = [dict(h, input=k) for k, hs in inputs.items() for h in hs]
        self.handovers = [{"from": h.get("from", "Agent"), "text": h.get("text", ""), "verdict": h.get("verdict", "success")}
                          for h in handovers]
        self.inputs = {k: [{"from": h.get("from", "Agent"), "text": h.get("text", ""),
                            "verdict": h.get("verdict", "success")} for h in hs] for k, hs in (inputs or {}).items()}
        self.outputs = outputs or []
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

    def route(self, output, text="", tasklist_id=None):
        chosen = [output] if isinstance(output, str) else list(output)
        known = [o["id"] for o in self.outputs]
        if not chosen or any(o not in known for o in chosen):
            raise PluginError(f"route: unknown output {chosen} (outputs: {', '.join(known) or '–'})")
        return NodeResult(True, text, tasklist_id, chosen)


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
        self.emitted: list[dict] = []

    def on(self, name, fn=None, *, include_own=False):
        def add(f):
            self.listeners.append((name, f))
            return f
        return add(fn) if fn is not None else add

    def emit(self, name, payload=None):
        if not name.startswith(self._ctx.id + "."):
            raise PluginError(f"a plugin's own events start with '{self._ctx.id}.'")
        self.emitted.append({**(payload or {}), "name": name, "source": self._ctx.source})


class FakeHook:
    def __init__(self, name, context, data, source="theron"):
        self.name, self.context, self.data, self.source = name, context, data, source
        self.handled_by: list[str] = []
        self.stopped = False

    def stop(self):
        self.stopped = True


class _Hooks:
    """Like Theron's ctx.hooks; ``await ctx.run_hook(name, data, context)`` runs the handlers as Theron would."""

    def __init__(self, ctx):
        self._ctx = ctx
        self.handlers: list[tuple[str, Callable, float | None]] = []

    def on(self, name, fn=None, *, timeout=None):
        def add(f):
            self.handlers.append((name, f, timeout))
            return f
        return add(fn) if fn is not None else add

    async def call(self, name, data, context=None):
        if not name.startswith(self._ctx.id + "."):
            raise PluginError(f"a plugin's own hooks start with '{self._ctx.id}.'")
        return await self._ctx.run_hook(name, data, context, source=self._ctx.source)


class _Ui:
    def __init__(self, ctx):
        self._ctx = ctx
        self.available = False          # set True in a test to register pages (needs PySide6)
        self.pages: list[dict] = []
        self.settings_factory = None
        self.opened: list[str] = []
        self.panels: list[dict] = []
        self.windows: dict[str, dict] = {}
        self.actions: list[dict] = []
        self.form_buttons: list[dict] = []
        self.answers: list = []
        self.dialogs: list[tuple] = []
        self.chat: dict[str, str] = {}
        self.refreshed = 0

    def add_page(self, title, factory, *, icon="", id=""):
        self.pages.append({"title": title, "factory": factory, "icon": icon, "id": id or title})

    def add_panel(self, page, title, factory, *, id="", icon="", area="right", order=0, collapsed=False):
        pages = (page,) if isinstance(page, str) else tuple(page)
        known = ("cockpit", "theron", "projects", "processes", "agents", "tasks", "databases")
        for p in pages:
            if p != "*" and p not in known and "/" not in p:
                raise PluginError(f"unknown page '{p}'")
        if area not in ("right", "bottom"):
            raise PluginError("area must be right or bottom")
        self.panels.append({"pages": pages, "title": title, "factory": factory, "id": id or title, "icon": icon,
                            "area": area, "order": order, "collapsed": collapsed})

    def add_action(self, page, label, run, *, id="", icon="", tooltip="", style="ghost", place="top"):
        if place not in ("top", "chat", "new", "lists", "items", "sidebar"):
            raise PluginError(f"unknown place '{place}'")
        if style not in ("ghost", "primary", "danger"):
            raise PluginError("style must be ghost, primary or danger")
        pages = (page,) if isinstance(page, str) else tuple(page)
        self.actions.append({"pages": pages, "label": label, "run": run, "id": id or str(label), "icon": icon,
                             "tooltip": tooltip, "style": style, "place": place})

    def action(self, id):
        """Test helper: the registered action ``id``."""
        return next(a for a in self.actions if a["id"] == id)

    def label_of(self, id, **context):
        """Test helper: the text the button shows for ``context`` (None = hidden)."""
        a = self.action(id)
        return a["label"](dict(context)) if callable(a["label"]) else a["label"]

    def click(self, id, **context):
        """Test helper: click the button ``id`` with what the page shows."""
        return self.action(id)["run"](dict(context))

    def refresh_actions(self):
        self.refreshed += 1

    def add_form_button(self, form, label, run, *, id="", icon="", tooltip="", style="ghost"):
        if form not in ("agent", "process", "project"):
            raise PluginError(f"unknown form '{form}'")
        self.form_buttons.append({"form": form, "label": label, "run": run, "id": id or str(label), "icon": icon,
                                  "tooltip": tooltip, "style": style})

    # dialogs: put the answers your test wants in ``answers`` (popped in order); ``dialogs`` records what was asked
    def ask_text(self, title, text, default=""):
        self.dialogs.append(("text", title, text))
        return self.answers.pop(0) if self.answers else None

    def ask_choice(self, title, text, options):
        self.dialogs.append(("choice", title, text, list(options)))
        return self.answers.pop(0) if self.answers else None

    def message(self, title, text, level="info"):
        self.dialogs.append(("message", title, text, level))

    def chat_input(self, page="cockpit"):
        return self.chat.get(page, "")

    def set_chat_input(self, text, page="cockpit", append=False):
        self.chat[page] = (self.chat.get(page, "").rstrip() + "\n" + text).strip() if append else text

    def open_window(self, title, factory, *, id="", width=560, height=440):
        self.windows[id or title] = {"title": title, "factory": factory, "size": (width, height)}

    def close_window(self, id):
        self.windows.pop(id, None)

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


class _Library:
    """In-memory processes / agents with the methods of ctx.processes / ctx.agents."""

    def __init__(self, kind):
        self.kind = kind
        self.items: dict[int, dict] = {}
        self._next = 100

    def list(self):
        return [{"id": d["id"], "name": d["name"]} for d in self.items.values()]

    def get(self, entity_id):
        return json.loads(json.dumps(self.items[entity_id])) if entity_id in self.items else None

    def find(self, name):
        return next((self.get(i) for i, d in self.items.items() if d["name"].lower() == name.strip().lower()), None)

    def _add(self, doc):
        if not str(doc.get("name") or "").strip():
            raise PluginError(f"a {self.kind} needs a name")
        self._next += 1
        self.items[self._next] = {**json.loads(json.dumps(doc)), "id": self._next}
        return self._next

    def update(self, entity_id, **fields):
        if entity_id not in self.items:
            raise PluginError(f"{self.kind} {entity_id} doesn't exist")
        self.items[entity_id].update({k: v for k, v in fields.items() if k != "id"})
        return self.get(entity_id)

    def delete(self, entity_id):
        if entity_id not in self.items:
            raise PluginError(f"{self.kind} {entity_id} doesn't exist")
        del self.items[entity_id]


class _Processes(_Library):
    def __init__(self):
        super().__init__("process")

    def create(self, data):
        return self._add({"steps": [], **data})

    def create_from_draft(self, draft):
        return self._add({"name": draft.get("name", "Draft"), "draft": draft, "steps": draft.get("steps", [])}), []

    def to_draft(self, entity_id):
        d = self.get(entity_id)
        return d.get("draft") if d else None

    def problems(self, data):
        return []


class _Agents(_Library):
    def __init__(self):
        super().__init__("agent")

    def create(self, name, task, rules="", **fields):
        if self.find(name):
            raise PluginError(f"an agent named '{name}' exists already")
        return self._add({"name": name, "task": task, "rules": rules, **fields})


class _Fields:
    """Plugin fields in Theron's forms – values per (kind, id) in memory."""

    def __init__(self):
        self.specs: list[dict] = []
        self.values: dict[tuple[str, int], dict] = {}

    def add(self, form, key, *, label, type="text", default=None, options=None, description=""):
        if form not in ("agent", "process", "project"):
            raise PluginError(f"unknown form '{form}'")
        if type not in ("text", "textarea", "number", "bool", "choice"):
            raise PluginError(f"unknown field type '{type}'")
        if type == "choice" and not options:
            raise PluginError("a choice field needs options")
        self.specs.append({"form": form, "key": key, "label": label, "type": type, "default": default,
                           "options": list(options or []), "description": description})

    def all(self, kind, entity_id):
        out = {f["key"]: f["default"] if f["default"] is not None else {"number": 0, "bool": False}.get(f["type"], "")
               for f in self.specs if f["form"] == kind}
        return {**out, **self.values.get((kind, entity_id), {})}

    def get(self, kind, entity_id, key, default=None):
        return self.all(kind, entity_id).get(key, default)

    def set(self, kind, entity_id, key, value):
        json.dumps(value)
        self.values.setdefault((kind, entity_id), {})[key] = value


class FakeForm:
    """What a form button's ``run(form)`` gets in Theron – for tests of form buttons."""

    def __init__(self, ctx, kind="agent", id=None, values=None):
        self.ctx, self.kind, self.id = ctx, kind, id
        self._values = dict(values or {})
        self.fields: dict = {}
        self.saved = self.reloaded = 0

    @property
    def data(self):
        return dict(self._values) if self.id else None

    def values(self):
        return {**self._values, "plugin_fields": {self.ctx.id: dict(self.fields)}}

    def get(self, key, default=None):
        return self.fields.get(key, default)

    def set(self, key, value):
        self.fields[key] = value

    def save(self):
        self.saved += 1
        return self.id or 1

    def reload(self):
        self.reloaded += 1


class FakeView:
    """What a panel's / window's factory gets in Theron (``view``) – for tests of panel code."""

    def __init__(self, ctx, page="cockpit", context=None):
        self.ctx, self.page, self.id, self.title = ctx, page, "", ""
        self.context = dict(context or {"page": page})
        self.visible = True
        self._listeners = []

    def on_context(self, fn):
        self._listeners.append(fn)
        return fn

    def set_title(self, text):
        self.title = text

    def set_visible(self, visible):
        self.visible = bool(visible)

    def show(self, **context):
        """Test helper: the page now shows ``context`` – calls the on_context callbacks."""
        self.context = {"page": self.page, **context}
        for fn in list(self._listeners):
            fn(dict(self.context))


class _Watch:
    def __init__(self, runs, entry):
        self._runs, self._entry = runs, entry

    def cancel(self):
        if self._entry in self._runs.watchers:
            self._runs.watchers.remove(self._entry)


class _Runs:
    """Fake tasks: put runs, workers and log events in and let your code read and react to them.

        ctx.runs.add_run(17, title="Shop", status="running")
        ctx.runs.add_worker(17, "dev", "Developer", status_note="Tests laufen")
        await ctx.runs.feed({"run_id": 17, "type": "agent_tool", "agent": "Developer", "summary": "Bash: pytest"})
    """

    def __init__(self):
        self.started: list[dict] = []
        self.runs: dict[int, dict] = {}
        self.worker_list: list[dict] = []
        self.event_log: list[dict] = []
        self.watchers: list[tuple] = []
        self.answers: list[tuple[int, str]] = []
        self.messages: list[tuple[int, str]] = []
        self.stopped: list[tuple[int, bool]] = []
        self.resets: list[tuple[int, str]] = []
        self.worker_answers: dict[str, str] = {}

    # ---- test helpers
    def add_run(self, run_id, title="", status="running", project_id=1, question=None, steps=None):
        self.runs[run_id] = {"id": run_id, "project_id": project_id, "title": title, "status": status,
                             "summary": "", "goal_reached": None, "tasklist_id": None, "parent_run": None,
                             "question": question, "steps": list(steps or [])}
        return run_id

    def add_worker(self, run_id, step_id, agent, status_note="", activity="", **extra):
        w = {"key": step_id, "run_id": run_id, "step_id": step_id, "step": 0, "agent": agent,
             "engine": "Claude Code · sonnet", "started": time.time(), "member": False, "status_note": status_note,
             "activity": activity, **extra}
        self.worker_list.append(w)
        return w

    async def feed(self, event: dict):
        """A new log event: stored for events()/log() and handed to every matching watch."""
        ev = {"id": len(self.event_log) + 1, "ts": time.time(), **event}
        self.event_log.append(ev)
        for fn, run_id, types, agent in list(self.watchers):
            if (run_id is None or ev.get("run_id") == run_id) and (not types or ev.get("type") in types) \
                    and (not agent or ev.get("agent") == agent):
                await _call(fn, {**ev, "line": f"{ev.get('agent', '')} {ev.get('type')}"})
        return ev

    # ---- the API
    def start(self, project_id, text, title="", process_id=None):
        self.started.append({"project_id": project_id, "text": text, "title": title})
        return len(self.started)

    def get(self, run_id):
        r = self.runs.get(run_id)
        return {k: v for k, v in r.items() if k not in ("question", "steps")} if r else None

    def list(self, project_id=None):
        return [self.get(i) for i, r in self.runs.items() if project_id in (None, r["project_id"])]

    def active(self, project_id=None):
        return [r for r in self.list(project_id) if r["status"] in ("running", "waiting_input")]

    def state(self, run_id):
        r = self.runs.get(run_id)
        if not r:
            return None
        return {**self.get(run_id), "phase": "", "process": "", "project": "", "question": r["question"],
                "agent_calls": 0, "cost_usd": 0.0, "steps": r["steps"], "workers": self.workers(run_id)}

    def workers(self, run_id=None):
        return [dict(w) for w in self.worker_list if run_id in (None, w["run_id"])]

    def events(self, run_id, since=0, types=None, limit=200):
        return [dict(e) for e in self.event_log if e.get("run_id") == run_id and e["id"] > since
                and (not types or e["type"] in types)][:limit]

    def log(self, run_id, last=100, agent=None):
        return [f"{e.get('agent', '')} {e['type']}" for e in self.event_log
                if e.get("run_id") == run_id and (not agent or e.get("agent") == agent)][-last:]

    def watch(self, fn, *, run_id=None, types=None, agent=None):
        entry = (fn, run_id, list(types or []), agent)
        self.watchers.append(entry)
        return _Watch(self, entry)

    async def ask_worker(self, run_id, key, question, timeout=120):
        if not any(w["run_id"] == run_id and key in (w["key"], w["step_id"]) for w in self.worker_list):
            raise PluginError(f"no agent works on {run_id}/{key} right now")
        return self.worker_answers.get(key, "")

    def message(self, run_id, text):
        self.messages.append((run_id, text))

    def answer(self, run_id, text):
        if not (self.runs.get(run_id) or {}).get("question"):
            raise PluginError(f"run {run_id} has no open question")
        self.answers.append((run_id, text))

    def stop(self, run_id, soon=False):
        self.stopped.append((run_id, soon))

    def reset(self, run_id, step_id):
        self.resets.append((run_id, step_id))


@dataclass
class AgentResult:
    text: str = ""
    session_id: str = "fake-session"
    cost_usd: float = 0.0
    is_error: bool = False


class _Session:
    def __init__(self, ai, system, model):
        self._ai, self.system, self.model = ai, system, model
        self.history: list[tuple[str, str]] = []

    async def send(self, text):
        answer = await self._ai.ask(text, self.system, self.model)
        self.history += [("user", text), ("assistant", answer)]
        return answer

    def reset(self):
        self.history = []


class _Ai:
    def __init__(self):
        self.answer: Callable[[str, str, str], str] = lambda prompt, system, model: "YES – fake answer"
        self.agent_answer: Callable[[str, dict], str] = lambda prompt, options: "agent done"
        self.prompts: list[str] = []
        self.agents: list[dict] = []

    async def ask(self, prompt, system="", model="haiku"):
        self.prompts.append(prompt)
        return self.answer(prompt, system, model)

    def session(self, system="", model="sonnet"):
        return _Session(self, system, model)

    async def agent(self, prompt, *, cwd=None, system="", model="", tools=None, max_turns=30, session_id="",
                    on_text=None):
        options = {"cwd": cwd, "system": system, "model": model, "tools": tools, "session_id": session_id}
        self.agents.append({"prompt": prompt, **options})
        return AgentResult(text=self.agent_answer(prompt, options))


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
        self.hooks = _Hooks(self)
        self.fields = _Fields()
        self.processes = _Processes()
        self.agents = _Agents()
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
        ports = node_ports(spec, cfg)
        unknown = set(kw.get("inputs") or {}) - {i["id"] for i in ports["inputs"]}
        if unknown:
            raise PluginError(f"{kind} has no input(s) {sorted(unknown)}")
        node = FakeNodeRun(self, cfg, handovers or [], outputs=ports["outputs"], **kw)
        result = await _call(spec["run"], node)
        if isinstance(result, dict):
            out = result.get("output", result.get("outputs")) or []
            result = NodeResult(bool(result.get("ok", True)), str(result.get("text", "")), result.get("tasklist_id"),
                                [out] if isinstance(out, str) else list(out))
        if isinstance(result, NodeResult):
            if ports["outputs"] and result.ok and not result.outputs:
                raise PluginError(f"{kind} has named outputs – return node.route(...)")
            return result
        return NodeResult(True, "" if result is None else str(result))

    def node_ports(self, kind: str, config: dict | None = None) -> dict:
        """The ports of a registered node for ``config`` – {"inputs": [...], "outputs": [...]}."""
        spec = self.nodes.items[kind]
        cfg = {f["key"]: f.get("default") for f in spec.get("fields") or []}
        cfg.update(config or {})
        return node_ports(spec, cfg)

    async def run_hook(self, name: str, data: dict, context: dict | None = None, source: str = "theron") -> dict:
        """Run this plugin's handlers of a hook like Theron does and return the data they leave."""
        import copy
        data = copy.deepcopy(data)
        hook = FakeHook(name, copy.deepcopy(context or {}), data, source)
        for hname, fn, timeout in self.hooks.handlers:
            if hname != name or hook.stopped:
                continue
            hook.data = copy.deepcopy(data)
            returned = await _call(fn, hook)
            data = returned if isinstance(returned, dict) else hook.data
        return data

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
