"""Hooks – stepping into what Theron does. Theron waits for the handlers (in the plugin order the user set) and takes
over what they change in ``hook.data``. ``hook.context`` says what it is about (run, project, process, step, agent …).

The three examples below are switched on by settings (plugin.toml): a WhatsApp message when a process moves from one
node to the next, a base prompt for everything the AI designs, and questions answered by Claude.
Reference: docs/hooks.md
"""

from __future__ import annotations

import json


def register(ctx):
    # ------------------------------------------------------------------ 1. WhatsApp on every node change
    # node.transition is an event (a notification): nothing to change, Theron doesn't wait for it.
    @ctx.events.on("node.transition")
    async def whatsapp(event):
        to = ctx.settings.get("whatsapp_to")
        if not to or not ctx.settings.get("twilio_sid"):
            return
        src, dst = event["from"], event["to"]
        who = f" ({dst['agent']})" if dst.get("agent") else ""
        text = f"Theron · {event['context']['run']['title']}: {src['name']} → {dst['name']}{who}"
        # placeholder: Twilio's WhatsApp API – replace with the messaging service you use
        resp = await ctx.http.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{ctx.settings['twilio_sid']}/Messages.json",
            data={"From": f"whatsapp:{ctx.settings.get('whatsapp_from')}", "To": f"whatsapp:{to}", "Body": text},
            headers={"Authorization": basic_auth(ctx.settings["twilio_sid"], ctx.settings.get("twilio_token") or "")})
        if not resp.ok:
            ctx.log.error(f"WhatsApp: HTTP {resp.status} {resp.text[:200]}")

    # ------------------------------------------------------------------ 2. a base prompt for AI designs
    @ctx.hooks.on("process.design.before")
    def process_base_prompt(hook):
        base = ctx.settings.get("design_base_prompt")
        if base:
            hook.data["system_prompt"] = f"{hook.data['system_prompt']}\n\nHOUSE RULES OF THE USER:\n{base}"

    @ctx.hooks.on("agent.design.before")
    def agent_base_prompt(hook):
        base = ctx.settings.get("design_base_prompt")
        if base:
            hook.data["system_prompt"] = f"{hook.data['system_prompt']}\n\nHOUSE RULES OF THE USER:\n{base}"

    # ------------------------------------------------------------------ 3. let Claude answer questions
    # hitl.question: Theron waits – set hook.data["answer"] and the question is answered without the user.
    @ctx.hooks.on("hitl.question", timeout=180)
    async def ai_answers(hook):
        if not ctx.settings.get("auto_answer"):
            return
        d = hook.data
        prompt = (f"Process: {hook.context['process']['name']} · task: {hook.context['run']['title']}\n\n"
                  f"Question: {d['question']}\nOptions: {json.dumps(d['options'], ensure_ascii=False)}\n\n"
                  f"Background:\n{(d.get('details') or '')[-8000:]}\n\n"
                  'Reply ONLY with JSON: {"answer": "<one of the options, word for word – or your own short answer>", '
                  '"confident": true|false}')
        reply = await ctx.ai.ask(prompt, system="You decide on behalf of a careful project lead.", model="sonnet")
        try:
            data = json.loads(reply[reply.index("{"): reply.rindex("}") + 1])
        except ValueError:
            return
        if data.get("confident") and str(data.get("answer") or "").strip():   # unsure: the user decides
            d["answer"] = str(data["answer"]).strip()
            ctx.log(f"answered “{d['question'][:80]}” with “{d['answer']}”")


def basic_auth(user: str, password: str) -> str:
    import base64
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
