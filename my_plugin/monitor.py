"""Watching the running agents (“workers”) and their logs – and reacting to them.

1. The watch: follows the log of every task (``ctx.runs.watch``). When an agent's output matches the setting
   ``watch_pattern`` (e.g. ``Traceback|FAILED``), the user gets a notification – once per agent and step.
2. The stuck check: every minute it looks at the working agents (``ctx.runs.workers``). One that works on the same step
   longer than ``stuck_minutes`` is asked on the side what it is doing (``ctx.runs.ask_worker`` – it keeps working);
   its answer becomes a notification.
3. The UI (desktop app): a panel next to the cockpit and the THERON page with the agents working in the task shown and
   the last lines of its log, plus a button that opens the live log in a window of its own (ui_monitor.py).

Reference: docs/manual.md → “Reading the running agents”, docs/context.md → ctx.runs
"""

from __future__ import annotations

import re
import time


class WorkerWatch:
    def __init__(self, ctx):
        self.ctx = ctx
        self.reported: set[tuple] = set()      # (run, agent, step) already notified about
        self.asked: set[str] = set()           # worker keys asked because they were stuck
        self.watch = None

    # ------------------------------------------------------------------ 1. the log
    def pattern(self):
        raw = (self.ctx.settings.get("watch_pattern") or "").strip()
        try:
            return re.compile(raw, re.IGNORECASE) if raw else None
        except re.error:
            self.ctx.log.error(f"watch_pattern is no valid regular expression: {raw}")
            return None

    def start(self) -> None:
        """Follow the agents' output of every task: tool calls, their texts and log lines."""
        self.watch = self.ctx.runs.watch(self.on_event, types=["agent_tool", "agent_text", "agent_log"])

    async def on_event(self, event: dict) -> None:
        rx = self.pattern()
        text = event.get("summary") or event.get("text") or ""
        if not rx or not rx.search(text):
            return
        key = (event.get("run_id"), event.get("agent"), event.get("step"))
        if key in self.reported:
            return
        self.reported.add(key)
        run = self.ctx.runs.get(event["run_id"]) or {}
        self.ctx.notify(self.ctx.tr("{agent} in “{title}”: {output}", agent=event.get("agent", "?"),
                                    title=run.get("title", ""), output=text[:200]), "warning")

    # ------------------------------------------------------------------ 2. stuck agents
    async def check_stuck(self) -> None:
        minutes = float(self.ctx.settings.get("stuck_minutes") or 0)
        if minutes <= 0:
            return
        for w in self.ctx.runs.workers():
            if w["key"] in self.asked or time.time() - w["started"] < minutes * 60:
                continue
            self.asked.add(w["key"])
            try:
                answer = await self.ctx.runs.ask_worker(w["run_id"], w["key"],
                                                        "You have been working on this step for a while. "
                                                        "What exactly are you doing, and are you stuck?")
            except Exception as exc:  # noqa: BLE001 – it finished meanwhile
                self.ctx.log(f"couldn't ask {w['agent']}: {exc}")
                continue
            if answer:
                self.ctx.notify(f"{w['agent']}: {answer}", "info")


def register(ctx) -> WorkerWatch:
    watch = WorkerWatch(ctx)
    ctx.on_start(watch.start)
    ctx.schedule(60, watch.check_stuck)
    if ctx.ui.available:
        from . import ui_monitor
        ctx.ui.add_panel(["cockpit", "theron"], ctx.tr("Agents at work"), ui_monitor.WorkersPanel, id="workers",
                         icon="📡")
    return watch
