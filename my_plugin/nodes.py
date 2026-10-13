"""Process nodes – they show up in Theron's process editor under TOOLS.

``run(node)`` gets a ``node`` with:
    node.config        the values of the fields below (as set in the editor)
    node.input         everything that came in as text (hand-overs + current requirement)
    node.handovers     the hand-overs one by one: [{"from", "text", "verdict"}]
    node.task          the task of the run · node.instructions  the step's instructions
    node.project       {"id", "name", "workspace"} · node.run_id · node.tasklist_id (a list that came in)
    node.progress(t)   status line on the node's card
and returns ``node.success(text, tasklist_id=None)`` (✔) or ``node.failure(text)`` (✖) – or just a string (✔).

Nodes like a switch have NAMED outputs (``outputs=[...]`` or ``outputs=lambda config: [...]`` – worked out from the
node's settings, the editor updates the ports when they change) and return ``node.route("output id", text)``.
Named inputs (``inputs=[...]``, ``wait="all" | "any"``) arrive per input in ``node.inputs``.
"""


def register(ctx, sync):
    # --- a node with one output (✔): asks the AI model, uses the user's Claude subscription
    async def summarize(node):
        node.progress("summarizing …")
        words = int(node.config.get("max_words") or 120)
        text = await ctx.ai.ask(
            f"Summarize in at most {words} words, style: {node.config.get('style')}.\n\n{node.input}",
            system="You write precise summaries.", model="haiku")
        return node.success(text)

    ctx.nodes.register(
        "summarize", label=ctx.tr("Summarize"), icon="✎", run=summarize, outputs="success",
        description=ctx.tr("Condenses the incoming hand-overs into a short summary."),
        ai_hint="Use to condense long results before a decision or a message",
        fields=[{"key": "max_words", "type": "number", "label": ctx.tr("Maximum words"), "default": 120},
                {"key": "style", "type": "choice", "label": ctx.tr("Style"), "options": ["bullet points", "prose"],
                 "default": "bullet points"}])

    # --- a node with two outputs (✔ / ✖) – a check the process can branch on
    async def check(node):
        rule = node.config.get("rule") or node.instructions
        answer = await ctx.ai.ask(f"Rule: {rule}\n\nInput:\n{node.input}\n\nAnswer YES or NO, then one sentence why.",
                                  model="haiku")
        ok = answer.strip().upper().startswith("YES")
        return node.success(answer) if ok else node.failure(answer)

    ctx.nodes.register(
        "check", label=ctx.tr("Check"), icon="✓", run=check, outputs="success_failure",
        description=ctx.tr("Checks the hand-overs against a rule – ✔ if it holds, ✖ if not."),
        ai_hint="A yes/no gate, e.g. 'the result contains a price'",
        fields=[{"key": "rule", "type": "textarea", "label": ctx.tr("Rule")}])

    # --- a node that brings data in: the Trello board as a task list, handed on (e.g. to a loop)
    async def trello_import(node):
        node.progress("reading the board …")
        name = node.config.get("tasklist_name") or "Trello"
        report = await sync.import_into(node.project["id"], name)
        return node.success(f"Imported {report['created_local']} new and {report['updated_local']} changed cards "
                            f"into “{name}”.", tasklist_id=report["tasklist_id"])

    ctx.nodes.register(
        "trello-import", label=ctx.tr("Import from Trello"), icon="▦", run=trello_import, outputs="success_failure",
        description=ctx.tr("Reads the Trello board into a task list and hands it on (e.g. to a loop)."),
        ai_hint="Start of a process that works through Trello cards",
        fields=[{"key": "tasklist_name", "type": "text", "label": ctx.tr("Task list name"), "default": "Trello"}])

    # --- a switch: one output per line of the "routes" field (the ports follow the setting) – the AI picks one
    def routes(config):
        names = [ln.strip() for ln in str(config.get("routes") or "").splitlines() if ln.strip()]
        return [{"id": f"r{k}", "label": name[:60]} for k, name in enumerate(names[:19])] + [
            {"id": "other", "label": ctx.tr("Other")}]

    async def route(node):
        options = [o for o in node.outputs if o["id"] != "other"]
        listing = "\n".join(f"{k + 1}. {o['label']}" for k, o in enumerate(options))
        answer = await ctx.ai.ask(f"Which route fits the input best? Answer with the number only, 0 if none fits.\n\n"
                                  f"Routes:\n{listing}\n\nInput:\n{node.input}", model="haiku")
        digits = "".join(ch for ch in answer if ch.isdigit())
        k = int(digits) if digits else 0
        chosen = options[k - 1] if 1 <= k <= len(options) else {"id": "other", "label": ctx.tr("Other")}
        return node.route(chosen["id"], f"→ {chosen['label']}")

    ctx.nodes.register(
        "route", label=ctx.tr("AI router"), icon="◇", run=route, outputs=routes,
        description=ctx.tr("Sends the input on via the route that fits best – one output per route."),
        ai_hint="A switch on the meaning of the input, e.g. routes 'Bug', 'Feature request', 'Question'",
        fields=[{"key": "routes", "type": "textarea", "label": ctx.tr("Routes (one per line)"),
                 "default": "Bug\nFeature request\nQuestion"}])

    # --- two named inputs: waits until both paths delivered, then combines them
    def merge(node):
        code = "\n\n".join(h["text"] for h in node.inputs.get("code", []))
        docs = "\n\n".join(h["text"] for h in node.inputs.get("docs", []))
        return node.success(f"## Code\n{code or '–'}\n\n## Documentation\n{docs or '–'}")

    ctx.nodes.register(
        "merge", label=ctx.tr("Merge code & docs"), icon="⋈", run=merge, outputs="success",
        inputs=[{"id": "code", "label": ctx.tr("Code")}, {"id": "docs", "label": ctx.tr("Docs")}], wait="all",
        description=ctx.tr("Waits for both inputs and hands on one combined report."),
        ai_hint="Joins a code path and a documentation path into one report")
