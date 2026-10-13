"""The extensions of Theron's pages (extend.py) and the worker watch (monitor.py) – with the devkit's fakes."""
import asyncio
import time

from devkit import FakeForm


def test_buttons_fields_and_places(ui_ctx):
    ctx = ui_ctx
    places = {a["id"]: a["place"] for a in ctx.ui.actions}
    assert places == {"reviewer": "new", "snippet": "chat", "export-md": "top", "status": "sidebar"}
    assert [p["id"] for p in ctx.ui.panels] == ["workers", "tasklist-sync"]
    assert {f["key"] for f in ctx.fields.specs} == {"jira_user", "customer"}
    assert ctx.fields.get("project", 3, "customer") == "internal"
    # the export button only shows while a task list is selected
    assert ctx.ui.label_of("export-md") is None and ctx.ui.label_of("export-md", tasklist_id=1) == "Export Markdown"


def test_the_form_button_fills_the_field(ui_ctx):
    ctx = ui_ctx
    (button,) = ctx.ui.form_buttons
    form = FakeForm(ctx, "agent", id=7, values={"name": "Code Reviewer"})
    assert button["label"](form) == "Check Jira user" and button["label"](FakeForm(ctx, "agent")) is None
    button["run"](form)
    assert form.get("jira_user") == "bot.code.reviewer"
    button["run"](form)
    assert ctx.ui.dialogs[-1][0] == "message"


def test_the_chat_button_inserts_a_text_block(ui_ctx):
    ctx = ui_ctx
    ctx.ui.chat["cockpit"] = "Build the login."
    ctx.ui.answers = ["Write tests first"]
    ctx.ui.click("snippet", page="cockpit")
    assert ctx.ui.chat["cockpit"] == "Build the login.\nWrite the tests first, then the code."
    ctx.ui.answers = [None]                                     # cancelled: nothing changes
    ctx.ui.click("snippet", page="cockpit")
    assert ctx.ui.chat["cockpit"].count("\n") == 1


def test_export_writes_markdown(ui_ctx):
    ctx = ui_ctx
    tid = ctx.tasklists.create(1, "Backlog")
    eid = ctx.tasklists.add_epic(tid, "Login")
    ctx.tasklists.add_requirement(eid, "Form", status="done")
    ctx.ui.click("export-md", tasklist_id=tid, page="tasks")
    text = (ctx.data_dir / f"tasklist-{tid}.md").read_text()
    assert "## Login" in text and "- [x] Form" in text


def test_the_watch_notifies_on_errors_once(ctx):
    from my_plugin.monitor import WorkerWatch
    watch = WorkerWatch(ctx)
    watch.start()
    ctx.runs.add_run(17, title="Shop")
    asyncio.run(ctx.runs.feed({"run_id": 17, "type": "agent_tool", "agent": "Dev", "step": 1, "summary": "Bash: pytest"}))
    assert ctx.notifications == []
    for _ in range(2):
        asyncio.run(ctx.runs.feed({"run_id": 17, "type": "agent_text", "agent": "Dev", "step": 1,
                                   "text": "3 FAILED, 12 passed"}))
    assert len(ctx.notifications) == 1 and "Shop" in ctx.notifications[0][1]


def test_a_stuck_agent_is_asked(ctx):
    from my_plugin.monitor import WorkerWatch
    ctx.settings.set("stuck_minutes", 1)
    ctx.runs.add_run(17, title="Shop")
    ctx.runs.add_worker(17, "dev", "Developer", started=time.time() - 120)
    ctx.runs.worker_answers["dev"] = "Waiting for the build."
    watch = WorkerWatch(ctx)
    asyncio.run(watch.check_stuck())
    asyncio.run(watch.check_stuck())                            # asked once only
    assert ctx.notifications == [("info", "Developer: Waiting for the build.")]
