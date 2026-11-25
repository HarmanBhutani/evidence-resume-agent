"""Read a local repo: files, commit history, diffs. Git is invoked as a plain subprocess."""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache",
              ".pytest_cache", ".cache", ".idea", ".vscode", "target"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock", "uv.lock", "Cargo.lock"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".tar", ".ico", ".woff", ".woff2",
              ".pyc", ".so", ".dylib", ".class", ".jar", ".db", ".sqlite", ".mp4", ".mov"}
MAX_FILE_BYTES = 200_000
HASH_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


class RepoError(Exception):
    pass


@dataclass
class CommitInfo:
    hash: str
    date: str
    subject: str
    files: list[str]


def _git(root: Path, *args: str, check: bool = True) -> str:
    # the repo is untrusted: switch off config that would make read-only git commands run programs
    r = subprocess.run(["git", "-c", "core.quotepath=false", "-c", "core.fsmonitor=false",
                        "-c", "log.showSignature=false", *args], cwd=root, capture_output=True,
                       text=True, errors="replace", timeout=60)
    if check and r.returncode != 0:
        raise RepoError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout


class Repo:
    def __init__(self, path: str | Path):
        self.root = Path(path).expanduser().resolve()
        if not self.root.is_dir():
            raise RepoError(f"Not a directory: {self.root}")
        self.name = self.root.name
        self.is_git = (self.root / ".git").exists()
        self.files: dict[str, list[str]] = {}
        self._commit_cache: dict[str, tuple[str, str] | None] = {}
        self._load_files()
        if not self.files:
            raise RepoError("No readable text files found in repo")

    def git(self, *args: str, check: bool = False) -> str:
        return _git(self.root, *args, check=check)

    # ---- files ----
    def _list_paths(self) -> list[str]:
        if self.is_git:
            out = _git(self.root, "ls-files", check=False)
            paths = [p for p in out.splitlines() if p]
            if paths:
                return paths
        res = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(self.root).parts):
                res.append(p.relative_to(self.root).as_posix())
        return res

    def _load_files(self) -> None:
        for rel in self._list_paths():
            p = self.root / rel
            if (Path(rel).name in SKIP_FILES or Path(rel).suffix.lower() in BINARY_EXT
                    or any(part in SKIP_DIRS for part in Path(rel).parts[:-1])):
                continue
            try:
                if not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
                    continue
                self.files[rel] = p.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue

    def file_lines(self, path: str) -> list[str] | None:
        """Only paths from the file listing resolve; traversal and absolute paths never match."""
        return self.files.get(path)

    # ---- commits ----
    def commits(self, limit: int = 200) -> list[CommitInfo]:
        if not self.is_git:
            return []
        out = _git(self.root, "log", f"-n{limit}", "--date=short", "--name-only",
                   "--format=@@%H|%ad|%s", check=False)
        commits: list[CommitInfo] = []
        for block in out.split("@@")[1:]:
            lines = block.splitlines()
            h, d, s = (lines[0].split("|", 2) + ["", ""])[:3]
            commits.append(CommitInfo(h, d, s, [l for l in lines[1:] if l.strip()]))
        return commits

    def commit_text(self, h: str) -> tuple[str, str] | None:
        """(full_hash, message+diff text) or None if the commit does not exist."""
        if not self.is_git or not HASH_RE.match(h or ""):
            return None
        if h in self._commit_cache:
            return self._commit_cache[h]
        r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{h}^{{commit}}"], cwd=self.root,
                           capture_output=True, text=True)
        if r.returncode != 0:
            self._commit_cache[h] = None
            return None
        full = r.stdout.strip()
        text = _git(self.root, "show", "--no-color", "--no-textconv", "--no-ext-diff", "--date=short", "--format=%H%n%ad%n%B", full)
        self._commit_cache[h] = (full, text)
        return full, text

    # ---- hashing / digest ----
    def repo_hash(self) -> str:
        h = hashlib.sha256()
        for path in sorted(self.files):
            h.update(path.encode())
            h.update("\n".join(self.files[path]).encode())
        if self.is_git:
            h.update(_git(self.root, "rev-parse", "HEAD", check=False).encode())
        return h.hexdigest()[:16]

    def digest(self, max_chars: int = 180_000, max_commits: int = 100) -> str:
        """Compact, line-numbered text of the repo for the LLM."""
        parts: list[str] = []
        used = 0
        omitted = []
        order = sorted(self.files, key=lambda p: (p.startswith("tests/"), p.count("/"), p))
        for path in order:
            lines = self.files[path][:400]
            body = "\n".join(f"{i:>4}| {l}" for i, l in enumerate(lines, 1))
            chunk = f"### FILE {path} ({len(self.files[path])} lines)\n{body}\n"
            if used + len(chunk) > max_chars * 0.7:
                omitted.append(path)
                continue
            parts.append(chunk)
            used += len(chunk)
        parts.append("\n### COMMIT HISTORY (newest first)\n")
        for c in self.commits(max_commits):
            ct = self.commit_text(c.hash)
            diff = ""
            if ct:
                diff_lines = [l for l in ct[1].splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
                diff = "\n".join(diff_lines[:25])
            chunk = f"## COMMIT {c.hash[:10]} {c.date} | {c.subject}\nfiles: {', '.join(c.files[:8])}\n{diff}\n"
            if used + len(chunk) > max_chars:
                parts.append("... (older commits omitted for size)\n")
                break
            parts.append(chunk)
            used += len(chunk)
        if omitted:
            parts.append(f"\n(files omitted for size: {', '.join(omitted)})\n")
        return "\n".join(parts)
