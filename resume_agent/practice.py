"""Interview practice: feedback on the candidate's answer to a question about their own code.

The LLM's feedback is an opinion and is labeled as such. What code enforces: every
"you missed this" point must quote the cited code, otherwise it is dropped.
"""
from __future__ import annotations

import hashlib

from . import prompts
from .ingest import Repo
from .llm.base import LLMProvider, LLMRequest
from .models import Feedback, FeedbackOut, Question
from .verifier import norm, verify_evidence

MAX_ANSWER_CHARS = 4000
DIMENSIONS = ("correctness", "tradeoffs", "failure_modes", "clarity")


class PracticeError(ValueError):
    pass


def cited_code(repo: Repo, q: Question) -> str:
    """Re-open the question's citations (the repo may have changed since the run)."""
    parts = []
    for e in q.evidence:
        checked, text = verify_evidence(repo, e)
        if not checked.verified:
            raise PracticeError(f"Citation {e.label()} no longer matches the repo ({checked.verify_note}). Run the analysis again.")
        parts.append(f"# {e.label()}\n{text}")
    if not parts:
        raise PracticeError("This question has no cited code.")
    return "\n\n".join(parts)


def give_feedback(repo: Repo, q: Question, answer: str, provider: LLMProvider) -> Feedback:
    answer = (answer or "").strip()
    if not answer:
        raise PracticeError("Write an answer first.")
    if len(answer) > MAX_ANSWER_CHARS:
        raise PracticeError(f"Answer is too long (max {MAX_ANSWER_CHARS} characters).")
    code = cited_code(repo, q)
    fp = hashlib.sha256(f"{q.question}\n{code}\n{answer}".encode()).hexdigest()[:16]
    resp = provider.complete(LLMRequest("feedback", prompts.SYSTEM, prompts.feedback_prompt(q.question, code, answer),
                                        FeedbackOut, fingerprint=fp,
                                        payload={"question": q.question, "code": code, "answer": answer}))
    return verify_feedback(resp.data, code, resp)


def verify_feedback(raw: FeedbackOut, code: str, resp=None) -> Feedback:
    hay = norm(code)
    missed = [m for m in raw.missed if len(norm(m.quote)) >= 3 and norm(m.quote) in hay][:3]
    return Feedback(scores={d: max(1, min(5, int(getattr(raw, d)))) for d in DIMENSIONS},
                    strengths=raw.strengths[:3], improve=raw.improve[:3], missed=missed,
                    dropped=len(raw.missed) - len(missed), follow_up=raw.follow_up,
                    provider=getattr(resp, "provider", ""), model=getattr(resp, "model", ""),
                    mode=getattr(resp, "mode", ""), cached=getattr(resp, "cached", False))
