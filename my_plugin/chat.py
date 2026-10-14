"""The chat – Theron only offers the hooks, the plugin decides what it shows (players, documents, diagrams …):

    ctx.chat.add_format(pattern, render)    text in ANY chat message that matches → your rich text
    ctx.chat.add_renderer(kind, render)     a block a node posts with node.say(kind=..., data=...) → your rich text
    ctx.chat.link(name, text, **params)     a clickable element in your rich text …
    ctx.chat.on_link(name, fn)              … and what a click does: fn(params)
    ctx.chat.refresh()                      draw the chats again (after a click changed what they show)

and in a node:
    await node.ask(question, options)       asks the user in the chat and waits for the answer
    node.say(text, kind=..., data=...)      a message of the node in the chat (text = fallback for the web)

Rich text is Qt's HTML subset: <b> <i> <span style> <p> <br> <table> <a href> <img src="file path">.
Escape what comes from outside (``html.escape``).
"""

import html
import re

HEX = re.compile(r"(?<![\w&])#([0-9a-fA-F]{6})\b")


def register(ctx):
    # --- 1. formatting: every #RRGGBB in a chat message gets a colour swatch
    def swatch(m):
        code = m.group(1).lower()
        return (f'<span style="background:#{code}; color:#{code};">■■</span> '
                f'<span style="font-family:monospace;">#{html.escape(code)}</span>')
    ctx.chat.add_format(HEX, swatch)

    # --- 2. a block of its own with buttons: a poll the node posts; clicks count votes
    def poll(data):
        votes = ctx.storage.get(f"votes:{data['id']}") or {}
        rows = "".join(
            f"<tr><td style='padding:2px 12px 2px 0;'>{ctx.chat.link('vote', '▲ ' + o, poll=data['id'], option=o)}"
            f"</td><td>{votes.get(o, 0)}</td></tr>" for o in data["options"])
        return f"<p><b>{html.escape(data['question'])}</b></p><table>{rows}</table>"
    ctx.chat.add_renderer("poll", poll)

    def vote(params):
        key = f"votes:{params['poll']}"
        votes = ctx.storage.get(key) or {}
        votes[params["option"]] = votes.get(params["option"], 0) + 1
        ctx.storage.set(key, votes)
        ctx.chat.refresh()   # the block shows the new count
    ctx.chat.on_link("vote", vote)

    # --- 3. a node that asks in the chat – choice options worked out from another field, a field with show_if
    def answers(config):
        return [{"value": o.strip(), "label": o.strip()} for o in (config.get("options") or "").split(",")
                if o.strip()]

    async def ask(node):
        options = [o["value"] for o in answers(node.config)]
        question = node.config.get("question") or node.instructions or ctx.tr("How shall we go on?")
        poll_id = f"{node.run_id}-{node.step_name}"
        node.say(question + "\n" + "\n".join(f"- {o}" for o in options),   # the text: the web's fallback
                 kind="poll", data={"id": poll_id, "question": question, "options": options})
        if node.config.get("mode") == "fixed":
            answer = node.config.get("answer") or (options[0] if options else "")
        else:
            answer = await node.ask(question, options)
        node.say(ctx.tr("Answer: **{answer}**", answer=answer))
        return node.success(ctx.tr("The user answered: {answer}", answer=answer))

    ctx.nodes.register(
        "ask-chat", label=ctx.tr("Ask in the chat"), icon="❓", run=ask, outputs="success",
        description=ctx.tr("Asks the user a question in the chat and hands the answer on."),
        ai_hint="Ask the user a question with fixed answers in the middle of a process",
        fields=[{"key": "question", "type": "text", "label": ctx.tr("Question")},
                {"key": "options", "type": "text", "label": ctx.tr("Answers (comma separated)"),
                 "default": "Yes, No",
                 # a button next to the field (Theron ≥ 0.18): runs with the node's current settings, the text shows
                 "buttons": [{"label": ctx.tr("Check"), "run": lambda cfg: (
                     (True, ctx.tr("{n} answers", n=len(answers(cfg)))) if len(answers(cfg)) > 1
                     else (False, ctx.tr("Give at least two answers.")))}]},
                {"key": "mode", "type": "choice", "label": ctx.tr("Mode"), "default": "ask",
                 "options": [{"value": "ask", "label": ctx.tr("Ask every time")},
                             {"value": "fixed", "label": ctx.tr("Always the same answer")}]},
                # options from a function of the node's settings – asked again whenever they change
                {"key": "answer", "type": "choice", "label": ctx.tr("Answer"), "options": answers,
                 "show_if": {"mode": "fixed"}}])

    # --- 4. a button in the plugin's settings dialog: checks what is typed there (saved or not)
    async def test_trello(values):
        key, token = values.get("trello_key"), values.get("trello_token")
        if not key or not token:
            return False, ctx.tr("Enter the Trello key and token first.")
        resp = await ctx.http.get("https://api.trello.com/1/members/me", params={"key": key, "token": token})
        if not resp.ok:
            return False, ctx.tr("Trello says: {status} {text}", status=resp.status, text=resp.text[:120])
        return True, ctx.tr("Connected as {name}", name=resp.json().get("fullName", "?"))
    ctx.settings.add_button(ctx.tr("Test Trello"), test_trello, tooltip=ctx.tr("Checks the key and the token."))
