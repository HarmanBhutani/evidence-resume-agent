"""End-to-end pipeline: ingest -> ledger -> JD parse -> match -> bullets + interview -> verify."""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Callable

from . import prompts
from .authorship import Authorship, normalize_ids
from .claims import check_claims, classify_noncode
from .ingest import Repo
from .llm.base import LLMProvider, LLMRequest
from .models import (AuthorshipReport, Bullet, Evidence, GenerateOut, JDOut, LedgerItem, LedgerOut, Match, MatchOut, Question,
                     RejectedItem, Requirement, RunMeta, RunResult, UserItem)
from .techvocab import detect_terms, in_text, is_enforceable
from .verifier import verify_all

Progress = Callable[[str, str, str], None]   # (step, state, detail)
STEPS = ["ingest", "ledger", "jd_parse", "match", "generate", "verify"]

NONCODE_NOTICE = ("Repos cannot prove leadership, mentoring, years of experience, communication or other "
                  "non-code work. Those requirements are never marked supported; add them manually below "
                  "and they appear labeled 'user-provided, unverified'.")


def _hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()[:16]


UNCHECKED_NOTICE = ("AUTHORSHIP NOT CHECKED: citations show the code exists in this repo, not that you wrote it. "
                    "Select your commit emails to check.")
CHECKED_NOTICE = ("Authorship checked against git history for the emails you selected. Git authorship can be faked "
                  "and does not show whether code was copied or generated, so this is evidence, not certification.")
NOT_YOURS = "exists in the repo but is not shown to be your work"


def check_evidence(repo: Repo, evidence: list[Evidence], author: Authorship | None):
    """Verify citations, then attribute them.

    Returns (all checked copies, citations usable as support, text claims may be traced to,
    verification failures, authorship exclusions). With an authorship check, usable citations
    and traceable text cover only the candidate's own work.
    """
    evs, text, fails = verify_all(repo, evidence)
    if author is None:
        return evs, [e for e in evs if e.verified], text, fails, []
    out, usable, texts, excluded = [], [], [], []
    for e in evs:
        if e.verified:
            e, owned_text = author.attribute(e)
            if owned_text:
                usable.append(e)
                texts.append(owned_text)
            else:
                excluded.append(f"{e.label()}: {e.authorship_note}")
        out.append(e)
    return out, usable, "\n".join(texts), fails, excluded


# ---------------- steps ----------------
def build_ledger(repo: Repo, raw: LedgerOut, author: Authorship | None = None,
                 not_yours: set[str] | None = None) -> tuple[list[LedgerItem], list[RejectedItem], dict[str, str]]:
    """Verify every ledger item. Returns items (ids L1..), rejected log, and id -> evidence text."""
    items, rejected, ev_text = [], [], {}
    for idx, r in enumerate(raw.items, 1):   # ids follow the raw order so recordings stay consistent
        _, valid, text, fails, excluded = check_evidence(repo, r.evidence, author)
        for f in fails + excluded:
            rejected.append(RejectedItem(what="evidence", text=f"{r.name}", reasons=[f]))
        if not valid and excluded:
            if not_yours is not None:
                not_yours.add(f"L{idx}")
            rejected.append(RejectedItem(what="ledger item", text=r.name, reasons=[f"evidence {NOT_YOURS}"]))
            continue
        if not valid:
            rejected.append(RejectedItem(what="ledger item", text=r.name,
                                         reasons=["no valid evidence (blocked: ledger items need verified citations)"]))
            continue
        problems = check_claims(r.name, text, check_unprovable=True)
        if problems:
            rejected.append(RejectedItem(what="ledger item", text=r.name, reasons=[str(p) for p in problems]))
            continue
        summary = r.summary
        sp = check_claims(summary, text, check_unprovable=True) if summary else []
        if sp:   # keep the verified item, withhold the untraceable prose
            rejected.append(RejectedItem(what="ledger summary", text=summary, reasons=[str(p) for p in sp]))
            summary = ""
        lid = f"L{idx}"
        items.append(LedgerItem(id=lid, kind=r.kind, name=r.name, summary=summary, evidence=valid))
        ev_text[lid] = text
    return items, rejected, ev_text


def build_requirements(raw: JDOut) -> list[Requirement]:
    reqs = []
    for i, r in enumerate(raw.requirements, 1):
        kws = []
        for k in list(r.keywords) + detect_terms(r.text, generic=True):
            if k and k.lower() not in {x.lower() for x in kws}:
                kws.append(k)
        nc = classify_noncode(r.text)
        provable, note = True, ""
        if nc:
            note = "Not provable from a repo: " + ", ".join(nc) + "."
            provable = any(is_enforceable(k) for k in kws)   # a skill part may still be supported; the non-code part never is
        reqs.append(Requirement(id=f"R{i}", text=r.text, priority=r.priority, keywords=kws,
                                provable_from_repo=provable, note=note))
    return reqs


def validate_matches(reqs: list[Requirement], ledger: list[LedgerItem], ev_text: dict[str, str],
                     raw: MatchOut, user_items: list[UserItem], not_yours: set[str] | None = None) -> list[Match]:
    """Code-enforced matching: the LLM's status is only a proposal."""
    by_req = {m.requirement_id: m for m in raw.matches}
    known = {it.id for it in ledger}
    out = []
    for r in reqs:
        m = by_req.get(r.id)
        adj: list[str] = []
        status = m.status if m else "GAP"
        ids = [i for i in (m.ledger_ids if m else []) if i in known]
        dropped = [i for i in (m.ledger_ids if m else []) if i not in known]
        if any(i in (not_yours or set()) for i in dropped):
            adj.append(f"dropped evidence that {NOT_YOURS}")
        if any(i not in (not_yours or set()) for i in dropped):
            adj.append("dropped unknown ledger ids")
        nc = classify_noncode(r.text)
        if status != "GAP" and not ids:
            adj.append(f"{status} without valid ledger evidence -> GAP")
            status = "GAP"
        enforced = [k for k in r.keywords if is_enforceable(k)]
        if status != "GAP" and enforced:
            text = "\n".join(ev_text[i] for i in ids)
            covered = [k for k in enforced if in_text(k, text)]
            if not covered:
                adj.append(f"{status} -> GAP: none of {enforced} appears in the cited evidence")
                status, ids = "GAP", []
            elif len(covered) < len(enforced) and status == "SUPPORTED":
                adj.append(f"SUPPORTED -> PARTIAL: not found in evidence: {[k for k in enforced if k not in covered]}")
                status = "PARTIAL"
        if nc and not enforced:
            if status != "GAP":
                adj.append("non-code requirement cannot be proven by a repo -> GAP")
            status, ids = "GAP", []
        elif nc and status == "SUPPORTED":
            adj.append(f"SUPPORTED -> PARTIAL: repo cannot prove {', '.join(nc)}")
            status = "PARTIAL"
        mine = [u.text for u in user_items
                if status != "SUPPORTED" and enforced and any(in_text(k, u.text) for k in enforced)]
        found_in = "\n".join(ev_text[i] for i in ids) if status != "GAP" else ""
        missing = [k for k in enforced if not in_text(k, found_in)]
        out.append(Match(requirement_id=r.id, status=status, ledger_ids=ids if status != "GAP" else [], missing=missing,
                         rationale=(m.rationale if m else "No match returned."), adjustments=adj,
                         user_provided=mine, non_code=bool(nc and not enforced)))
    return out


def verify_bullets(repo: Repo, raw: GenerateOut, ledger_ids: set[str], req_ids: set[str],
                   author: Authorship | None = None):
    bullets, questions, rejected = [], [], []
    n = 0
    for b in raw.bullets:
        n += 1
        evs, usable, text, fails, excluded = check_evidence(repo, b.evidence, author)
        reasons = list(fails)
        if not b.evidence:
            reasons.append("no evidence cited")
        elif not usable:
            reasons += [f"not your work: {x}" for x in excluded] or ["no valid evidence"]
        if not reasons:
            reasons += [str(p) for p in check_claims(b.text, text)]
        status = "blocked" if reasons else "ok"
        if status == "ok" and excluded:     # never show someone else's code as support for a bullet
            evs = usable
            rejected += [RejectedItem(what="evidence", text=b.text, reasons=[x]) for x in excluded]
        bullets.append(Bullet(id=f"B{n}", text=b.text, status=status,
                              requirement_ids=[r for r in b.requirement_ids if r in req_ids],
                              ledger_ids=[l for l in b.ledger_ids if l in ledger_ids],
                              evidence=evs, block_reasons=reasons))
        if reasons:
            rejected.append(RejectedItem(what="bullet", text=b.text, reasons=reasons))
    for q in raw.interview:
        _, valid, text, fails, excluded = check_evidence(repo, q.evidence, author)
        if fails or not valid:
            rejected.append(RejectedItem(what="question", text=q.question,
                                         reasons=fails or excluded or ["no evidence cited"]))
            continue
        questions.append(Question(question=q.question, why=q.why, evidence=valid))
    return bullets, questions, rejected


# ---------------- orchestrator ----------------
def run_pipeline(repo_path: str, jd_text: str, provider: LLMProvider, *, user_items: list[UserItem] | None = None,
                 progress: Progress | None = None, authors: list[str] | None = None) -> RunResult:
    user_items = user_items or []
    prog = progress or (lambda *a: None)
    timings: dict[str, float] = {}
    step_modes: dict[str, str] = {}
    responses = []

    def call(step: str, req: LLMRequest):
        t = time.time()
        prog(step, "running", f"calling {provider.name}…")
        resp = provider.complete(req)
        timings[step] = round(time.time() - t, 2)
        step_modes[step] = resp.mode + (" (cached)" if resp.cached else "")
        responses.append(resp)
        prog(step, "done", f"{resp.mode}{' cached' if resp.cached else ''} in {timings[step]}s")
        return resp.data

    prog("ingest", "running", "reading repo and git history")
    repo = Repo(repo_path)
    rhash, jhash = repo.repo_hash(), _hash(jd_text)
    # fail on bad identities before spending any LLM calls
    author = Authorship(repo, authors) if normalize_ids(authors) else None
    not_yours: set[str] = set()
    prog("ingest", "done", f"{len(repo.files)} files, {len(repo.commits())} commits")

    led_raw = call("ledger", LLMRequest("ledger", prompts.SYSTEM, prompts.ledger_prompt(repo.digest()), LedgerOut,
                                        fingerprint=rhash, payload={"repo": repo}))
    ledger, rejected, ev_text = build_ledger(repo, led_raw, author, not_yours)

    jd_raw = call("jd_parse", LLMRequest("jd_parse", prompts.SYSTEM, prompts.jd_prompt(jd_text), JDOut,
                                         fingerprint=jhash, payload={"jd_text": jd_text}))
    reqs = build_requirements(jd_raw)

    req_view = [{"id": r.id, "text": r.text, "priority": r.priority, "keywords": r.keywords} for r in reqs]
    led_view = [{"id": it.id, "kind": it.kind, "name": it.name, "summary": it.summary,
                 "evidence": [{"label": e.label(), "quote": e.quote} for e in it.evidence],
                 "evidence_text": ev_text[it.id]} for it in ledger]
    led_prompt_view = [{k: v for k, v in d.items() if k != "evidence_text"} for d in led_view]
    match_raw = call("match", LLMRequest("match", prompts.SYSTEM, prompts.match_prompt(req_view, led_prompt_view),
                                         MatchOut, fingerprint=f"{rhash}-{jhash}",
                                         payload={"requirements": req_view, "ledger": led_view}))
    matches = validate_matches(reqs, ledger, ev_text, match_raw, user_items, not_yours)

    # full evidence objects (path/lines/commit) so the model can copy citations verbatim
    led_full = [{"id": it.id, "kind": it.kind, "name": it.name, "summary": it.summary,
                 "evidence": [e.model_dump(include={"kind", "path", "start_line", "end_line", "commit", "quote"},
                                           exclude_none=True) for e in it.evidence]} for it in ledger]
    m_view = [{"requirement_id": m.requirement_id, "status": m.status, "ledger_ids": m.ledger_ids} for m in matches]
    gen_raw = call("generate", LLMRequest("generate", prompts.SYSTEM,
                                          prompts.generate_prompt(req_view, m_view, led_full), GenerateOut,
                                          fingerprint=f"{rhash}-{jhash}",
                                          payload={"ledger": led_full, "matches": m_view, "requirements": req_view}))
    prog("verify", "running", "opening every citation…")
    bullets, questions, rej2 = verify_bullets(repo, gen_raw, {i.id for i in ledger}, {r.id for r in reqs}, author)
    rejected += rej2
    for u in user_items:
        bullets.append(Bullet(id=f"U{len([b for b in bullets if b.origin != 'verified']) + 1}", text=u.text,
                              status="ok", origin="user-provided, unverified"))
    ok = sum(b.status == "ok" and b.origin == "verified" for b in bullets)
    prog("verify", "done", f"{ok} bullets verified, {len(rejected)} items rejected")

    modes = {r.mode for r in responses}
    mode = modes.pop() if len(modes) == 1 else "REPLAYED" if "REPLAYED" in modes else "LIVE"
    meta = RunMeta(provider=provider.name, model=responses[0].model if responses else provider.model, mode=mode,
                   cached=all(r.cached for r in responses), repo_name=repo.name, repo_hash=rhash, jd_hash=jhash,
                   jd_title=jd_raw.title, step_modes=step_modes, timings_s=timings,
                   generated_at=max((r.generated_at for r in responses), default="") or
                   datetime.now(timezone.utc).isoformat(timespec="seconds"))
    notices = [CHECKED_NOTICE if author else UNCHECKED_NOTICE, NONCODE_NOTICE]
    report = author.report() if author else AuthorshipReport()
    notices += [f"AUTHORSHIP WARNING: {w}" for w in report.warnings]
    if mode == "REPLAYED":
        notices.insert(0, "REPLAYED: these LLM outputs were recorded earlier from a live run. They were NOT generated just now.")
    if mode == "MOCK":
        notices.insert(0, "MOCK: deterministic offline rules, not a real model.")
    if meta.cached:
        notices.insert(0, "CACHED: live output from an earlier identical run (same repo + JD).")
    return RunResult(meta=meta, ledger=ledger, requirements=reqs, matches=matches, bullets=bullets,
                     interview=questions, rejected=rejected, user_items=user_items, notices=notices,
                     authorship=report)
