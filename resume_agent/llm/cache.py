"""Disk cache for live responses, keyed by hash of (task, model, prompt) -> i.e. repo + JD content."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .base import LLMProvider, LLMRequest, LLMResponse

DEFAULT_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "llm"


class CachingProvider(LLMProvider):
    """Wraps a live provider. Cached results are still LIVE output but flagged cached=True."""

    def __init__(self, inner: LLMProvider, directory: Path | None = None):
        self.inner = inner
        self.dir = Path(directory or DEFAULT_CACHE)
        self.name, self.model = inner.name, inner.model

    def _key(self, req: LLMRequest) -> Path:
        h = hashlib.sha256(f"{req.task}|{self.inner.model}|{req.system}|{req.prompt}".encode()).hexdigest()[:32]
        return self.dir / f"{req.task}_{h}.json"

    def complete(self, req: LLMRequest) -> LLMResponse:
        p = self._key(req)
        if p.exists():
            try:
                rec = json.loads(p.read_text())
                resp = LLMResponse(data=req.schema.model_validate(rec["response"]), provider=self.name,
                                   model=self.model, mode="LIVE", cached=True,
                                   generated_at=rec.get("generated_at", ""))
                recorder = getattr(self.inner, "recorder", None)
                if recorder:   # keep recordings of one session consistent (e.g. one ledger for all JDs)
                    recorder(req, resp.data.model_dump(mode="json"), resp)
                return resp
            except Exception:
                p.unlink(missing_ok=True)
        resp = self.inner.complete(req)
        self.dir.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"generated_at": resp.generated_at, "response": resp.data.model_dump(mode="json")}))
        return resp
