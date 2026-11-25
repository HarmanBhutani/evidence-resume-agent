"""CLI: python -m resume_agent {serve,run,demo,build-sample}"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .authorship import list_authors
from .export import write_outputs
from .ingest import Repo, RepoError
from .llm import LLMError, get_provider
from .models import UserItem
from .pipeline import run_pipeline
from .server import DEMO_REPO, JD_DIR, ROOT, ensure_demo_repo


DEMO_AUTHOR = "demo@example.invalid"   # the synthetic author of demo/sample_repo


def _summary(r) -> str:
    c = {s: sum(m.status == s for m in r.matches) for s in ("SUPPORTED", "PARTIAL", "GAP")}
    ok = sum(b.status == "ok" and b.origin == "verified" for b in r.bullets)
    bl = sum(b.status == "blocked" for b in r.bullets)
    return (f"[{r.meta.mode}{' cached' if r.meta.cached else ''} · {r.meta.provider}/{r.meta.model}] "
            f"ledger={len(r.ledger)} reqs: {c['SUPPORTED']} supported / {c['PARTIAL']} partial / {c['GAP']} gap · "
            f"bullets: {ok} ok, {bl} blocked · questions={len(r.interview)} · rejected={len(r.rejected)}")


def _progress(step, state, detail):
    if state == "done":
        print(f"  ✓ {step}: {detail}", flush=True)


def cmd_run(a) -> int:
    jd = Path(a.jd).read_text()
    prov = get_provider(a.provider, record=a.record, use_cache=not a.no_cache)
    r = run_pipeline(a.repo, jd, prov, progress=_progress, authors=a.author,
                     user_items=[UserItem(text=t) for t in a.user_item])
    if not r.authorship.checked:
        print("NOTE: authorship not checked. Pass --author <your commit email> to check it.")
    for w in r.authorship.warnings:
        print(f"WARNING: {w}")
    out = write_outputs(r, a.out)
    print(_summary(r))
    print(f"outputs written to {out}")
    return 0


def cmd_demo(a) -> int:
    ensure_demo_repo()
    prov = get_provider(a.provider, record=a.record, use_cache=not a.no_cache)
    for p in sorted(JD_DIR.glob("*.txt")):
        print(f"\n== {p.stem}")
        r = run_pipeline(str(DEMO_REPO), p.read_text(), prov, progress=_progress, authors=[DEMO_AUTHOR])
        out = write_outputs(r, Path(a.out) / r.meta.mode.lower() / p.stem)
        print(_summary(r))
        for q, m in zip(r.requirements, r.matches):
            print(f"   {m.status:9} {q.text[:70]}")
        print(f"   -> {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="resume_agent")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("serve"); s.add_argument("--port", type=int, default=8000)
    for name in ("run", "demo"):
        p = sp.add_parser(name)
        p.add_argument("--provider", choices=["claude_cli", "mock", "replay"])
        p.add_argument("--record", action="store_true", help="save live responses to samples/recorded/")
        p.add_argument("--no-cache", action="store_true")
        p.add_argument("--out", default=str(ROOT / "out"))
        if name == "run":
            p.add_argument("--repo", required=True); p.add_argument("--jd", required=True)
            p.add_argument("--author", action="append", default=[],
                           help="your commit email (repeatable); only your code then counts as evidence")
            p.add_argument("--user-item", action="append", default=[], help="unverified, labeled as such")
    sp.add_parser("build-sample")
    sp.add_parser("authors", help="list commit emails in a repo").add_argument("--repo", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "serve":
            from .server import main as serve
            serve(port=a.port); return 0
        if a.cmd == "build-sample":
            import subprocess
            return subprocess.call([sys.executable, str(ROOT / "demo" / "build_sample_repo.py")])
        if a.cmd == "authors":
            for x in list_authors(Repo(a.repo)):
                print(f"{x['commits']:5}  {x['email']}  ({x['name']})")
            return 0
        return cmd_run(a) if a.cmd == "run" else cmd_demo(a)
    except RepoError as e:
        print(f"\nERROR (input_error): {e}", file=sys.stderr)
        return 2
    except LLMError as e:
        print(f"\nERROR ({e.kind}): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
