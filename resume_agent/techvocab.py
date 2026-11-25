"""Technology / concept vocabulary used for deterministic claim tracing.

canonical term -> aliases (all lowercase). Used to decide whether a claim like "Kafka" or
"pagination" is literally present in evidence text.
"""
from __future__ import annotations

import re
from functools import lru_cache

VOCAB: dict[str, list[str]] = {
    "python": ["python", "pip", "pytest", "fastapi", "django", "flask", "pydantic", "asyncio"],
    "java": ["java", "jvm", "maven", "gradle"], "javascript": ["javascript", "js"],
    "typescript": ["typescript"], "go": ["golang"], "rust": ["rust", "cargo"], "c++": ["c++"],
    "c#": ["c#", "csharp"], "ruby": ["ruby"], "scala": ["scala"], "kotlin": ["kotlin"],
    "sql": ["sql", "select", "insert into", "create table"],
    "postgresql": ["postgresql", "postgres", "psycopg", "psycopg2", "asyncpg"],
    "mysql": ["mysql"], "sqlite": ["sqlite", "sqlite3"], "mongodb": ["mongodb", "pymongo"],
    "redis": ["redis"], "kafka": ["kafka", "kafkaconsumer", "kafkaproducer"],
    "rabbitmq": ["rabbitmq", "pika", "amqp"], "spark": ["spark", "pyspark"],
    "airflow": ["airflow"], "fastapi": ["fastapi"], "flask": ["flask"], "django": ["django"],
    "react": ["react"], "node.js": ["node.js", "nodejs"], "pydantic": ["pydantic"],
    "sqlalchemy": ["sqlalchemy"], "docker": ["docker", "dockerfile", "docker-compose"],
    "kubernetes": ["kubernetes", "k8s", "kubectl", "helm"], "helm": ["helm"],
    "terraform": ["terraform", ".tf"], "ansible": ["ansible"],
    "aws": ["aws", "boto3", "amazon web services"], "gcp": ["gcp", "google cloud"],
    "azure": ["azure"], "prometheus": ["prometheus", "prometheus_client", "prometheus-client"],
    "grafana": ["grafana"], "pytest": ["pytest"],
    "testing": ["pytest", "unittest", "def test_", "junit", "jest"],
    "ci/cd": ["ci/cd", "github actions", "github-actions", ".github/workflows", "gitlab ci",
              "jenkins", "circleci", "workflow"],
    "github actions": ["github actions", ".github/workflows", "github-actions", "actions/checkout"],
    "continuous integration": ["continuous integration", "ci/cd", ".github/workflows", "jenkins",
                               "circleci", "gitlab ci", "github actions"],
    "rest": ["rest", "restful", "@app.get", "@app.post", "@router.get", "fastapi", "flask"],
    "grpc": ["grpc"], "graphql": ["graphql"], "openapi": ["openapi", "swagger"],
    "microservices": ["microservice", "microservices"], "linux": ["linux"],
    "dead-letter queue": ["dead-letter", "dead letter", "dead_letter", "dlq"],
    "idempotency": ["idempotent", "idempotency", "on conflict"],
    "pagination": ["pagination", "paginate", "cursor", "keyset"],
    "exponential backoff": ["backoff", "exponential"],
    "retries": ["retry", "retries", "max_retries"],
    "snowflake": ["snowflake"], "bigquery": ["bigquery"], "elasticsearch": ["elasticsearch", "opensearch"],
    "cassandra": ["cassandra"], "dynamodb": ["dynamodb"], "celery": ["celery"], "nginx": ["nginx"],
    "numpy": ["numpy"], "pandas": ["pandas"], "pytorch": ["pytorch", "torch"], "tensorflow": ["tensorflow"],
    "spring boot": ["spring boot", "springboot"], "next.js": ["next.js", "nextjs"], "vue": ["vue", "vue.js"],
    "angular": ["angular"], "php": ["php"], "swift": ["swift"], "bash": ["bash", "shell script"],
    "datadog": ["datadog"], "splunk": ["splunk"], "opentelemetry": ["opentelemetry", "otel"],
    "pulsar": ["pulsar"], "nats": ["nats"], "etcd": ["etcd"], "vault": ["vault"],
    "metrics": ["metrics", "prometheus", "counter", "histogram"],
    "monitoring": ["monitoring", "metrics", "prometheus", "grafana", "histogram", "counter"],
}
# Single/double letter names that need a case-sensitive whole-word match.
AMBIGUOUS_CASE_SENSITIVE = {"go": "Go", "c": "C", "r": "R"}


def _canon_lookup() -> dict[str, str]:
    m: dict[str, str] = {}
    for canon, aliases in VOCAB.items():
        m.setdefault(canon, canon)
        for a in aliases:
            m.setdefault(a, canon)
    return m


@lru_cache(maxsize=1)
def canon_map() -> dict[str, str]:
    return _canon_lookup()


def canonical(term: str) -> str | None:
    t = term.strip().lower()
    m = canon_map()
    for cand in (t, t.replace("-", " "), t.replace(" ", "-"), t[:-1] if t.endswith("s") else t,
                 t[:-2] if t.endswith("es") else t):
        if cand in m:
            return m[cand]
    return None


def is_enforceable(keyword: str) -> bool:
    """Keywords the code can check literally: known vocabulary, or tech-looking tokens (CamelCase/ALLCAPS).
    Plain words like 'consumers' or 'observability' are descriptive and not enforced."""
    k = keyword.strip()
    return bool(k) and (canonical(k) is not None or bool(re.search(r"[a-z][A-Z]", k)) or
                        bool(re.fullmatch(r"[A-Z][A-Z0-9+#.]+", k)))


def aliases_for(term: str) -> list[str]:
    """All strings that count as evidence of `term` (term itself + its canonical aliases)."""
    t = term.strip().lower()
    c = canonical(t)
    out = {t, t.replace("-", " "), t.rstrip("s")}
    if c:
        out.add(c)
        out.update(VOCAB.get(c, []))
    return sorted(out)


def _word_re(s: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def in_text(term: str, text: str) -> bool:
    """True if `term` (or a vocabulary alias for it) literally appears in `text`."""
    t = term.strip()
    if not t:
        return True
    if t.lower() in AMBIGUOUS_CASE_SENSITIVE and canonical(t) in ("go", "c", "r"):
        cs = AMBIGUOUS_CASE_SENSITIVE[t.lower()]
        if re.search(r"(?<![A-Za-z0-9])" + cs + r"(?![A-Za-z0-9])", text):
            return True
        return any(_word_re(a).search(text) for a in aliases_for(t) if a != t.lower())
    return any(_word_re(a).search(text) for a in aliases_for(t))


# Terms whose *bare* appearance in a bullet is detected via the vocabulary scan. Alias-only
# words (e.g. "select", "workflow", "cursor") are excluded from detection to avoid false blocks.
_DETECT_EXCLUDE = {"select", "insert into", "create table", "workflow", "cursor", "counter",
                   "histogram", "pip", "js", "exponential", "metrics", "rest", "testing",
                   "retries", "monitoring", "continuous integration", "ci/cd", "go", "c", "r",
                   "jvm", "cargo", "def test_", "on conflict", "keyset", ".tf"}


# Generic concept terms that are safe to detect in *job descriptions* (not in bullets).
_JD_GENERIC = {"metrics", "monitoring", "testing", "retries", "continuous integration", "ci/cd",
               "exponential"}


@lru_cache(maxsize=2)
def detect_patterns(generic: bool = False) -> list[tuple[re.Pattern, str]]:
    pats = []
    for canon, aliases in VOCAB.items():
        for a in {canon, *aliases}:
            if (a in _DETECT_EXCLUDE and not (generic and a in _JD_GENERIC)) or len(a) < 2 \
                    or (a in VOCAB and a != canon):
                continue
            pats.append((_word_re(a), canon))
    return pats


def mask_terms(text: str) -> str:
    """Blank out detected vocabulary phrases (so e.g. 'GitHub Actions' isn't re-checked word by word)."""
    for pat, _ in detect_patterns():
        text = pat.sub(lambda m: " " * len(m.group(0)), text)
    return text


def detect_terms(text: str, generic: bool = False) -> list[str]:
    """Canonical vocabulary terms mentioned in `text` (order of first appearance)."""
    found: dict[str, int] = {}
    for pat, canon in detect_patterns(generic):
        m = pat.search(text)
        if m and (canon not in found or m.start() < found[canon]):
            found[canon] = m.start()
    # case-sensitive "Go" as a language, only when followed by typical context
    if re.search(r"(?<![A-Za-z0-9])Go(?![A-Za-z0-9a-z])(?=\s*(?:,|\(|for\b|services?\b|tooling|programming|language|$|\.))", text):
        found.setdefault("go", text.find("Go"))
    return [k for k, _ in sorted(found.items(), key=lambda kv: kv[1])]
