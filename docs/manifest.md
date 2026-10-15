# plugin.toml

The manifest is a [TOML](https://toml.io) file in the plugin's root folder. Theron reads it before any code runs.

```toml
id = "trello-sync"
name = "Trello Sync"
version = "1.2.0"
description = "Syncs task lists with a Trello board."
author = "Ada Lovelace"
homepage = "https://github.com/ada/trello-sync"
license = "MIT"
theron_api = 1
min_theron = "0.14.0"
entry = "trello_sync"
permissions = ["network", "tasklists"]

[[settings]]
key = "api_key"
type = "secret"
label = "API key"
description = "From trello.com/power-ups/admin"
required = true
```

## Fields

| Field | Required | Type | Meaning |
|---|---|---|---|
| `id` | ✔ | text | Unique id: lower-case letters, digits and `-`, 2–41 characters, starting with a letter or digit (`^[a-z0-9][a-z0-9-]{1,40}$`). Used for folders, storage keys, tool names and node ids – don't change it after release. |
| `version` | ✔ | text | The plugin's version, e.g. `1.2.0`. |
| `name` | | text | Display name (default: the id), max. 80 characters. |
| `description` | | text | One or two sentences, shown before installing and in Settings → Plugins. |
| `author`, `homepage`, `license` | | text | Shown in the install dialog / `theron plugin info`. |
| `theron_api` | | integer | Plugin API version the plugin is written for. Default `1`. |
| `min_theron` | | text | The oldest Theron version it runs on, e.g. `"0.14.0"`. |
| `entry` | | text | Name of the Python package (folder with `__init__.py`) that contains `register(ctx)`. Default: the id with `-` replaced by `_`. Must be a valid Python identifier. |
| `permissions` | | list | What the plugin uses – see below. |
| `[[settings]]` | | tables | The plugin's settings – see below. |

Unknown fields are ignored.

## Permissions

Shown to the user before installing (`theron plugin info` lists them, too). They are **information, not a sandbox** –
see [Security](security.md). Unknown names are an error.

| Name | Declare it when the plugin … |
|---|---|
| `network` | talks to services on the internet (`ctx.http` or any other client) |
| `tasklists` | reads or changes task lists, epics, requirements (`ctx.tasklists`) |
| `processes` | reads, creates, changes or deletes processes (`ctx.processes`) |
| `agents` | reads, creates, changes or deletes agents (`ctx.agents`) |
| `runs` | starts tasks or reads their results (`ctx.runs`) |
| `agent-tools` | gives agents tools (`ctx.tools`) |
| `hooks` | steps into Theron's flow (`ctx.hooks`): prompts, results, questions, AI drafts |
| `ui` | adds pages or windows (`ctx.ui`) |
| `files` | reads or writes files outside `ctx.data_dir` |
| `ai` | asks the AI model (`ctx.ai`) – this uses the user's Claude subscription |

## Settings

Each `[[settings]]` table declares one setting. They appear, in this order, in the plugin's settings dialog
(Settings → Plugins → Settings …), are stored by Theron and read with `ctx.settings`.

| Key | Required | Meaning |
|---|---|---|
| `key` | ✔ | Name used in code: letters, digits, `_`, `.`, `-`, starting with a letter or `_`. Unique within the plugin. |
| `type` | | One of the types below. Default `text`. |
| `label` | | Label in the dialog (default: the key). Translated with the plugin's `i18n` files. |
| `description` | | Hint below the field. Translated. |
| `default` | | Value before the user changes it. |
| `required` | | `true` marks it with `*`; Settings → Plugins lists missing required settings. Theron doesn't block anything – check `ctx.settings.missing()` or the value yourself. |
| `options` | for `choice` | The values to choose from – plain values (shown as they are) or tables `{value = "docker", label = "Load via Docker"}` (the label is shown and translated; 0.20). |

| Type | Input | Value in `ctx.settings` | Empty value |
|---|---|---|---|
| `text` | one line | `str` | `""` |
| `secret` | one line, hidden | `str` | `""` |
| `textarea` | several lines | `str` | `""` |
| `number` | spin box (whole numbers; decimals if the default has decimals) | `int` or `float` | `0` |
| `bool` | check box | `bool` | `False` |
| `choice` | drop-down of `options` | the chosen option (`str`) | `""` |
| `tasklist` | drop-down of the user's task lists (“Project · List”) | task list id (`int`) or `None` | `None` |
| `project` | drop-down of the user's projects | project id (`int`) or `None` | `None` |

Secrets are stored in Theron's settings database on the user's machine like Theron's own tokens – not encrypted.

## Files next to plugin.toml

| Path | Meaning |
|---|---|
| `<entry>/__init__.py` | the package with `register(ctx)` (required) |
| `lib/` | pure-Python dependencies, added to the import path (shared by all plugins – prefer unique package names) |
| `i18n/<language>.json` | translations: `{"English text": "Übersetzung"}` for `ctx.tr` and the manifest's labels/descriptions; languages: `de`, `en` |
| `.theronignore` | files that stay out of the package – see [Packaging](packaging.md) |
| `SIGNATURE.json` | written by signing – see [Packaging](packaging.md) |
