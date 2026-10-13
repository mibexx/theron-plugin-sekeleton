"""Two-way sync between a Theron task list and a service (through an Adapter).

    service item  ↔  requirement      (the mapping lives in ctx.storage: "<adapter>:item:<id>" → requirement id)
    item group    ↔  epic             (created when missing)

Each side's last synced state is stored as a fingerprint. A side that changed since then wins; if both changed,
``prefer`` decides ("theron" or "service"). Deleting is never synced – a deleted item or requirement only drops the
mapping, so nothing disappears by accident.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time

from .adapter import Adapter, RemoteItem


def fingerprint(title: str, description: str, status: str) -> str:
    return hashlib.sha1(json.dumps([title or "", description or "", status or ""]).encode()).hexdigest()


class TaskListSync:
    prefer = "theron"

    def __init__(self, ctx, adapter: Adapter):
        self.ctx = ctx
        self.adapter = adapter
        self.lock = asyncio.Lock()
        self.last = {"time": None, "report": None, "error": ""}

    # ------------------------------------------------------------ settings
    @property
    def direction(self) -> str:
        return self.ctx.settings.get("sync_direction") or "both"

    def tasklist_id(self) -> int | None:
        value = self.ctx.settings.get("sync_tasklist")
        return int(value) if value else None

    def configured(self) -> bool:
        return self.adapter.configured() and self.tasklist_id() is not None

    # ------------------------------------------------------------ storage keys
    def _item_key(self, item_id: str) -> str:
        return f"{self.adapter.name}:item:{item_id}"

    def _req_key(self, req_id: int) -> str:
        return f"{self.adapter.name}:req:{req_id}"

    def _remember(self, item_id: str, req_id: int, theron_fp: str, service_fp: str) -> None:
        self.ctx.storage.set(self._item_key(item_id), {"req": req_id, "theron": theron_fp, "service": service_fp})
        self.ctx.storage.set(self._req_key(req_id), item_id)

    def _forget(self, item_id: str, req_id: int | None) -> None:
        self.ctx.storage.delete(self._item_key(item_id))
        if req_id is not None:
            self.ctx.storage.delete(self._req_key(req_id))

    # ------------------------------------------------------------ entry points
    async def run_if_configured(self) -> dict | None:
        """The scheduled sync (``ctx.schedule``): quietly off until the settings are complete."""
        if not self.configured():
            return None
        return await self.run()

    async def run(self, tasklist_id: int | None = None) -> dict:
        """One full sync in both directions (as the settings allow)."""
        async with self.lock:
            report = {"created_local": 0, "updated_local": 0, "created_remote": 0, "updated_remote": 0,
                      "tasklist_id": tasklist_id or self.tasklist_id()}
            try:
                tid = report["tasklist_id"]
                if tid is None or self.ctx.tasklists.get(tid) is None:
                    raise RuntimeError("no task list chosen in the settings")
                items = await self.adapter.fetch()
                if self.direction in ("both", "service-to-theron"):
                    await self._pull(tid, items, report)
                if self.direction in ("both", "theron-to-service"):
                    await self._push(tid, {i.id: i for i in items}, report)
                self.last = {"time": time.time(), "report": report, "error": ""}
                self.ctx.log(f"sync: {report}")
            except Exception as exc:
                self.last = {"time": time.time(), "report": None, "error": str(exc)}
                self.ctx.log.exception("sync failed")
                raise
            return report

    async def import_into(self, project_id: int, name: str) -> dict:
        """The service into a task list of a project (found by name or created) – for the import node."""
        found = self.ctx.tasklists.find(project_id, name)
        tid = found["id"] if found else self.ctx.tasklists.create(project_id, name)
        async with self.lock:
            report = {"created_local": 0, "updated_local": 0, "created_remote": 0, "updated_remote": 0,
                      "tasklist_id": tid}
            await self._pull(tid, await self.adapter.fetch(), report)
            return report

    async def push_requirement(self, req_id: int) -> None:
        """A requirement changed in Theron: send just this one (event ``requirement.saved``)."""
        if not self.configured() or self.direction == "service-to-theron":
            return
        req = self.ctx.tasklists.requirement(req_id)
        if req is None or not self._in_synced_list(req):
            return
        async with self.lock:
            item_id = self.ctx.storage.get(self._req_key(req_id))
            fp = fingerprint(req["title"], req["description"], req["status"])
            if item_id is None:
                epic = self.ctx.tasklists.epic(req["epic_id"]) or {}
                item = await self.adapter.create(req["title"], req["description"], req["status"], epic.get("name", ""))
                self._remember(item.id, req_id, fp, fingerprint(item.title, item.description, item.status))
            else:
                state = self.ctx.storage.get(self._item_key(item_id)) or {}
                if state.get("theron") != fp:
                    await self.adapter.update(item_id, req["title"], req["description"], req["status"])
                    self._remember(item_id, req_id, fp, fp)

    def _in_synced_list(self, req: dict) -> bool:
        epic = self.ctx.tasklists.epic(req["epic_id"])
        return bool(epic) and epic["tasklist_id"] == self.tasklist_id()

    # ------------------------------------------------------------ the two directions
    async def _pull(self, tid: int, items: list[RemoteItem], report: dict) -> None:
        epics = {e["name"]: e["id"] for e in self.ctx.tasklists.get(tid)["epics"]}
        for item in items:
            state = self.ctx.storage.get(self._item_key(item.id))
            service_fp = fingerprint(item.title, item.description, item.status)
            req = self.ctx.tasklists.requirement(state["req"]) if state else None
            if state and req is None:          # the requirement was deleted in Theron: let go of the item
                self._forget(item.id, state["req"])
                continue
            if req is None:                    # new on the service side
                group = item.group or "Inbox"
                if group not in epics:
                    epics[group] = self.ctx.tasklists.add_epic(tid, group)
                rid = self.ctx.tasklists.add_requirement(epics[group], item.title, item.description, status=item.status)
                self._remember(item.id, rid, service_fp, service_fp)
                report["created_local"] += 1
                continue
            theron_fp = fingerprint(req["title"], req["description"], req["status"])
            service_changed = state["service"] != service_fp
            theron_changed = state["theron"] != theron_fp
            if service_changed and (not theron_changed or self.prefer == "service"):
                self.ctx.tasklists.update_requirement(req["id"], title=item.title, description=item.description,
                                                      status=item.status)
                self._remember(item.id, req["id"], service_fp, service_fp)
                report["updated_local"] += 1

    async def _push(self, tid: int, items: dict[str, RemoteItem], report: dict) -> None:
        for epic in self.ctx.tasklists.get(tid)["epics"]:
            for req in epic["requirements"]:
                theron_fp = fingerprint(req["title"], req["description"], req["status"])
                item_id = self.ctx.storage.get(self._req_key(req["id"]))
                if item_id is None:
                    item = await self.adapter.create(req["title"], req["description"], req["status"], epic["name"])
                    self._remember(item.id, req["id"], theron_fp, fingerprint(item.title, item.description, item.status))
                    report["created_remote"] += 1
                    continue
                if item_id not in items:       # gone on the service side: let go of the requirement
                    self._forget(item_id, req["id"])
                    continue
                state = self.ctx.storage.get(self._item_key(item_id)) or {}
                if state.get("theron") != theron_fp:
                    await self.adapter.update(item_id, req["title"], req["description"], req["status"])
                    self._remember(item_id, req["id"], theron_fp, theron_fp)
                    report["updated_remote"] += 1
