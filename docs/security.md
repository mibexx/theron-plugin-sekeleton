# Security

## What a plugin can do

A plugin is Python code running **inside** the Theron process. Python offers no sandbox, so a plugin can do everything
Theron can: read and write the user's files, read Theron's database (projects, settings including tokens), start
processes, use the network – and use the user's Claude login. The `permissions` in `plugin.toml` are shown to the user
so they know what the plugin is meant to do; Theron does not enforce them.

That's why installing a plugin is a decision of trust, and Theron supports it:

- **Signatures** show who built a plugin and that it wasn't changed – see [Packaging](packaging.md#signing).
- **The install dialog** shows name, author, version, signature status and permissions, and requires an explicit
  “I trust this plugin” for anything not verified.
- **Invalid signatures** (changed after signing) are never installed or loaded.
- **Updates** of an installed plugin go through the same check.

## What Theron protects

- A plugin that raises while loading is switched off with its error; Theron and the other plugins keep running.
- A plugin that crashed Theron while loading is switched off at the next start.
- Exceptions in callbacks, nodes, tools and jobs are caught and logged.
- `--no-plugins` / `THERON_NO_PLUGINS=1` start Theron without any plugin.
- Packages with path tricks (absolute paths, `..`, links) or over 200 MB are refused.
- Plugins are installed per machine; the Theron server never distributes plugin code.

## Recommendations for plugin authors

- **Sign every release** and publish your public key where users can check it.
- **Declare honest permissions** – users decide based on them.
- **Secrets** belong in settings of type `secret`. Never log them, never put them in `ctx.storage` keys, never send
  them anywhere but the service they belong to.
- **Talk only to the services your plugin is about.** No telemetry without the user's explicit opt-in – Theron itself
  switches all telemetry off.
- **Validate input from services** before it ends up in task lists or prompts: a ticket text becomes part of an
  agent's prompt.
- **Agent tools act with the user's rights** – make destructive actions explicit (e.g. a separate `delete_…` tool with a
  clear description) or leave them out.
- **Keep `lib/` small** and pin the versions of what you vendor; you ship that code to your users.
- **Use `ctx.ai` sparingly** – every call uses the user's Claude subscription.

## Reporting a vulnerability in Theron

Please contact mibexx via the imprint on [www.theron-ai.de](https://www.theron-ai.de/imprint.html) instead of opening a
public issue.
