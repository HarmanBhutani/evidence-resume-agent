#!/usr/bin/env python3
"""Build the synthetic sample repo (demo/sample_repo) with a real, deterministic git history.

All content is synthetic. Dates and identity are pinned so commit hashes are reproducible,
which keeps recorded LLM responses (samples/recorded/) valid across rebuilds.

Usage: python demo/build_sample_repo.py [target_dir]
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "sample_repo"

README = '''# orderflow

Synthetic demo service (not a real project). Consumes order events from Kafka,
stores them in SQLite, and exposes a small REST API.
'''

REQUIREMENTS = '''kafka-python==2.0.2
fastapi==0.110.0
uvicorn==0.29.0
prometheus-client==0.20.0
pytest==8.1.1
httpx==0.27.0
'''

CONFIG_V1 = '''"""Runtime configuration for the orderflow service."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
    topic: str = "orders.events"
    group_id: str = "orderflow-consumer"
    db_path: str = os.getenv("ORDERFLOW_DB", "orderflow.db")
'''

CONFIG_V2 = '''"""Runtime configuration for the orderflow service."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
    topic: str = "orders.events"
    dlq_topic: str = "orders.events.dlq"
    group_id: str = "orderflow-consumer"
    max_retries: int = 5
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 30.0
    db_path: str = os.getenv("ORDERFLOW_DB", "orderflow.db")
'''

HANDLERS = '''"""Business handling of a single order event."""
from orderflow.store import Store

REQUIRED_FIELDS = ("order_id", "status", "amount_cents", "version")


class PermanentError(Exception):
    """Raised for malformed events that must never be retried."""


def validate_event(event: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in event]
    if missing:
        raise PermanentError(f"missing fields: {missing}")
    if event["amount_cents"] < 0:
        raise PermanentError("negative amount")


def process_order_event(event: dict, store: Store | None = None) -> None:
    validate_event(event)
    store = store or Store()
    store.upsert_order(
        order_id=event["order_id"],
        status=event["status"],
        amount_cents=event["amount_cents"],
        version=event["version"],
    )
'''

CONSUMER_V1 = '''"""Kafka consumer for order events."""
import json
import logging

from kafka import KafkaConsumer

from orderflow.config import Settings
from orderflow.handlers import process_order_event

log = logging.getLogger(__name__)


class OrderConsumer:
    def __init__(self, settings: Settings, consumer=None):
        self.settings = settings
        self.consumer = consumer or KafkaConsumer(
            settings.topic,
            bootstrap_servers=settings.bootstrap_servers,
            group_id=settings.group_id,
            enable_auto_commit=False,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )

    def run(self) -> None:
        for message in self.consumer:
            process_order_event(message.value)
            # commit only after the event is fully processed (at-least-once delivery)
            self.consumer.commit()
'''

CONSUMER_V2 = '''"""Kafka consumer for order events with retries."""
import json
import logging
import time

from kafka import KafkaConsumer

from orderflow.config import Settings
from orderflow.handlers import PermanentError, process_order_event

log = logging.getLogger(__name__)


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff: base * 2^attempt, capped."""
    return min(cap, base * (2 ** attempt))


class OrderConsumer:
    def __init__(self, settings: Settings, consumer=None, sleep=time.sleep):
        self.settings = settings
        self.consumer = consumer or KafkaConsumer(
            settings.topic,
            bootstrap_servers=settings.bootstrap_servers,
            group_id=settings.group_id,
            enable_auto_commit=False,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        self._sleep = sleep

    def handle_with_retries(self, event: dict) -> bool:
        """Return True if processed, False if retries were exhausted."""
        for attempt in range(self.settings.max_retries):
            try:
                process_order_event(event)
                return True
            except PermanentError:
                log.warning("permanent failure for order %s", event.get("order_id"))
                return False
            except Exception:
                delay = backoff_delay(
                    attempt, self.settings.backoff_base_seconds, self.settings.backoff_max_seconds
                )
                log.warning("attempt %d failed, retrying in %.1fs", attempt + 1, delay)
                self._sleep(delay)
        return False

    def run(self) -> None:
        for message in self.consumer:
            if not self.handle_with_retries(message.value):
                log.error("giving up on offset %s", message.offset)
            self.consumer.commit()
'''

CONSUMER_V3 = '''"""Kafka consumer for order events with retries and a dead-letter queue."""
import json
import logging
import time

from kafka import KafkaConsumer, KafkaProducer

from orderflow.config import Settings
from orderflow.handlers import PermanentError, process_order_event

log = logging.getLogger(__name__)


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff: base * 2^attempt, capped."""
    return min(cap, base * (2 ** attempt))


class OrderConsumer:
    def __init__(self, settings: Settings, consumer=None, producer=None, sleep=time.sleep):
        self.settings = settings
        self.consumer = consumer or KafkaConsumer(
            settings.topic,
            bootstrap_servers=settings.bootstrap_servers,
            group_id=settings.group_id,
            enable_auto_commit=False,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        self.producer = producer or KafkaProducer(
            bootstrap_servers=settings.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        self._sleep = sleep

    def handle_with_retries(self, event: dict) -> bool:
        """Return True if processed, False if retries were exhausted."""
        for attempt in range(self.settings.max_retries):
            try:
                process_order_event(event)
                return True
            except PermanentError:
                log.warning("permanent failure for order %s", event.get("order_id"))
                return False
            except Exception:
                delay = backoff_delay(
                    attempt, self.settings.backoff_base_seconds, self.settings.backoff_max_seconds
                )
                log.warning("attempt %d failed, retrying in %.1fs", attempt + 1, delay)
                self._sleep(delay)
        return False

    def send_to_dlq(self, message, reason: str) -> None:
        """Publish a poison message to the dead-letter topic so the partition keeps moving."""
        self.producer.send(
            self.settings.dlq_topic,
            {"original": message.value, "reason": reason, "offset": message.offset},
        )
        self.producer.flush()

    def run(self) -> None:
        for message in self.consumer:
            if not self.handle_with_retries(message.value):
                self.send_to_dlq(message, "retries exhausted or permanent error")
            self.consumer.commit()
'''

STORE_V1 = '''"""SQLite persistence for orders."""
import sqlite3

from orderflow.config import Settings


class Store:
    def __init__(self, path: str | None = None):
        self.conn = sqlite3.connect(path or Settings().db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                version INTEGER NOT NULL
            )"""
        )

    def upsert_order(self, order_id: str, status: str, amount_cents: int, version: int) -> None:
        """Idempotent write: replays and stale versions never overwrite newer data."""
        self.conn.execute(
            """INSERT INTO orders(order_id, status, amount_cents, version)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(order_id) DO UPDATE SET
                 status = excluded.status,
                 amount_cents = excluded.amount_cents,
                 version = excluded.version
               WHERE excluded.version > orders.version""",
            (order_id, status, amount_cents, version),
        )
        self.conn.commit()

    def get_order(self, order_id: str):
        row = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        return dict(row) if row else None
'''

STORE_V2 = STORE_V1 + '''
    def list_orders(self, limit: int = 50, after: str | None = None) -> list[dict]:
        """Keyset pagination: stable ordering by order_id, no OFFSET scans."""
        if after:
            rows = self.conn.execute(
                "SELECT * FROM orders WHERE order_id > ? ORDER BY order_id LIMIT ?", (after, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM orders ORDER BY order_id LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
'''

STORE_V3 = STORE_V2.replace(
    '''                version INTEGER NOT NULL
            )"""
        )
''',
    '''                version INTEGER NOT NULL
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS dead_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                reason TEXT NOT NULL
            )"""
        )
''',
) + '''
    def add_dead_letter(self, payload: str, reason: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO dead_letters(payload, reason) VALUES (?, ?)", (payload, reason)
        )
        self.conn.commit()
        return cur.lastrowid

    def pop_dead_letter(self, dead_letter_id: int):
        row = self.conn.execute(
            "SELECT * FROM dead_letters WHERE id = ?", (dead_letter_id,)
        ).fetchone()
        if row:
            self.conn.execute("DELETE FROM dead_letters WHERE id = ?", (dead_letter_id,))
            self.conn.commit()
        return dict(row) if row else None
'''

API_V1 = '''"""REST API for order lookup."""
from fastapi import FastAPI, HTTPException

from orderflow.store import Store

app = FastAPI(title="orderflow")
store = Store()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict:
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order
'''

API_V2 = API_V1 + '''

@app.get("/orders")
def list_orders(limit: int = 50, cursor: str | None = None) -> dict:
    """Cursor-paginated listing; next_cursor is null on the last page."""
    limit = max(1, min(limit, 200))
    items = store.list_orders(limit=limit + 1, after=cursor)
    has_more = len(items) > limit
    items = items[:limit]
    return {"items": items, "next_cursor": items[-1]["order_id"] if has_more else None}
'''

API_V3 = API_V2 + '''

@app.post("/dlq/{dead_letter_id}/replay")
def replay_dead_letter(dead_letter_id: int) -> dict:
    """Re-run a dead-lettered event through the normal handler."""
    import json

    from orderflow.handlers import process_order_event

    entry = store.pop_dead_letter(dead_letter_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="dead letter not found")
    process_order_event(json.loads(entry["payload"]), store=store)
    return {"replayed": dead_letter_id}
'''

METRICS = '''"""Prometheus metrics shared by the consumer and the API."""
from prometheus_client import Counter, Histogram

EVENTS_PROCESSED = Counter("orderflow_events_processed_total", "Order events processed")
EVENTS_DEAD_LETTERED = Counter("orderflow_events_dead_lettered_total", "Events sent to the DLQ")
RETRY_ATTEMPTS = Counter("orderflow_retry_attempts_total", "Handler retry attempts")
REQUEST_LATENCY = Histogram("orderflow_request_seconds", "API request latency in seconds")
'''

TEST_CONSUMER = '''"""Consumer tests: retries with backoff and dead-letter routing."""
from types import SimpleNamespace

import pytest

from orderflow import consumer as consumer_mod
from orderflow.config import Settings
from orderflow.consumer import OrderConsumer, backoff_delay


class FakeProducer:
    def __init__(self):
        self.sent = []

    def send(self, topic, value):
        self.sent.append((topic, value))

    def flush(self):
        pass


def make_consumer(max_retries=3):
    sleeps = []
    c = OrderConsumer(
        Settings(max_retries=max_retries),
        consumer=iter(()),
        producer=FakeProducer(),
        sleep=sleeps.append,
    )
    return c, sleeps


def test_backoff_is_exponential_and_capped():
    assert backoff_delay(0, 0.5, 30) == 0.5
    assert backoff_delay(3, 0.5, 30) == 4.0
    assert backoff_delay(20, 0.5, 30) == 30


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(event):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")

    monkeypatch.setattr(consumer_mod, "process_order_event", flaky)
    c, sleeps = make_consumer(max_retries=5)
    assert c.handle_with_retries({"order_id": "o1"}) is True
    assert calls["n"] == 3
    assert sleeps == [0.5, 1.0]


def test_exhausted_retries_go_to_dlq(monkeypatch):
    def always_fail(event):
        raise RuntimeError("down")

    monkeypatch.setattr(consumer_mod, "process_order_event", always_fail)
    c, _ = make_consumer(max_retries=3)
    assert c.handle_with_retries({"order_id": "o2"}) is False
    msg = SimpleNamespace(value={"order_id": "o2"}, offset=41)
    c.send_to_dlq(msg, "retries exhausted")
    topic, payload = c.producer.sent[0]
    assert topic == "orders.events.dlq"
    assert payload["offset"] == 41
'''

TEST_API = '''"""API tests: pagination, lookup, and DLQ replay."""
import json

import pytest
from fastapi.testclient import TestClient

from orderflow import api
from orderflow.store import Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "t.db"))
    monkeypatch.setattr(api, "store", store)
    for i in range(7):
        store.upsert_order(f"o{i}", "paid", 100 + i, 1)
    return TestClient(api.app), store


def test_get_order_404(client):
    c, _ = client
    assert c.get("/orders/nope").status_code == 404


def test_cursor_pagination_walks_all_pages(client):
    c, _ = client
    seen, cursor = [], None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        body = c.get("/orders", params=params).json()
        seen += [o["order_id"] for o in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"o{i}" for i in range(7)]


def test_idempotent_upsert_ignores_stale_version(client):
    _, store = client
    store.upsert_order("o1", "refunded", 999, 5)
    store.upsert_order("o1", "paid", 100, 2)
    assert store.get_order("o1")["status"] == "refunded"


def test_dlq_replay(client):
    c, store = client
    dl = store.add_dead_letter(
        json.dumps({"order_id": "z", "status": "paid", "amount_cents": 5, "version": 1}), "x"
    )
    assert c.post(f"/dlq/{dl}/replay").status_code == 200
    assert store.get_order("z") is not None
'''

DOCKERFILE = '''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY orderflow ./orderflow
EXPOSE 8000
CMD ["uvicorn", "orderflow.api:app", "--host", "0.0.0.0", "--port", "8000"]
'''

CI = '''name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -r requirements.txt
      - run: pytest -q
'''

C = "orderflow/"
COMMITS = [
    ("2024-01-08T10:00:00", "Initial project skeleton and config", {
        "README.md": README, "requirements.txt": REQUIREMENTS,
        C + "__init__.py": "", C + "config.py": CONFIG_V1}),
    ("2024-01-15T14:20:00", "Add Kafka consumer with manual offset commits", {
        C + "handlers.py": HANDLERS, C + "consumer.py": CONSUMER_V1}),
    ("2024-01-22T09:45:00", "Add SQLite store with idempotent order upserts", {
        C + "store.py": STORE_V1}),
    ("2024-02-05T16:10:00", "Add retry with exponential backoff to consumer", {
        C + "config.py": CONFIG_V2, C + "consumer.py": CONSUMER_V2}),
    ("2024-02-19T11:30:00", "Add dead-letter queue publishing for poison messages", {
        C + "consumer.py": CONSUMER_V3}),
    ("2024-03-04T13:00:00", "Add FastAPI REST endpoints for order lookup", {
        C + "api.py": API_V1}),
    ("2024-03-18T15:25:00", "Add cursor pagination to order listing", {
        C + "api.py": API_V2, C + "store.py": STORE_V2}),
    ("2024-04-02T10:05:00", "Add DLQ replay endpoint and dead_letters table", {
        C + "api.py": API_V3, C + "store.py": STORE_V3}),
    ("2024-04-16T17:40:00", "Add Prometheus metrics for consumer and API", {
        C + "metrics.py": METRICS,
        C + "consumer.py": CONSUMER_V3
            .replace("from orderflow.handlers import",
                     "from orderflow.metrics import EVENTS_DEAD_LETTERED, EVENTS_PROCESSED, RETRY_ATTEMPTS\n"
                     "from orderflow.handlers import")
            .replace("                process_order_event(event)\n                return True",
                     "                process_order_event(event)\n                EVENTS_PROCESSED.inc()\n                return True")
            .replace("                self._sleep(delay)", "                RETRY_ATTEMPTS.inc()\n                self._sleep(delay)")
            .replace("        self.producer.flush()", "        self.producer.flush()\n        EVENTS_DEAD_LETTERED.inc()")}),
    ("2024-04-30T09:15:00", "Add pytest suite for consumer retries and DLQ", {
        "tests/__init__.py": "", "tests/test_consumer.py": TEST_CONSUMER}),
    ("2024-05-14T14:50:00", "Add API tests for pagination and DLQ replay", {
        "tests/test_api.py": TEST_API}),
    ("2024-05-28T12:00:00", "Add Dockerfile and GitHub Actions CI workflow", {
        "Dockerfile": DOCKERFILE, ".github/workflows/ci.yml": CI}),
]


def git(*args: str, date: str | None = None) -> None:
    env = dict(os.environ, GIT_AUTHOR_NAME="Demo Dev", GIT_AUTHOR_EMAIL="demo@example.invalid",
               GIT_COMMITTER_NAME="Demo Dev", GIT_COMMITTER_EMAIL="demo@example.invalid",
               GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date + " +0000"
    subprocess.run(["git", *args], cwd=TARGET, env=env, check=True, capture_output=True)


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    git("init", "-q", "-b", "main")
    for date, msg, files in COMMITS:
        for rel, content in files.items():
            p = TARGET / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        git("add", "-A")
        git("commit", "-q", "-m", msg, date=date)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=TARGET, capture_output=True,
                          text=True).stdout.strip()
    print(f"built {TARGET} with {len(COMMITS)} commits, HEAD={head}")


if __name__ == "__main__":
    main()
