import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from devkit import FakeContext, load_plugin  # noqa: E402


@pytest.fixture
def ctx():
    """The plugin, registered against a stand-in Theron (devkit/fake_theron.py)."""
    c = FakeContext.from_plugin(ROOT)
    c.module = load_plugin(c, ROOT)
    return c


@pytest.fixture
def ui_ctx():
    """The plugin as in the desktop app (ctx.ui.available) – registers its buttons, panels and pages (needs PySide6)."""
    c = FakeContext.from_plugin(ROOT)
    c.ui.available = True
    c.module = load_plugin(c, ROOT)
    return c


@pytest.fixture
def trello(ctx):
    """A fake Trello board: lists To do / Doing / Done and two cards – the sync talks to it through ctx.http."""
    board = {"lists": [{"id": "L1", "name": "To do"}, {"id": "L2", "name": "Doing"}, {"id": "L3", "name": "Done"}],
             "cards": [{"id": "C1", "name": "Login page", "desc": "with 2FA", "idList": "L1", "closed": False},
                       {"id": "C2", "name": "Imprint", "desc": "", "idList": "L3", "closed": False}]}

    def new_card(req):
        card = {"id": f"C{len(board['cards']) + 1}", "name": req["params"]["name"], "desc": req["params"]["desc"],
                "idList": req["params"]["idList"], "closed": False}
        board["cards"].append(card)
        return card

    def update_card(req):
        card = next(c for c in board["cards"] if req["url"].endswith(c["id"]))
        card.update(name=req["params"]["name"], desc=req["params"]["desc"], idList=req["params"]["idList"])
        return card

    ctx.http.route("GET", "/lists", lambda req: board["lists"])
    ctx.http.route("GET", "/cards", lambda req: board["cards"])
    ctx.http.route("GET", "/members/me", {"fullName": "Ada"})
    ctx.http.route("POST", "/cards", new_card)
    ctx.http.route("PUT", "/cards/", update_card)
    tid = ctx.tasklists.create(1, "Sprint")
    ctx.settings.update({"trello_key": "k", "trello_token": "t", "trello_board": "B1", "sync_tasklist": tid})
    return board
