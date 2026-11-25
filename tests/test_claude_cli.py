import json
import subprocess

import pytest

from resume_agent.llm.base import (CLIMissing, InvalidOutput, LLMError, LLMRequest, LLMTimeout, NotLoggedIn,
                                   UsageLimit)
from resume_agent.llm.claude_cli import ClaudeCLIProvider
from resume_agent.models import MatchOut

REQ = LLMRequest("match", "SYS", "PROMPT with repo text", MatchOut, fingerprint="f")
GOOD = {"matches": [{"requirement_id": "R1", "status": "GAP"}]}


def envelope(result, is_error=False):
    return json.dumps({"type": "result", "is_error": is_error, "result": result})


class Fake:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        o = self.outputs.pop(0)
        if isinstance(o, Exception):
            raise o
        out, err, code = o
        return subprocess.CompletedProcess(cmd, code, out, err)


@pytest.fixture
def run(monkeypatch):
    def _run(outputs, **kw):
        f = Fake(outputs)
        monkeypatch.setattr(subprocess, "run", f)
        return f, ClaudeCLIProvider(binary="claude", **kw)
    return _run


def test_success_and_safe_invocation(run, monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-passed")
    f, p = run([(envelope(json.dumps(GOOD)), "", 0)])
    resp = p.complete(REQ)
    assert resp.mode == "LIVE" and resp.data.matches[0].status == "GAP"
    cmd, kw = f.calls[0]
    assert cmd[:2] == ["claude", "-p"] and "--output-format" in cmd and "json" in cmd
    assert cmd[cmd.index("--tools") + 1] == "" and "--no-session-persistence" in cmd
    assert "--disable-slash-commands" in cmd and cmd[cmd.index("--model") + 1] == "sonnet"
    assert kw["input"] == REQ.prompt                       # prompt via stdin, not argv
    assert REQ.prompt not in " ".join(cmd)
    assert "ANTHROPIC_API_KEY" not in kw["env"]
    assert kw["cwd"] != "." and "resume_agent_llm_" in kw["cwd"] and kw["timeout"] == 300


def test_fenced_json_accepted(run):
    _, p = run([(envelope("```json\n" + json.dumps(GOOD) + "\n```"), "", 0)])
    assert p.complete(REQ).data.matches


def test_bad_json_retries_once_then_succeeds(run):
    f, p = run([(envelope("sorry, here you go"), "", 0), (envelope(json.dumps(GOOD)), "", 0)])
    assert p.complete(REQ).data.matches and len(f.calls) == 2
    assert "not valid" in f.calls[1][1]["input"]


def test_bad_json_twice_fails(run):
    f, p = run([(envelope("nope"), "", 0), (envelope('{"matches": 5}'), "", 0)])
    with pytest.raises(InvalidOutput):
        p.complete(REQ)
    assert len(f.calls) == 2


def test_timeout(run):
    _, p = run([subprocess.TimeoutExpired("claude", 5)], timeout=5)
    with pytest.raises(LLMTimeout, match="timed out"):
        p.complete(REQ)


def test_not_logged_in(run):
    _, p = run([(envelope("Not logged in · Please run /login", True), "", 1)])
    with pytest.raises(NotLoggedIn):
        p.complete(REQ)


def test_usage_limit(run):
    _, p = run([(envelope("Claude AI usage limit reached|1700000000", True), "", 1)])
    with pytest.raises(UsageLimit):
        p.complete(REQ)


def test_limit_via_stderr_only(run):
    _, p = run([("", "You've hit your limit", 1)])
    with pytest.raises(UsageLimit):
        p.complete(REQ)


def test_cli_missing(run):
    _, p = run([FileNotFoundError()])
    with pytest.raises(CLIMissing):
        p.complete(REQ)


def test_unknown_failure_is_clear(run):
    _, p = run([("", "boom", 3)])
    with pytest.raises(LLMError, match="exit 3"):
        p.complete(REQ)
