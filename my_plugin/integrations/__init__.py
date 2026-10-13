"""Integrations: a generic two-way task-list sync (sync.py) and adapters for the services it talks to.

    sync.py       TaskListSync – keeps a Theron task list and a service in step (mapping, change detection)
    adapter.py    Adapter – the interface an adapter implements, RemoteItem – one card / issue / ticket
    trello.py     TrelloAdapter – a complete adapter for Trello boards
    template.py   ServiceAdapter – placeholders for your own service (Jira, GitHub Issues, Linear, Asana …)
"""
