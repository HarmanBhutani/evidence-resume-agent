# Tailored bullets: Staff Infrastructure Engineer (Synthetic Example Co. - adversarial sample)

> Output mode: **MOCK · provider=mock · model=mock-hallucination-attack** · repo `sample_repo` @ `4884b93823923129`

> Authorship: **checked for demo@example.invalid**

> MOCK: deterministic offline rules, not a real model.
> Authorship checked against git history for the emails you selected. Git authorship can be faked and does not show whether code was copied or generated, so this is evidence, not certification.
> Repos cannot prove leadership, mentoring, years of experience, communication or other non-code work. Those requirements are never marked supported; add them manually below and they appear labeled 'user-provided, unverified'.

## Requirement match
- **GAP** [required] Production Terraform: modules, remote state, multi-account AWS landscapes — SUPPORTED -> GAP: none of ['terraform', 'aws'] appears in the cited evidence — not found in the code: terraform, aws
- **GAP** [required] Systems programming in Rust — SUPPORTED -> GAP: none of ['rust'] appears in the cited evidence — not found in the code: rust
- **GAP** [required] Operating Kubernetes clusters with Helm — SUPPORTED -> GAP: none of ['kubernetes', 'helm'] appears in the cited evidence — not found in the code: kubernetes, helm
- **GAP** [required] Go for internal tooling — SUPPORTED -> GAP: none of ['go'] appears in the cited evidence — not found in the code: go
- **GAP** [required] Leading a platform team of 8+ engineers (non-code: cannot be proven from a repo) — non-code requirement cannot be proven by a repo -> GAP
- **GAP** [preferred] Python — SUPPORTED -> GAP: none of ['python'] appears in the cited evidence — not found in the code: python
- **GAP** [preferred] Docker — SUPPORTED -> GAP: none of ['docker'] appears in the cited evidence — not found in the code: docker
- **GAP** [preferred] GraphQL federation — SUPPORTED -> GAP: none of ['graphql'] appears in the cited evidence — not found in the code: graphql

## Bullets (every claim cites repo evidence)

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
