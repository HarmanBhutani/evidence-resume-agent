# Tailored bullets: Senior Backend Engineer, Event Streaming (Synthetic Example Co.)

> Output mode: **MOCK · provider=mock · model=mock-hallucination-attack** · repo `sample_repo` @ `4884b93823923129`

> Authorship: **checked for demo@example.invalid**

> MOCK: deterministic offline rules, not a real model.
> Authorship checked against git history for the emails you selected. Git authorship can be faked and does not show whether code was copied or generated, so this is evidence, not certification.
> Repos cannot prove leadership, mentoring, years of experience, communication or other non-code work. Those requirements are never marked supported; add them manually below and they appear labeled 'user-provided, unverified'.

## Requirement match
- **GAP** [required] Strong Python experience building production services — SUPPORTED -> GAP: none of ['python'] appears in the cited evidence — not found in the code: python
- **PARTIAL** [required] Hands-on experience with Kafka consumers, including retry and error-handling strategies — SUPPORTED -> PARTIAL: not found in evidence: ['retries'] — not found in the code: retries
- **GAP** [required] Experience designing dead-letter queues and idempotent message processing — SUPPORTED -> GAP: none of ['dead-letter queue', 'idempotency'] appears in the cited evidence — not found in the code: dead-letter queue, idempotency
- **GAP** [required] Building REST APIs with FastAPI or a similar framework — SUPPORTED -> GAP: none of ['fastapi'] appears in the cited evidence — not found in the code: fastapi
- **GAP** [required] Writing automated tests with pytest — SUPPORTED -> GAP: none of ['pytest'] appears in the cited evidence — not found in the code: pytest
- **GAP** [required] Containerizing services with Docker — SUPPORTED -> GAP: none of ['docker'] appears in the cited evidence — not found in the code: docker
- **GAP** [required] 5+ years of professional software engineering experience (non-code: cannot be proven from a repo) — non-code requirement cannot be proven by a repo -> GAP
- **GAP** [required] Mentoring junior engineers (non-code: cannot be proven from a repo) — non-code requirement cannot be proven by a repo -> GAP
- **GAP** [preferred] Observability experience with Prometheus — SUPPORTED -> GAP: none of ['prometheus'] appears in the cited evidence — not found in the code: prometheus
- **GAP** [preferred] CI/CD pipelines (GitHub Actions) — SUPPORTED -> GAP: none of ['ci/cd', 'github actions'] appears in the cited evidence — not found in the code: ci/cd, github actions
- **GAP** [preferred] PostgreSQL in production — SUPPORTED -> GAP: none of ['postgresql'] appears in the cited evidence — not found in the code: postgresql
- **GAP** [preferred] Experience with Kubernetes — SUPPORTED -> GAP: none of ['kubernetes'] appears in the cited evidence — not found in the code: kubernetes

## Bullets (every claim cites repo evidence)
- Built a Kafka consumer that disables auto commit and commits offsets after processing.  
  evidence: `orderflow/consumer.py:6-6 (yours)`; `orderflow/consumer.py:27-27 (yours)`

## Blocked by the verifier
- ~~Reduced consumer latency by 40% using Kafka and Terraform.~~ — number '40' not found in cited evidence; technology/concept 'terraform' not found in cited evidence
- ~~Built a Kafka consumer.~~ — commit deadbee: commit not found: 'deadbee'; no valid evidence
- ~~Led a team of 5 engineers building the Kafka pipeline.~~ — number '5' not found in cited evidence; 'led' (leadership/mentoring/non-code) cannot be proven from a repo
- ~~Built a Kafka consumer.~~ — orderflow/consumer.py:1-2: quoted snippet not found in orderflow/consumer.py:1-2; no valid evidence
- ~~Wrote Rust services.~~ — no evidence cited

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
