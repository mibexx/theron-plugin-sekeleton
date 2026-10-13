"""The hook examples (my_plugin/hooks.py) against the devkit."""
import asyncio
import json


def test_base_prompt_goes_into_ai_designs(ctx):
    ctx.settings.update({"design_base_prompt": "Always add a reviewer."})
    data = asyncio.run(ctx.run_hook("process.design.before", {"request": "a shop", "system_prompt": "SYS", "prompt": None}))
    assert data["system_prompt"].endswith("Always add a reviewer.")
    data = asyncio.run(ctx.run_hook("agent.design.before", {"request": "x", "system_prompt": "SYS", "prompt": None}))
    assert "HOUSE RULES" in data["system_prompt"]


def test_claude_answers_a_question_when_sure(ctx):
    ctx.settings.update({"auto_answer": True})
    hook = {"question": "Deploy now?", "options": ["Yes", "No"], "recommended": 0, "details": "all tests green",
            "answer": None}
    context = {"process": {"name": "Release"}, "run": {"title": "v2"}}
    ctx.ai.answer = lambda prompt, system, model: json.dumps({"answer": "Yes", "confident": True})
    assert asyncio.run(ctx.run_hook("hitl.question", dict(hook), context))["answer"] == "Yes"
    ctx.ai.answer = lambda prompt, system, model: json.dumps({"answer": "No", "confident": False})
    assert asyncio.run(ctx.run_hook("hitl.question", dict(hook), context))["answer"] is None   # unsure: the user decides


def test_whatsapp_on_node_change(ctx):
    ctx.settings.update({"whatsapp_to": "+491701234567", "whatsapp_from": "+14155238886", "twilio_sid": "AC1",
                         "twilio_token": "t"})
    ctx.http.route("POST", "/Messages.json", {"sid": "SM1"}, status=201)
    asyncio.run(ctx.emit("node.transition", {
        "from": {"id": "s1", "name": "Developer", "type": "agent", "agent": "Developer"},
        "to": {"id": "s2", "name": "Reviewer", "type": "agent", "agent": "Reviewer"},
        "context": {"run": {"title": "Shop"}}}))
    body = ctx.http.requests[-1]["data"]["Body"]
    assert body == "Theron · Shop: Developer → Reviewer (Reviewer)"
