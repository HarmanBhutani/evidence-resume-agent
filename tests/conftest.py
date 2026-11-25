import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from resume_agent.server import DEMO_REPO, JD_DIR, ensure_demo_repo  # noqa: E402

JD_NAMES = ["backend_streaming_engineer", "python_api_engineer", "adversarial_infra_rust"]


@pytest.fixture(scope="session")
def repo_path():
    ensure_demo_repo()
    return str(DEMO_REPO)


@pytest.fixture(scope="session")
def repo(repo_path):
    from resume_agent.ingest import Repo
    return Repo(repo_path)


@pytest.fixture(scope="session")
def jds():
    return {n: (JD_DIR / f"{n}.txt").read_text() for n in JD_NAMES}


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def assert_integrity(repo_path, result):
    """Independent re-check: open every citation in the final output and find the quote.
    Deliberately does not reuse resume_agent.verifier."""
    root = Path(repo_path)
    refs = [e for it in result.ledger for e in it.evidence]
    refs += [e for b in result.bullets if b.status == "ok" and b.origin == "verified" for e in b.evidence]
    refs += [e for q in result.interview for e in q.evidence]
    assert refs, "no citations to check"
    for e in refs:
        if e.kind == "file":
            lines = (root / e.path).read_text().splitlines()
            assert 1 <= e.start_line <= e.end_line <= len(lines), e
            assert norm(e.quote) in norm("\n".join(lines[e.start_line - 1:e.end_line])), e
        else:
            out = subprocess.run(["git", "show", "--no-color", e.resolved_commit or e.commit], cwd=root,
                                 capture_output=True, text=True, check=True).stdout
            stripped = "\n".join(l[1:] if l[:1] in "+- " else l for l in out.splitlines())
            assert norm(e.quote) in norm(out) or norm(e.quote) in norm(stripped), e
    return len(refs)
