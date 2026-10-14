# Theron Plugin Documentation

The complete reference of Theron's plugin interface – **plugin API v1** (`theron_api = 1`, Theron 0.14.0 and newer; panels, windows, buttons, form fields and `ctx.runs` reading need 0.16.0; the chat (`ctx.chat`, `node.ask`, `node.say`), settings buttons and dynamic node fields need 0.17.0).

| Document | What's in it |
|---|---|
| [**Manual**](manual.md) | **Step by step: pages, nodes, windows on pages, buttons and forms, task lists, events, own events, transactions, running agents and logs, the chat** |
| [Getting started](getting-started.md) | From zero to an installed plugin in five minutes |
| [Concepts & lifecycle](lifecycle.md) | How Theron finds, loads, starts and stops plugins; hosts; restarts; failures |
| [plugin.toml](manifest.md) | Every field of the manifest, settings types, permissions, compatibility |
| [The context `ctx`](context.md) | The complete API reference – every attribute and method |
| [Process nodes](nodes.md) | `ctx.nodes.register`, the `node` object, results, fields, outputs, the AI designer |
| [Pages & settings UI](ui.md) | Navigation pages, panels and windows, buttons on pages, form fields and buttons, dialogs, settings pages, threads, Theron's styles |
| [Hooks](hooks.md) | Stepping into Theron's flow: every hook, its context and what can be changed; plugin order |
| [Events](events.md) | Every event with its payload, sources, delivery rules; a plugin's own events |
| [Data shapes](data.md) | Projects, task lists, epics, requirements, processes (and the draft format), agents, runs |
| [Tools for agents](tools.md) | `ctx.tools.register`, parameter schemas, naming |
| [Integrations & sync](integrations.md) | The sync engine of this skeleton, adapters, HTTP, storage, schedules |
| [Packaging, signing & installing](packaging.md) | The `.theronplugin` format, `.theronignore`, signatures, all ways to install |
| [Security](security.md) | What plugins can do, what Theron checks, recommendations |
| [Testing with the devkit](testing.md) | Testing a plugin without Theron |
| [Troubleshooting](troubleshooting.md) | Logs, safe mode, common errors |

The user-facing documentation lives on the website: [theron.mibexx.de/docs-plugins.html](https://theron.mibexx.de/docs-plugins.html).

## Stability promise

Everything documented here is part of plugin API v1 and stays compatible as long as a Theron release supports API 1.
Anything not documented – Theron's internal modules, the database, private attributes starting with `_` – may change
in any release. Never import from `theron.*`; use `ctx`.

## Conventions in this reference

- `async` methods must be awaited: `text = await ctx.ai.ask(...)`.
- *Callback* means a function you pass to Theron. It may be `async def` or a plain `def`. Plain functions run in a
  worker thread, so they may block (file I/O, a synchronous HTTP library …).
- Ids of projects, task lists, epics, requirements and runs are integers.
- “Raises `PluginError`” refers to Theron's `PluginError` (a `RuntimeError`) – catch `RuntimeError` or `Exception`.
