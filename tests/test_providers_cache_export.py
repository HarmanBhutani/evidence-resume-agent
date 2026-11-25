import json

import pytest

from resume_agent.export import write_outputs
from resume_agent.llm import get_provider
from resume_agent.llm.base import LLMRequest, LLMResponse, NoRecording
from resume_agent.llm.cache import CachingProvider
from resume_agent.llm.claude_cli import ClaudeCLIProvider
from resume_agent.llm.replay import Recorder, ReplayProvider
from resume_agent.models import MatchOut
from resume_agent.pipeline import run_pipeline

REQ = LLMRequest("match", "S", "P", MatchOut, fingerprint="fp1")
GOOD = {"matches": [{"requirement_id": "R1", "status": "GAP"}]}


def test_factory_default_and_unknown(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert get_provider().name == "claude_cli"
    assert get_provider("mock").name == "mock" and get_provider("replay").name == "replay"
    with pytest.raises(ValueError):
        get_provider("nope")


def test_model_configurable(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "opus")
    assert get_provider("claude_cli", use_cache=False).model == "opus"


def test_record_then_replay_roundtrip(tmp_path, monkeypatch):
    live = ClaudeCLIProvider(recorder=Recorder(tmp_path))
    monkeypatch.setattr(live, "_run_once", lambda s, p: json.dumps(GOOD))
    assert live.complete(REQ).mode == "LIVE"
    r = ReplayProvider(tmp_path).complete(REQ)
    assert r.mode == "REPLAYED" and r.data.matches[0].requirement_id == "R1" and "recorded" in r.model


def test_replay_missing_recording_is_clear(tmp_path):
    with pytest.raises(NoRecording, match="No recorded response"):
        ReplayProvider(tmp_path).complete(REQ)


def test_cache_hit_skips_cli_and_is_flagged(tmp_path, monkeypatch):
    live = ClaudeCLIProvider()
    n = {"c": 0}
    def fake(s, p):
        n["c"] += 1
        return json.dumps(GOOD)
    monkeypatch.setattr(live, "_run_once", fake)
    cp = CachingProvider(live, tmp_path)
    a, b = cp.complete(REQ), cp.complete(REQ)
    assert n["c"] == 1 and not a.cached and b.cached and b.mode == "LIVE"
    other = LLMRequest("match", "S", "different prompt", MatchOut, fingerprint="fp1")
    cp.complete(other)
    assert n["c"] == 2


def test_replayed_pipeline_is_labelled_replayed(repo_path, jds, tmp_path):
    """Record from the mock-as-live stand-in, then replay: mode must read REPLAYED, never LIVE."""
    from resume_agent.llm.mock import MockProvider
    class Recording(MockProvider):
        def complete(self, req):
            resp = super().complete(req)
            Recorder(tmp_path)(req, resp.data.model_dump(mode="json"), LLMResponse(resp.data, "claude_cli", "sonnet", "LIVE", generated_at="2024-01-01T00:00:00+00:00"))
            return resp
    run_pipeline(repo_path, jds["python_api_engineer"], Recording())
    r = run_pipeline(repo_path, jds["python_api_engineer"], ReplayProvider(tmp_path))
    assert r.meta.mode == "REPLAYED" and r.meta.provider == "replay"
    assert any("REPLAYED" in n and "NOT generated just now" in n for n in r.notices)
    assert r.bullets and all(m == "REPLAYED" for m in r.meta.step_modes.values())


def test_export_writes_all_artifacts(repo_path, jds, tmp_path):
    r = run_pipeline(repo_path, jds["backend_streaming_engineer"], get_provider("mock"))
    d = write_outputs(r, tmp_path)
    for f in ("ledger.json", "match_report.json", "bullets.json", "interview_questions.json", "resume_bullets.md", "result.json"):
        assert (d / f).exists()
    md = (d / "resume_bullets.md").read_text()
    assert "MOCK" in md and "GAP" in md and "evidence:" in md
