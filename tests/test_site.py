"""Static online demo (scripts/build_site.py + static/static-demo.js)."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    import build_site
    return build_site.build(tmp_path_factory.mktemp("site") / "site")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def test_all_results_built_and_labeled(site):
    demo = json.loads((site / "data/demo.json").read_text())
    assert demo["config"]["static"] and len(demo["jds"]) == 3
    for jd in demo["jds"]:
        for prov, mode in [("replay", "REPLAYED"), ("mock", "MOCK"), ("mock_attack", "MOCK")]:
            for auth in ("checked", "unchecked"):
                r = json.loads((site / f"data/results/{prov}__{jd['id']}__{auth}.json").read_text())
                assert r["meta"]["mode"] == mode and r["authorship"]["checked"] == (auth == "checked")
    attack = json.loads((site / "data/results/mock_attack__adversarial_infra_rust__checked.json").read_text())
    assert attack["meta"]["model"] == "mock-hallucination-attack" and any(b["status"] == "blocked" for b in attack["bullets"])


def test_every_citation_resolves_from_published_data(site):
    """Independent of the verifier: the published repo copy must contain every quoted snippet."""
    repo = json.loads((site / "data/repo.json").read_text())
    n = 0
    for f in (site / "data/results").glob("*.json"):
        r = json.loads(f.read_text())
        evs = [e for i in r["ledger"] for e in i["evidence"]] + [e for q in r["interview"] for e in q["evidence"]]
        evs += [e for b in r["bullets"] if b["status"] == "ok" and b["origin"] == "verified" for e in b["evidence"]]
        for e in evs:
            if e["kind"] == "file":
                text = "\n".join(repo["files"][e["path"]][e["start_line"] - 1:e["end_line"]])
            else:
                full = [k for k in repo["commits"] if k.startswith(e["resolved_commit"] or e["commit"])]
                assert len(full) == 1, e
                text = repo["commits"][full[0]]
                text += "\n" + "\n".join(l[1:] for l in text.splitlines() if l[:1] in "+- ")
            assert norm(e["quote"]) in norm(text), (f.name, e)
            n += 1
    assert n > 100


def test_pages_use_relative_links_and_no_local_paths(site):
    index, learn = (site / "index.html").read_text(), (site / "learn.html").read_text()
    assert '<script src="static-demo.js"></script>' in index and '"/learn' not in index
    assert 'src="sims.js"' in learn and 'href="/"' not in learn
    for f in site.rglob("*"):
        if f.is_file():
            assert str(Path.home()) not in f.read_text(errors="replace"), f


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_browser_feedback_matches_python_mock(site, repo_path, jds):
    from resume_agent.ingest import Repo
    from resume_agent.llm import get_provider
    from resume_agent.pipeline import run_pipeline
    from resume_agent.practice import give_feedback
    r = json.loads((site / "data/results/replay__backend_streaming_engineer__checked.json").read_text())
    answer = "I commit offsets after processing because a crash would otherwise lose the message; the cost is duplicates."
    from resume_agent.models import Question
    py = give_feedback(Repo(repo_path), Question.model_validate(r["interview"][0]), answer, get_provider("mock"))
    js_src = (site / "static-demo.js").read_text()
    harness = f"""
      const fs = require("fs"), path = require("path"), site = {json.dumps(str(site))};
      global.location = {{ href: "http://demo.test/" }};
      global.fetch = async p => ({{ ok: true, json: async () => JSON.parse(fs.readFileSync(path.join(site, p), "utf8")) }});
      const el = () => ({{ prepend(){{}}, closest(){{ return el(); }}, querySelector(){{ return el(); }}, style: {{}} }});
      global.document = {{ createElement: el, querySelector: el, getElementById: el }};
      global.window = global;
      {js_src}
      (async () => {{
        const run = await STATIC_API("/api/run", {{ body: JSON.stringify({{ jd_text: {json.dumps(jds["backend_streaming_engineer"])},
                                                   provider: "replay", authors: ["demo@example.invalid"] }}) }});
        await STATIC_API("/api/jobs/" + run.job_id);
        const fb = await STATIC_API("/api/feedback", {{ body: JSON.stringify({{ job_id: run.job_id, question_index: 0,
                                                       answer: {json.dumps(answer)}, provider: "mock" }}) }});
        let bad = null; try {{ await STATIC_API("/api/run", {{ body: JSON.stringify({{ jd_text: "my own job" }}) }}); }} catch (e) {{ bad = e.message; }}
        console.log(JSON.stringify({{ fb, bad }}));
      }})().catch(e => {{ console.error(e); process.exit(1); }});
    """
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got["fb"]["scores"] == py.scores
    assert [m["quote"] for m in got["fb"]["missed"]] == [m.quote for m in py.missed]
    assert "only has the three sample jobs" in got["bad"]
