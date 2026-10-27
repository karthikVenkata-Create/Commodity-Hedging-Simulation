"""
Chat with the AI treasury analyst in the browser.

    streamlit run streamlit_app.py

Same agent as src/ai_analyst.py: Claude decides which tools to call, my code does the
math, and the guardrail checks every figure. This page only adds a chat box, shows the
tool calls as they happen, and caps usage so a public link can't run up the API bill.
The API key comes from Streamlit secrets (when hosted) or the .env file (locally).
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import ai_analyst  # noqa: E402

QUESTIONS_PER_VISIT = 6
QUESTIONS_PER_DAY = 150
REPO = "https://github.com/karthikVenkata-Create/Commodity-Hedging-Simulation"

# A guided path from "what is this?" to the hard questions. The first two show up on an empty
# chat; after each answer the next two unasked ones are offered, so a visitor never has to
# know what to ask.
TOUR = [   # (stage, button label, question sent to Claude)
    ("Start here", "What is this project about?", "What is this project about?"),
    ("Start here", "Walk me through Round 1", "Walk me through Round 1: what did Karthik do, and how did it turn out?"),
    ("Go deeper", "Which round was his best call?", "Which round was Karthik's best hedging decision, and why?"),
    ("Go deeper", "What if he'd hedged 40% in Round 4?", "What if Karthik had hedged only 40% in Round 4?"),
    ("Advanced", "Was the $75 call in Round 5 a mistake?", "Was the $75 call in Round 5 a mistake?"),
    ("Advanced", "Were the free collars actually fair?", "Were the game's free collars actually fair?"),
]

st.set_page_config(page_title="Hedging analyst", page_icon="📈")


def api_key():
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass   # no secrets file when running locally
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass
    return os.getenv("ANTHROPIC_API_KEY")


@st.cache_resource
def daily_counter():
    """Shared across every visitor to this app, so the day's total can be capped."""
    return {}


def under_daily_cap():
    counts, today = daily_counter(), dt.date.today().isoformat()
    return counts.get(today, 0) < QUESTIONS_PER_DAY


def count_question():
    counts, today = daily_counter(), dt.date.today().isoformat()
    counts[today] = counts.get(today, 0) + 1


state = st.session_state
state.setdefault("messages", [])    # what goes to Claude, including tool calls and results
state.setdefault("trace", [])       # every tool call this visit, for the guardrail
state.setdefault("chat", [])        # what the page shows: role, text, tool calls, guardrail
state.setdefault("asked", 0)
state.setdefault("asked_q", [])     # tour questions already asked, so suggestions move on

def md(text):
    """Streamlit reads $...$ as a math formula, and every answer is full of dollar amounts."""
    return text.replace("$", "\\$")


st.title("AI treasury analyst")
st.caption(md(
    "Karthik played an eight-round commodity hedging game at UIC in Fall 2025: 100,000 units a round, "
    "swaps and collars to choose from, a $20M bankruptcy penalty below one line and an investment project "
    "above another. This chat reviews his decisions. Claude chooses which tools to run, Karthik's Python "
    "code does the settlement, Monte Carlo and Black-76 math, and every figure is checked against a tool "
    f"result before you see it. [Code on GitHub]({REPO})"))


@st.cache_data
def glance():
    import ai_tools
    return ai_tools.portfolio_summary()


g = glance()
c1, c2, c3, c4 = st.columns(4)
quiet = dict(delta_color="off", delta_arrow="off", border=True)
c1.metric("Rounds settled", g["rounds_settled"], "Oct to Dec 2025", **quiet)
c2.metric("Revenue, hedged", f"${g['total_hedged_revenue'] / 1e6:.1f}M",
          f"cost ${g['cost_of_hedging'] / 1e6:.1f}M", **quiet)
c3.metric("Revenue swings", f"-{g['revenue_volatility_reduction_pct']:.0f}%", "from hedging", **quiet)
c4.metric("Stress test", "10,000", "scenarios per round", **quiet)


def show_tools(calls):
    """One compact block listing every tool call, folded away by default."""
    if calls:
        with st.expander(f"How it got there: {len(calls)} tool calls"):
            st.code("\n".join(f"{c['tool']}({json.dumps(c['input'])})" + ("   # error, sent back to Claude" if c["is_error"] else "")
                              for c in calls), language="python", wrap_lines=True)


for m in state.chat:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            show_tools(m["tools"])
        st.markdown(md(m["text"]))
        if m.get("guardrail"):
            st.caption(m["guardrail"])

key = api_key()
left = QUESTIONS_PER_VISIT - state.asked
picked = None

if not key:
    st.info("This copy has no API key set, so the chat is off. See the README to add one.")
elif left <= 0:
    st.info(f"That's the {QUESTIONS_PER_VISIT}-question limit for one visit. The full code and saved reviews are on GitHub.")
elif not under_daily_cap():
    st.info("The demo has hit its daily question limit. Try again tomorrow, or read the saved reviews on GitHub.")
else:
    upcoming = [t for t in TOUR if t[2] not in state.asked_q][:2]
    if upcoming:
        st.write("**Start here:**" if not state.chat else "**Next up:**")
        cols = st.columns(len(upcoming))
        for col, (stage, label, q) in zip(cols, upcoming):
            if col.button(md(label), help=stage, use_container_width=True, key=f"tour-{q}"):
                picked = q
    typed = st.chat_input(f"Ask about any round or a what-if ({left} questions left this visit)")
    question = (typed or picked or "").strip()[:500]

    if question:
        state.chat.append({"role": "user", "text": question})
        if question in {t[2] for t in TOUR}:
            state.asked_q.append(question)
        with st.chat_message("user"):
            st.markdown(md(question))
        with st.chat_message("assistant"):
            before, n_msgs = len(state.trace), len(state.messages)
            with st.status("Working...", expanded=True) as status:
                def on_tool(name, args, is_error):
                    status.write(f"`{name}({json.dumps(dict(args))})`" + (" (error, retrying)" if is_error else ""))
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=key)
                    text, bad = ai_analyst.answer(client, state.messages, state.trace, question, on_tool=on_tool)
                    count_question()
                    state.asked += 1
                    status.update(label="Done", state="complete", expanded=False)
                except Exception as e:   # API down, out of credit, etc.
                    status.update(label="Something went wrong", state="error")
                    st.error(f"The analyst couldn't answer: {type(e).__name__}. Please try again later.")
                    state.chat.pop()
                    if state.asked_q and state.asked_q[-1] == question:
                        state.asked_q.pop()
                    del state.messages[n_msgs:]   # drop the half-finished exchange so the next question starts clean
                    del state.trace[before:]
                    st.stop()
            calls = state.trace[before:]
            show_tools(calls)
            st.markdown(md(text))
            guard = ai_analyst._guardrail_line(bad)
            st.caption(guard)
        state.chat.append({"role": "assistant", "text": text, "tools": calls, "guardrail": guard})
        st.rerun()
