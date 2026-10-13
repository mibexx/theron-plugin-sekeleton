"""Reacting to what happens in Theron. Events: app.started, app.stopping, settings.changed, run.event, run.status,
run.finished and <kind>.saved / <kind>.deleted for project, process, agent, tasklist, epic and requirement.
Changes this plugin makes itself (through ctx.tasklists) don't come back to it – no endless sync loops."""


def register(ctx, sync):
    @ctx.events.on("run.finished")
    def finished(event):
        if ctx.settings.get("notify_on_finish"):
            status = "✔ goal reached" if event.get("goal_reached") else event.get("status", "")
            ctx.notify(ctx.tr("Task “{title}” finished: {status}", title=event.get("title", ""), status=status))

    @ctx.events.on("requirement.saved")
    async def requirement_changed(event):
        # a requirement of the synced list was changed in Theron → push it right away (Theron → service)
        await sync.push_requirement(event["id"])

    @ctx.events.on("settings.changed")
    def settings_changed(event):
        ctx.log(f"settings changed: {', '.join(event.get('keys', []))}")
