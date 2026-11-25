"""Deterministic offline 'LLM'. Rule-based, works from the structured payload (not the prompt).

MockProvider(hallucinate=True) additionally tries to cheat in every step (invented skill, fake
citations, invented metrics, GAPs claimed as SUPPORTED) so tests can prove the verifier blocks it.
"""
from __future__ import annotations

import re

from ..techvocab import detect_terms, in_text
from .base import LLMProvider, LLMRequest, LLMResponse

# name, kind, evidence regexes (searched in file lines, first hit each), summary (only mentions terms in its quotes)
RECIPES = [
    ("Kafka consumer with manual offset commits", "skill", [r"KafkaConsumer", r"enable_auto_commit\s*=\s*False"],
     "Built a Kafka consumer that disables auto commit and commits offsets after processing."),
    ("Retry with exponential backoff", "skill", [r"def backoff_delay", r"range\(self\.settings\.max_retries\)"],
     "Implemented retry handling with a capped exponential backoff."),
    ("Dead-letter queue for poison messages", "achievement", [r"def send_to_dlq", r"dlq_topic"],
     "Added dead-letter queue publishing so failed messages are routed to a DLQ topic."),
    ("Idempotent order upserts", "skill", [r"ON CONFLICT", r"excluded\.version > orders\.version"],
     "Made order writes idempotent with an upsert that ignores stale versions."),
    ("REST API with FastAPI", "skill", [r"from fastapi import", r"@app\.get\(\"/orders/\{order_id\}\"\)"],
     "Built REST endpoints with FastAPI for order lookup."),
    ("Cursor pagination", "skill", [r"def list_orders\(limit", r"Cursor-paginated listing"],
     "Implemented cursor pagination for order listing."),
    ("Prometheus metrics", "skill", [r"from prometheus_client import", r"Counter\("],
     "Instrumented the service with Prometheus counters and a histogram."),
    ("Automated testing with pytest", "skill", [r"import pytest", r"def test_\w+"],
     "Wrote automated tests with pytest."),
    ("SQLite persistence", "skill", [r"import sqlite3", r"sqlite3\.connect"],
     "Persisted order data in SQLite."),
    ("Docker containerization", "skill", [r"^FROM python", r"^CMD "],
     "Containerized the service with a Dockerfile."),
    ("GitHub Actions CI", "skill", [r"runs-on:", r"run: pytest"],
     "Set up a GitHub Actions workflow that runs pytest."),
    ("Python service development", "skill", [r"^import |^from ", r"^def |^class "],
     "Developed the service in Python."),
]
COMMIT_RECIPES = [(r"dead-letter", "Shipped dead-letter queue handling"), (r"retry", "Shipped consumer retries"),
                  (r"pagination", "Shipped cursor pagination")]


class MockProvider(LLMProvider):
    name = "mock"
    model = "mock-deterministic"

    def __init__(self, hallucinate: bool = False):
        self.hallucinate = hallucinate
        if hallucinate:   # make the attack mode visible in badges and exports
            self.model = "mock-hallucination-attack"

    def complete(self, req: LLMRequest) -> LLMResponse:
        fn = getattr(self, f"_{req.task}")
        raw = fn(req.payload)
        return LLMResponse(data=req.schema.model_validate(raw), provider="mock", model=self.model,
                           mode="MOCK", generated_at="")

    # ---- ledger ----
    def _ledger(self, p: dict) -> dict:
        repo = p["repo"]
        items = []
        for name, kind, pats, summary in RECIPES:
            evs = []
            for pat in pats:
                rx = re.compile(pat)
                hit = None
                for path in sorted(repo.files, key=lambda x: (x.startswith("tests/"), x)):
                    if name.startswith("Automated testing") != path.startswith("tests/"):
                        continue
                    if path.endswith(".md"):
                        continue
                    for i, line in enumerate(repo.files[path], 1):
                        if rx.search(line):
                            hit = {"kind": "file", "path": path, "start_line": i, "end_line": i,
                                   "quote": line.strip()}
                            break
                    if hit:
                        break
                if hit:
                    evs.append(hit)
            if evs:
                items.append({"kind": kind, "name": name, "summary": summary, "evidence": evs})
        for c in repo.commits():
            for pat, label in COMMIT_RECIPES:
                if re.search(pat, c.subject, re.I):
                    items.append({"kind": "achievement", "name": f"{label} (commit)",
                                  "summary": c.subject + ".",
                                  "evidence": [{"kind": "commit", "commit": c.hash[:10], "quote": c.subject}]})
        if self.hallucinate:
            items.append({"kind": "skill", "name": "Terraform infrastructure as code",
                          "summary": "Managed AWS infrastructure with Terraform modules.",
                          "evidence": [{"kind": "file", "path": "infra/main.tf", "start_line": 1, "end_line": 8,
                                        "quote": "resource \"aws_msk_cluster\" \"main\" {"}]})
            items.append({"kind": "achievement", "name": "Kafka pipeline at 2M events/day",
                          "summary": "Scaled the Kafka consumer to 2M events per day.",
                          "evidence": [{"kind": "file", "path": "orderflow/consumer.py", "start_line": 1,
                                        "end_line": 1, "quote": "Kafka consumer for order events"}]})
            items.append({"kind": "skill", "name": "Rust systems programming", "summary": "Wrote Rust services.",
                          "evidence": [{"kind": "commit", "commit": "deadbeef", "quote": "Rewrite hot path in Rust"}]})
        return {"items": items}

    # ---- jd ----
    def _jd_parse(self, p: dict) -> dict:
        title, reqs, prio = "", [], "required"
        for raw in p["jd_text"].splitlines():
            line = raw.strip()
            if not line:
                continue
            if not title:
                title = line
            if line[0] in "-*•":
                text = line.lstrip("-*• ").strip()
                reqs.append({"text": text, "priority": prio, "keywords": detect_terms(text, generic=True)})
            elif re.search(r"prefer|nice to have|bonus|plus", line, re.I) and len(line) < 40:
                prio = "preferred"
            elif re.search(r"require|must|qualif|responsib", line, re.I) and len(line) < 40:
                prio = "required"
        return {"title": title, "requirements": reqs}

    # ---- match ----
    def _match(self, p: dict) -> dict:
        ledger = p["ledger"]  # list of dicts incl. evidence_text
        out = []
        for r in p["requirements"]:
            kws = r["keywords"]
            hits = [it for it in ledger if kws and any(in_text(k, it["evidence_text"]) for k in kws)]
            covered = [k for k in kws if any(in_text(k, it["evidence_text"]) for it in ledger)]
            if hits and len(covered) == len(kws):
                st = "SUPPORTED"
            elif hits:
                st = "PARTIAL"
            else:
                st = "GAP"
            if self.hallucinate and ledger:
                st, hits = "SUPPORTED", ledger[:1]   # claim everything is supported
            out.append({"requirement_id": r["id"], "status": st, "ledger_ids": [h["id"] for h in hits[:3]],
                        "rationale": "Evidence found for " + ", ".join(covered) if covered else "No matching evidence."})
        return {"matches": out}

    # ---- generate ----
    def _generate(self, p: dict) -> dict:
        ledger = {it["id"]: it for it in p["ledger"]}
        bullets, used = [], set()
        for m in p["matches"]:
            if m["status"] == "GAP":
                continue
            for lid in m["ledger_ids"]:
                it = ledger.get(lid)
                if it and lid not in used:
                    used.add(lid)
                    bullets.append({"text": it["summary"], "requirement_ids": [m["requirement_id"]],
                                    "ledger_ids": [lid], "evidence": it["evidence"][:2]})
                    break
            if len(bullets) >= 7:
                break
        interview = []
        qs = {"Retry": "Why did you cap the backoff, and how would you add jitter?",
              "Dead-letter": "How would you monitor and safely replay messages from the dead-letter queue?",
              "Idempotent": "How does your upsert stay correct when events arrive out of order?",
              "Cursor": "Why keyset/cursor pagination instead of OFFSET, and what breaks if the sort key isn't unique?",
              "Kafka": "What delivery guarantee does committing after processing give you, and what duplicates can occur?"}
        for key, q in qs.items():
            it = next((i for i in p["ledger"] if key.lower() in i["name"].lower() and i["kind"] == "skill"), None) \
                or next((i for i in p["ledger"] if key.lower() in i["name"].lower()), None)
            if it:
                interview.append({"question": q, "why": f"Your code: {it['name']}.", "evidence": it["evidence"][:1]})
        if self.hallucinate:
            ev = ledger[next(iter(ledger))]["evidence"][:1] if ledger else []
            bullets += [
                {"text": "Reduced consumer latency by 40% using Kafka and Terraform.", "requirement_ids": [],
                 "ledger_ids": [], "evidence": ev},
                {"text": "Built a Kafka consumer.", "requirement_ids": [], "ledger_ids": [],
                 "evidence": [{"kind": "commit", "commit": "deadbee", "quote": "Add Kafka consumer"}]},
                {"text": "Led a team of 5 engineers building the Kafka pipeline.", "requirement_ids": [],
                 "ledger_ids": [], "evidence": ev},
                {"text": "Built a Kafka consumer.", "requirement_ids": [], "ledger_ids": [],
                 "evidence": [{"kind": "file", "path": "orderflow/consumer.py", "start_line": 1, "end_line": 2,
                               "quote": "this text is not in the file"}]},
                {"text": "Wrote Rust services.", "requirement_ids": [], "ledger_ids": [], "evidence": []},
            ]
            interview.append({"question": "Tell us about your Rust migration.", "why": "invented",
                              "evidence": [{"kind": "file", "path": "src/main.rs", "start_line": 1, "end_line": 1,
                                            "quote": "fn main() {"}]})
        return {"bullets": bullets, "interview": interview}

    # ---- answer feedback (simple word rules, clearly not a real judgment) ----
    def _feedback(self, p: dict) -> dict:
        code, answer = p["code"], p["answer"].lower()
        code_lines = [l.strip() for l in code.splitlines() if l.strip() and not l.startswith("# ")]
        names = []
        for l in code_lines:
            for w in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", l):
                if (("_" in w or any(c.isupper() for c in w[1:])) and w not in names):
                    names.append(w)
        hit = [w for w in names if w.lower() in answer or w.lower().replace("_", " ") in answer]
        miss = [w for w in names if w not in hit][:3]
        words = len(answer.split())
        why = any(k in answer for k in ("because", "trade", "instead", "cost", "so that"))
        fail = any(k in answer for k in ("fail", "retry", "error", "crash", "timeout", "duplicate", "lost"))
        out = {
            "correctness": min(5, 1 + len(hit)), "tradeoffs": 4 if why else 2, "failure_modes": 4 if fail else 2,
            "clarity": 4 if 40 <= words <= 250 else 2,
            "strengths": [f"Mentions {', '.join(hit[:3])} from the code."] if hit else [],
            "improve": ([] if why else ["Say why you chose this design and what it costs."]) +
                       ([] if fail else ["Describe what happens when something fails."]),
            "missed": [{"point": f"The code uses {w}; explain its role.",
                        "quote": next(l for l in code_lines if w in l)} for w in miss],
            "follow_up": f"What would break if {miss[0]} behaved differently?" if miss else
                         "How would you test this under failure?",
        }
        if self.hallucinate:   # invented code reference must be dropped by the verifier
            out["missed"].append({"point": "You forgot the Redis lock.", "quote": "redis.lock(order_id)"})
        return out
