# Test report

Run on 2026-11-24, macOS, Python 3.13.9, Claude Code CLI 2.1.319 (logged in, model alias `sonnet` → claude-sonnet-5-5).
Command: `make test` → **92 passed, 0 failed, 0 skipped** (82 s, including one fresh live run). Raw log: `test-report.txt`.

## What ran

| # | Requirement | Where | Result |
|---|---|---|---|
| 1 | Unit: ingestion, verifier (valid/missing file, bad ranges, quote outside range, short quote, commit full/short hash, bad hashes incl. `HEAD`/`--all`, non-git folder, path traversal) | `test_ingest_verifier.py` | pass |
| 1 | Unit: claim tracer (invented number/tech/scale/leadership, plain prose not blocked), non-code classifier, JD parser, matcher (downgrades, unknown ids, user items never upgrade) | `test_claims_jd_match.py` | pass |
| 1 | Unit: bullet generator + blocker | `test_hallucination_e2e.py` | pass |
| 1 | Unit: `claude_cli` wrapper, subprocess mocked: success + exact flags/stdin/cwd/env, fenced JSON, bad-JSON retry→success, bad-JSON twice→error, timeout, not-logged-in, usage-limit (envelope and stderr), CLI missing, unknown failure | `test_claude_cli.py` | pass |
| 1 | Providers: factory, `LLM_MODEL`, record→replay round trip, missing recording, cache hit flagged, REPLAYED labelling, export files | `test_providers_cache_export.py` | pass |
| 2 | Hallucination: mock LLM invents Terraform/Rust skills, "2M events/day", a 40% metric, a fake commit, a bad quote, "led a team of 5", an invented interview question, and claims every GAP is SUPPORTED → all blocked/downgraded, GAPs still reported | `test_hallucination_e2e.py` | pass |
| 3 | Reference integrity: every citation in final output re-opened by an independent check (not the verifier code) and the quote found; runs on mock, on committed live recordings, and on the fresh live run | `conftest.assert_integrity` | pass |
| 4 | End-to-end, sample repo × 3 JDs, mock: expected SUPPORTED/GAP per JD (e.g. Terraform, Rust, Kubernetes, Go, leadership, GraphQL = GAP; PostgreSQL, Kubernetes, 5+ years, mentoring = GAP) | `test_hallucination_e2e.py` | pass |
| 4b | Committed live recordings replayed offline for all 3 JDs (labelled REPLAYED, integrity + expected GAPs) | same | pass |
| 5 | Server smoke: real uvicorn process, full flow over HTTP (run → poll → result), citation endpoints (file + commit), traversal rejected, error surfacing (bad repo, empty JD, no recording), server stdout has no Traceback/ERROR, `node --check` on the UI script | `test_server_smoke.py` | pass |
| 5b | **Browser** smoke (manual, in-app browser): opened UI on replay provider, picked adversarial JD, added a user item, ran, checked 6 steps done, REPLAYED badge, GAP styling, opened a citation drawer (highlighted lines), read the Rejected panel; browser console empty, server log empty | manual | pass |
| 6 | Live run through real `claude_cli`, cache bypassed, `--record` path: adversarial JD → mode LIVE, integrity assertions, Terraform/Rust/Kubernetes/leadership = GAP, no such terms in bullets, recording replays as REPLAYED with identical statuses | `test_live_claude.py` | pass |
| A | Authorship, on temporary two-author repos: yours / partly yours / not yours, borrowed quotes in mixed ranges, co-authors, commit context and removed lines, moved code, uncommitted lines, `.mailmap`, shallow clone, bulk-commit warning, unknown email rejected before any LLM call, LLM-supplied authorship discarded, demo end to end, `/api/authors` | `test_authorship.py`, `test_server_smoke.py` | pass |
| A | Hostile local git config (fsmonitor, textconv, external diff, clean filter) runs nothing. A manual control showed unprotected `git blame` and `git show` do run a textconv script | `test_authorship.py` + manual | pass |
| A | Real repos, mock mode, local only: 8, 3 and 662 authors (up to ~4,800 files): no errors, under 10 s per run | manual | pass |
| A | Fresh copy (no venv, no sample repo, no cache): `make setup`, offline tests, `make run` uses the venv | manual | pass |
| A | Browser (manual, replay provider): author list, selected the demo author, "yours" labels, citation drawer; no console or server errors | manual | pass |
| B | Interview practice: mock scoring rewards naming the code, invented code points dropped, scores clamped, answer fenced as data, empty/too-long answers rejected, changed citation reported, `/api/feedback` over HTTP (incl. replay refused) | `test_practice.py`, `test_server_smoke.py` | pass |
| B | Gap keywords: gaps list missing technologies (PostgreSQL, Kubernetes), supported requirements list none | `test_practice.py` | pass |
| B | One live Claude feedback call: 8 s, valid scores, all 3 suggested code quotes found in the cited code | manual | pass |
| C | Simulations in node: same seed same result; even spread on equal servers; least connections p95 3×+ better with a slow server; faster health check loses fewer requests; least-connections black hole after a crash; overload rejects; two transfers deadlock once and finish; lock ordering gives 0 deadlocks over 4 seeds; slow detector freezes more work; youngest transfer aborted and its lock released | `test_sims.py` | pass |
| C | `/learn` and `/static/sims.js` served; both pages' scripts pass `node --check` | `test_server_smoke.py` | pass |
| C | Browser (manual): new main UI at desktop and phone widths, light and dark; summary, filters, gap links, bullet selection, practice feedback, Esc closes the source drawer. Learn page: crash, health-check removal, quiz, comparison tables, deadlock auto-pause. No console or server errors | manual | pass |
| D | Online demo build: 18 results (3 jobs × replay/mock/attack × authorship on/off) correctly labeled; every citation in every result found in the published repo copy (independent check); relative links; no local paths; in-browser feedback gives the same scores and code points as the Python mock; own job descriptions refused with a clear message | `test_site.py` | pass |
| D | Published site checked in a browser at the public URL: banner, results, citation drawer, Learn page, hidden local-only controls; no console errors | manual | pass |
| 7 | One command | `make test` | pass |

## Live results (samples/outputs/live, recorded in samples/recorded)

| JD | supported / partial / gap | bullets ok / blocked | rejected log entries |
|---|---|---|---|
| backend_streaming_engineer | 7 / 1 / 4 | 5 / 3 | 4 |
| python_api_engineer | 6 / 1 / 1 | 7 / 0 | 1 |
| adversarial_infra_rust | 2 / 0 / 6 | 3 / 2 | 3 |

Fresh live run on 2026-11-24 with the authorship check on (sample repo's synthetic author); every citation shown is
labeled "yours". LLM output varies between runs (an earlier run the same day gave 8 / 7 / 4 ready bullets).
The 5 blocked bullets each name something absent from the lines they cite: Python, SQLite, FastAPI, "retries", and a
pagination test that cites unrelated code (a real catch). An earlier run also exposed a bug: "test double" was read as
"doubled" (×2) and blocked a true bullet; fixed in `claims.py`, with a regression test.

Observed: the real model did not invent bullets for the adversarial JD; the verifier's live rejections were over-strict
cases (a summary mentioning "Kafka"/"HTTP" not in the cited lines; items like "SQLite persistence" or "pytest" whose cited
lines lack the exact word). That is the intended trade-off: false negatives, not false positives.

## Not covered / unverified

- Answer feedback quality was checked on one live answer only; mock feedback is a crude word count.
- The simulations are simplified models; their numbers are not validated against real load balancers or databases.
  Clipboard copy and file downloads were not exercised by automation.

- Authorship has not been run on a real multi-author project; squash merges and large histories are untested.
  The live run does not use the authorship check (the check runs in code after the model's replies).
- Samples in `samples/outputs/` were all regenerated on 2026-11-24 with the authorship check on.

- **Live hallucination attempts by a real model**: the real model was well-behaved on 3 JDs; adversarial cheating is only proven
  with the mock attacker. The live path was exercised, not stress-tested.
- **Other repos**: only the synthetic sample repo (14 files, 12 commits) has been run end to end. Large repos are truncated
  (~180k chars digest) and untested at scale; non-git folders are only unit-tested.
- **Cross-browser / real mouse flow**: only the in-app browser, driven partly via script; no Playwright/Selenium suite in `make test`
  (browser automation isn't installed). The automated UI test is HTTP-level + JS syntax check.
- **Usage-limit / not-logged-in with the real CLI**: tested with mocked subprocess output, not against a genuinely rate-limited account.
  The error-text patterns are my best guess at the CLI's wording.
- Semantic exaggeration (e.g. "optimized", "robust") isn't detected by the lexical claim tracer.
- Python 3.11/3.12 not tested (only 3.13.9 available here).
- Recordings are from one live run each; LLM output varies run to run, so a fresh live run can differ from the recorded one.
