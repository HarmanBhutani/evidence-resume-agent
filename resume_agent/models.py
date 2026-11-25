"""Pydantic models: LLM output schemas and final result structures."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    """A pointer into the candidate's repo plus the quoted snippet that proves a claim."""
    model_config = ConfigDict(extra="ignore")
    kind: Literal["file", "commit"]
    path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    commit: Optional[str] = None
    quote: str = ""
    # Filled in by the verifier (never trusted from the LLM):
    verified: bool = False
    verify_note: str = ""
    resolved_commit: Optional[str] = None
    # Filled in by the authorship check (never trusted from the LLM):
    authorship: Literal["unchecked", "mine", "mixed", "not_mine"] = "unchecked"
    authorship_note: str = ""

    def label(self) -> str:
        if self.kind == "file":
            return f"{self.path}:{self.start_line}-{self.end_line}"
        return f"commit {(self.resolved_commit or self.commit or '')[:8]}"


# ---------- LLM output schemas (what we ask the model for) ----------
class LedgerItemRaw(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: Literal["skill", "achievement"] = "skill"
    name: str
    summary: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class LedgerOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: list[LedgerItemRaw]


class RequirementRaw(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    priority: Literal["required", "preferred"] = "required"
    keywords: list[str] = Field(default_factory=list)


class JDOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    requirements: list[RequirementRaw]


class MatchRaw(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requirement_id: str
    status: Literal["SUPPORTED", "PARTIAL", "GAP"]
    ledger_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class MatchOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    matches: list[MatchRaw]


class BulletRaw(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    requirement_ids: list[str] = Field(default_factory=list)
    ledger_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class QuestionRaw(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str
    why: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class GenerateOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bullets: list[BulletRaw] = Field(default_factory=list)
    interview: list[QuestionRaw] = Field(default_factory=list)


# ---------- Final, verified structures ----------
class LedgerItem(BaseModel):
    id: str
    kind: Literal["skill", "achievement"]
    name: str
    summary: str
    evidence: list[Evidence]


class RejectedItem(BaseModel):
    what: str          # "ledger item" | "evidence" | "bullet" | "question" | "match"
    text: str
    reasons: list[str]


class Requirement(BaseModel):
    id: str
    text: str
    priority: Literal["required", "preferred"]
    keywords: list[str] = Field(default_factory=list)
    provable_from_repo: bool = True
    note: str = ""


class Match(BaseModel):
    requirement_id: str
    status: Literal["SUPPORTED", "PARTIAL", "GAP"]
    ledger_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    adjustments: list[str] = Field(default_factory=list)   # what code changed vs. the LLM
    user_provided: list[str] = Field(default_factory=list)  # unverified user items that mention it
    non_code: bool = False
    missing: list[str] = Field(default_factory=list)        # required technologies not found in your evidence


class Bullet(BaseModel):
    id: str
    text: str
    status: Literal["ok", "blocked"]
    origin: Literal["verified", "user-provided, unverified"] = "verified"
    requirement_ids: list[str] = Field(default_factory=list)
    ledger_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    block_reasons: list[str] = Field(default_factory=list)


class Question(BaseModel):
    question: str
    why: str = ""
    evidence: list[Evidence]


class FeedbackPointRaw(BaseModel):
    model_config = ConfigDict(extra="ignore")
    point: str
    quote: str = ""


class FeedbackOut(BaseModel):
    """Answer feedback proposed by the LLM. Scores are 1-5."""
    model_config = ConfigDict(extra="ignore")
    correctness: int = 1
    tradeoffs: int = 1
    failure_modes: int = 1
    clarity: int = 1
    strengths: list[str] = Field(default_factory=list)
    improve: list[str] = Field(default_factory=list)
    missed: list[FeedbackPointRaw] = Field(default_factory=list)
    follow_up: str = ""


class Feedback(BaseModel):
    scores: dict[str, int]
    strengths: list[str]
    improve: list[str]
    missed: list[FeedbackPointRaw]          # only points whose quote was found in the cited code
    dropped: int = 0                        # code points removed because their quote was not in the code
    follow_up: str = ""
    provider: str = ""
    model: str = ""
    mode: str = ""
    cached: bool = False


class UserItem(BaseModel):
    text: str
    label: str = "user-provided, unverified"


class AuthorshipReport(BaseModel):
    checked: bool = False
    identities: list[str] = Field(default_factory=list)   # only the candidate's own emails
    warnings: list[str] = Field(default_factory=list)


class RunMeta(BaseModel):
    provider: str
    model: str
    mode: Literal["LIVE", "REPLAYED", "MOCK"]
    cached: bool = False
    generated_at: str = ""
    repo_name: str = ""
    repo_hash: str = ""
    jd_hash: str = ""
    jd_title: str = ""
    step_modes: dict[str, str] = Field(default_factory=dict)
    timings_s: dict[str, float] = Field(default_factory=dict)


class RunResult(BaseModel):
    meta: RunMeta
    ledger: list[LedgerItem]
    requirements: list[Requirement]
    matches: list[Match]
    bullets: list[Bullet]
    interview: list[Question]
    rejected: list[RejectedItem] = Field(default_factory=list)
    user_items: list[UserItem] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    authorship: AuthorshipReport = Field(default_factory=AuthorshipReport)
