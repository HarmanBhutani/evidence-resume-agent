"""Build the online demo: a static copy of the UI plus precomputed results (no server, no model calls).

    python scripts/build_site.py [out_dir]      (default: site/)

Results come from the recorded live responses in samples/recorded/ (labeled REPLAYED) and the offline
mock provider (normal and hallucination-attack mode), for the synthetic sample repo and the three
sample jobs, with the authorship check on and off. The output can be served by any static host
(GitHub Pages, Netlify Drop, ...).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from resume_agent.ingest import Repo  # noqa: E402
from resume_agent.llm.mock import MockProvider  # noqa: E402
from resume_agent.llm.replay import ReplayProvider  # noqa: E402
from resume_agent.pipeline import STEPS, run_pipeline  # noqa: E402
from resume_agent.server import DEMO_REPO, JD_DIR, STATIC, ensure_demo_repo  # noqa: E402

DEMO_AUTHOR = "demo@example.invalid"
PROVIDERS = {"replay": ReplayProvider, "mock": MockProvider, "mock_attack": lambda: MockProvider(hallucinate=True)}
FORBIDDEN = [str(ROOT), str(Path.home()), "/Users/", "/home/", "C:\\\\"]   # never publish local paths


def page(name: str) -> str:
    """Static copies of the pages: server routes become relative files (works under any sub-path)."""
    html = (STATIC / name).read_text()
    html = html.replace('"/learn', '"learn.html').replace('href="/"', 'href="index.html"')
    html = html.replace('src="/static/sims.js"', 'src="sims.js"')
    if name == "index.html":
        html = html.replace("<script>\n", '<script src="static-demo.js"></script>\n<script>\n', 1)
    return html


def build(out: Path) -> Path:
    ensure_demo_repo()
    if out.exists():
        shutil.rmtree(out)
    (out / "data" / "results").mkdir(parents=True)
    for name in ("index.html", "learn.html"):
        (out / name).write_text(page(name))
    for name in ("sims.js", "static-demo.js"):
        shutil.copy(STATIC / name, out / name)
    (out / ".nojekyll").write_text("")            # serve files as-is on GitHub Pages

    repo = Repo(DEMO_REPO)
    commits = {c.hash: repo.commit_text(c.hash)[1] for c in repo.commits()}
    (out / "data" / "repo.json").write_text(json.dumps({"files": repo.files, "commits": commits}))

    jds = []
    for p in sorted(JD_DIR.glob("*.txt")):
        text = p.read_text()
        jds.append({"id": p.stem, "title": text.splitlines()[0], "text": text})
        for prov, make in PROVIDERS.items():
            for auth in ("checked", "unchecked"):
                r = run_pipeline(str(DEMO_REPO), text, make(), authors=[DEMO_AUTHOR] if auth == "checked" else None)
                (out / "data" / "results" / f"{prov}__{p.stem}__{auth}.json").write_text(r.model_dump_json())
    from resume_agent.authorship import list_authors
    demo = {"repo_path": "demo/sample_repo (synthetic)", "demo_author": DEMO_AUTHOR, "jds": jds,
            "authors": list_authors(repo), "providers": list(PROVIDERS),
            "config": {"provider": "replay", "model": "recorded", "expected_mode": "REPLAYED", "cli_found": False,
                       "static": True, "steps": STEPS}}
    (out / "data" / "demo.json").write_text(json.dumps(demo))

    for f in out.rglob("*"):
        if f.is_file():
            text = f.read_text(errors="replace")
            leaks = [x for x in FORBIDDEN if x and x in text]
            if leaks:
                raise SystemExit(f"refusing to build: {f.relative_to(out)} contains a local path ({leaks[0]!r})")
    return out


if __name__ == "__main__":
    out = build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site")
    n = len(list((out / "data" / "results").glob("*.json")))
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"built {out} : {n} precomputed results, {size // 1024} KB")
