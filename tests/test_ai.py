"""Tests for the AI layer. None of these call the API, so they cost nothing to run.
The agent loop is tested with a fake client that plays back scripted Claude responses."""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ai_analyst  # noqa: E402
from ai_tools import TOOLS, evaluate_hedge, get_round, memo_search, portfolio_summary, price_collar, run_tool  # noqa: E402
from hedge_engine import load_rounds, settle  # noqa: E402
from stress_test import realized_vol, stress_round  # noqa: E402


# ---------------------------------------------------------------- tools agree with the engine

def test_get_round_matches_settlement_and_memo():
    s = settle(load_rounds())
    for _, r in s.iterrows():
        g = get_round(int(r["round"]))
        assert g["hedged_revenue"] == round(r["hedged_rev"])
        assert g["matches_memo"] and g["hedged_revenue"] == g["memo_reported_revenue"]


def test_evaluate_actual_book_matches_stress_test():
    s = settle(load_rounds())
    sig = realized_vol(s["spot"])
    for _, r in s.iterrows():
        e = evaluate_hedge(int(r["round"]))
        ref = stress_round(r, sig)
        st = e["stress_test"]
        assert e["is_my_actual_position"]
        assert st["tested_position"]["var95"] == round(ref["hedged_var95_M"] * 1e6)
        assert st["unhedged"]["var95"] == round(ref["unhedged_var95_M"] * 1e6)
        assert all(v in (0, None) for v in st["tested_minus_my_actual"].values())


def test_what_if_changes_the_result():
    e = evaluate_hedge(5, call_strike=95)
    assert not e["is_my_actual_position"]
    assert e["tested_position"]["call_strike"] == 95
    # a higher call cap gives back upside: settled revenue rises at a spot of $83.80
    assert e["settled_revenue_vs_my_actual"] > 0


def test_unhedged_alternative_equals_unhedged_book():
    e = evaluate_hedge(4, swap_qty=0, collar_qty=0)
    assert e["settled_revenue_vs_unhedged"] == 0
    assert e["stress_test"]["tested_position"] == e["stress_test"]["unhedged"]


def test_round7_collar_value_matches_readme():
    c = price_collar(7, 200, 240)
    assert c["net_cost_per_unit"] * 50_000 == pytest.approx(165_000, rel=0.01)
    assert c["zero_cost_call_strike"] == pytest.approx(229, abs=1)


def test_portfolio_summary_matches_readme():
    p = portfolio_summary()
    assert p["total_hedged_revenue"] == 74_695_500
    assert p["cost_of_hedging"] == 3_634_500


@pytest.mark.parametrize("name,args", [
    ("get_round", {"round": 9}),
    ("evaluate_hedge", {"round": 2, "collar_qty": 20000, "put_strike": 100, "call_strike": 150}),  # no collars before round 5
    ("price_collar", {"round": 1, "put_strike": 40, "call_strike": 60}),
    ("evaluate_hedge", {"round": 5, "swap_qty": 80000}),            # 80k swap + 60k collar > 100k
    ("evaluate_hedge", {"round": 5, "put_strike": 80}),             # put above the $75 call
    ("price_collar", {"round": 7, "put_strike": 250, "call_strike": 240}),
    ("evaluate_hedge", {"round": 3, "sigma": 74}),                  # percent instead of decimal
    ("nope", {}),
])
def test_bad_inputs_come_back_as_errors_not_crashes(name, args):
    out, is_error = run_tool(name, args)
    assert is_error and isinstance(out, str)


def test_every_schema_matches_a_function():
    from ai_tools import FUNCTIONS
    assert {t["name"] for t in TOOLS} == set(FUNCTIONS)


# ---------------------------------------------------------------- memo search

@pytest.mark.parametrize("query,section", [
    ("why did I choose the $75 call collar", "Round 5 decision"),
    ("why hedge 70% in round 1", "Round 1 decision"),
    ("what did I learn from the whole game", "Final takeaways"),
    ("round 7 put payoff", "Round 7 result"),
])
def test_memo_search_finds_the_right_section(query, section):
    assert memo_search(query)["results"][0]["section"] == section


def test_memo_search_round_filter():
    res = memo_search("rationale", round=3)["results"]
    assert res and all(r["round"] == 3 for r in res)


# ---------------------------------------------------------------- guardrail

TRACE = [{"tool": "get_round", "input": {"round": 5}, "output": get_round(5), "is_error": False}]


def test_traced_numbers_pass():
    text = "Round 5 settled at $7.02M against $8.38M unhedged; the swap lost $834K on 30,000 units, and the collar cost $528,000."
    assert ai_analyst.unverified(text, TRACE) == []


def test_made_up_numbers_are_caught():
    text = "Revenue was $7.02M, which beat the hurdle by $1.2M and cut risk 42%."
    assert ai_analyst.unverified(text, TRACE) == ["$1.2M", "42%"]


def test_precision_is_respected():
    assert ai_analyst.unverified("about $7M", TRACE) == []          # 7,018,000 rounds to $7M
    assert ai_analyst.unverified("$7.10M", TRACE) == ["$7.10M"]     # but not to $7.10M


def test_game_facts_and_question_numbers_are_allowed():
    assert ai_analyst.unverified("a $20M penalty on 100,000 units", []) == []
    assert ai_analyst.unverified("you asked about 40%", [], "What if I hedged 40%?") == []


# ---------------------------------------------------------------- agent loop with a fake client

def text(t):
    return NS(type="text", text=t)


def tool(id_, name, args):
    return NS(type="tool_use", id=id_, name=name, input=args)


class FakeClient:
    """Plays back scripted responses and records what it was sent."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        content, stop = self.responses.pop(0)
        return NS(content=content, stop_reason=stop)


def test_agent_runs_tools_and_returns_answer():
    client = FakeClient([
        ([text("Let me pull Round 5."), tool("t1", "get_round", {"round": 5})], "tool_use"),
        ([text("Round 5 settled at $7.02M versus $8.38M unhedged.")], "end_turn"),
    ])
    msgs, trace = [], []
    out, bad = ai_analyst.answer(client, msgs, trace, "How did Round 5 go?")
    assert out == "Round 5 settled at $7.02M versus $8.38M unhedged."
    assert bad == []
    assert [s["tool"] for s in trace] == ["get_round"]
    sent = client.calls[1]["messages"][-1]["content"][0]   # the tool result Claude got back
    assert sent["type"] == "tool_result" and sent["tool_use_id"] == "t1" and "7018000" in sent["content"]
    assert client.calls[0]["tools"] == TOOLS


def test_tool_errors_go_back_to_claude():
    client = FakeClient([
        ([tool("t1", "get_round", {"round": 9})], "tool_use"),
        ([tool("t2", "get_round", {"round": 7})], "tool_use"),
        ([text("Round 7 earned $17.78M.")], "end_turn"),
    ])
    out, bad = ai_analyst.answer(client, [], trace := [], "Round 9?")
    assert trace[0]["is_error"] and not trace[1]["is_error"]
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True
    assert bad == []


def test_guardrail_sends_one_fix_request():
    client = FakeClient([
        ([tool("t1", "get_round", {"round": 5})], "tool_use"),
        ([text("Round 5 made $7.02M and beat the hurdle by $2.5M.")], "end_turn"),   # $2.5M is invented
        ([text("Round 5 made $7.02M and missed the $9.5M hurdle.")], "end_turn"),
    ])
    out, bad = ai_analyst.answer(client, [], [], "How did Round 5 go?")
    fix_request = client.calls[2]["messages"][-1]["content"]
    assert "Guardrail check" in fix_request and "$2.5M" in fix_request
    assert bad == [] and "missed" in out


def test_guardrail_warns_if_claude_does_not_fix_it():
    client = FakeClient([
        ([text("It made $99M.")], "end_turn"),
        ([text("It made $99M.")], "end_turn"),
    ])
    _, bad = ai_analyst.answer(client, [], [], "?")
    assert bad == ["$99M"]


def test_review_writes_memo_with_audit_trail(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_analyst, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(ai_analyst, "ROOT", tmp_path)
    client = FakeClient([
        ([tool("t1", "evaluate_hedge", {"round": 5, "call_strike": 95})], "tool_use"),
        ([text("**Verdict** - a $95 call would have kept more upside.")], "end_turn"),
    ])
    (path,) = ai_analyst.cmd_review([5], client=client)
    md = path.read_text()
    assert "Round 5 review" in md and "Audit trail" in md and "evaluate_hedge" in md
    assert "every dollar figure" in md
    assert np.isfinite(len(md))


def test_swap_only_rounds_still_allow_swap_what_ifs():
    e = evaluate_hedge(1, swap_qty=90000)
    assert e["tested_position"]["swap_qty"] == 90000 and e["tested_position"]["float_qty"] == 10000


def test_collar_fair_value_removes_the_free_lunch():
    # The simulation is risk-neutral and the collars are priced off the same forward and vol,
    # so once the new collar is paid for at fair value, changing a strike should be close to a wash.
    for strike in (85, 95, 120):
        fv = evaluate_hedge(5, call_strike=strike)["collar_fair_value"]
        assert fv["extra_cost_vs_my_actual_at_fair_value"] > 0
        assert abs(fv["expected_revenue_vs_my_actual_after_paying_fair_value"]) < 20_000


def test_round7_actual_collar_fair_value_matches_readme():
    fv = evaluate_hedge(7)["collar_fair_value"]
    assert fv["my_actual_collar_fair_cost"] == pytest.approx(165_000, rel=0.01)


def test_no_collar_pricing_before_round_5():
    assert "collar_fair_value" not in evaluate_hedge(3)


def test_cut_off_answer_is_labelled():
    client = FakeClient([([text("Round 5 settled at $7.02M and")], "max_tokens")])
    out, _ = ai_analyst.answer(client, [], [], "?")
    assert "cut off" in out
