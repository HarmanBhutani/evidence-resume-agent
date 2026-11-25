# Tailored bullets: Senior Backend Engineer, Event Streaming

> Output mode: **LIVE · provider=claude_cli · model=sonnet** · repo `sample_repo` @ `4884b93823923129`

> Authorship: **checked for demo@example.invalid**

> Authorship checked against git history for the emails you selected. Git authorship can be faked and does not show whether code was copied or generated, so this is evidence, not certification.
> Repos cannot prove leadership, mentoring, years of experience, communication or other non-code work. Those requirements are never marked supported; add them manually below and they appear labeled 'user-provided, unverified'.

## Requirement match
- **PARTIAL** [required] Strong Python experience building production services
- **SUPPORTED** [required] Hands-on experience with Kafka consumers, including retry and error-handling strategies
- **SUPPORTED** [required] Experience designing dead-letter queues and idempotent message processing
- **SUPPORTED** [required] Building REST APIs with FastAPI or a similar framework
- **SUPPORTED** [required] Writing automated tests with pytest
- **SUPPORTED** [required] Containerizing services with Docker
- **GAP** [required] 5+ years of professional software engineering experience (non-code: cannot be proven from a repo)
- **GAP** [required] Mentoring junior engineers (non-code: cannot be proven from a repo)
- **SUPPORTED** [preferred] Observability experience with Prometheus
- **SUPPORTED** [preferred] CI/CD pipelines (GitHub Actions)
- **GAP** [preferred] PostgreSQL in production — not found in the code: PostgreSQL
- **GAP** [preferred] Experience with Kubernetes — not found in the code: Kubernetes

## Bullets (every claim cites repo evidence)
- Built a Kafka consumer with a group id and auto-commit disabled, committing offsets manually after each message is handled.  
  evidence: `orderflow/consumer.py:23-29 (yours)`; `orderflow/consumer.py:64-68 (yours)`
- Added dead-letter queue publishing for poison messages so the partition keeps moving, plus a POST replay endpoint backed by a dead_letters table.  
  evidence: `orderflow/consumer.py:55-61 (yours)`; `orderflow/api.py:33-35 (yours)`
- Implemented cursor-paginated order listing in the API on top of keyset pagination in the store, avoiding OFFSET scans.  
  evidence: `orderflow/api.py:23-30 (yours)`; `orderflow/store.py:45-46 (yours)`
- Configured a GitHub Actions workflow that runs pytest across a Python version matrix of 3.11 and 3.12.  
  evidence: `.github/workflows/ci.yml:1-15 (yours)`; `.github/workflows/ci.yml:15-15 (yours)`
- Instrumented the consumer with Prometheus metrics, defining counters and a histogram using prometheus_client.  
  evidence: `orderflow/metrics.py:1-7 (yours)`; `orderflow/consumer.py:41-41 (yours)`

## Blocked by the verifier
- ~~Implemented retry with exponential backoff in the consumer, stopping immediately on a PermanentError rather than retrying.~~ — technology/concept 'retries' not found in cited evidence
- ~~Wrote an idempotent SQLite upsert so replays and stale versions never overwrite newer data, guarded by a version check.~~ — technology/concept 'sqlite' not found in cited evidence
- ~~Built FastAPI REST endpoints for order lookup that raise an HTTPException with status 404 when an order is not found.~~ — technology/concept 'fastapi' not found in cited evidence

## Interview prep (from your own code)
- Why did you disable auto-commit and commit offsets manually after each message? What happens if the process crashes between handling and commit?  
  based on: `orderflow/consumer.py:23-29 (yours)`; `orderflow/consumer.py:64-68 (yours)`
- How did you choose the backoff parameters and cap, and what are the risks of blocking the partition while retrying?  
  based on: `orderflow/consumer.py:15-17 (yours)`
- Why does the retry loop stop immediately on PermanentError, and how do you decide which errors are permanent?  
  based on: `orderflow/consumer.py:43-45 (yours)`; `orderflow/handlers.py:4-16 (yours)`
- What are the failure modes of publishing to the dead-letter topic, and what happens if the DLQ publish itself fails?  
  based on: `orderflow/consumer.py:55-61 (yours)`
- How does the DLQ replay endpoint interact with the idempotent store, and could replaying an event cause duplicates or overwrite newer data?  
  based on: `orderflow/api.py:33-35 (yours)`; `orderflow/store.py:32-36 (yours)`
- Why use keyset pagination instead of OFFSET, and what are its limitations with respect to ordering and cursor design?  
  based on: `orderflow/store.py:45-46 (yours)`; `orderflow/api.py:23-30 (yours)`
- How did you test the consumer's retry and DLQ behavior without a real Kafka broker?  
  based on: `tests/test_consumer.py:11-19 (yours)`; `commit 1ee4a5fb (yours)`
