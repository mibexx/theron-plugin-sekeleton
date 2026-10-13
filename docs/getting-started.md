# Getting started

## 1. Requirements

- **Theron 0.14.0** or newer ([download](https://theron.mibexx.de/#download)) – for running the plugin.
- **Python 3.11+** – only for developing: running the tests and the pack script. Inside Theron the plugin runs on
  Theron's own Python (3.12 or newer); nothing has to be installed.

## 2. Create the plugin

Either clone this skeleton:

```bash
git clone https://github.com/mibexx/theron-plugin my-plugin
cd my-plugin
```

or let Theron create a minimal one:

```bash
theron plugin new my-plugin --id my-plugin --name "My Plugin"
```

## 3. The smallest possible plugin

```
hello/
├── plugin.toml
└── hello/
    └── __init__.py
```

```toml
# plugin.toml
id = "hello"
name = "Hello"
version = "0.1.0"
theron_api = 1
entry = "hello"
```

```python
# hello/__init__.py
def register(ctx):
    async def greet(node):
        node.progress("greeting …")
        return node.success(f"Hello! {len(node.handovers)} hand-overs came in.")

    ctx.nodes.register("greet", label="Say hello", run=greet, outputs="success")
```

## 4. Pack and install

```bash
theron plugin pack hello               # → hello-0.1.0.theronplugin next to the folder
theron plugin install hello-0.1.0.theronplugin
```

Without Theron's command on the machine use this skeleton's `python scripts/pack.py`. In the app:
**Settings → Plugins → “Upload plugin …”**.

## 5. Restart and use it

Restart Theron. Open **PROZESSE / PROCESSES**, drag **Say hello** from **TOOLS** onto the canvas and connect it. When a
task runs through the node, its result appears as a hand-over in the chat (`⬢ Say hello ✔ …`).

## 6. Iterate

1. Change the code, raise `version` in `plugin.toml`.
2. Pack and install again (an update replaces the installed version; settings and data stay).
3. Restart Theron.

Tip: write tests with the [devkit](testing.md) – most of the work can be checked without restarting Theron at all.
