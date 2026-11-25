# Tailored bullets: Staff Infrastructure Engineer

> Output mode: **LIVE · provider=claude_cli · model=sonnet** · repo `sample_repo` @ `4884b93823923129`

> Authorship: **checked for demo@example.invalid**

> Authorship checked against git history for the emails you selected. Git authorship can be faked and does not show whether code was copied or generated, so this is evidence, not certification.
> Repos cannot prove leadership, mentoring, years of experience, communication or other non-code work. Those requirements are never marked supported; add them manually below and they appear labeled 'user-provided, unverified'.

## Requirement match
- **GAP** [required] Production Terraform: modules, remote state, multi-account AWS landscapes — not found in the code: Terraform, AWS
- **GAP** [required] Systems programming in Rust — not found in the code: Rust
- **GAP** [required] Operating Kubernetes clusters with Helm — not found in the code: Kubernetes, Helm
- **GAP** [required] Go for internal tooling — not found in the code: Go
- **GAP** [required] Leading a platform team of 8+ engineers (non-code: cannot be proven from a repo)
- **SUPPORTED** [preferred] Python
- **SUPPORTED** [preferred] Docker
- **GAP** [preferred] GraphQL federation — not found in the code: GraphQL

## Bullets (every claim cites repo evidence)
- Built FastAPI endpoints for order lookup that raise an HTTPException with a 404 status when an order is not found.  
  evidence: `orderflow/api.py:10-20 (yours)`; `commit 1effbbdb (yours)`
- Configured a GitHub Actions workflow that runs pytest across a Python version matrix of 3.11 and 3.12.  
  evidence: `.github/workflows/ci.yml:1-15 (yours)`; `.github/workflows/ci.yml:15-15 (yours)`
- Wrote a Dockerfile that runs the FastAPI app with uvicorn, containerizing the service.  
  evidence: `Dockerfile:1-7 (yours)`; `commit f3fbc6a4 (yours)`

## Blocked by the verifier
- ~~Built a Kafka consumer in Python with a group id and auto-commit disabled, committing offsets manually after each message is handled.~~ — technology/concept 'python' not found in cited evidence
- ~~Wrote a pytest suite using a FakeProducer to test consumer retries and DLQ behavior, plus a cursor pagination test across all pages.~~ — technology/concept 'pagination' not found in cited evidence

## Interview prep (from your own code)
- Why did you disable auto-commit and commit offsets manually after each message, and what delivery guarantee does that give you?  
  based on: `orderflow/consumer.py:23-29 (yours)`; `orderflow/consumer.py:64-68 (yours)`
- How does your retry logic distinguish permanent from transient errors, and why is the backoff capped?  
  based on: `orderflow/consumer.py:15-17 (yours)`; `orderflow/consumer.py:43-45 (yours)`
- What are the trade-offs of publishing poison messages to a dead-letter topic rather than blocking the partition?  
  based on: `orderflow/consumer.py:55-61 (yours)`
- How does the DLQ replay endpoint work, and what could go wrong when replaying a dead-lettered event?  
  based on: `orderflow/api.py:33-35 (yours)`; `orderflow/store.py:20-25 (yours)`
- How does your upsert guarantee that replays and stale versions never overwrite newer data?  
  based on: `orderflow/store.py:27-39 (yours)`; `orderflow/store.py:32-36 (yours)`
- Why did you choose keyset/cursor pagination over OFFSET, and how do you handle the last page?  
  based on: `orderflow/store.py:45-46 (yours)`; `orderflow/api.py:23-30 (yours)`
- Why did you make the settings a frozen dataclass read from environment variables?  
  based on: `orderflow/config.py:6-8 (yours)`; `orderflow/config.py:15-15 (yours)`
