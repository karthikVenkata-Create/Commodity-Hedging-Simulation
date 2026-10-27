"""The chat page, run with Streamlit's test harness and a fake Claude client (no API key used)."""

import sys
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ai import FakeClient, text, tool  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def script(n):
    """n questions' worth of scripted replies: one tool call, then an answer."""
    out = []
    for i in range(n):
        out += [([tool(f"t{i}", "get_round", {"round": 5})], "tool_use"),
                ([text("Round 5 settled at $7.02M against $8.38M unhedged.")], "end_turn")]
    return out


@pytest.fixture
def fake(monkeypatch):
    import anthropic
    client = FakeClient(script(10))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return client


def test_no_key_turns_chat_off(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    at = st_testing.AppTest.from_file(APP).run()
    assert "no API key" in at.info[0].value
    assert len(at.chat_input) == 0


def test_question_shows_answer_tool_calls_and_guardrail(fake):
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    assert [b.label for b in at.button] == ["What is this project about?", "Walk me through Round 1"]
    at.chat_input[0].set_value("How did Round 5 go?").run()
    assert not at.exception
    page = " ".join(m.value for m in at.markdown)
    assert "How did Round 5 go?" in page and "\\$7.02M" in page
    assert any("every dollar figure" in c.value for c in at.caption)
    assert any("get_round" in c.value for c in at.code)
    assert len(at.button) == 2                      # a typed question doesn't skip the tour
    assert at.session_state["asked"] == 1


def test_tour_moves_forward_as_questions_are_asked(fake):
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    at.button[0].click().run()
    assert "What is this project about?" in " ".join(m.value for m in at.markdown)
    labels = [b.label for b in at.button]
    assert labels == ["Walk me through Round 1", "Which round was his best call?"]
    at.button[0].click().run()
    at.button[0].click().run()
    at.button[0].click().run()
    assert at.button[0].label == "Was the \\$75 call in Round 5 a mistake?"


def test_glance_numbers(fake):
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    vals = {m.label: m.value for m in at.metric}
    assert vals["Rounds settled"] == "7" and vals["Revenue, hedged"] == "$74.7M"


def test_visit_cap(fake):
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    for i in range(6):
        at.chat_input[0].set_value(f"q{i}").run()
    assert "6-question limit" in at.info[0].value
    assert len(at.chat_input) == 0


def test_api_failure_is_shown_and_rolled_back(monkeypatch):
    import anthropic

    class Broken:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("out of credit")

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: Broken())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("hello").run()
    assert "couldn't answer" in at.error[0].value
    assert at.session_state["messages"] == [] and at.session_state["chat"] == []
