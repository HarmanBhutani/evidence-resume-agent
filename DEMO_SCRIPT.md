# Demo script (3–5 minutes)

**Setup (before the call):** Claude Code installed and logged in (`claude auth status`), then `make run` and open
http://127.0.0.1:8000. Keep `LLM_PROVIDER` unset for live. If you expect trouble, have a second terminal ready for
`LLM_PROVIDER=replay make run`.

**Mode honesty rule:** read the badge top-right out loud every time. `LIVE` = generated just now by Claude through the
local CLI. `LIVE · cached` = a live result from an earlier identical run. `REPLAYED (not live)` = recorded earlier.
`MOCK` = offline rules, no model.

## 0:00 — The problem (20 s)
Say: "AI resume tools inflate bullets to match a job description, and that falls apart in interviews. The best proof of
my work is already in my repos and commits. This tool only writes what the code can prove, and enforces that in code, not in a prompt."

## 0:20 — Point at the page (20 s)
- Top-right: "Provider is claude_cli, the badge says **LIVE** after a run. It runs on my own Claude login, locally."
- Under **Which commits are yours?**, tick the demo author. "It checks who wrote each line, not just that the code is there. Git authorship can be faked, so this isn't certification."
- Repository field is pre-filled with the synthetic `sample_repo` (a Kafka-style order consumer with retries, a DLQ, a REST API, tests).

## 0:40 — Good match (60–90 s)
1. JD dropdown → **Senior Backend Engineer, Event Streaming**. Click **Analyze & generate**.
2. While the steps tick (ingest → ledger → jd_parse → match → generate → verify, ~1 minute live): "Four model calls; everything after is deterministic code."
3. **Panel 1, Evidence Ledger:** click a blue citation chip (e.g. `orderflow/consumer.py:23-29`). The drawer shows the real
   lines highlighted and "verified ✓ — quoted snippet found". Click a `commit …` chip too.
4. **Panel 2, Requirement Match:** green = SUPPORTED, amber = PARTIAL, red = GAP. Point at `PostgreSQL` and `Kubernetes`:
   "The repo uses SQLite and has no Kubernetes, so these are gaps. No bullet is written for them."
   Point at "5+ years" and "Mentoring": "Repos can't prove that, so it says so (grey tag) instead of pretending."
5. **Panel 3, Bullets:** every bullet carries chips. Click one.

## 2:15 — Try to make it lie (60 s)
1. JD dropdown → **Staff Infrastructure Engineer (adversarial)**. Run.
2. Say: "This posting asks for Terraform, Rust, Kubernetes, Go, and leading a team. My repo has none of it."
3. Panel 2 is mostly red GAPs; Panel 3 only has bullets for Python/Docker-type evidence.
4. Open **Rejected by the verifier**: "When the model overreaches (an uncited summary, a term not in the quoted lines),
   code blocks it and shows why." (Offline proof: `MOCK_HALLUCINATE=1` makes a fake model invent Terraform, a 40% metric, a
   made-up commit and 'led a team of 5'; see `samples/outputs/mock_hallucination_attack/`, all blocked.)

## 3:15 — Your own non-code items (30 s)
Type "Mentored 2 junior engineers" under **Add non-code item** → Add → Run again. It appears as
**user-provided, unverified**: purple, no citation, never counted as supported.

## 3:45 — Interview practice + export (60 s)
1. Under the first question, click **Practice answer**, type a two-sentence answer and click **Get feedback**:
   "Scores are an AI opinion. The code points it suggests must quote my cited code, or they're dropped."
2. In the bullets panel, untick one bullet and click **Copy selected**.

## 4:45 — Learn system design (45 s)
1. In the match panel, the PostgreSQL gap links to the **database deadlocks** simulator. Open it.
2. It pauses when the two transfers block each other. Resume: the check aborts the younger one. Switch to
   **Lock lowest id first**: no deadlock.
3. Optional: **Load balancing**, tick "Server 2 is 4× slower", then **Compare all three**.

## 5:30 — Close (15 s)
"Every claim is traceable to a line or a commit; gaps are flagged; anything the repo can't prove is labeled unverified."

---

## If live fails
| UI error | meaning | do this |
|---|---|---|
| `USAGE LIMIT: …` | Claude Pro limit hit | switch provider (below) |
| `NOT LOGGED IN` | CLI not signed in | run `claude` in a terminal and log in |
| `TIMEOUT` | CLI too slow | retry, or `LLM_TIMEOUT=600 make run`, or switch |
| `CLI_MISSING` banner | `claude` not on PATH | set `CLAUDE_BIN` or switch |

**Switch to replay without restarting:** in the "LLM provider" dropdown choose **replay (recorded)** and click Analyze
again (works for the sample repo + 3 sample JDs; instant). Or restart: `LLM_PROVIDER=replay make run`.

**What to say, honestly:** "The live model hit a limit, so I'm showing a **recorded** run of the same pipeline. The badge says
REPLAYED. The model output is from earlier, but the verification code is running right now on the real repo, and every
citation still opens." Never say "live" while the badge reads REPLAYED or MOCK.

Last-resort offline: `LLM_PROVIDER=mock make run`: say "this is the offline rule-based stand-in, not Claude".
