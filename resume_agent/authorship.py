"""Authorship check: did the candidate write the cited code, not just have it in their repo?

The candidate says which commit emails are theirs. Every citation is then attributed with
`git blame` (file lines) or the commit's author (commits). Only text attributed to the
candidate may be used to support a claim.

Limits: git authorship is self-reported metadata. It can be faked, and it cannot tell
whether code was copied or generated before the candidate committed it. This is
"evidence from your repository", not certification.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass

from .ingest import Repo, RepoError
from .models import AuthorshipReport, Evidence
from .verifier import norm

OWNED = {"mine", "shared"}                    # line ownership that counts for the candidate
BULK_SHARE = 0.6                              # one commit adding this share of all lines -> warning
BULK_MIN_LINES = 200
EMAIL_RE = re.compile(r"<([^<>\s]+@[^<>\s]+)>")
_ZERO = "0" * 40


def normalize_ids(emails) -> list[str]:
    return sorted({e.strip().strip("<>").lower() for e in emails or [] if e and e.strip()})


@dataclass
class _Commit:
    author: str
    coauthors: set[str]


def _parse_coauthors(trailers: str) -> set[str]:
    return {m.lower() for m in EMAIL_RE.findall(trailers)}


def list_authors(repo: Repo) -> list[dict]:
    """Everyone who authored or co-authored a commit, so the candidate can pick themselves."""
    if not repo.is_git:
        return []
    out = repo.git("log", "--format=%x1e%ae%x1f%an%x1f%(trailers:key=Co-authored-by,valueonly)")
    commits, names = Counter(), {}
    for rec in out.split("\x1e")[1:]:
        email, name, trailers = (rec.split("\x1f") + ["", ""])[:3]
        people = {email.strip().lower(): name.strip()}
        for line in trailers.splitlines():
            m = EMAIL_RE.search(line)
            if m:
                people.setdefault(m.group(1).lower(), line.split("<")[0].strip())
        for e, n in people.items():
            commits[e] += 1
            names.setdefault(e, n)
    return [{"email": e, "name": names[e], "commits": c} for e, c in commits.most_common()]


class Authorship:
    def __init__(self, repo: Repo, identities):
        self.repo = repo
        self.ids = set(normalize_ids(identities))
        if not self.ids:
            raise ValueError("Authorship check needs at least one commit email")
        if not repo.is_git:
            raise RepoError("Authorship check needs a git repository")
        known = {a["email"] for a in list_authors(repo)}
        if not self.ids & known:
            raise RepoError("None of the given emails appears as an author or co-author in this repo's history. "
                            "Check the spelling, or list the authors with: python -m resume_agent authors --repo <path>")
        self.shallow = repo.git("rev-parse", "--is-shallow-repository").strip() == "true"
        self._commits: dict[str, _Commit] = {}
        self._lines: dict[str, list[str]] = {}

    # ---- commit and line attribution ----
    def _commit(self, sha: str) -> _Commit:
        if sha not in self._commits:
            out = self.repo.git("show", "-s", "--format=%ae%x1f%(trailers:key=Co-authored-by,valueonly)", sha)
            author, _, trailers = out.partition("\x1f")
            self._commits[sha] = _Commit(author.strip().lower(), _parse_coauthors(trailers))
        return self._commits[sha]

    def _ownership(self, sha: str) -> str:
        c = self._commit(sha)
        people = {c.author} | c.coauthors
        if not people & self.ids:
            return "other"
        return "mine" if people <= self.ids else "shared"

    def line_owners(self, path: str) -> list[str]:
        """One of mine | shared | other | uncommitted | unknown for each line of the file.

        Blames HEAD (never the working tree, so repo-configured filters do not run), then
        maps the result onto the working-tree lines the verifier reads.
        """
        if path in self._lines:
            return self._lines[path]
        current = self.repo.file_lines(path) or []
        owners = ["uncommitted"] * len(current)
        try:
            out = self.repo.git("blame", "--line-porcelain", "--no-textconv", "-w", "-M", "-C",
                                "HEAD", "--", path, check=True)
        except RepoError:
            out = ""                          # not in HEAD
        committed, shas, sha, boundary = [], [], _ZERO, False
        for line in out.split("\n"):
            if line.startswith("\t"):
                committed.append(line[1:].rstrip("\r"))
                # in a shallow clone, boundary lines are blamed on whoever made the cut-off commit
                shas.append((sha, boundary and self.shallow))
                boundary = False
            elif re.match(r"^[0-9a-f]{40} \d+ \d+", line):
                sha = line[:40]
            elif line == "boundary":
                boundary = True
        matcher = difflib.SequenceMatcher(a=committed, b=current, autojunk=False)
        for a, b, size in matcher.get_matching_blocks():
            for k in range(size):
                h, cut = shas[a + k]
                owners[b + k] = "unknown" if cut else self._ownership(h)
        self._lines[path] = owners
        return owners

    # ---- evidence ----
    def attribute(self, e: Evidence) -> tuple[Evidence, str]:
        """For an already verified citation: return (labeled copy, text the candidate may claim from it).

        The text is '' when the citation does not count as the candidate's work.
        """
        e = e.model_copy(deep=True)
        return self._attribute_file(e) if e.kind == "file" else self._attribute_commit(e)

    def _attribute_file(self, e: Evidence) -> tuple[Evidence, str]:
        lines = self.repo.file_lines(e.path)[e.start_line - 1:e.end_line]
        owners = self.line_owners(e.path)[e.start_line - 1:e.end_line]
        real = [i for i, l in enumerate(lines) if any(ch.isalnum() for ch in l)]   # ignore braces, blanks
        owned = [i for i in real if owners[i] in OWNED]
        if not owned:
            kinds = {owners[i] for i in real}
            if kinds and kinds <= {"uncommitted"}:
                return _mark(e, "not_mine", "cited lines are not committed, so no author can be shown")
            if "unknown" in kinds:
                return _mark(e, "not_mine", "authorship unknown (shallow clone); fetch full history")
            return _mark(e, "not_mine", "cited lines were not written under your commit emails")
        if not _quote_touches(lines, e.quote, set(owned)):
            return _mark(e, "not_mine", "the quoted snippet is not in lines you wrote")
        text = e.path + "\n" + "\n".join(lines[i] for i in range(len(lines)) if owners[i] in OWNED)
        if all(owners[i] == "mine" for i in real):
            _mark(e, "mine", f"all {len(real)} cited code lines are yours")
        else:
            shared = sum(owners[i] == "shared" for i in real)
            note = f"{len(owned)} of {len(real)} cited code lines are yours"
            if shared:
                note += f" ({shared} co-authored)"
            _mark(e, "mixed", note)
        return e, text

    def _attribute_commit(self, e: Evidence) -> tuple[Evidence, str]:
        full = e.resolved_commit
        who = self._ownership(full)
        if who == "other":
            return _mark(e, "not_mine", "commit was not authored or co-authored by you")
        message = self.repo.git("show", "-s", "--format=%B", full)
        diff = self.repo.commit_text(full)[1]
        added = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
        quote = norm(e.quote)
        plus_quote = norm("\n".join(l[1:] if l.startswith("+") else l for l in e.quote.splitlines()))
        if quote not in norm(message) and plus_quote not in norm(added):
            # removed and context lines can be someone else's code
            return _mark(e, "not_mine", "quote is not in the commit message or in lines this commit added")
        if who == "mine":
            _mark(e, "mine", "you authored this commit")
        else:
            _mark(e, "mixed", "co-authored commit")
        subject = message.strip().splitlines()[0] if message.strip() else ""
        return e, f"{subject}\n{e.quote}"

    # ---- report ----
    def warnings(self) -> list[str]:
        out = []
        if self.shallow:
            out.append("Shallow clone: some lines cannot be attributed. Fetch the full history.")
        log = self.repo.git("log", "--no-merges", "--numstat", "--format=%x1e%H")
        added = {}
        for rec in log.split("\x1e")[1:]:
            rows = rec.strip().splitlines()
            added[rows[0]] = sum(int(r.split("\t")[0]) for r in rows[1:] if r.split("\t")[0].isdigit())
        total = sum(added.values())
        if total >= BULK_MIN_LINES:
            sha, n = max(added.items(), key=lambda kv: kv[1])
            if n / total >= BULK_SHARE:
                out.append(f"Commit {sha[:8]} added {n * 100 // total}% of all lines in this history. "
                           "Git cannot show whether that code was written, copied or generated.")
        return out

    def report(self) -> AuthorshipReport:
        return AuthorshipReport(checked=True, identities=sorted(self.ids), warnings=self.warnings())


def _mark(e: Evidence, status: str, note: str) -> tuple[Evidence, str]:
    e.authorship, e.authorship_note = status, note
    return e, ""


def _quote_touches(lines: list[str], quote: str, owned: set[int]) -> bool:
    """True if some occurrence of the quote overlaps a line the candidate owns."""
    parts = [norm(l) for l in lines]
    joined, spans, pos = [], [], 0
    for i, p in enumerate(parts):
        if not p:
            continue
        spans.append((pos, pos + len(p), i))
        joined.append(p)
        pos += len(p) + 1
    hay, needle = " ".join(joined), norm(quote)
    at = hay.find(needle)
    while at != -1:
        if any(i in owned and a < at + len(needle) and b > at for a, b, i in spans):
            return True
        at = hay.find(needle, at + 1)
    return False
