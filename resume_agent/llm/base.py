"""Provider interface. A provider turns an LLMRequest into a validated pydantic object."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class LLMError(Exception):
    """Base error; `kind` is shown in the UI."""
    kind = "llm_error"


class CLIMissing(LLMError):
    kind = "cli_missing"


class NotLoggedIn(LLMError):
    kind = "not_logged_in"


class UsageLimit(LLMError):
    kind = "usage_limit"


class LLMTimeout(LLMError):
    kind = "timeout"


class InvalidOutput(LLMError):
    kind = "invalid_output"


class NoRecording(LLMError):
    kind = "no_recording"


@dataclass
class LLMRequest:
    task: str                      # ledger | jd_parse | match | generate
    system: str
    prompt: str
    schema: type[BaseModel]
    fingerprint: str = ""          # stable input id (used by replay/record)
    payload: dict[str, Any] = field(default_factory=dict)  # structured inputs (used by mock only)


@dataclass
class LLMResponse:
    data: BaseModel
    provider: str
    model: str
    mode: str                      # LIVE | REPLAYED | MOCK
    duration_s: float = 0.0
    cached: bool = False
    generated_at: str = ""


class LLMProvider(ABC):
    name = "base"
    model = ""

    @abstractmethod
    def complete(self, req: LLMRequest) -> LLMResponse: ...


def extract_json(text: str) -> Any:
    """Parse a JSON object out of model text (tolerates ``` fences and chatter around it)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a == -1 or b <= a:
            raise
        return json.loads(t[a:b + 1])
