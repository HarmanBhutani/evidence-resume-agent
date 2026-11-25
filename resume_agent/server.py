"""FastAPI server + single-page UI. Bind to localhost only (personal demo)."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .authorship import list_authors
from .ingest import Repo, RepoError
from .llm import LLMError, get_provider
from .models import Question, UserItem
from .practice import PracticeError, give_feedback
from .pipeline import STEPS, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "static"
DEMO_REPO = ROOT / "demo" / "sample_repo"
JD_DIR = ROOT / "demo" / "jds"

app = FastAPI(title="Evidence-Grounded Resume Agent")
JOBS: dict[str, dict] = {}
MAX_JOBS = 50          # keep memory bounded; oldest finished jobs are dropped


class RunRequest(BaseModel):
    repo_path: str
    jd_text: str
    user_items: list[str] = []
    authors: list[str] = []
    provider: str | None = None
    record: bool = False
    use_cache: bool = True


def ensure_demo_repo() -> None:
    if not (DEMO_REPO / ".git").exists():
        subprocess.run([sys.executable, str(ROOT / "demo" / "build_sample_repo.py")], check=True,
                       capture_output=True)


def _provider_info(name: str | None = None) -> dict:
    n = (name or os.getenv("LLM_PROVIDER") or "claude_cli").lower()
    mock = "mock-hallucination-attack" if os.getenv("MOCK_HALLUCINATE") == "1" else "mock-deterministic"
    model = {"mock": mock, "replay": "recorded"}.get(n, os.getenv("LLM_MODEL", "sonnet"))
    return {"provider": n, "model": model,
            "expected_mode": {"claude_cli": "LIVE", "replay": "REPLAYED", "mock": "MOCK"}.get(n, "?")}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})  # no stale UI after updates


@app.get("/learn")
def learn():
    return FileResponse(STATIC / "learn.html", headers={"Cache-Control": "no-store"})


@app.get("/static/sims.js")
def sims_js():
    return FileResponse(STATIC / "sims.js", media_type="text/javascript", headers={"Cache-Control": "no-store"})


@app.get("/api/config")
def config():
    import shutil
    return {**_provider_info(), "cli_found": bool(shutil.which(os.getenv("CLAUDE_BIN") or "claude")),
            "steps": STEPS}


@app.get("/api/demo")
def demo():
    ensure_demo_repo()
    jds = []
    for p in sorted(JD_DIR.glob("*.txt")):
        text = p.read_text()
        jds.append({"id": p.stem, "title": text.splitlines()[0], "text": text})
    return {"repo_path": str(DEMO_REPO), "demo_author": "demo@example.invalid", "jds": jds}


class FeedbackRequest(BaseModel):
    job_id: str
    question_index: int
    answer: str
    provider: str | None = None


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    j = JOBS.get(req.job_id)
    if not j or j.get("status") != "done":
        raise HTTPException(404, "Run an analysis first.")
    qs = j["result"]["interview"]
    if not 0 <= req.question_index < len(qs):
        raise HTTPException(404, "unknown question")
    name = (req.provider or j["provider"]["provider"]).lower()
    if name == "replay":
        raise HTTPException(400, "Answer feedback needs the live or mock provider: replay only has the recorded "
                                 "analysis, not feedback on new answers.")
    try:
        fb = give_feedback(Repo(j["repo_path"]), Question.model_validate(qs[req.question_index]), req.answer,
                           get_provider(name))
    except PracticeError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        return JSONResponse({"detail": f"{e.kind.replace('_', ' ').upper()}: {e}", "kind": e.kind}, status_code=502)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return fb.model_dump()


@app.get("/api/authors")
def authors(repo_path: str):
    return {"authors": list_authors(Repo(repo_path))}


def _worker(job_id: str, req: RunRequest) -> None:
    job = JOBS[job_id]

    def progress(step: str, state: str, detail: str) -> None:
        job["steps"][step] = {"state": state, "detail": detail}

    try:
        provider = get_provider(req.provider, record=req.record, use_cache=req.use_cache)
        result = run_pipeline(req.repo_path, req.jd_text, provider, progress=progress, authors=req.authors,
                              user_items=[UserItem(text=t) for t in req.user_items if t.strip()])
        job["result"], job["status"] = result.model_dump(mode="json"), "done"
    except LLMError as e:
        job.update(status="error", error={"kind": e.kind, "message": str(e)})
    except (RepoError, ValueError) as e:
        job.update(status="error", error={"kind": "input_error", "message": str(e)})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job.update(status="error", error={"kind": "internal", "message": f"{type(e).__name__}: {e}"})


@app.post("/api/run")
def run(req: RunRequest):
    if not req.jd_text.strip():
        raise HTTPException(400, "Paste a job description first.")
    for old in [k for k, v in JOBS.items() if v["status"] != "running"][:max(0, len(JOBS) - MAX_JOBS + 1)]:
        del JOBS[old]
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "steps": {s: {"state": "pending", "detail": ""} for s in STEPS},
                    "repo_path": req.repo_path, "provider": _provider_info(req.provider)}
    threading.Thread(target=_worker, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    return {k: v for k, v in j.items() if k != "repo_path"}


def _job_repo(job_id: str) -> Repo:
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    return Repo(j["repo_path"])


@app.get("/api/source")
def source(job_id: str, path: str, start: int = 1, end: int = 1, context: int = 6):
    lines = _job_repo(job_id).file_lines(path)
    if lines is None:
        raise HTTPException(404, "file not in repo")
    a, b = max(1, start - context), min(len(lines), end + context)
    return {"path": path, "start": start, "end": end,
            "lines": [{"n": i, "text": lines[i - 1], "hit": start <= i <= end} for i in range(a, b + 1)]}


@app.get("/api/commit")
def commit(job_id: str, hash: str):
    ct = _job_repo(job_id).commit_text(hash)
    if ct is None:
        raise HTTPException(404, "commit not found")
    return {"hash": ct[0], "text": ct[1][:20000]}


@app.exception_handler(RepoError)
def _repo_err(_, e: RepoError):
    return JSONResponse({"detail": str(e)}, status_code=400)


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn
    ensure_demo_repo()
    uvicorn.run(app, host=host, port=port, log_level="warning")
