"""Deterministic claim tracing: numbers, technologies, scale and leadership claims in a
sentence must be traceable to evidence text, otherwise the sentence is blocked."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .techvocab import canonical, detect_terms, in_text, mask_terms

NUM_RE = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(%|x\b|k\b|m\b|ms\b|s\b|[a-z]+)?", re.IGNORECASE)
NUMBER_WORDS = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                "eight": "8", "nine": "9", "ten": "10", "dozen": "12", "hundred": "100",
                "hundreds": "100", "thousand": "1000", "thousands": "1000", "million": "1000000",
                "millions": "1000000", "billion": "1000000000", "double": "2", "doubled": "2",
                "triple": "3", "tripled": "3", "twice": "2", "tenfold": "10"}
SCALE_WORDS = ["million", "millions", "billion", "thousands of", "high-throughput", "high throughput",
               "high-volume", "high volume", "large-scale", "large scale", "at scale",
               "mission-critical", "enterprise", "petabyte", "terabyte", "massive", "zero downtime",
               "24/7", "real-time", "real time", "low-latency", "low latency"]
UNPROVABLE_WORDS = ["led ", "lead ", "leading", "leadership", "mentored", "mentoring", "managed a team",
                    "managed team", "managing", "spearheaded", "supervised", "directed a",
                    "cross-functional", "stakeholder", "stakeholders", "team of", "onboarded",
                    "coached", "hired", "headed"]
GENERIC_ALLOWED = {"API", "APIs", "CI", "CD", "CLI", "ID", "IDs", "OK", "UI", "URL", "URLs", "I", "A",
                   "TTL", "CRUD", "DB", "N", "IO", "E2E", "UTC"}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.+#_][A-Za-z0-9]+)*")


@dataclass
class Problem:
    kind: str     # number | technology | scale | unprovable
    token: str
    message: str

    def __str__(self) -> str:
        return self.message


def numbers_in(text: str) -> list[str]:
    """Numeric claim tokens (as digit strings) in `text`, incl. a few number words."""
    out = []
    for m in NUM_RE.finditer(text):
        out.append(m.group(1).replace(",", ""))
    # set phrases where a number word is not a quantity ("test double" is a testing term)
    plain = re.sub(r"(?i)\btest[\s-]+doubles?\b|\bdouble[\s-]+(?:check\w*|quot\w*|click\w*)", " ", text)
    for w in re.findall(r"[A-Za-z]+", plain):
        if w.lower() in NUMBER_WORDS:
            out.append(NUMBER_WORDS[w.lower()])
    return out


def _evidence_numbers(evidence_text: str) -> set[str]:
    nums = set(re.findall(r"\d+(?:\.\d+)?", evidence_text.replace(",", "")))
    for w in re.findall(r"[A-Za-z]+", evidence_text):
        if w.lower() in NUMBER_WORDS:
            nums.add(NUMBER_WORDS[w.lower()])
    return nums


def heuristic_tokens(text: str) -> list[str]:
    """Tokens that look like proper nouns / product names / acronyms (not in the vocabulary)."""
    out = []
    toks = list(TOKEN_RE.finditer(text))
    for i, m in enumerate(toks):
        t = m.group(0)
        if t in GENERIC_ALLOWED or len(t) < 2:
            continue
        camel = bool(re.search(r"[a-z][A-Z]", t))
        allcaps = t.isupper() and len(t) >= 2 and t.isalpha()
        prev_end = toks[i - 1].end() if i else 0
        sentence_start = i == 0 or re.search(r"[.!?:;—\-]\s*$", text[prev_end:m.start()]) is not None \
            and re.search(r"[.!?]\s*$", text[prev_end:m.start()]) is not None
        mid_cap = t[0].isupper() and not sentence_start and i > 0 and not allcaps
        if camel or allcaps or mid_cap:
            out.append(t)
    return out


def check_claims(text: str, evidence_text: str, *, check_scale: bool = True,
                 check_unprovable: bool = True) -> list[Problem]:
    """Return a list of problems; empty means every checked claim is traceable."""
    problems: list[Problem] = []
    ev_nums = _evidence_numbers(evidence_text)
    seen: set[str] = set()
    for n in numbers_in(text):
        if n in seen:
            continue
        seen.add(n)
        if n not in ev_nums and n.lstrip("0") not in ev_nums:
            problems.append(Problem("number", n, f"number '{n}' not found in cited evidence"))
    checked: set[str] = set()
    for term in detect_terms(text):
        checked.add(term.lower())
        if not in_text(term, evidence_text):
            problems.append(Problem("technology", term, f"technology/concept '{term}' not found in cited evidence"))
    for tok in heuristic_tokens(mask_terms(text)):
        if tok.lower() in checked or canonical(tok):
            continue
        checked.add(tok.lower())
        if not in_text(tok, evidence_text):
            problems.append(Problem("technology", tok, f"named term '{tok}' not found in cited evidence"))
    low = " " + text.lower() + " "
    if check_scale:
        for w in SCALE_WORDS:
            if w in low and w not in evidence_text.lower():
                problems.append(Problem("scale", w, f"scale/impact claim '{w.strip()}' not found in cited evidence"))
    if check_unprovable:
        for w in UNPROVABLE_WORDS:
            if re.search(r"(?<![a-z])" + re.escape(w.strip()) + (r"(?![a-z])" if w.endswith(" ") else ""), low) \
                    and w.strip() not in evidence_text.lower():
                problems.append(Problem("unprovable", w.strip(),
                                        f"'{w.strip()}' (leadership/mentoring/non-code) cannot be proven from a repo"))
                break
    return problems


NONCODE_PATTERNS = [
    (re.compile(r"\b\d+\s*\+?\s*(?:years?|yrs?)\b", re.I), "years of experience"),
    (re.compile(r"\bmentor(?:ing|ship)?\b|\bcoach(?:ing)?\b", re.I), "mentoring"),
    (re.compile(r"\blead(?:ing|ership)?\b|\bmanag(?:e|ing|ement)\b.*\bteam\b|\bteam of\b|\bheadcount\b", re.I), "leadership"),
    (re.compile(r"\bcommunicat\w*|\bstakeholder\w*|\bcross-functional\b|\bcollaborat\w*", re.I), "communication/stakeholders"),
    (re.compile(r"\bdegree\b|\bbachelor|\bmaster'?s\b|\bph\.?d\b", re.I), "education"),
    (re.compile(r"\bon-?call\b|\bagile\b|\bscrum\b", re.I), "process/on-call"),
]


def classify_noncode(text: str) -> list[str]:
    return [label for pat, label in NONCODE_PATTERNS if pat.search(text)]
