"""Provider factory. LLM_PROVIDER = claude_cli (default) | mock | replay."""
from __future__ import annotations

import os

from .base import (CLIMissing, InvalidOutput, LLMError, LLMProvider, LLMRequest, LLMResponse,  # noqa: F401
                   LLMTimeout, NoRecording, NotLoggedIn, UsageLimit)


def get_provider(name: str | None = None, *, record: bool = False, use_cache: bool = True) -> LLMProvider:
    name = (name or os.getenv("LLM_PROVIDER") or "claude_cli").strip().lower()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider(hallucinate=os.getenv("MOCK_HALLUCINATE") == "1")
    if name == "replay":
        from .replay import ReplayProvider
        return ReplayProvider()
    if name == "claude_cli":
        from .cache import CachingProvider
        from .claude_cli import ClaudeCLIProvider
        from .replay import Recorder
        rec = Recorder() if (record or os.getenv("LLM_RECORD") == "1") else None
        p = ClaudeCLIProvider(model=os.getenv("LLM_MODEL", "sonnet"),
                              timeout=int(os.getenv("LLM_TIMEOUT", "300")), recorder=rec)
        return CachingProvider(p) if use_cache else p
    raise ValueError(f"Unknown LLM_PROVIDER '{name}' (use claude_cli, mock, or replay)")
