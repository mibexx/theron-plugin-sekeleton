"""The chat (chat.py): a format, a block with buttons, a node that asks, a settings button – with the devkit's fakes."""
import asyncio


def test_colour_codes_get_a_swatch(ctx):
    out = ctx.chat.format("Brand colour #1F6F8B, not &#123456 or #12345")
    assert out.count("■■") == 1 and "#1f6f8b" in out and "#12345" in out


def test_the_node_asks_in_the_chat_and_posts_a_poll(ctx):
    ctx.chat.answers = ["No"]
    result = asyncio.run(ctx.run_node("ask-chat", {"question": "Ship it?", "options": "Yes, No"}))
    assert result.ok and result.text == "The user answered: No"
    node = ctx.last_node
    assert node.asked == [{"question": "Ship it?", "options": ["Yes", "No"], "recommended": None, "details": ""}]
    poll, answer = node.said
    assert poll["kind"] == "poll" and poll["data"]["options"] == ["Yes", "No"] and "- Yes" in poll["text"]
    assert answer["text"] == "Answer: **No**"


def test_clicks_on_the_poll_count_votes(ctx):
    data = {"id": "p1", "question": "Ship it?", "options": ["Yes", "No"]}
    html = ctx.chat.render("poll", data)
    assert "theron-plugin://my-plugin/vote?poll=p1&amp;option=Yes" in html
    asyncio.run(ctx.chat.click("theron-plugin://my-plugin/vote?poll=p1&option=Yes"))
    asyncio.run(ctx.chat.click("vote", poll="p1", option="Yes"))
    assert ctx.storage.get("votes:p1") == {"Yes": 2} and ctx.chat.refreshed == 2
    assert "<td>2</td>" in ctx.chat.render("poll", data)


def test_fixed_mode_shows_the_answer_field_with_options_from_the_answers(ctx):
    assert not ctx.field_visible("ask-chat", "answer", {"mode": "ask"})
    assert ctx.field_visible("ask-chat", "answer", {"mode": "fixed"})
    assert [o["value"] for o in ctx.field_options("ask-chat", "answer", {"options": "Red, Green"})] == ["Red", "Green"]
    result = asyncio.run(ctx.run_node("ask-chat", {"mode": "fixed", "options": "Red, Green", "answer": "Green"}))
    assert result.text == "The user answered: Green" and ctx.last_node.asked == []


def test_the_settings_button_checks_trello(ctx, trello):
    assert asyncio.run(ctx.settings.press("Test Trello")) == (True, "Connected as Ada")
    ok, text = asyncio.run(ctx.settings.press("Test Trello", {"trello_token": ""}))
    assert not ok and "first" in text


def test_the_check_button_next_to_the_answers(ctx):
    assert asyncio.run(ctx.press_field_button("ask-chat", "options", 0, {"options": "Yes, No"})) == \
        ("Check", (True, "2 answers"), "Check")
    assert asyncio.run(ctx.press_field_button("ask-chat", "options", "Check", {"options": "Yes"}))[1][0] is False
