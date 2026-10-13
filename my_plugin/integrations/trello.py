"""Trello: cards of one board ↔ requirements, lists ↔ epics / statuses.

Settings: trello_key, trello_token (https://trello.com/power-ups/admin → your power-up → API key → token),
trello_board (the id in the board URL). A card's list decides its status: a list named like "Done" → done,
"Doing" / "In progress" → in_progress, everything else → open.
"""

from __future__ import annotations

from .adapter import Adapter, RemoteItem

API = "https://api.trello.com/1"
DONE_WORDS = ("done", "erledigt", "fertig", "closed")
DOING_WORDS = ("doing", "progress", "in arbeit", "review")


def status_of(list_name: str, closed: bool = False) -> str:
    low = (list_name or "").lower()
    if closed or any(w in low for w in DONE_WORDS):
        return "done"
    if any(w in low for w in DOING_WORDS):
        return "in_progress"
    return "open"


class TrelloAdapter(Adapter):
    name = "trello"

    def _auth(self) -> dict:
        return {"key": self.ctx.settings.get("trello_key"), "token": self.ctx.settings.get("trello_token")}

    def configured(self) -> bool:
        return all(self.ctx.settings.get(k) for k in ("trello_key", "trello_token", "trello_board"))

    async def _get(self, path: str, **params):
        resp = await self.ctx.http.get(f"{API}{path}", params={**self._auth(), **params})
        return resp.raise_for_status().json()

    async def test(self) -> str:
        me = await self._get("/members/me", fields="fullName,username")
        return me.get("fullName") or me.get("username") or "?"

    async def _lists(self) -> list[dict]:
        return await self._get(f"/boards/{self.ctx.settings.get('trello_board')}/lists", fields="name")

    async def fetch(self) -> list[RemoteItem]:
        board = self.ctx.settings.get("trello_board")
        lists = {x["id"]: x["name"] for x in await self._lists()}
        cards = await self._get(f"/boards/{board}/cards", fields="name,desc,idList,closed,shortUrl")
        return [RemoteItem(id=c["id"], title=c["name"], description=c.get("desc", ""),
                           status=status_of(lists.get(c["idList"], ""), c.get("closed", False)),
                           group=lists.get(c["idList"], ""), url=c.get("shortUrl", ""))
                for c in cards]

    async def _list_for(self, status: str, group: str = "") -> str:
        lists = await self._lists()
        if not lists:
            raise RuntimeError("the board has no lists")
        if status in ("done", "closed", "skipped"):
            hit = next((x for x in lists if status_of(x["name"]) == "done"), None)
        elif status == "in_progress":
            hit = next((x for x in lists if status_of(x["name"]) == "in_progress"), None)
        else:
            hit = next((x for x in lists if x["name"] == group), None) \
                or next((x for x in lists if status_of(x["name"]) == "open"), None)
        return (hit or lists[0])["id"]

    async def create(self, title: str, description: str, status: str, group: str) -> RemoteItem:
        resp = await self.ctx.http.post(f"{API}/cards", params={
            **self._auth(), "idList": await self._list_for(status, group), "name": title, "desc": description})
        card = resp.raise_for_status().json()
        return RemoteItem(id=card["id"], title=card["name"], description=card.get("desc", ""), status=status,
                          group=group, url=card.get("shortUrl", ""))

    async def update(self, item_id: str, title: str, description: str, status: str) -> None:
        resp = await self.ctx.http.put(f"{API}/cards/{item_id}", params={
            **self._auth(), "name": title, "desc": description, "idList": await self._list_for(status)})
        resp.raise_for_status()
