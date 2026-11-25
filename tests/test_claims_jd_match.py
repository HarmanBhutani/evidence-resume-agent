from resume_agent.claims import check_claims, classify_noncode
from resume_agent.llm.base import LLMRequest
from resume_agent.llm.mock import MockProvider
from resume_agent.models import JDOut, LedgerItem, Evidence, MatchOut, MatchRaw, UserItem
from resume_agent.pipeline import build_requirements, validate_matches

EV = "from kafka import KafkaConsumer\nmax_retries: int = 5\nprometheus_client Counter"


def kinds(text, ev=EV):
    return {p.kind for p in check_claims(text, ev)}


def test_claims_traceable_ok():
    assert check_claims("Built a Kafka consumer with 5 retries", EV) == []


def test_invented_number_and_tech_and_scale_and_leadership():
    assert "number" in kinds("Built a Kafka consumer handling 10k messages")
    assert "technology" in kinds("Built a Kafka consumer deployed with Terraform")
    assert "technology" in kinds("Integrated Stripe payments")           # unknown proper noun
    assert "scale" in kinds("Built a high-throughput Kafka consumer")
    assert "unprovable" in kinds("Led the Kafka consumer redesign")
    assert "unprovable" in kinds("Mentored engineers on Kafka")
    assert "number" in kinds("Doubled throughput of the Kafka consumer")
    assert "number" in kinds("Cut costs tenfold with Kafka")


def test_no_false_block_on_plain_prose():
    assert check_claims("Built a consumer that commits offsets after processing", EV) == []


def test_noncode_classifier():
    assert classify_noncode("5+ years of professional experience") == ["years of experience"]
    assert "mentoring" in classify_noncode("Mentoring junior engineers")
    assert "leadership" in classify_noncode("Leading a platform team of 8+ engineers")
    assert classify_noncode("Writing automated tests with pytest") == []


def test_mock_jd_parser(jds):
    raw = MockProvider().complete(LLMRequest("jd_parse", "", "", JDOut, payload={"jd_text": jds["backend_streaming_engineer"]})).data
    reqs = build_requirements(raw)
    assert sum(r.priority == "required" for r in reqs) == 8 and sum(r.priority == "preferred" for r in reqs) == 4
    kafka = next(r for r in reqs if "Kafka" in r.text)
    assert "kafka" in [k.lower() for k in kafka.keywords]
    yrs = next(r for r in reqs if "5+ years" in r.text)
    assert not yrs.provable_from_repo and yrs.note


def _ledger():
    ev = Evidence(kind="file", path="a.py", start_line=1, end_line=1, quote="from kafka import KafkaConsumer", verified=True)
    return [LedgerItem(id="L1", kind="skill", name="Kafka", summary="s", evidence=[ev])], {"L1": "a.py\nfrom kafka import KafkaConsumer"}


def _reqs(*texts_kw):
    return build_requirements(JDOut(requirements=[{"text": t, "keywords": k} for t, k in texts_kw]))


def test_matcher_downgrades_unsupported_claims():
    led, ev = _ledger()
    reqs = _reqs(("Terraform experience", ["Terraform"]), ("Kafka consumers", ["Kafka"]),
                 ("Kafka and Rust", ["Kafka", "Rust"]), ("Mentoring juniors", []), ("5+ years of Kafka", ["Kafka"]))
    raw = MatchOut(matches=[MatchRaw(requirement_id=r.id, status="SUPPORTED", ledger_ids=["L1"]) for r in reqs])
    m = validate_matches(reqs, led, ev, raw, [])
    assert [x.status for x in m] == ["GAP", "SUPPORTED", "PARTIAL", "GAP", "PARTIAL"]
    assert m[3].non_code and m[0].adjustments


def test_matcher_unknown_ids_and_missing_matches_become_gap():
    led, ev = _ledger()
    reqs = _reqs(("Kafka consumers", ["Kafka"]), ("Kafka again", ["Kafka"]))
    raw = MatchOut(matches=[MatchRaw(requirement_id="R1", status="SUPPORTED", ledger_ids=["L99"])])
    assert [x.status for x in validate_matches(reqs, led, ev, raw, [])] == ["GAP", "GAP"]


def test_user_items_never_upgrade_status():
    led, ev = _ledger()
    reqs = _reqs(("Terraform experience", ["Terraform"]),)
    raw = MatchOut(matches=[MatchRaw(requirement_id="R1", status="GAP")])
    m = validate_matches(reqs, led, ev, raw, [UserItem(text="Used Terraform at a past job")])
    assert m[0].status == "GAP" and m[0].user_provided == ["Used Terraform at a past job"]


def test_number_words_in_set_phrases_are_not_quantities():
    # found in a live run: "test double" was read as "doubled" (x2) and blocked a true bullet
    from resume_agent.claims import numbers_in
    assert numbers_in("Added a pytest suite using a FakeProducer test double.") == []
    assert numbers_in("double-checked locking with double quotes") == []
    assert numbers_in("Doubled throughput") == ["2"] and numbers_in("twice as fast") == ["2"]
