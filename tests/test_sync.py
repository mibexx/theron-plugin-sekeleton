"""The two-way task-list sync against a fake Trello board."""
import asyncio


def sync_of(ctx):
    from tests.conftest import ROOT  # noqa: F401
    return ctx.module.__dict__["TaskListSync"](ctx, ctx.module.__dict__["TrelloAdapter"](ctx))


def test_first_sync_imports_cards_and_pushes_requirements(ctx, trello):
    tid = ctx.settings["sync_tasklist"]
    epic = ctx.tasklists.add_epic(tid, "To do")
    ctx.tasklists.add_requirement(epic, "Newsletter", "double opt-in")
    report = asyncio.run(sync_of(ctx).run())
    assert report["created_local"] == 2 and report["created_remote"] == 1
    tl = ctx.tasklists.get(tid)
    reqs = {r["title"]: r for e in tl["epics"] for r in e["requirements"]}
    assert reqs["Login page"]["status"] == "open" and reqs["Imprint"]["status"] == "done"
    assert {e["name"] for e in tl["epics"]} == {"To do", "Done"}
    assert any(c["name"] == "Newsletter" and c["idList"] == "L1" for c in trello["cards"])


def test_changes_flow_both_ways_and_nothing_is_doubled(ctx, trello):
    sync = sync_of(ctx)
    asyncio.run(sync.run())
    tid = ctx.settings["sync_tasklist"]
    login = next(r for e in ctx.tasklists.get(tid)["epics"] for r in e["requirements"] if r["title"] == "Login page")
    trello["cards"][0]["idList"] = "L2"                                  # moved to Doing in Trello
    report = asyncio.run(sync.run())
    assert ctx.tasklists.requirement(login["id"])["status"] == "in_progress" and report["created_local"] == 0
    asyncio.run(ctx.tasklists.app_updates_requirement(login["id"], status="done"))   # done in Theron → pushed
    assert trello["cards"][0]["idList"] == "L3"
    assert asyncio.run(sync.run()) == {"created_local": 0, "updated_local": 0, "created_remote": 0,
                                       "updated_remote": 0, "tasklist_id": tid}


def test_import_node_hands_a_task_list_on(ctx, trello):
    result = asyncio.run(ctx.run_node("trello-import", config={"tasklist_name": "Board"}))
    assert result.ok and result.tasklist_id and ctx.tasklists.get(result.tasklist_id)["name"] == "Board"


def test_the_sync_stays_off_until_configured(ctx):
    assert asyncio.run(ctx.jobs[0]["fn"]()) is None and ctx.http.requests == []
