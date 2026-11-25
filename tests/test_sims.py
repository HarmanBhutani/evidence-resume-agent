"""System design simulations (resume_agent/static/sims.js), run in node.

These check that each model shows the behaviour the page teaches, with a fixed seed."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SIMS = Path(__file__).resolve().parents[1] / "resume_agent" / "static" / "sims.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def run(js: str):
    code = f"const S = require({json.dumps(str(SIMS))});\nconsole.log(JSON.stringify((() => {{ {js} }})()));"
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def lb(**opts):
    return run(f"return S.LoadBalancerSim.run({json.dumps(opts)}, 30);")


def dl(seconds=60, **opts):
    return run(f"return S.DeadlockSim.run({json.dumps(opts)}, {seconds});")


def test_same_seed_same_result():
    assert lb(algo="random") == lb(algo="random")
    assert lb(algo="random", seed=1) != lb(algo="random", seed=2)


def test_identical_servers_share_work_evenly():
    s = lb(algo="round_robin")
    served = [x["served"] for x in s["perServer"]]
    assert s["failed"] == s["rejected"] == 0 and max(served) - min(served) <= 5


def test_least_connections_beats_round_robin_on_a_slow_server():
    rr, lc = lb(algo="round_robin", slowServer=1), lb(algo="least_connections", slowServer=1)
    assert lc["p95"] * 3 < rr["p95"]
    assert lc["perServer"][1]["served"] < rr["perServer"][1]["served"]


def test_crash_loses_requests_until_health_check():
    fast = lb(crashServer=1, crashAtS=5.5, healthEveryS=1)
    slow = lb(crashServer=1, crashAtS=5.5, healthEveryS=10)
    assert 0 < fast["failed"] < slow["failed"]
    assert fast["perServer"][1]["down"] and fast["perServer"][1]["crashed"]


def test_least_connections_black_hole_after_crash():
    # a dead server has no open connections, so least connections keeps choosing it
    rr = lb(algo="round_robin", crashServer=1, crashAtS=5.5, healthEveryS=5)
    lc = lb(algo="least_connections", crashServer=1, crashAtS=5.5, healthEveryS=5)
    assert lc["failed"] > rr["failed"]


def test_overload_rejects_requests():
    assert lb(rps=400)["rejected"] > 0


def test_classic_two_transfers_deadlock_once_then_finish():
    script = [{"at": 0, "from": "A", "to": "B"}, {"at": 0, "from": "B", "to": "A"}]
    s = dl(3, accounts=2, rate=0, script=script)
    assert s["deadlocks"] == 1 and s["committed"] == 2 and s["inFlight"] == 0
    assert dl(3, accounts=2, rate=0, script=script, order="sorted")["deadlocks"] == 0


def test_lock_ordering_prevents_deadlocks():
    for seed in (1, 2, 3, 4):
        assert dl(order="as_written", seed=seed)["deadlocks"] > 0
        assert dl(order="sorted", seed=seed)["deadlocks"] == 0


def test_slow_detector_freezes_more_work():
    quick, slow = dl(detectEveryS=0.5), dl(detectEveryS=5)
    assert slow["committed"] < quick["committed"] and slow["waitingNow"] > quick["waitingNow"]


def test_victim_is_youngest_and_locks_released():
    out = run("""const s = new S.DeadlockSim({accounts: 2, rate: 0, script: [{at: 0, from: "A", to: "B"}, {at: 0, from: "B", to: "A"}]});
                 s.advance(1001); return {log: s.log.map(l => l.text), locks: s.locks, cycle: s.lastCycle};""")
    assert "Aborted T2" in out["log"][0] and list(out["locks"].values()) == [1]
