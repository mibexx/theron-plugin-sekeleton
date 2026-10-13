# Tools for agents

A plugin can give every Claude agent additional tools – an agent writing code can create a ticket, look up a
customer in your CRM, post to a channel.

```python
async def create_card(args):
    card = await trello.create(args["title"], args.get("description", ""))
    return f"Card created: {card['shortUrl']}"

ctx.tools.register(
    "create_card",
    description="Create a card on the team's Trello board. Use it for follow-up work you can't do yourself.",
    params={"title": "string", "description": {"type": "string", "optional": True}},
    run=create_card)
```

## How agents see tools

- The tools of all plugins form one MCP server, `theron_plugins`. A tool's full name is
  `mcp__theron_plugins__<plugin id with _>__<name>`, e.g. `mcp__theron_plugins__trello_sync__create_card`.
- Every **Claude** agent (Claude Code backend) gets them in every step, allowed without asking. Agents running on
  OpenCode don't get plugin tools.
- The agent decides from `description` whether and how to use the tool – describe what it does, when to use it and
  what it returns. Mention the tool in an agent's rules or a step's instructions to make sure it is used.

## Parameters

`params` describes the arguments as JSON Schema. Three forms:

```python
# 1. name → type ("string", "number", "integer", "boolean") – all required
params={"title": "string", "priority": "integer"}

# 2. name → property schema; "optional": True = not required
params={"title": {"type": "string", "description": "short title"},
        "labels": {"type": "array", "items": {"type": "string"}, "optional": True}}

# 3. a complete object schema
params={"type": "object",
        "properties": {"title": {"type": "string"}, "due": {"type": "string", "format": "date"}},
        "required": ["title"]}
```

## `run(args)`

- receives the arguments as a `dict`,
- returns the result as text (`str`; other values are converted with `str()`, `None` becomes empty),
- may be async or plain.

If `run` raises, the agent receives `Error: <message>` (marked as an error) and the traceback goes to the plugin's log.
Keep results short and useful for a model – a summary, not a whole API response.

## Where tools run

A tool runs in the process the agent runs in: in the app, on the slave, or in a console run – `ctx.host` tells which.
`ctx.ui` may not be available there.
