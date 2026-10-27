"""
Retrieval over my eight decision memos (the "R" in RAG).

Each memo is split at its "## " headings, so every chunk is one section:
a round's result or a round's decision. Chunks are ranked with BM25, the
keyword-ranking method covered in the course's RAG module. BM25 works well
here because the memos are short and the questions use the same words the
memos do (round numbers, strikes, "collar", "bankruptcy"). It also needs no
second API key, unlike an embedding model.
"""

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

MEMO_DIR = Path(__file__).resolve().parents[1] / "memos"

STOPWORDS = set("""
a an and are as at be because but by for from has have i if in is it its of on or
so that the their there this to was we were what when which while will with you
our us my me do does did not no it's than then them they these those can could
""".split())


# Questions are phrased differently from the memos ("why did I choose..." vs "Rationale: I chose...").
# Mapping a few words onto the memo's own vocabulary fixes most misses without a stemmer.
SYNONYMS = {
    "why": "rationale", "reason": "rationale", "reasoning": "rationale", "thinking": "rationale",
    "choose": "chose", "choice": "chose", "picked": "chose", "pick": "chose", "decided": "chose",
    "outcome": "result", "settled": "result", "performance": "result",
    "learn": "learned", "lesson": "learned", "lessons": "learned", "takeaway": "takeaways",
    "floor": "put", "cap": "call", "capped": "call", "unhedged": "float", "floating": "float",
}


def tokenize(text):
    """Lowercase words and numbers. '$75' and '75' both become '75', '4.5M' stays '4.5m'."""
    toks = re.findall(r"[a-z]+|\d+(?:\.\d+)?[mk]?", text.lower())
    return [SYNONYMS.get(t, t) for t in toks if t not in STOPWORDS]


def _round_of(heading):
    m = re.search(r"round\s+(\d+)", heading, re.I)
    return int(m.group(1)) if m else None


@lru_cache(maxsize=1)
def load_chunks(memo_dir=MEMO_DIR):
    chunks = []
    for path in sorted(Path(memo_dir).glob("*.md")):
        text = path.read_text()
        title = text.splitlines()[0].lstrip("# ").strip()
        for part in re.split(r"^## ", text, flags=re.M)[1:]:
            heading, _, body = part.partition("\n")
            chunks.append({
                "source": path.name,
                "memo": title,
                "section": heading.strip(),
                "round": _round_of(heading),
                "text": body.strip(),
            })
    return tuple(chunks)


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.toks = [tokenize(d) for d in docs]
        self.avgdl = sum(map(len, self.toks)) / len(self.toks)
        df = Counter(t for doc in self.toks for t in set(doc))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(doc) for doc in self.toks]

    def scores(self, query):
        q = tokenize(query)
        out = []
        for tf, doc in zip(self.tf, self.toks):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl))
            out.append(s)
        return out


def search_memos(query, round=None, top_k=3):
    """Return the memo sections that best match the query, optionally limited to one round."""
    chunks = load_chunks()
    # the section heading is searchable too, so "round 5 decision" finds the right section
    index = BM25([f"{c['section']} {c['text']}" for c in chunks])
    ranked = sorted(zip(index.scores(query), chunks), key=lambda x: -x[0])
    hits = [(s, c) for s, c in ranked if round is None or c["round"] == round]
    hits = [(s, c) for s, c in hits if s > 0] or hits  # a round filter alone still returns that round
    return [{"score": round_(s), **c} for s, c in hits[:top_k]]


def round_(x):
    return float(f"{x:.3f}")
