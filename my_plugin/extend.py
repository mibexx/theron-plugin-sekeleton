"""Extending Theron's own pages – one example for every place a plugin can add something.

    ctx.ui.add_action(page, label, run, place=…)   a button: "top" (a page's tool bar), "chat" (next to “Send”),
                                                   "new" (next to “+ New …”), "lists" / "items" (task-list page),
                                                   "sidebar" (Theron's sidebar)
    ctx.fields.add(form, key, …)                   a field in the form of agents, processes, projects
    ctx.ui.add_form_button(form, label, run)       a button in that form, next to “Save”
    ctx.ui.add_panel(page, title, factory)         a window next to / below a page   (see monitor.py, pages.py)
    ctx.ui.open_window(title, factory)             a window of its own                (see ui_monitor.py)

Buttons run on the UI thread: ask with ctx.ui.ask_text / ask_choice / message, start slow work with ctx.spawn and come
back with ctx.ui.call. Reference: docs/manual.md, docs/ui.md
"""

from __future__ import annotations


def register(ctx):
    # ---- a field in every agent's form: values are stored with the agent, read them with ctx.fields.get
    ctx.fields.add("agent", "jira_user", label=ctx.tr("Jira user"),
                   description=ctx.tr("The Jira account this agent's work is booked on (example)."))
    ctx.fields.add("project", "customer", label=ctx.tr("Customer"), type="choice",
                   options=["internal", "customer A", "customer B"], default="internal")
    if not ctx.ui.available:
        return

    # ---- a button in the agent form: reads and sets the plugin's field in the open form
    def check_jira(form):
        user = (form.get("jira_user") or "").strip()
        if not user:
            name = (form.values().get("name") or "agent").lower().replace(" ", ".")
            form.set("jira_user", f"bot.{name}")            # shown in the form, saved with “Save”
            return
        ctx.ui.message(ctx.tr("Jira"), ctx.tr("{user} would be checked against Jira here.", user=user))

    ctx.ui.add_form_button("agent", lambda form: ctx.tr("Check Jira user") if form.id else None, check_jira,
                           id="check-jira", icon="✓")

    # ---- a button next to “+ New agent”
    def from_template(context):
        name = ctx.ui.ask_text(ctx.tr("Agent from template"), ctx.tr("Name of the new reviewer agent:"))
        if name:
            ctx.agents.create(name, task="Review the result of the previous step against the requirement.",
                              rules="Be specific. Name file and line.")
    ctx.ui.add_action("agents", ctx.tr("Reviewer from template"), from_template, id="reviewer", place="new",
                      icon="✦")

    # ---- a button next to “Send” in the cockpit and on the THERON page: fills in a text block
    def snippet(context):
        choice = ctx.ui.ask_choice(ctx.tr("Text blocks"), ctx.tr("Which text block?"),
                                   [ctx.tr("Definition of done"), ctx.tr("Write tests first")])
        if choice:
            text = {ctx.tr("Definition of done"): "Done means: tests green, docs updated, reviewed.",
                    ctx.tr("Write tests first"): "Write the tests first, then the code."}[choice]
            ctx.ui.set_chat_input(text, page=context["page"], append=True)
    ctx.ui.add_action(["cockpit", "theron"], "¶", snippet, id="snippet", place="chat",
                      tooltip=ctx.tr("Insert a text block"))

    # ---- a button in the task-list page's tool bar – only while a list is selected (label → None hides it)
    def export(context):
        tl = ctx.tasklists.get(context["tasklist_id"])
        lines = [f"# {tl['name']}"]
        for epic in tl["epics"]:
            lines.append(f"\n## {epic['name']}")
            lines += [f"- [{'x' if r['status'] == 'done' else ' '}] {r['title']}" for r in epic["requirements"]]
        path = ctx.data_dir / f"tasklist-{tl['id']}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ctx.notify(ctx.tr("Exported to {path}", path=path))
    ctx.ui.add_action("tasks", lambda c: ctx.tr("Export Markdown") if c.get("tasklist_id") else None, export,
                      id="export-md", icon="⇩")

    # ---- a button in Theron's sidebar (one for all pages)
    def status(context):
        runs = ctx.runs.active()
        ctx.ui.message(ctx.name, ctx.tr("{n} tasks running – page: {page}", n=len(runs), page=context["page"]))
    ctx.ui.add_action("*", ctx.tr("Status"), status, id="status", place="sidebar", icon="⬢")
