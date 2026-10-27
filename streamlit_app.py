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

EXAMPLES = [
    "Was the $75 call in Round 5 a mistake?",
    "What if I had hedged only 40% in Round 4?",
    "Which round was my best hedging decision, and why?",
    "Were the game's free collars actually fair?",
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

def md(text):
    """Streamlit reads $...$ as a math formula, and every answer is full of dollar amounts."""
    return text.replace("$", "\\$")


st.title("AI treasury analyst")
st.caption(
    md("Ask about Karthik's Fall 2025 commodity hedging game: seven rounds of swaps and collars "
    "on 100,000 units, with a $20M bankruptcy penalty and an investment hurdle. Claude picks "
    "which tools to run; the settlement, Monte Carlo and Black-76 math is Karthik's Python code, "
    f"and every figure in an answer is checked against a tool result. [Code on GitHub]({REPO})")
)


def show_tools(calls):
    if calls:
        with st.expander(f"{len(calls)} tool calls"):
            for c in calls:
                st.code(f"{c['tool']}({json.dumps(c['input'])})" + ("   # error, sent back to Claude" if c["is_error"] else ""),
                        language="python")


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
    if not state.chat:
        st.write("Try one:")
        cols = st.columns(2)
        for i, q in enumerate(EXAMPLES):
            if cols[i % 2].button(q, use_container_width=True):
                picked = q
    typed = st.chat_input(f"Ask about any round or a what-if ({left} questions left this visit)")
    question = (typed or picked or "").strip()[:500]

    if question:
        state.chat.append({"role": "user", "text": question})
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
