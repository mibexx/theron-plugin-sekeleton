"""Template for another service – copy this file, fill in the TODOs and use it in ``register``:

    from .integrations.template import ServiceAdapter
    sync = TaskListSync(ctx, ServiceAdapter(ctx))

Typical candidates: Jira (issues of a project / JQL), GitHub Issues (a repository), Linear, Asana, a ticket system.
Add the settings it needs (URL, token, project …) to plugin.toml.
"""

from __future__ import annotations

from .adapter import Adapter, RemoteItem


class ServiceAdapter(Adapter):
    name = "service"                       # TODO: a short unique name, e.g. "jira"

    def configured(self) -> bool:
        # TODO: the settings this service needs
        return bool(self.ctx.settings.get("service_url") and self.ctx.settings.get("service_token"))

    def _headers(self) -> dict:
        # TODO: how the service authenticates (Bearer token, Basic auth …)
        return {"Authorization": f"Bearer {self.ctx.settings.get('service_token')}"}

    async def test(self) -> str:
        # TODO: an endpoint that tells who you are
        resp = await self.ctx.http.get(f"{self.ctx.settings.get('service_url')}/me", headers=self._headers())
        return resp.raise_for_status().json().get("name", "?")

    async def fetch(self) -> list[RemoteItem]:
        # TODO: list the items to sync and map their status to Theron's (open, in_progress, done …)
        resp = await self.ctx.http.get(f"{self.ctx.settings.get('service_url')}/items", headers=self._headers())
        return [RemoteItem(id=str(x["id"]), title=x["title"], description=x.get("body", ""),
                           status="done" if x.get("state") == "closed" else "open", group=x.get("milestone") or "")
                for x in resp.raise_for_status().json()]

    async def create(self, title: str, description: str, status: str, group: str) -> RemoteItem:
        # TODO: create an item
        resp = await self.ctx.http.post(f"{self.ctx.settings.get('service_url')}/items", headers=self._headers(),
                                        json={"title": title, "body": description})
        x = resp.raise_for_status().json()
        return RemoteItem(id=str(x["id"]), title=title, description=description, status=status, group=group)

    async def update(self, item_id: str, title: str, description: str, status: str) -> None:
        # TODO: update an item (title, description, status)
        resp = await self.ctx.http.patch(f"{self.ctx.settings.get('service_url')}/items/{item_id}",
                                         headers=self._headers(),
                                         json={"title": title, "body": description,
                                               "state": "closed" if status in ("done", "closed") else "open"})
        resp.raise_for_status()
