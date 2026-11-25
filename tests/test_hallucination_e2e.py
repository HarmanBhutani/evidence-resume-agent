import pytest

from resume_agent.llm.mock import MockProvider
from resume_agent.pipeline import run_pipeline
from conftest import JD_NAMES, assert_integrity


def run(repo_path, jd, **kw):
    return run_pipeline(repo_path, jd, MockProvider(**kw))


# ---------- hallucination tests ----------
def test_mock_llm_cannot_invent_skills_or_metrics(repo_path, jds):
    r = run(repo_path, jds["adversarial_infra_rust"], hallucinate=True)
    names = " ".join(i.name for i in r.ledger).lower()
    assert "terraform" not in names and "rust" not in names and "2m" not in names
    texts = " ".join(b.text for b in r.bullets if b.status == "ok").lower()
    for bad in ("40%", "terraform", "led a team", "rust"):
        assert bad not in texts
    blocked = [b for b in r.bullets if b.status == "blocked"]
    assert len(blocked) == 5 and all(b.block_reasons for b in blocked)
    reasons = " | ".join(" ".join(b.block_reasons) for b in blocked)
    for expect in ("number '40'", "terraform", "commit not found", "snippet not found", "no evidence cited",
                   "cannot be proven"):
        assert expect in reasons.lower() or expect in reasons
    assert not any("Rust" in q.question for q in r.interview)
    assert_integrity(repo_path, r)


def test_gaps_reported_even_if_llm_claims_supported(repo_path, jds):
    r = run(repo_path, jds["adversarial_infra_rust"], hallucinate=True)
    st = {q.text.split()[0]: m.status for q, m in zip(r.requirements, r.matches)}
    for key in ("Production", "Systems", "Operating", "Go", "Leading", "GraphQL"):
        assert st[key] == "GAP", (key, st)
    assert any("SUPPORTED -> GAP" in a for m in r.matches for a in m.adjustments)
    assert any(x.what == "bullet" for x in r.rejected) and any(x.what == "ledger item" for x in r.rejected)


# ---------- end to end (mock) ----------
EXPECT = {
    "backend_streaming_engineer": dict(
        supported=["Kafka", "dead-letter", "FastAPI", "pytest", "Docker", "Prometheus", "GitHub Actions"],
        gaps=["5+ years", "Mentoring", "PostgreSQL", "Kubernetes"]),
    "python_api_engineer": dict(supported=["FastAPI", "Pagination", "pytest", "Docker", "Continuous integration"],
                                gaps=["communication"]),
    "adversarial_infra_rust": dict(supported=["Python", "Docker"],
                                   gaps=["Terraform", "Rust", "Kubernetes", "Go for", "Leading", "GraphQL"]),
}


@pytest.mark.parametrize("name", JD_NAMES)
def test_end_to_end_mock(repo_path, jds, name):
    r = run(repo_path, jds[name])
    assert r.meta.mode == "MOCK" and r.ledger and r.requirements and len(r.matches) == len(r.requirements)
    status = {q.text: m.status for q, m in zip(r.requirements, r.matches)}
    for key in EXPECT[name]["supported"]:
        assert any(key in t and s == "SUPPORTED" for t, s in status.items()), (key, status)
    for key in EXPECT[name]["gaps"]:
        assert any(key in t and s == "GAP" for t, s in status.items()), (key, status)
    ok = [b for b in r.bullets if b.status == "ok"]
    assert ok and all(b.evidence and all(e.verified for e in b.evidence) for b in ok)
    assert not [b for b in r.bullets if b.status == "blocked"], "honest mock should not be blocked"
    # no bullet addresses a GAP requirement
    gap_ids = {m.requirement_id for m in r.matches if m.status == "GAP"}
    assert not any(set(b.requirement_ids) & gap_ids for b in ok)
    assert r.interview and not r.rejected
    n = assert_integrity(repo_path, r)
    assert n >= 10


def test_adversarial_has_no_supported_infra_and_few_bullets(repo_path, jds):
    r = run(repo_path, jds["adversarial_infra_rust"])
    txt = " ".join(b.text for b in r.bullets).lower()
    for w in ("terraform", "rust", "kubernetes", "aws", "graphql", "golang"):
        assert w not in txt


def test_user_provided_items_are_labelled_and_unverified(repo_path, jds):
    from resume_agent.models import UserItem
    r = run_pipeline(repo_path, jds["backend_streaming_engineer"], MockProvider(),
                     user_items=[UserItem(text="Mentored 2 junior engineers")])
    ub = [b for b in r.bullets if b.origin != "verified"]
    assert len(ub) == 1 and ub[0].origin == "user-provided, unverified" and not ub[0].evidence
    mentor = next(m for q, m in zip(r.requirements, r.matches) if "Mentoring" in q.text)
    assert mentor.status == "GAP" and mentor.non_code
    assert any("cannot prove leadership" in n for n in r.notices)


# ---------- committed live recordings replay offline ----------
@pytest.mark.parametrize("name", JD_NAMES)
def test_committed_recordings_replay_and_pass_integrity(repo_path, jds, name):
    from resume_agent.llm.replay import ReplayProvider
    rec = ReplayProvider()
    if not list(rec.dir.glob("ledger__*.json")):
        pytest.skip("no recordings in samples/recorded (run `make record`)")
    r = run_pipeline(repo_path, jds[name], rec)
    assert r.meta.mode == "REPLAYED" and r.meta.model.endswith("(recorded)")
    assert_integrity(repo_path, r)
    status = {q.text: m.status for q, m in zip(r.requirements, r.matches)}
    for key in EXPECT[name]["gaps"]:
        assert any(key in t and s == "GAP" for t, s in status.items()), (key, status)
    assert not [b for b in r.bullets if b.status == "ok" and any(w in b.text.lower() for w in ("terraform", "rust", "kubernetes"))]
