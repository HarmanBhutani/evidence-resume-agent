"""One real run through the Claude Code CLI (skipped if not installed / not logged in / SKIP_LIVE=1).
Records into a temp dir, asserts integrity, then proves the recording replays as REPLAYED."""
import json
import os
import shutil
import subprocess

import pytest

from resume_agent.llm import get_provider
from resume_agent.llm.replay import ReplayProvider
from resume_agent.pipeline import run_pipeline
from conftest import assert_integrity


def cli_ready() -> str | None:
    if os.getenv("SKIP_LIVE") == "1":
        return "SKIP_LIVE=1"
    if not shutil.which(os.getenv("CLAUDE_BIN") or "claude"):
        return "claude CLI not installed"
    try:
        out = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, timeout=30).stdout
        return None if json.loads(out).get("loggedIn") else "claude CLI not logged in"
    except Exception as e:  # noqa: BLE001
        return f"cannot determine login state ({type(e).__name__})"


reason = cli_ready()


@pytest.mark.skipif(reason is not None, reason=reason or "")
def test_live_run_integrity_and_replay(repo_path, jds, tmp_path, monkeypatch):
    from resume_agent.llm import replay
    monkeypatch.setattr(replay, "DEFAULT_DIR", tmp_path / "rec")
    prov = get_provider("claude_cli", record=True, use_cache=False)
    r = run_pipeline(repo_path, jds["adversarial_infra_rust"], prov, authors=["demo@example.invalid"])
    assert r.meta.mode == "LIVE" and r.ledger and r.matches and r.authorship.checked
    shown = [e for i in r.ledger for e in i.evidence] + [e for b in r.bullets if b.status == "ok" for e in b.evidence]
    assert {e.authorship for e in shown} == {"mine"}
    assert_integrity(repo_path, r)
    status = {q.text: m.status for q, m in zip(r.requirements, r.matches)}
    for key in ("Terraform", "Rust", "Kubernetes", "Leading"):
        assert all(s == "GAP" for t, s in status.items() if key in t), status
    txt = " ".join(b.text for b in r.bullets if b.status == "ok").lower()
    assert "terraform" not in txt and "rust" not in txt
    rp = run_pipeline(repo_path, jds["adversarial_infra_rust"], ReplayProvider(tmp_path / "rec"))
    assert rp.meta.mode == "REPLAYED"
    assert [m.status for m in rp.matches] == [m.status for m in r.matches]
