import subprocess

from resume_agent.ingest import Repo
from resume_agent.models import Evidence
from resume_agent.verifier import MAX_RANGE_LINES, verify_evidence


def test_ingest_files_and_commits(repo):
    assert "orderflow/consumer.py" in repo.files and "tests/test_api.py" in repo.files
    cs = repo.commits()
    assert len(cs) == 12 and cs[-1].subject.startswith("Initial project skeleton")
    assert all(len(c.hash) == 40 for c in cs)


def test_repo_hash_stable(repo_path):
    assert Repo(repo_path).repo_hash() == Repo(repo_path).repo_hash()


def test_digest_has_line_numbers_and_commits(repo):
    d = repo.digest()
    assert "### FILE orderflow/consumer.py" in d and "| class OrderConsumer" in d
    assert "## COMMIT" in d and "dead-letter" in d


def test_path_traversal_never_resolves(repo):
    for p in ["../secret", "/etc/passwd", "orderflow/../../x", ".git/config"]:
        assert repo.file_lines(p) is None


def _line(repo, path, needle):
    for i, l in enumerate(repo.files[path], 1):
        if needle in l:
            return i, l.strip()
    raise AssertionError(needle)


def test_valid_file_ref(repo):
    n, q = _line(repo, "orderflow/consumer.py", "enable_auto_commit=False")
    e, text = verify_evidence(repo, Evidence(kind="file", path="orderflow/consumer.py", start_line=n, end_line=n, quote=q))
    assert e.verified and q in text


def test_quote_whitespace_normalised(repo):
    n, q = _line(repo, "orderflow/consumer.py", "enable_auto_commit=False")
    e, _ = verify_evidence(repo, Evidence(kind="file", path="orderflow/consumer.py", start_line=n, end_line=n,
                                          quote="  " + q.replace("=", " = ")))
    assert not e.verified   # different tokens, not just whitespace -> rejected


def test_missing_file_blocked(repo):
    e, t = verify_evidence(repo, Evidence(kind="file", path="infra/main.tf", start_line=1, end_line=2, quote="resource aws"))
    assert not e.verified and "not found" in e.verify_note and t == ""


def test_bad_ranges_blocked(repo):
    base = dict(kind="file", path="orderflow/consumer.py", quote="class OrderConsumer")
    for s, t in [(0, 3), (5, 3), (1, 9999), (None, None)]:
        assert not verify_evidence(repo, Evidence(start_line=s, end_line=t, **base))[0].verified
    wide = verify_evidence(repo, Evidence(kind="file", path="orderflow/consumer.py", start_line=1,
                                          end_line=MAX_RANGE_LINES + 5, quote="class OrderConsumer"))[0]
    assert not wide.verified and "too wide" in wide.verify_note


def test_quote_must_be_inside_range(repo):
    n, q = _line(repo, "orderflow/consumer.py", "enable_auto_commit=False")
    e, _ = verify_evidence(repo, Evidence(kind="file", path="orderflow/consumer.py", start_line=1, end_line=3, quote=q))
    assert not e.verified and "not found" in e.verify_note


def test_short_or_empty_quote_blocked(repo):
    assert not verify_evidence(repo, Evidence(kind="file", path="orderflow/consumer.py", start_line=1, end_line=1, quote="a"))[0].verified


def test_commit_refs(repo):
    c = next(c for c in repo.commits() if "dead-letter" in c.subject)
    for h in (c.hash, c.hash[:7]):
        e, _ = verify_evidence(repo, Evidence(kind="commit", commit=h, quote=c.subject))
        assert e.verified and e.resolved_commit == c.hash
    # a quote from the diff (with +/- prefix stripped) is accepted
    e, _ = verify_evidence(repo, Evidence(kind="commit", commit=c.hash, quote="def send_to_dlq(self, message, reason: str)"))
    assert e.verified


def test_bad_commit_refs(repo):
    for h in ["deadbeef", "HEAD", "--all", "zzzzzzz", "", "abc"]:
        assert not verify_evidence(repo, Evidence(kind="commit", commit=h, quote="Add Kafka consumer"))[0].verified
    c = repo.commits()[0]
    assert not verify_evidence(repo, Evidence(kind="commit", commit=c.hash, quote="Rewrite everything in Rust"))[0].verified


def test_non_git_folder_works(tmp_path):
    (tmp_path / "a.py").write_text("import os\nprint(os.getcwd())\n")
    r = Repo(tmp_path)
    assert not r.is_git and r.commits() == []
    assert not verify_evidence(r, Evidence(kind="commit", commit="abcdef1", quote="whatever text"))[0].verified
