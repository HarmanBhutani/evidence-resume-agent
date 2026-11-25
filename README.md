# Evidence-Grounded Resume Agent (demo)

AI resume tools hallucinate: they inflate bullets to match a job description, and the inflation collapses in the
interview. Meanwhile the best proof of an engineer's work (repos, commits, diffs) goes unused.

This demo builds resume bullets **only from evidence in your own git repo**, and enforces that in code:

1. **Ingest** a local repo (files, commit history, diffs).
2. **Verified skills ledger**: skills/achievements, each with `file:lines` and/or commit citations + the quoted snippet.
3. **JD parsing**: pasted job description → required / preferred requirements.
4. **Matching**: each requirement → `SUPPORTED` / `PARTIAL` / `GAP`. Gaps are flagged, never invented.
5. **Tailored bullets**: every claim links to evidence; bullets without valid evidence are blocked **by code**.
6. **Interview prep**: questions drawn from your own code, each citing it. Type an answer and get feedback.
7. **Learn system design** (`/learn`): two interactive simulations, load balancing and database deadlocks, linked
   from related gaps.

> Local personal demo. All sample data is synthetic. Not a hosted service.

## For evaluators: 5-minute look (no Claude login needed)

```bash
pip install -r requirements.txt     # Python 3.11+
make eval                           # UI at http://127.0.0.1:8000 on recorded live outputs (badge: REPLAYED)
```

1. Pick **Staff Infrastructure Engineer (adversarial)** and click **Analyze & generate**. Terraform, Rust, Kubernetes and
   leadership come back as **GAP**, and no bullet mentions them.
2. Click any blue citation chip: the drawer opens the real lines in the sample repo, with who wrote them.
3. Open **Rejected by the verifier** to see what code blocked.
4. Stop the server and start `MOCK_HALLUCINATE=1 LLM_PROVIDER=mock make run` to watch a cheating fake model (invented
   Terraform, a 40% metric, a fake commit, "led a team of 5") get blocked.
5. `SKIP_LIVE=1 make test` runs the offline test suite (about 20 s).

Saved outputs for all three sample JDs are in `samples/outputs/` (`live`, `mock`, `mock_hallucination_attack`), each with
a readable `resume_bullets.md`. To run live on your own repo you need Claude Code installed and logged in (below).

## Quick start

```bash
# 1. Install Claude Code and log in FIRST (the default LLM backend runs on your own Claude login)
#    https://docs.claude.com/claude-code  ->  run `claude` once and sign in. Check: claude auth status
python3 --version          # needs 3.11+
make setup                 # optional: venv + deps; later make targets use the venv automatically
make run                   # UI at http://127.0.0.1:8000   (default provider: claude_cli = LIVE)
make demo                  # CLI: 3 sample JDs end to end -> out/<mode>/<jd>/
make test                  # everything (see "Testing")
make eval                  # UI on recorded outputs, no login needed
make samples               # regenerate offline samples (mock + hallucination attack)
```

No Claude login? Use `LLM_PROVIDER=replay make run` (recorded live outputs) or `LLM_PROVIDER=mock make run` (offline rules).

| env var | default | meaning |
|---|---|---|
| `LLM_PROVIDER` | `claude_cli` | `claude_cli` (live), `replay` (saved live responses), `mock` (deterministic offline) |
| `LLM_MODEL` | `sonnet` | model alias passed to `claude --model` |
| `LLM_TIMEOUT` | `300` | seconds per CLI call |
| `LLM_RECORD` | unset | `1` = save live responses to `samples/recorded/` (or tick "record" in the UI / `--record`) |
| `CLAUDE_BIN` | `claude` on PATH | path to the CLI |
| `MOCK_HALLUCINATE` | unset | `1` = the mock tries to cheat (used to prove the verifier blocks it) |

## Architecture

```
 repo (git) ──► ingest ──► digest (line-numbered files + commits) ─┐
                                                                    ▼
 JD text ───────────────────────────────────────────►  LLM provider (claude_cli | replay | mock)
                                                         4 calls: ledger · jd_parse · match · generate
                                                                    │  JSON only, pydantic-validated, 1 retry
                                                                    ▼
        ┌──────────────── CODE (no LLM) enforces ────────────────┐
        │ reference verifier: file exists · line range valid ·    │
        │   commit exists · quote found in that range/commit      │
        │ claim tracer: numbers, technologies, scale, leadership  │
        │   words must appear in the cited evidence text          │
        │ matcher: status downgraded if keywords not in evidence  │
        │ non-code requirements (years, mentoring…) never SUPPORTED│
        └─────────────────────────────────────────────────────────┘
                                   ▼
        FastAPI + single-page UI: Ledger │ Match │ Bullets (+ interview, rejected log)
```

LLM backend: `claude -p --output-format json --model sonnet --tools "" --no-session-persistence
--disable-slash-commands --strict-mcp-config --setting-sources "" --system-prompt …`, prompt on **stdin**, run in an
empty temp dir. Flags were checked against `claude --help` (v2.1.319). The app never reads, copies or stores any Claude
token, never logs prompts or secrets, and removes `ANTHROPIC_API_KEY` from the child env so your Pro login is used.
Repo/JD text goes inside nonce-delimited `<<<DATA …>>>` blocks and the system prompt says to ignore instructions inside.
Responses are cached on disk (`.cache/llm/`, keyed by prompt hash = repo + JD content), and the UI shows `LIVE · cached`
when a result is a cache hit — still labeled honestly.

## How the verifier works (`resume_agent/verifier.py`, `claims.py`)

The LLM's output is a *proposal*. Before anything is shown:

- **Citation check** – each evidence object is opened: the file must be in the repo listing (no traversal), the line range
  valid and ≤ 60 lines, a commit hash must resolve via `git rev-parse` (hex only), and the quoted snippet must appear
  (whitespace-normalised) inside that exact range / commit message+diff.
- **Claim tracing** – numbers (incl. "tenfold", "doubled"), named technologies/concepts (vocabulary + CamelCase/ALLCAPS/
  proper-noun heuristic), scale words ("high-throughput", "millions") and leadership words ("led", "mentored") in a bullet
  must be traceable to the cited evidence text (quote + cited lines + verified path). Otherwise the bullet is **blocked**
  and shown in the Rejected log with the reason. (We block rather than strip: stripping words changes meaning.)
- **Ledger** – items need ≥1 valid citation; an untraceable name drops the item; untraceable summary prose is withheld.
- **Matching** – SUPPORTED needs valid ledger ids *and* every technology keyword of the requirement present in that
  evidence; otherwise downgraded to PARTIAL/GAP (shown as "code adjusted"). Requirements about years of experience,
  mentoring, leadership, communication, etc. can't be proven by a repo → never SUPPORTED. You can add such items by hand;
  they appear labeled **user-provided, unverified**, never get citations, and never change a status.
- **Interview questions** with invalid citations are dropped.

## Authorship check (`resume_agent/authorship.py`)

A verified citation shows code **exists** in the repo, not that **you wrote it**. Select your commit emails in the UI,
or pass them on the command line:

```bash
python3 -m resume_agent authors --repo /path/to/repo
```

```bash
python3 -m resume_agent run --repo /path/to/repo --jd job.txt --author you@example.com
```

- File citations use `git blame` on HEAD (ignores whitespace changes, follows moved code, ignores `.mailmap`).
  Each is labeled **yours**, **partly yours** or **not yours**. Commit citations use the commit's author and co-authors.
- Only your lines can support a claim. If a range mixes authors, technologies and numbers must appear in *your* lines,
  and the quoted snippet must touch them. For commits, the quote must be in the message or in lines the commit added.
- Ledger items, bullets and interview questions with no evidence of yours are dropped or blocked; affected requirements
  become gaps. Co-authored work (pairs, AI assistants listed as co-authors) shows as partly yours.
- Uncommitted lines don't count. In shallow clones, lines from the cut-off commit are unknown and don't count.
- You get a warning if one commit added 60% or more of all lines (only for histories of 200+ added lines).
- With no email selected, results say **AUTHORSHIP NOT CHECKED**. On the sample repo, the UI pre-selects its synthetic
  author and `make demo` uses it.

Tried locally (mock mode, nothing sent anywhere) on three real repos with 8, 3 and 662 authors (up to ~4,800 files):
no errors, under 10 s per run.

**What it can't do:** git authorship is self-reported and can be faked. A copied or generated file committed under your
email counts as yours. Squash merges and rewritten history change attribution. Fork, template and vendored-code
detection is not built. This is evidence from your repository, not certification.

## Interview practice (`resume_agent/practice.py`)

Under each interview question, **Practice answer** opens a box for the answer you would give. **Get feedback** scores it
1–5 on correctness, trade-offs, failure cases and clarity, lists what worked and what to improve, suggests code you
should have mentioned, and gives a likely follow-up question.

- The feedback is an AI opinion and is labeled as one. What code enforces: the cited lines are re-opened (a changed
  file is reported, not guessed), and every "worth mentioning" point must quote that code or it is dropped.
- Your answer is sent inside a fenced data block and treated as untrusted. Answers are limited to 4,000 characters.
- Providers: `claude_cli` (default when installed, about 10 s) or `mock` (simple word rules: it counts code names you
  mention, so it can score a sound answer low). Replay can't give feedback, since a new answer was never recorded.

## Learn system design (`/learn`, `resume_agent/static/learn.html`, `sims.js`)

Two original simulations, each with a predict-first question, live controls, a comparison table, "try this" ideas
and a one-line interview answer:

- **Load balancing**: round robin, least connections or random across 3 servers. Slow one down, crash one, change the
  health-check interval and traffic. Shows queues, p50/p95 latency, lost and rejected requests. It also shows a real
  pitfall: after a crash, least connections loses the most requests, because a dead server always looks idle.
- **Database deadlocks**: two transfers locking rows in opposite order (pauses on the moment they block each other),
  or a busy bank with random transfers. Compare "lock from first" with "lock lowest id first", and the deadlock-check
  interval.

The models are simple (random arrivals, fixed service times, 1 ms steps, fixed seed) and meant to show behaviour,
not to match a real system. The logic in `sims.js` has no drawing code, so `tests/test_sims.py` runs it in node.
Requirements that mention related topics (load balancing, failover, locks, transactions, SQL databases) link to the
matching simulator. Practising never changes a requirement's status. Topics are original work; the external
[SimuVeda lab](https://sysdesign.simuveda.in/lab/) is linked for further study and nothing is copied from it.

## Testing

`make test` runs 90+ tests (pytest): simulations (node), answer feedback, authorship, ingestion, verifier, claim tracer, JD parser, matcher, bullet generator/blocker,
`claude_cli` wrapper with mocked subprocess (success, bad JSON, retry, timeout, not logged in, usage limit, missing CLI),
providers/cache/record/replay, hallucination attacks, reference-integrity re-check (independent of the verifier), end-to-end
on all 3 sample JDs (mock), committed live recordings replayed offline, a real server smoke test over HTTP (+ `node --check`
of the UI script), and one live Claude CLI run (auto-skipped if the CLI is missing/logged out; `SKIP_LIVE=1` to skip).
See [TEST_REPORT.md](TEST_REPORT.md) for what ran and what is not covered.

## Layout

```
resume_agent/   ingest.py authorship.py verifier.py claims.py techvocab.py pipeline.py prompts.py models.py export.py server.py __main__.py
resume_agent/llm/   base.py claude_cli.py mock.py replay.py cache.py
resume_agent/practice.py            answer feedback
resume_agent/static/index.html      single-page UI · learn.html + sims.js: system design simulations
demo/build_sample_repo.py           builds demo/sample_repo (deterministic hashes) · demo/jds/*.txt (3 JDs, 1 adversarial)
samples/outputs/{live,mock,mock_hallucination_attack}/<jd>/   ledger.json match_report.json bullets.json interview_questions.json resume_bullets.md
samples/recorded/                   recorded live Claude responses (replay)
tests/  Makefile  DEMO_SCRIPT.md  TEST_REPORT.md
```

## Defaults I chose (you can change them)

- Sonnet via CLI; 4 LLM calls per run (ledger is shared across JDs for the same repo via cache); 300 s timeout.
- Blocking beats stripping; strictness is deliberately high: some true claims get rejected when the cited lines don't
  contain the exact term (e.g. a "pytest" item citing lines without the word "pytest"). That is a false-negative by design.
- Recordings are keyed by input fingerprint (repo hash, JD hash), not prompt text, so prompt tweaks don't invalidate them;
  they only replay for the sample repo + sample JDs (the sample repo has pinned commit dates, so hashes are reproducible).
- API-key provider intentionally **not** built; `LLMProvider` is a small interface (`complete(LLMRequest)`) so one can be added.
- Server binds to 127.0.0.1 only. `.env`-style secrets are never read.

## Known limits

- Authorship is opt-in and based on git metadata; see the section above.
- **Claude Pro usage limits & speed**: a live run is 4 sequential CLI calls (~50 s observed on the sample repo; large repos
  are truncated to ~180k chars of digest). If the limit is hit the UI shows "USAGE LIMIT"; switch to replay.
- **Local-only, personal use**: relies on your local Claude Code login; don't host it for others.
- **Claim tracing is lexical**: it catches invented numbers, technologies, scale and leadership words, not every
  semantic exaggeration ("optimized", "robust"). Citations make those reviewable, not provably true. Review before sending.
- Repos can't prove leadership, mentoring, years of experience, product impact or non-code work (flagged, user-added only).
- Technology vocabulary is a curated list (~80 canonical terms, ~150 aliases) plus heuristics; exotic tools are checked by heuristic only.
- Requirement keyword "X or Y" is treated as "X and Y" for the SUPPORTED check (so "SQLite or PostgreSQL" → PARTIAL).
- Replay works only for recorded inputs. Replayed output is always labeled REPLAYED, never LIVE.
- Reads the working tree (not a historical checkout); file citations refer to current files, commits to history.
