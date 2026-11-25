"""Authorship: only code the candidate wrote may support a claim."""
import os
import subprocess
from pathlib import Path

import pytest

from resume_agent.authorship import Authorship, list_authors
from resume_agent.ingest import Repo, RepoError
from resume_agent.llm import get_provider
from resume_agent.models import (BulletRaw, Evidence, GenerateOut, LedgerItemRaw, LedgerOut, MatchOut, MatchRaw,
                                 QuestionRaw, Requirement)
from resume_agent.pipeline import build_ledger, run_pipeline, validate_matches, verify_bullets

ME, OTHER = "me@example.invalid", "other@example.invalid"


def git(root, *args, who=ME):
    env = dict(os.environ, GIT_AUTHOR_NAME=who.split("@")[0], GIT_AUTHOR_EMAIL=who,
               GIT_COMMITTER_NAME="c", GIT_COMMITTER_EMAIL=who,
               GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)


def commit(root, files, message, who=ME):
    for name, text in files.items():
        (root / name).write_text(text)
    git(root, "add", "-A", who=who)
    git(root, "commit", "-q", "-m", message, who=who)


KAFKA = "from kafka import KafkaConsumer\n\ndef consume(topic):\n    return KafkaConsumer(topic)\n"
DB = "import sqlite3\n\ndef connect(path):\n    return sqlite3.connect(path)\n"


@pytest.fixture()
def mixed_repo(tmp_path):
    """OTHER writes the Kafka consumer. ME writes SQLite code and adds one line to the Kafka file."""
    root = tmp_path / "r"
    root.mkdir()
    git(root, "init", "-q")
    commit(root, {"consumer.py": KAFKA}, "Add Kafka consumer", who=OTHER)
    commit(root, {"db.py": DB}, "Add SQLite storage")
    commit(root, {"consumer.py": KAFKA + "\nDEFAULT_TOPIC = 'orders'\n"}, "Add default topic")
    commit(root, {"pair.py": "import redis\ncache = redis.Redis()\n"},
           f"Add Redis cache\n\nCo-authored-by: Me <{ME}>", who=OTHER)
    return root


def file_ev(path, start, end, quote, **kw):
    return Evidence(kind="file", path=path, start_line=start, end_line=end, quote=quote, **kw)


def attribute(root, ev, ids=(ME,)):
    from resume_agent.verifier import verify_evidence
    repo = Repo(root)
    checked, _ = verify_evidence(repo, ev)
    assert checked.verified, checked.verify_note
    return Authorship(repo, list(ids)).attribute(checked)


def head(root, grep):
    return subprocess.run(["git", "log", "--format=%H", f"--grep={grep}"], cwd=root, capture_output=True,
                          text=True, check=True).stdout.split()[0]


@pytest.mark.parametrize("ev,status,counts", [
    (file_ev("db.py", 1, 4, "sqlite3.connect(path)"), "mine", True),
    (file_ev("consumer.py", 1, 4, "KafkaConsumer(topic)"), "not_mine", False),
    (file_ev("consumer.py", 1, 6, "DEFAULT_TOPIC = 'orders'"), "mixed", True),
    # citing a wide range that includes one of my lines must not borrow someone else's quote
    (file_ev("consumer.py", 1, 6, "from kafka import KafkaConsumer"), "not_mine", False),
    (file_ev("pair.py", 1, 2, "redis.Redis()"), "mixed", True),
])
def test_file_attribution(mixed_repo, ev, status, counts):
    labeled, text = attribute(mixed_repo, ev)
    assert (labeled.authorship, bool(text)) == (status, counts), labeled.authorship_note


def test_traceable_text_holds_only_my_lines(mixed_repo):
    _, text = attribute(mixed_repo, file_ev("consumer.py", 1, 6, "DEFAULT_TOPIC = 'orders'"))
    assert "DEFAULT_TOPIC" in text and "Kafka" not in text


def test_commit_attribution(mixed_repo):
    def ev(grep, quote):
        return Evidence(kind="commit", commit=head(mixed_repo, grep), quote=quote)
    assert attribute(mixed_repo, ev("SQLite", "Add SQLite storage"))[0].authorship == "mine"
    assert attribute(mixed_repo, ev("Kafka consumer", "Add Kafka consumer"))[0].authorship == "not_mine"
    assert attribute(mixed_repo, ev("Redis", "Add Redis cache"))[0].authorship == "mixed"


def test_my_commit_cannot_claim_context_or_removed_lines(mixed_repo):
    commit(mixed_repo, {"consumer.py": "DEFAULT_TOPIC = 'orders'\n"}, "Remove consumer")
    labeled, text = attribute(mixed_repo, Evidence(kind="commit", commit=head(mixed_repo, "Remove consumer"),
                                                   quote="from kafka import KafkaConsumer"))
    assert labeled.authorship == "not_mine" and not text


def test_moved_code_stays_with_original_author(mixed_repo):
    (mixed_repo / "consumer.py").unlink()
    commit(mixed_repo, {"moved.py": KAFKA}, "Move consumer")
    assert attribute(mixed_repo, file_ev("moved.py", 1, 4, "KafkaConsumer(topic)"))[0].authorship == "not_mine"


def test_uncommitted_and_untracked_lines_do_not_count(mixed_repo):
    (mixed_repo / "db.py").write_text(DB + "import terraform_client\n")
    assert attribute(mixed_repo, file_ev("db.py", 5, 5, "import terraform_client"))[1] == ""
    assert attribute(mixed_repo, file_ev("db.py", 1, 4, "sqlite3.connect(path)"))[0].authorship == "mine"


def test_repo_mailmap_cannot_reassign_authorship(mixed_repo):
    commit(mixed_repo, {".mailmap": f"Me <{ME}> <{OTHER}>\n"}, "Add mailmap")
    assert attribute(mixed_repo, file_ev("consumer.py", 1, 4, "KafkaConsumer(topic)"))[1] == ""


def test_shallow_clone_boundary_is_unknown(mixed_repo, tmp_path):
    clone = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth=1", mixed_repo.as_uri(), str(clone)], check=True)
    a = Authorship(Repo(clone), [ME])       # ME co-authored the tip commit
    assert set(a.line_owners("consumer.py")) == {"unknown"}
    assert any("Shallow" in w for w in a.warnings())


def test_bulk_commit_warning(tmp_path):
    root = tmp_path / "bulk"
    root.mkdir()
    git(root, "init", "-q")
    commit(root, {"big.py": "".join(f"x{i} = {i}\n" for i in range(400))}, "Initial upload")
    assert any("added 100%" in w for w in Authorship(Repo(root), [ME]).warnings())


def test_authors_listed_and_unknown_email_rejected(mixed_repo):
    assert {a["email"] for a in list_authors(Repo(mixed_repo))} == {ME, OTHER}
    with pytest.raises(RepoError):
        Authorship(Repo(mixed_repo), ["nobody@example.invalid"])


def test_pipeline_pieces_exclude_others_work(mixed_repo):
    repo, a = Repo(mixed_repo), Authorship(Repo(mixed_repo), [ME])
    kafka = file_ev("consumer.py", 1, 4, "KafkaConsumer(topic)", authorship="mine")   # LLM lies
    sqlite = file_ev("db.py", 1, 4, "sqlite3.connect(path)")
    not_yours = set()
    ledger, rejected, ev_text = build_ledger(repo, LedgerOut(items=[
        LedgerItemRaw(name="Kafka", evidence=[kafka]), LedgerItemRaw(name="SQLite", evidence=[sqlite])]), a, not_yours)
    assert [i.name for i in ledger] == ["SQLite"] and not_yours == {"L1"}
    assert any("not shown to be your work" in r.reasons[0] for r in rejected)

    reqs = [Requirement(id="R1", text="Kafka experience", priority="required", keywords=["Kafka"])]
    m = validate_matches(reqs, ledger, ev_text, MatchOut(matches=[
        MatchRaw(requirement_id="R1", status="SUPPORTED", ledger_ids=["L1"])]), [], not_yours)[0]
    assert m.status == "GAP" and any("not shown to be your work" in x for x in m.adjustments)

    bullets, questions, _ = verify_bullets(repo, GenerateOut(
        bullets=[BulletRaw(text="Built a Kafka consumer", evidence=[kafka]),
                 BulletRaw(text="Used SQLite for storage", evidence=[sqlite, kafka]),
                 BulletRaw(text="Used SQLite with Kafka", evidence=[sqlite, kafka])],
        interview=[QuestionRaw(question="Why Kafka?", evidence=[kafka])]), {"L2"}, {"R1"}, a)
    assert [b.status for b in bullets] == ["blocked", "ok", "blocked"]
    assert [e.path for e in bullets[1].evidence] == ["db.py"]     # others' code is not shown as support
    assert questions == []

    # without the check the same Kafka bullet passes, but is labeled unchecked
    b = verify_bullets(repo, GenerateOut(bullets=[BulletRaw(text="Built a Kafka consumer", evidence=[kafka])]),
                       set(), set())[0][0]
    assert b.status == "ok" and b.evidence[0].authorship == "unchecked"


def test_end_to_end_demo_author_and_report(repo_path, jds, tmp_path):
    jd = jds["backend_streaming_engineer"]
    mock = lambda: get_provider("mock", use_cache=False)  # noqa: E731
    plain = run_pipeline(repo_path, jd, mock())
    mine = run_pipeline(repo_path, jd, mock(), authors=["Demo@Example.invalid"])
    assert not plain.authorship.checked and plain.notices[1 if plain.meta.mode == "MOCK" else 0].startswith("AUTHORSHIP NOT CHECKED")
    assert mine.authorship.checked and mine.authorship.identities == ["demo@example.invalid"]
    assert [m.status for m in mine.matches] == [m.status for m in plain.matches]
    used = [e for i in mine.ledger for e in i.evidence] + [e for b in mine.bullets if b.status == "ok" for e in b.evidence]
    assert used and {e.authorship for e in used} == {"mine"}
    from conftest import assert_integrity
    assert_integrity(repo_path, mine)


def test_bad_identity_fails_before_any_llm_call(repo_path, jds):
    class Boom:
        name = model = "boom"
        def complete(self, req):
            raise AssertionError("LLM called")
    with pytest.raises(RepoError):
        run_pipeline(repo_path, jds["python_api_engineer"], Boom(), authors=["typo@example.invalid"])


def test_hostile_repo_config_runs_nothing(mixed_repo, tmp_path):
    marker = tmp_path / "pwned"
    evil = tmp_path / "evil.sh"
    evil.write_text(f"#!/bin/sh\ntouch '{marker}'\ncat \"$@\"\n")
    evil.chmod(0o755)
    (mixed_repo / ".gitattributes").write_text("*.py diff=evil filter=evil\n")
    for key, val in [("core.fsmonitor", str(evil)), ("diff.evil.textconv", str(evil)),
                     ("diff.external", str(evil)), ("filter.evil.clean", str(evil))]:
        git(mixed_repo, "config", key, val)
    marker.unlink(missing_ok=True)
    repo = Repo(mixed_repo)
    repo.repo_hash(); repo.digest()
    a = Authorship(repo, [ME])
    a.line_owners("db.py"); a.warnings(); list_authors(repo)
    attribute(mixed_repo, Evidence(kind="commit", commit=head(mixed_repo, "SQLite"), quote="Add SQLite storage"))
    assert not marker.exists()
