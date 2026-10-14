"""Everything the plugin registers – and the nodes and tools doing their job (no Theron needed)."""
import asyncio


def test_registers_nodes_tools_jobs_and_events(ctx):
    assert set(ctx.nodes.items) == {"summarize", "check", "trello-import", "route", "merge", "ask-chat"}
    assert set(ctx.tools.items) == {"list_tasklists", "add_requirement"}
    assert ctx.jobs and ctx.jobs[0]["every"] == 5 * 60
    assert {name for name, _ in ctx.events.listeners} == {"run.finished", "requirement.saved", "settings.changed",
                                                         "node.transition"}
    assert {name for name, _, _ in ctx.hooks.handlers} == {"process.design.before", "agent.design.before", "hitl.question"}


def test_summarize_and_check_nodes(ctx):
    ctx.ai.answer = lambda prompt, system, model: "- short"
    result = asyncio.run(ctx.run_node("summarize", handovers=[{"text": "a long report"}]))
    assert result.ok and result.text == "- short" and "a long report" in ctx.ai.prompts[-1]
    ctx.ai.answer = lambda prompt, system, model: "NO – there is no price"
    result = asyncio.run(ctx.run_node("check", config={"rule": "contains a price"}, handovers=[{"text": "x"}]))
    assert not result.ok and "no price" in result.text


def test_router_outputs_follow_its_settings(ctx):
    ports = ctx.node_ports("route", {"routes": "Bug\nQuestion"})
    assert [o["label"] for o in ports["outputs"]] == ["Bug", "Question", "Other"]
    ctx.ai.answer = lambda prompt, system, model: "2"
    result = asyncio.run(ctx.run_node("route", config={"routes": "Bug\nQuestion"}, handovers=[{"text": "how do I…?"}]))
    assert result.outputs == ["r1"] and "Question" in result.text
    ctx.ai.answer = lambda prompt, system, model: "0"
    assert asyncio.run(ctx.run_node("route", handovers=[{"text": "?"}])).outputs == ["other"]


def test_merge_combines_its_two_inputs(ctx):
    assert [i["id"] for i in ctx.node_ports("merge")["inputs"]] == ["code", "docs"]
    result = asyncio.run(ctx.run_node("merge", inputs={"code": [{"text": "def f(): …"}], "docs": [{"text": "f does x"}]}))
    assert result.ok and "def f()" in result.text and "f does x" in result.text


def test_agent_tools(ctx):
    tid = ctx.tasklists.create(1, "Backlog")
    assert "Backlog" in asyncio.run(ctx.call_tool("list_tasklists", {}))
    assert "added" in asyncio.run(ctx.call_tool("add_requirement", {"tasklist_id": tid, "title": "Fix the footer"}))
    assert ctx.tasklists.get(tid)["epics"][0]["requirements"][0]["title"] == "Fix the footer"


def test_notification_when_a_task_finishes(ctx):
    asyncio.run(ctx.emit("run.finished", {"title": "Relaunch", "status": "done", "goal_reached": True}))
    assert ctx.notifications == [("info", "Task “Relaunch” finished: ✔ goal reached")]


def test_german_texts(ctx):
    from devkit import FakeContext
    from tests.conftest import ROOT
    de = FakeContext.from_plugin(ROOT, language="de")
    assert de.tr("Sync now") == "Jetzt synchronisieren"
