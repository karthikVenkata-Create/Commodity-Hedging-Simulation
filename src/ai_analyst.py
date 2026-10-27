"""
AI treasury analyst: Claude on top of the hedging engine.

    python src/ai_analyst.py ask "What if I had hedged only 40% in Round 5?"
    python src/ai_analyst.py review --round 5      # one round, saved to outputs/ai_reviews/
    python src/ai_analyst.py review --all          # every round
    python src/ai_analyst.py chat                  # back-and-forth in the terminal

How it works
1. Claude gets the question plus the five tools in ai_tools.py.
2. It answers with a tool request. Python runs the tool (my settlement, stress test,
   Black-76 or memo search code) and sends the result back.
3. That repeats until Claude has what it needs and writes the answer.
4. Guardrail: every dollar figure and percentage in the answer is checked against the
   numbers the tools actually returned. Anything that can't be traced back gets sent to
   Claude once to fix; if it is still there, the answer is printed with a warning.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from ai_tools import TOOLS, run_tool

ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "outputs" / "ai_reviews"
TRANSCRIPT_DIR = ROOT / "outputs" / "ai_transcripts"
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_TOOL_ROUNDS = 15

SYSTEM = """You are an AI treasury analyst reviewing Karthik's decisions in a commodity hedging simulation he played at UIC in Fall 2025.

The game: a producer sells 100,000 units of a commodity each round at the settlement spot price. Each round Karthik could lock in a price with a fixed-price swap, protect units with a zero-cost collar (long put, short call), or leave units floating. If revenue fell below the round's bankruptcy line the firm paid a $20M penalty; if it cleared the investment hurdle it could fund a positive-NPV project. Seven rounds settled.

Rules:
1. Every number you write must come from a tool result in this conversation. Do not add, subtract, multiply or convert figures yourself. The tools already return differences (fields named *_vs_* and tested_minus_*). If you need a number no tool gave you, call a tool or leave the number out.
2. Quote Karthik's reasoning only from memo_search results, and say which memo it is from.
3. Separate hindsight from the decision. Settled revenue is what happened. The stress test is what the book looked like before the trade. Judge a decision mainly on the stress test.
4. When you test alternatives, pick each one for a reason and say the reason. If the bankruptcy probability was high, test more protection. If hedging cut the chance of clearing the hurdle, test a collar call strike at or above the price the firm needed to clear the hurdle, or a smaller hedge. Test at most three alternatives per round.
5. Rounds 1 to 4 offered only fixed-price swaps; collars were added in Round 5. In Rounds 1 to 4, test only different swap sizes.
6. The game gave every collar for free. When an alternative changes collar strikes, report its collar_fair_value result and judge it after paying fair value, not as if the new collar were free.
7. Rounds 1 and 6 had no stated bankruptcy line or hurdle. Say so instead of guessing.
8. VaR and expected shortfall are at the 95% level; label them VaR95 and ES95.
9. Write about Karthik in the third person ("Karthik", "his book"), never "you" or "I held". Write like a treasury analyst writing to a CFO: plain sentences, short paragraphs, specific numbers, no hype. Write money as $7.02M or $834K."""

REVIEW_PROMPT = """Review Round {n} as a short treasury memo. Start directly with the first section heading, no title. Sections:

**Position** - what Karthik held.
**Karthik's reasoning at the time** - from his memo.
**What happened** - settled revenue vs fully unhedged, and against the bankruptcy line and hurdle.
**Risk before the trade** - stress test of my actual book vs unhedged.
**Alternatives tested** - up to three, each with why you chose it and what it changed.
**Verdict** - was it a good decision on the information available, and what would you change."""


# ------------------------------------------------------------------ guardrail

MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(million|billion|thousand|M|B|K|k|m|bn)?(?![a-zA-Z])")
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent(?:age points?)?\b|pp\b)")
BIG = re.compile(r"(?<![\$\d.,])(\d{1,3}(?:,\d{3})+)(?![\d.,]*\s*(?:%|percent))")
SCALE = {None: 1, "thousand": 1e3, "k": 1e3, "K": 1e3, "million": 1e6, "m": 1e6, "M": 1e6,
         "billion": 1e9, "B": 1e9, "bn": 1e9}


def figures(text):
    """Every dollar amount, percentage and large number in a piece of text, with how
    precisely it was written. '$7.0M' means 7,000,000 give or take 50,000."""
    out = []
    for m in MONEY.finditer(text):
        num, unit = m.group(1).replace(",", ""), m.group(2)
        decimals = len(num.split(".")[1]) if "." in num else 0
        scale = SCALE[unit]
        out.append((m.group(0).strip(), float(num) * scale, 0.5 * 10**-decimals * scale))
    for m in PCT.finditer(text):
        num = m.group(1)
        decimals = len(num.split(".")[1]) if "." in num else 0
        out.append((m.group(0).strip(), float(num), 0.5 * 10**-decimals))
    for m in BIG.finditer(text):
        out.append((m.group(1), float(m.group(1).replace(",", "")), 0.5))
    return out


def known_numbers(trace, extra_text=""):
    """Every number that appeared in a tool input or output (including figures inside memo text)."""
    nums = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            nums.add(abs(float(x)))
        elif isinstance(x, str):
            nums.update(v for _, v, _ in figures(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    for step in trace:
        walk(step["input"])
        walk(step["output"])
    # game facts stated in the instructions (the $20M penalty, 100,000 units) count as known
    nums.update(v for _, v, _ in figures(extra_text + " " + SYSTEM))
    return nums


def unverified(answer, trace, extra_text=""):
    """Figures in the answer that don't match any tool number within the precision they were written."""
    known = known_numbers(trace, extra_text)
    bad = []
    for label, value, tol in figures(answer):
        tol = max(tol, 0.5)
        if not any(abs(value - k) <= tol + 1e-9 for k in known):
            bad.append(label)
    return sorted(set(bad))


# ------------------------------------------------------------------ agent loop

def get_client():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("No ANTHROPIC_API_KEY found. Put it in a .env file in the project folder (see README).")
    import anthropic
    return anthropic.Anthropic()


def _text(content):
    return "\n".join(b.text for b in content if b.type == "text").strip()


def run_agent(client, messages, trace, max_tokens=2500, on_tool=None):
    """The tool-use loop. Mutates messages and trace; returns Claude's final text."""
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return _text(resp.content)

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            output, is_error = run_tool(block.name, dict(block.input))
            trace.append({"tool": block.name, "input": dict(block.input), "output": output, "is_error": is_error})
            if on_tool:
                on_tool(block.name, block.input, is_error)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output if is_error else json.dumps(output),
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})
    return _text(resp.content) + "\n\n(Stopped: hit the limit of tool calls for one answer.)"


def answer(client, messages, trace, question, max_tokens=2500, on_tool=None):
    """Ask, then run the guardrail. One automatic fix attempt if numbers don't trace back."""
    asked_so_far = " ".join(m["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], str))
    messages.append({"role": "user", "content": question})
    text = run_agent(client, messages, trace, max_tokens, on_tool)
    bad = unverified(text, trace, asked_so_far + " " + question)
    if bad:
        messages.append({"role": "user", "content": (
            "Guardrail check: these figures in your answer don't match any tool result: "
            + ", ".join(bad)
            + ". Get each one from a tool call or remove it. Then reply with the full corrected answer only, "
              "written as if it were your first answer: no note about what changed.")})
        text = run_agent(client, messages, trace, max_tokens, on_tool)
        bad = unverified(text, trace, asked_so_far + " " + question)
    return text, bad


# ------------------------------------------------------------------ output

def _audit_trail(trace):
    lines = ["## Audit trail", "", f"{len(trace)} tool calls. Every figure above comes from one of these.", ""]
    for i, s in enumerate(trace, 1):
        flag = " (error, sent back to Claude)" if s["is_error"] else ""
        lines.append(f"{i}. `{s['tool']}({json.dumps(s['input'])})`{flag}")
    lines += ["", "<details><summary>Raw tool outputs</summary>", ""]
    for i, s in enumerate(trace, 1):
        lines += [f"**{i}. {s['tool']}**", "```json", json.dumps(s["output"], indent=1), "```"]
    lines.append("</details>")
    return "\n".join(lines)


def _guardrail_line(bad):
    if not bad:
        return "Guardrail: every dollar figure and percentage traced back to a tool result."
    return "Guardrail warning: these figures could not be traced to a tool result: " + ", ".join(bad)


def save(path, title, question, text, trace, bad):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [f"# {title}", "",
            f"*Generated by the AI treasury analyst ({MODEL}) on {dt.date.today():%b %d, %Y}.*", "",
            f"**Question:** {question}", "", text, "", f"> {_guardrail_line(bad)}", "", _audit_trail(trace)]
    path.write_text("\n".join(body) + "\n")
    return path


def _plain(text):
    """Terminals don't render markdown, so drop the bold markers there. Saved files keep them."""
    return text.replace("**", "")


def _show_tool(name, args, is_error):
    print(f"  -> {name}({json.dumps(dict(args))}){'  [error]' if is_error else ''}")


# ------------------------------------------------------------------ commands

def cmd_ask(question, save_it=False, client=None):
    client = client or get_client()
    messages, trace = [], []
    text, bad = answer(client, messages, trace, question, on_tool=_show_tool)
    print("\n" + _plain(text) + "\n\n" + _guardrail_line(bad))
    if save_it:
        slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:50]
        p = save(TRANSCRIPT_DIR / f"{dt.datetime.now():%Y%m%d-%H%M}_{slug}.md", "AI analyst Q&A", question, text, trace, bad)
        print(f"Saved to {p.relative_to(ROOT)}")
    return text, trace, bad


def cmd_review(rounds, client=None):
    client = client or get_client()
    paths = []
    for n in rounds:
        print(f"\nReviewing Round {n}...")
        messages, trace = [], []
        q = REVIEW_PROMPT.format(n=n)
        text, bad = answer(client, messages, trace, q, max_tokens=3500, on_tool=_show_tool)
        paths.append(save(REVIEW_DIR / f"round_{n}.md", f"Round {n} review", f"Review Round {n}.", text, trace, bad))
        print(f"  {_guardrail_line(bad)}\n  Saved to {paths[-1].relative_to(ROOT)}")
    return paths


def cmd_chat(client=None):
    client = client or get_client()
    messages, trace = [], []
    print("AI treasury analyst. Ask about any round, or a what-if. Type 'exit' to quit.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit"}:
            break
        if q:
            text, bad = answer(client, messages, trace, q, on_tool=_show_tool)
            print("\n" + _plain(text) + "\n\n" + _guardrail_line(bad) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description="AI treasury analyst for the hedging game")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="ask one question")
    a.add_argument("question")
    a.add_argument("--save", action="store_true", help="save the answer and audit trail to outputs/ai_transcripts/")
    r = sub.add_parser("review", help="write a review memo for one or all rounds")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--round", type=int, nargs="+", choices=range(1, 8), help="one or more rounds, e.g. --round 1 2 3 4")
    g.add_argument("--all", action="store_true")
    sub.add_parser("chat", help="interactive chat")
    args = p.parse_args(argv)

    if args.cmd == "ask":
        cmd_ask(args.question, args.save)
    elif args.cmd == "review":
        cmd_review(range(1, 8) if args.all else args.round)
    else:
        cmd_chat()


if __name__ == "__main__":
    main()
