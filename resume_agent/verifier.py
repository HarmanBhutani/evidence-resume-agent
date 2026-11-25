"""Reference verifier: every citation is opened and checked against the real repo."""
from __future__ import annotations

import re

from .ingest import Repo
from .models import Evidence

MAX_RANGE_LINES = 60
MIN_QUOTE_CHARS = 5


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _strip_diff_prefix(text: str) -> str:
    return "\n".join(l[1:] if l[:1] in "+- " and not l.startswith(("+++", "---")) else l
                     for l in text.splitlines())


def verify_evidence(repo: Repo, ev: Evidence) -> tuple[Evidence, str]:
    """Return (copy of ev with verified/verify_note set, evidence_text).

    evidence_text is the repo text this citation actually covers (used to trace claims);
    it is '' when the citation is invalid.
    """
    e = ev.model_copy(deep=True)
    e.verified = False
    e.authorship, e.authorship_note = "unchecked", ""   # discard anything the LLM put here
    quote = norm(e.quote or "")
    if len(quote) < MIN_QUOTE_CHARS:
        e.verify_note = "quote missing or too short"
        return e, ""
    if e.kind == "file":
        lines = repo.file_lines(e.path or "")
        if lines is None:
            e.verify_note = f"file not found in repo: {e.path!r}"
            return e, ""
        s, t = e.start_line, e.end_line
        if s is None or t is None or s < 1 or t < s or t > len(lines):
            e.verify_note = f"invalid line range {s}-{t} (file has {len(lines)} lines)"
            return e, ""
        if t - s + 1 > MAX_RANGE_LINES:
            e.verify_note = f"line range too wide (>{MAX_RANGE_LINES} lines)"
            return e, ""
        text = "\n".join(lines[s - 1:t])
        if quote not in norm(text):
            e.verify_note = f"quoted snippet not found in {e.path}:{s}-{t}"
            return e, ""
        e.verified, e.verify_note = True, "ok"
        return e, f"{e.path}\n{text}"   # the (verified) path is part of the citation
    # commit
    ct = repo.commit_text(e.commit or "")
    if ct is None:
        e.verify_note = f"commit not found: {e.commit!r}"
        return e, ""
    full, text = ct
    if quote not in norm(text) and quote not in norm(_strip_diff_prefix(text)):
        e.verify_note = f"quoted snippet not found in commit {full[:8]}"
        return e, ""
    e.verified, e.verify_note, e.resolved_commit = True, "ok", full
    # the evidence text for a commit is the quote plus the subject line (not the whole diff)
    subject = text.splitlines()[2] if len(text.splitlines()) > 2 else ""
    return e, f"{subject}\n{e.quote}"


def verify_all(repo: Repo, evidence: list[Evidence]) -> tuple[list[Evidence], str, list[str]]:
    """Verify a list. Returns (checked copies, combined evidence text of valid ones, failure notes)."""
    out, texts, fails = [], [], []
    for ev in evidence:
        v, t = verify_evidence(repo, ev)
        out.append(v)
        if v.verified:
            texts.append(t)
        else:
            fails.append(f"{ev.label()}: {v.verify_note}")
    return out, "\n".join(texts), fails
