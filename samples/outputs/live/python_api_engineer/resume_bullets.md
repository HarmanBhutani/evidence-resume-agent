# Tailored bullets: Python API Engineer

> Output mode: **LIVE · provider=claude_cli · model=sonnet** · repo `sample_repo` @ `4884b93823923129`

> Authorship: **checked for demo@example.invalid**

> Authorship checked against git history for the emails you selected. Git authorship can be faked and does not show whether code was copied or generated, so this is evidence, not certification.
> Repos cannot prove leadership, mentoring, years of experience, communication or other non-code work. Those requirements are never marked supported; add them manually below and they appear labeled 'user-provided, unverified'.

## Requirement match
- **SUPPORTED** [required] Python and FastAPI
- **SUPPORTED** [required] Pagination and API design best practices
- **PARTIAL** [required] SQL databases (SQLite or PostgreSQL) — SUPPORTED -> PARTIAL: not found in evidence: ['PostgreSQL'] — not found in the code: PostgreSQL
- **SUPPORTED** [required] Unit and API testing with pytest
- **SUPPORTED** [required] Metrics and monitoring of services
- **SUPPORTED** [preferred] Docker
- **SUPPORTED** [preferred] Continuous integration
- **GAP** [preferred] Strong communication with stakeholders (non-code: cannot be proven from a repo)

## Bullets (every claim cites repo evidence)
- Built FastAPI endpoints for order lookup that return a 404 through HTTPException when an order is missing.  
  evidence: `orderflow/api.py:10-20 (yours)`; `commit 1effbbdb (yours)`
- Implemented cursor pagination for order listing in the API, backed by keyset pagination in the store with no OFFSET scans.  
  evidence: `orderflow/api.py:23-30 (yours)`; `orderflow/store.py:45-46 (yours)`
- Wrote a SQLite store with idempotent upserts so replays and stale versions never overwrite newer data.  
  evidence: `orderflow/store.py:27-39 (yours)`; `commit f3cfc390 (yours)`
- Wrote a pytest suite covering consumer retries and DLQ, plus an API test that walks all pages of cursor pagination.  
  evidence: `commit 1ee4a5fb (yours)`; `tests/test_api.py:25-35 (yours)`
- Instrumented services with Prometheus counters and a histogram, wiring the counters into the consumer.  
  evidence: `orderflow/metrics.py:1-7 (yours)`; `orderflow/consumer.py:41-41 (yours)`
- Wrote a Dockerfile that runs the FastAPI app with uvicorn.  
  evidence: `Dockerfile:1-7 (yours)`
- Configured a GitHub Actions workflow that runs pytest across Python 3.11 and 3.12.  
  evidence: `.github/workflows/ci.yml:1-15 (yours)`; `.github/workflows/ci.yml:15-15 (yours)`

## Interview prep (from your own code)
- Why did you choose keyset pagination over OFFSET, and what are the trade-offs for clients?  
  based on: `orderflow/store.py:45-46 (yours)`; `orderflow/api.py:23-30 (yours)`
- How does the version check in the upsert protect against out-of-order or replayed events?  
  based on: `orderflow/store.py:32-36 (yours)`; `orderflow/store.py:27-39 (yours)`
- Why disable Kafka auto-commit and commit manually, and what happens if the process crashes between handling and commit?  
  based on: `orderflow/consumer.py:23-29 (yours)`; `orderflow/consumer.py:64-68 (yours)`
- Why does the retry loop stop immediately on PermanentError, and how did you design the backoff cap?  
  based on: `orderflow/consumer.py:15-17 (yours)`; `orderflow/consumer.py:43-45 (yours)`
- What is the purpose of the dead-letter topic, and how do you ensure poison messages don't block a partition?  
  based on: `orderflow/consumer.py:55-61 (yours)`
- How does the DLQ replay endpoint work, and what risks arise when replaying an event?  
  based on: `orderflow/api.py:33-35 (yours)`; `orderflow/store.py:20-25 (yours)`
- How did you test the consumer without a real Kafka broker?  
  based on: `tests/test_consumer.py:11-19 (yours)`
- Why use a frozen dataclass for configuration read from environment variables?  
  based on: `orderflow/config.py:6-8 (yours)`; `orderflow/config.py:15-15 (yours)`
