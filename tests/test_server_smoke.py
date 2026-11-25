"""UI/server smoke: start the real server, drive a full flow over HTTP, check the page & JS."""
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def server(repo_path):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = dict(os.environ, LLM_PROVIDER="mock")
    proc = subprocess.Popen([sys.executable, "-m", "resume_agent", "serve", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(base + "/api/config", timeout=1); break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill(); pytest.fail("server did not start")
    yield base, proc
    proc.terminate()
    out = proc.communicate(timeout=10)[0]
    assert "Traceback" not in out and "ERROR" not in out, out


def wait(base, job):
    for _ in range(100):
        j = httpx.get(f"{base}/api/jobs/{job}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.1)
    pytest.fail("job timed out")


def test_full_flow_over_http(server, jds):
    base, _ = server
    assert "Evidence Ledger" in httpx.get(base + "/").text
    assert "Load balancing" in httpx.get(base + "/learn").text
    assert "LoadBalancerSim" in httpx.get(base + "/static/sims.js").text
    cfg = httpx.get(base + "/api/config").json()
    assert cfg["provider"] == "mock" and cfg["expected_mode"] == "MOCK"
    demo = httpx.get(base + "/api/demo").json()
    assert len(demo["jds"]) == 3
    people = httpx.get(base + "/api/authors", params={"repo_path": demo["repo_path"]}).json()["authors"]
    assert [a["email"] for a in people] == [demo["demo_author"]]
    job = httpx.post(base + "/api/run", json={"repo_path": demo["repo_path"], "jd_text": jds["backend_streaming_engineer"],
                                              "user_items": ["Mentored 2 juniors"], "authors": [demo["demo_author"]]}).json()["job_id"]
    j = wait(base, job)
    assert j["status"] == "done" and all(s["state"] == "done" for s in j["steps"].values())
    res = j["result"]
    assert res["meta"]["mode"] == "MOCK" and res["ledger"] and res["bullets"] and res["authorship"]["checked"]
    fb = httpx.post(base + "/api/feedback", json={"job_id": job, "question_index": 0,
                                                 "answer": "I commit offsets after processing because a crash would lose messages."}, timeout=30)
    assert fb.status_code == 200 and fb.json()["mode"] == "MOCK" and set(fb.json()["scores"]) == {"correctness", "tradeoffs", "failure_modes", "clarity"}
    assert httpx.post(base + "/api/feedback", json={"job_id": job, "question_index": 0, "answer": " "}).status_code == 400
    assert httpx.post(base + "/api/feedback", json={"job_id": job, "question_index": 99, "answer": "x"}).status_code == 404
    assert httpx.post(base + "/api/feedback", json={"job_id": job, "question_index": 0, "answer": "x",
                                                    "provider": "replay"}).status_code == 400
    bad = httpx.post(base + "/api/run", json={"repo_path": demo["repo_path"], "jd_text": "x",
                                              "authors": ["typo@example.invalid"]}).json()["job_id"]
    assert wait(base, bad)["error"]["kind"] == "input_error"
    # clickable citations: open one file and one commit citation through the API
    fe = next(e for it in res["ledger"] for e in it["evidence"] if e["kind"] == "file")
    src = httpx.get(f"{base}/api/source", params={"job_id": job, "path": fe["path"], "start": fe["start_line"], "end": fe["end_line"]}).json()
    assert any(l["hit"] and fe["quote"].split()[0] in l["text"] for l in src["lines"])
    ce = next(e for it in res["ledger"] for e in it["evidence"] if e["kind"] == "commit")
    assert ce["quote"] in httpx.get(f"{base}/api/commit", params={"job_id": job, "hash": ce["resolved_commit"]}).json()["text"]
    assert httpx.get(f"{base}/api/source", params={"job_id": job, "path": "../../etc/passwd"}).status_code == 404


def test_errors_are_surfaced(server, jds):
    base, _ = server
    assert httpx.post(base + "/api/run", json={"repo_path": "x", "jd_text": " "}).status_code == 400
    job = httpx.post(base + "/api/run", json={"repo_path": "/nonexistent/repo", "jd_text": "- Python"}).json()["job_id"]
    j = wait(base, job)
    assert j["status"] == "error" and j["error"]["kind"] == "input_error"
    job = httpx.post(base + "/api/run", json={"repo_path": str(ROOT / "demo/sample_repo"), "jd_text": "- Python", "provider": "replay"}).json()["job_id"]
    j = wait(base, job)
    assert j["status"] == "error" and j["error"]["kind"] == "no_recording"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("page", ["index.html", "learn.html"])
def test_ui_javascript_parses(tmp_path, page):
    html = (ROOT / "resume_agent/static" / page).read_text()
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    f = tmp_path / "ui.js"; f.write_text(js)
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_authors_endpoint(repo_path):
    from resume_agent.server import authors
    assert [a["email"] for a in authors(repo_path)["authors"]] == ["demo@example.invalid"]
