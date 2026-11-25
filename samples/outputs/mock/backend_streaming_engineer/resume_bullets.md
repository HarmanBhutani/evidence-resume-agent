# Tailored bullets: Senior Backend Engineer, Event Streaming (Synthetic Example Co.)

> Output mode: **MOCK · provider=mock · model=mock-deterministic** · repo `sample_repo` @ `4884b93823923129`

> Authorship: **checked for demo@example.invalid**

> MOCK: deterministic offline rules, not a real model.
> Authorship checked against git history for the emails you selected. Git authorship can be faked and does not show whether code was copied or generated, so this is evidence, not certification.
> Repos cannot prove leadership, mentoring, years of experience, communication or other non-code work. Those requirements are never marked supported; add them manually below and they appear labeled 'user-provided, unverified'.

## Requirement match
- **SUPPORTED** [required] Strong Python experience building production services
- **SUPPORTED** [required] Hands-on experience with Kafka consumers, including retry and error-handling strategies
- **SUPPORTED** [required] Experience designing dead-letter queues and idempotent message processing
- **SUPPORTED** [required] Building REST APIs with FastAPI or a similar framework
- **SUPPORTED** [required] Writing automated tests with pytest
- **SUPPORTED** [required] Containerizing services with Docker
- **GAP** [required] 5+ years of professional software engineering experience (non-code: cannot be proven from a repo)
- **GAP** [required] Mentoring junior engineers (non-code: cannot be proven from a repo)
- **SUPPORTED** [preferred] Observability experience with Prometheus
- **SUPPORTED** [preferred] CI/CD pipelines (GitHub Actions)
- **GAP** [preferred] PostgreSQL in production — not found in the code: postgresql
- **GAP** [preferred] Experience with Kubernetes — not found in the code: kubernetes

## Bullets (every claim cites repo evidence)
- Built REST endpoints with FastAPI for order lookup.  
  evidence: `orderflow/api.py:2-2 (yours)`; `orderflow/api.py:15-15 (yours)`
- Built a Kafka consumer that disables auto commit and commits offsets after processing.  
  evidence: `orderflow/consumer.py:6-6 (yours)`; `orderflow/consumer.py:27-27 (yours)`
- Added dead-letter queue publishing so failed messages are routed to a DLQ topic.  
  evidence: `orderflow/consumer.py:55-55 (yours)`; `orderflow/config.py:10-10 (yours)`
- Wrote automated tests with pytest.  
  evidence: `tests/test_api.py:4-4 (yours)`; `tests/test_api.py:20-20 (yours)`
- Containerized the service with a Dockerfile.  
  evidence: `Dockerfile:1-1 (yours)`; `Dockerfile:7-7 (yours)`
- Instrumented the service with Prometheus counters and a histogram.  
  evidence: `orderflow/metrics.py:2-2 (yours)`; `orderflow/metrics.py:4-4 (yours)`
- Set up a GitHub Actions workflow that runs pytest.  
  evidence: `.github/workflows/ci.yml:5-5 (yours)`; `.github/workflows/ci.yml:15-15 (yours)`

## Interview prep (from your own code)
- Why did you cap the backoff, and how would you add jitter?  
  based on: `orderflow/consumer.py:15-15 (yours)`
- How would you monitor and safely replay messages from the dead-letter queue?  
  based on: `orderflow/consumer.py:55-55 (yours)`
- How does your upsert stay correct when events arrive out of order?  
  based on: `orderflow/store.py:32-32 (yours)`
- Why keyset/cursor pagination instead of OFFSET, and what breaks if the sort key isn't unique?  
  based on: `orderflow/api.py:24-24 (yours)`
- What delivery guarantee does committing after processing give you, and what duplicates can occur?  
  based on: `orderflow/consumer.py:6-6 (yours)`
