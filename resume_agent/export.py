"""Write a RunResult to disk as separate artifacts + a Markdown resume snippet."""
from __future__ import annotations

import json
from pathlib import Path

from .models import RunResult


def cite(e) -> str:
    tag = {"mine": " (yours)", "mixed": " (partly yours)", "not_mine": " (not yours)"}.get(e.authorship, "")
    return e.label() + tag


def to_markdown(r: RunResult) -> str:
    m = r.meta
    banner = f"{m.mode}{' (cached)' if m.cached else ''} · provider={m.provider} · model={m.model}"
    out = [f"# Tailored bullets: {m.jd_title or 'job'}", "", f"> Output mode: **{banner}** · repo `{m.repo_name}` "
           f"@ `{m.repo_hash}`", ""]
    a = r.authorship
    out += [f"> Authorship: **{'checked for ' + ', '.join(a.identities) if a.checked else 'NOT CHECKED'}**", ""]
    out += [f"> {n}" for n in r.notices] + [""]
    out.append("## Requirement match")
    by = {x.requirement_id: x for x in r.matches}
    for q in r.requirements:
        mm = by[q.id]
        extra = f" — {'; '.join(mm.adjustments)}" if mm.adjustments else ""
        if mm.missing:
            extra += f" — not found in the code: {', '.join(mm.missing)}"
        tag = " (non-code: cannot be proven from a repo)" if mm.non_code else ""
        out.append(f"- **{mm.status}** [{q.priority}] {q.text}{tag}{extra}")
    out += ["", "## Bullets (every claim cites repo evidence)"]
    for b in r.bullets:
        if b.status == "ok":
            refs = "; ".join(f"`{cite(e)}`" for e in b.evidence) or f"_{b.origin}_"
            out.append(f"- {b.text}  \n  evidence: {refs}")
    blocked = [b for b in r.bullets if b.status == "blocked"]
    if blocked:
        out += ["", "## Blocked by the verifier"]
        out += [f"- ~~{b.text}~~ — {'; '.join(b.block_reasons)}" for b in blocked]
    out += ["", "## Interview prep (from your own code)"]
    for q in r.interview:
        out.append(f"- {q.question}  \n  based on: {'; '.join(f'`{cite(e)}`' for e in q.evidence)}")
    return "\n".join(out) + "\n"


def write_outputs(r: RunResult, outdir: str | Path) -> Path:
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (d / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")  # noqa: E731
    meta = {**r.meta.model_dump(), "authorship": r.authorship.model_dump()}
    dump("ledger.json", {"meta": meta, "items": [i.model_dump() for i in r.ledger],
                         "rejected": [x.model_dump() for x in r.rejected if x.what in ("ledger item", "ledger summary", "evidence")]})
    dump("match_report.json", {"meta": meta, "requirements": [q.model_dump() for q in r.requirements],
                               "matches": [x.model_dump() for x in r.matches]})
    dump("bullets.json", {"meta": meta, "bullets": [b.model_dump() for b in r.bullets],
                          "rejected": [x.model_dump() for x in r.rejected if x.what == "bullet"]})
    dump("interview_questions.json", {"meta": meta, "questions": [q.model_dump() for q in r.interview]})
    dump("result.json", r.model_dump())
    (d / "resume_bullets.md").write_text(to_markdown(r))
    return d
