"""LLM calls through the locally installed Claude Code CLI (`claude -p`).

Security notes:
- Subprocess only. We never read, copy, or store any Claude login/OAuth token; the CLI uses
  its own stored login. ANTHROPIC_API_KEY is removed from the child env so the Pro login is used.
- Prompt goes over stdin. Tools are disabled (`--tools ""`), no session is persisted, slash
  commands/skills and user/project settings are off, and the child runs in an empty temp dir.
- Prompts/responses are never logged; only metadata.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone

from pydantic import ValidationError

from .base import (CLIMissing, InvalidOutput, LLMError, LLMProvider, LLMRequest, LLMResponse,
                   LLMTimeout, NotLoggedIn, UsageLimit, extract_json)

log = logging.getLogger("resume_agent.claude_cli")

_NOT_LOGGED_IN = re.compile(r"not logged in|please run /login|/login|invalid api key|authentication|"
                            r"unauthorized|oauth token (has )?expired|401", re.I)
_LIMIT = re.compile(r"usage limit|limit reached|hit your limit|rate.?limit|quota|too many requests|429|"
                    r"limit will reset|resets? at", re.I)


class ClaudeCLIProvider(LLMProvider):
    name = "claude_cli"

    def __init__(self, model: str = "sonnet", timeout: int = 300, binary: str | None = None,
                 recorder=None):
        self.model = model
        self.timeout = timeout
        self.binary = binary or os.getenv("CLAUDE_BIN") or shutil.which("claude") or "claude"
        self.recorder = recorder  # optional callable(req, data_dict, response)

    # -- subprocess --
    def _build_cmd(self, system: str) -> list[str]:
        return [self.binary, "-p", "--output-format", "json", "--model", self.model,
                "--tools", "", "--no-session-persistence", "--disable-slash-commands",
                "--strict-mcp-config", "--setting-sources", "", "--system-prompt", system]

    def _run_once(self, system: str, prompt: str) -> str:
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with tempfile.TemporaryDirectory(prefix="resume_agent_llm_") as tmp:
            try:
                proc = subprocess.run(self._build_cmd(system), input=prompt, capture_output=True, text=True,
                                      timeout=self.timeout, cwd=tmp, env=env)
            except FileNotFoundError as e:
                raise CLIMissing("Claude Code CLI not found. Install it and log in (run `claude`), "
                                 "or set CLAUDE_BIN.") from e
            except subprocess.TimeoutExpired as e:
                raise LLMTimeout(f"Claude CLI timed out after {self.timeout}s "
                                 "(raise LLM_TIMEOUT or switch to LLM_PROVIDER=replay).") from e
        out, err = proc.stdout or "", proc.stderr or ""
        envelope = None
        try:
            envelope = json.loads(out) if out.strip() else None
        except json.JSONDecodeError:
            envelope = None
        if isinstance(envelope, dict):
            result = str(envelope.get("result", ""))
            if envelope.get("is_error") or proc.returncode != 0:
                self._raise_for(result or err, proc.returncode)
            return result
        self._raise_for(err or out or "empty output", proc.returncode)
        return out  # not reached

    @staticmethod
    def _raise_for(text: str, code: int) -> None:
        msg = (text or "").strip()[:400]
        if _NOT_LOGGED_IN.search(msg):
            raise NotLoggedIn(f"Claude CLI is not logged in. Run `claude` once and log in. ({msg})")
        if _LIMIT.search(msg):
            raise UsageLimit(f"Claude usage limit reached. Wait for reset or use replay mode. ({msg})")
        raise LLMError(f"Claude CLI failed (exit {code}): {msg}")

    # -- provider API --
    def complete(self, req: LLMRequest) -> LLMResponse:
        t0 = time.time()
        prompt = req.prompt
        last_err = ""
        for attempt in (1, 2):
            text = self._run_once(req.system, prompt)
            try:
                data = req.schema.model_validate(extract_json(text))
                resp = LLMResponse(data=data, provider=self.name, model=self.model, mode="LIVE",
                                   duration_s=round(time.time() - t0, 2),
                                   generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                if self.recorder:
                    self.recorder(req, data.model_dump(mode="json"), resp)
                return resp
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_err = str(e)[:300]
                log.warning("task=%s attempt=%d invalid output (%s)", req.task, attempt, type(e).__name__)
                prompt = (req.prompt + "\n\nYour previous reply was not valid for the required schema: "
                          f"{last_err}\nReply again with ONLY the corrected JSON object, no prose, no code fences.")
        raise InvalidOutput(f"Claude returned invalid JSON twice for task '{req.task}': {last_err}")
