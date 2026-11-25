"""Replay + record: serve saved live responses from samples/recorded/, or save new ones."""
from __future__ import annotations

import json
from pathlib import Path

from .base import LLMProvider, LLMRequest, LLMResponse, NoRecording

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "samples" / "recorded"


def record_path(directory: Path, task: str, fingerprint: str) -> Path:
    return directory / f"{task}__{fingerprint}.json"


class Recorder:
    """Callable used by the live provider to save each successful response."""

    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory or DEFAULT_DIR)

    def __call__(self, req: LLMRequest, data: dict, resp: LLMResponse) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        rec = {"task": req.task, "fingerprint": req.fingerprint, "provider": resp.provider,
               "model": resp.model, "recorded_at": resp.generated_at, "response": data}
        record_path(self.dir, req.task, req.fingerprint).write_text(json.dumps(rec, indent=2))


class ReplayProvider(LLMProvider):
    name = "replay"

    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory or DEFAULT_DIR)
        self.model = "recorded"

    def complete(self, req: LLMRequest) -> LLMResponse:
        p = record_path(self.dir, req.task, req.fingerprint)
        if not p.exists():
            raise NoRecording(f"No recorded response for task '{req.task}' and this input "
                              f"(expected {p.name}). Replay only works for inputs recorded from a live run; "
                              "use the sample repo + sample JDs, or switch to live/mock.")
        rec = json.loads(p.read_text())
        self.model = rec.get("model", "recorded")
        return LLMResponse(data=req.schema.model_validate(rec["response"]), provider="replay",
                           model=f"{rec.get('model', '?')} (recorded)", mode="REPLAYED",
                           generated_at=rec.get("recorded_at", ""))
