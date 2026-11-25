# Tailored bullets: Staff Infrastructure Engineer (Synthetic Example Co. - adversarial sample)

> Output mode: **MOCK · provider=mock · model=mock-deterministic** · repo `sample_repo` @ `4884b93823923129`

> Authorship: **checked for demo@example.invalid**

> MOCK: deterministic offline rules, not a real model.
> Authorship checked against git history for the emails you selected. Git authorship can be faked and does not show whether code was copied or generated, so this is evidence, not certification.
> Repos cannot prove leadership, mentoring, years of experience, communication or other non-code work. Those requirements are never marked supported; add them manually below and they appear labeled 'user-provided, unverified'.

## Requirement match
- **GAP** [required] Production Terraform: modules, remote state, multi-account AWS landscapes — not found in the code: terraform, aws
- **GAP** [required] Systems programming in Rust — not found in the code: rust
- **GAP** [required] Operating Kubernetes clusters with Helm — not found in the code: kubernetes, helm
- **GAP** [required] Go for internal tooling — not found in the code: go
- **GAP** [required] Leading a platform team of 8+ engineers (non-code: cannot be proven from a repo)
- **SUPPORTED** [preferred] Python
- **SUPPORTED** [preferred] Docker
- **GAP** [preferred] GraphQL federation — not found in the code: graphql

## Bullets (every claim cites repo evidence)
- Built REST endpoints with FastAPI for order lookup.  
  evidence: `orderflow/api.py:2-2 (yours)`; `orderflow/api.py:15-15 (yours)`
- Containerized the service with a Dockerfile.  
  evidence: `Dockerfile:1-1 (yours)`; `Dockerfile:7-7 (yours)`

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
