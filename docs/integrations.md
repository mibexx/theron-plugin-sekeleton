# Integrations & sync

An integration connects Theron to another service. The building blocks:

| Need | Use |
|---|---|
| call the service | [`ctx.http`](context.md#ctxhttp) (or a pure-Python client in `lib/`) |
| credentials, ids, options | `[[settings]]` in `plugin.toml` (`type = "secret"` for tokens) → `ctx.settings` |
| remember mappings, cursors | [`ctx.storage`](context.md#ctxstorage) |
| poll the service | [`ctx.schedule`](context.md#background-work) |
| react to changes in Theron | [`ctx.events`](events.md) |
| read and change task lists | [`ctx.tasklists`](context.md#ctxtasklists) |
| start work in Theron | [`ctx.runs.start`](context.md#ctxruns) |
| bring service data into a process | a [node](nodes.md) – e.g. an import node that hands a task list on |
| let agents use the service | a [tool](tools.md) |

## Patterns

**Service → Theron (polling).** A schedule fetches what changed since the last run (keep a cursor in `ctx.storage`)
and creates or updates requirements – or starts tasks:

```python
async def inbox():
    since = ctx.storage.get("cursor", 0)
    resp = await ctx.http.get(f"{URL}/tickets", params={"updated_after": since, "token": ctx.settings["token"]})
    for t in resp.raise_for_status().json():
        ctx.runs.start(ctx.settings["project"], f"Handle ticket {t['id']}: {t['subject']}\n\n{t['body']}",
                       title=f"Ticket {t['id']}")
        since = max(since, t["updated"])
    ctx.storage.set("cursor", since)

ctx.schedule(300, inbox, first=20)
```

**Theron → service (events).** React to `requirement.saved`, `run.finished` … and push:

```python
@ctx.events.on("run.finished")
async def report(e):
    await ctx.http.post(ctx.settings["webhook"], json={"text": f"{e['title']}: {e['summary']}"})
```

**Both ways (sync).** Combine both and keep a mapping – that's what this skeleton's sync engine does.

## The sync engine of this skeleton

[`my_plugin/integrations/`](../my_plugin/integrations) contains a generic two-way sync between one Theron task list
and one service:

| Theron | Service |
|---|---|
| task list (`sync_tasklist` setting) | board / project / filter |
| epic | group (Trello list, Jira epic, milestone …) |
| requirement: title, description, status | item: title, description, status |

```python
from .integrations.sync import TaskListSync
from .integrations.trello import TrelloAdapter

sync = TaskListSync(ctx, TrelloAdapter(ctx))
ctx.schedule(5 * 60, sync.run_if_configured, first=15)                     # pull + push every 5 minutes
ctx.events.on("requirement.saved", lambda e: sync.push_requirement(e["id"]))   # push a change right away
```

### How it decides

For every mapped pair the engine stores a fingerprint of both sides as they were after the last sync
(`ctx.storage`: `"<adapter>:item:<id>"` → `{"req", "theron", "service"}` and `"<adapter>:req:<id>"` → item id).

| Theron changed | Service changed | Result |
|---|---|---|
| – | – | nothing |
| ✔ | – | push to the service |
| – | ✔ | pull into Theron |
| ✔ | ✔ | `TaskListSync.prefer` decides: `"theron"` (default) or `"service"` |

New items become requirements (in the epic named after their group, created if needed); new requirements become
items. Deletions are never synced – a deleted item or requirement only drops the mapping, so nothing disappears by
accident. The `sync_direction` setting limits it to one direction.

### `TaskListSync` reference

| Member | Description |
|---|---|
| `TaskListSync(ctx, adapter)` | the engine for one adapter |
| `prefer` | class attribute: `"theron"` or `"service"` on conflicts |
| `configured()` | adapter configured and a task list chosen |
| `await run(tasklist_id=None)` | one full sync, returns `{"created_local", "updated_local", "created_remote", "updated_remote", "tasklist_id"}` |
| `await run_if_configured()` | `run()` if configured, else `None` – for schedules |
| `await import_into(project_id, name)` | pull the service into a task list of the project (found by name or created) – for an import node |
| `await push_requirement(requirement_id)` | push one requirement (if it belongs to the synced list) |
| `last` | `{"time", "report", "error"}` of the last run – e.g. for a status page |

### Writing an adapter

Subclass `Adapter` ([`adapter.py`](../my_plugin/integrations/adapter.py)); [`template.py`](../my_plugin/integrations/template.py)
is a starting point with `TODO`s, [`trello.py`](../my_plugin/integrations/trello.py) a complete example.

| Member | Description |
|---|---|
| `name` | short unique name – part of the storage keys (don't change it later) |
| `configured() -> bool` | all settings the adapter needs are there |
| `await test() -> str` | check the connection, return e.g. the account name, raise on failure |
| `await fetch() -> list[RemoteItem]` | every item that is synced |
| `await create(title, description, status, group) -> RemoteItem` | create an item for a requirement |
| `await update(item_id, title, description, status)` | bring an item up to date |

`RemoteItem(id, title, description="", status="open", group="", url="", extra={})` – `status` must already be one of
Theron's statuses (`open`, `in_progress`, `hitl`, `done`, `failed`, `skipped`, `closed`); map the service's states in
the adapter.

### Example: GitHub Issues

```python
class GitHubIssues(Adapter):
    name = "github"

    def configured(self):
        return bool(self.ctx.settings.get("gh_repo") and self.ctx.settings.get("gh_token"))

    def _headers(self):
        return {"Authorization": f"Bearer {self.ctx.settings['gh_token']}", "Accept": "application/vnd.github+json"}

    async def test(self):
        r = await self.ctx.http.get("https://api.github.com/user", headers=self._headers())
        return r.raise_for_status().json()["login"]

    async def fetch(self):
        r = await self.ctx.http.get(f"https://api.github.com/repos/{self.ctx.settings['gh_repo']}/issues",
                                    params={"state": "all", "per_page": 100}, headers=self._headers())
        return [RemoteItem(id=str(i["number"]), title=i["title"], description=i.get("body") or "",
                           status="done" if i["state"] == "closed" else "open",
                           group=(i.get("milestone") or {}).get("title", ""), url=i["html_url"])
                for i in r.raise_for_status().json() if "pull_request" not in i]

    async def create(self, title, description, status, group):
        r = await self.ctx.http.post(f"https://api.github.com/repos/{self.ctx.settings['gh_repo']}/issues",
                                     json={"title": title, "body": description}, headers=self._headers())
        i = r.raise_for_status().json()
        return RemoteItem(id=str(i["number"]), title=title, description=description, status=status, group=group)

    async def update(self, item_id, title, description, status):
        r = await self.ctx.http.patch(f"https://api.github.com/repos/{self.ctx.settings['gh_repo']}/issues/{item_id}",
                                      json={"title": title, "body": description,
                                            "state": "closed" if status in ("done", "closed", "skipped") else "open"},
                                      headers=self._headers())
        r.raise_for_status()
```

## Good practice

- **Stay quiet until configured** – check the settings before calling a service (`run_if_configured`).
- **Don't loop** – changes you make through `ctx.tasklists` don't come back as events to your plugin; don't subscribe
  with `include_own=True` in a sync.
- **Be gentle** – poll every few minutes, not seconds; respect the service's rate limits (`resp.status == 429`).
- **Keep secrets in settings** of type `secret`, never in the code or the log.
- **Show the state** – a page or the settings page with “last sync / last error” saves the user a look into the log.
