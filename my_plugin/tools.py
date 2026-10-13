"""Tools for agents – every Claude agent can call them while it works, as
``mcp__theron_plugins__<plugin id with _>__<name>``. ``run(args)`` returns text for the agent."""


def register(ctx):
    def list_tasklists(args):
        project = args.get("project_id")
        lists = ctx.tasklists.list(int(project) if project else None)
        return "\n".join(f"{t['id']}: {t['name']}" for t in lists) or "no task lists"

    ctx.tools.register("list_tasklists", description="List Theron's task lists (id: name), optionally of one project",
                       params={"project_id": {"type": "integer", "description": "a project id", "optional": True}},
                       run=list_tasklists)

    async def add_requirement(args):
        tl = ctx.tasklists.get(int(args["tasklist_id"]))
        if tl is None:
            return "no such task list"
        epic = next((e for e in tl["epics"] if e["name"] == "From agents"), None)
        epic_id = epic["id"] if epic else ctx.tasklists.add_epic(tl["id"], "From agents")
        rid = ctx.tasklists.add_requirement(epic_id, args["title"], args.get("description", ""))
        return f"requirement {rid} added"

    ctx.tools.register("add_requirement", description="Add a requirement (follow-up work) to a Theron task list",
                       params={"type": "object",
                               "properties": {"tasklist_id": {"type": "integer"}, "title": {"type": "string"},
                                              "description": {"type": "string"}},
                               "required": ["tasklist_id", "title"]},
                       run=add_requirement)
