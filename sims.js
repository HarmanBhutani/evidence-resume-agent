/* System design simulations: plain, deterministic models (seeded random numbers, 1 ms ticks).
   No drawing code here, so the same logic runs in the browser and in tests (node).
   The numbers are a simplified model chosen to make behaviour visible, not to match a real system. */
(function (root) {
  "use strict";

  function rng(seed) {                       // mulberry32: small, fast, reproducible
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const expo = (r, mean) => -Math.log(1 - r()) * mean;
  function pct(values, p) {
    if (!values.length) return 0;
    const s = values.slice().sort((a, b) => a - b);
    return s[Math.min(s.length - 1, Math.floor(p * s.length))];
  }
  const keepLast = (list, n) => { if (list.length > n) list.splice(0, list.length - n); };

  /* ---------------- Load balancer ----------------
     Requests arrive at random (Poisson). The balancer picks a server; each server works on
     `concurrency` requests at once and queues the rest (up to `queueLimit`, then rejects).
     A crashed server fails everything sent to it until a health check marks it down. */
  class LoadBalancerSim {
    constructor(opts = {}) {
      this.o = Object.assign({
        algo: "round_robin", rps: 60, servers: 3, concurrency: 4, serviceMs: 50,
        slowServer: -1, slowFactor: 4, queueLimit: 30, healthEveryS: 2,
        crashServer: -1, crashAtS: Infinity, seed: 7,
      }, opts);
      this.r = rng(this.o.seed);
      this.t = 0;
      this.rr = 0;
      this.nextArrival = expo(this.r, 1000 / this.o.rps);
      this.nextHealth = this.o.healthEveryS * 1000;
      this.servers = Array.from({ length: this.o.servers }, (_, id) => ({
        id, active: [], queue: [], crashed: false, markedDown: false, served: 0, failed: 0,
      }));
      this.latencies = [];
      this.done = 0; this.failed = 0; this.rejected = 0; this.sent = 0;
      this.events = [];                      // recent dispatches, for animation
      this.log = [];                         // notable moments, in words
      this.crashDetectedAt = null;
    }

    serviceTime(s) {
      const slow = s.id === this.o.slowServer ? this.o.slowFactor : 1;
      return expo(this.r, this.o.serviceMs * slow);
    }

    pick() {
      const live = this.servers.filter(s => !s.markedDown);
      if (!live.length) return null;
      const start = this.rr++ % live.length;
      if (this.o.algo === "round_robin") return live[start];
      if (this.o.algo === "random") return live[Math.floor(this.r() * live.length)];
      let best = null;                       // least connections; ties rotate so no server is favoured
      for (let k = 0; k < live.length; k++) {
        const s = live[(start + k) % live.length];
        if (!best || s.active.length + s.queue.length < best.active.length + best.queue.length) best = s;
      }
      return best;
    }

    dispatch() {
      this.sent++;
      const s = this.pick();
      if (!s) { this.failed++; return; }
      let kind;
      if (s.crashed) { s.failed++; this.failed++; kind = "failed"; }
      else if (s.active.length < this.o.concurrency) { s.active.push({ arrived: this.t, doneAt: this.t + this.serviceTime(s) }); kind = "served"; }
      else if (s.queue.length < this.o.queueLimit) { s.queue.push({ arrived: this.t }); kind = "queued"; }
      else { this.rejected++; kind = "rejected"; }
      this.events.push({ t: this.t, server: s.id, kind });
      keepLast(this.events, 300);
    }

    tick() {
      const t = this.t;
      if (this.o.crashServer >= 0 && t >= this.o.crashAtS * 1000) {
        const s = this.servers[this.o.crashServer];
        if (s && !s.crashed) {
          const lost = s.active.length + s.queue.length;
          s.failed += lost; this.failed += lost;
          s.active = []; s.queue = []; s.crashed = true;
          this.log.push({ t, text: `Server ${s.id + 1} crashed; ${lost} in-flight request(s) lost.` });
        }
      }
      if (t >= this.nextHealth) {
        for (const s of this.servers) {
          if (s.crashed && !s.markedDown) {
            s.markedDown = true;
            this.crashDetectedAt = t;
            this.log.push({ t, text: `Health check marked server ${s.id + 1} down; traffic stops going to it.` });
          }
        }
        this.nextHealth += this.o.healthEveryS * 1000;
      }
      while (this.nextArrival <= t) {
        this.dispatch();
        this.nextArrival += expo(this.r, 1000 / this.o.rps);
      }
      for (const s of this.servers) {
        if (s.crashed) continue;
        for (let i = s.active.length - 1; i >= 0; i--) {
          if (s.active[i].doneAt <= t) {
            this.latencies.push(t - s.active[i].arrived);
            s.served++; this.done++;
            s.active.splice(i, 1);
          }
        }
        while (s.active.length < this.o.concurrency && s.queue.length) {
          const q = s.queue.shift();
          s.active.push({ arrived: q.arrived, doneAt: t + this.serviceTime(s) });
        }
      }
      this.t += 1;
    }

    advance(ms) { const end = this.t + ms; while (this.t < end) this.tick(); }

    summary() {
      const L = this.latencies;
      return {
        seconds: this.t / 1000, sent: this.sent, done: this.done, failed: this.failed, rejected: this.rejected,
        errorRate: this.sent ? (this.failed + this.rejected) / this.sent : 0,
        p50: pct(L, 0.5), p95: pct(L, 0.95), p99: pct(L, 0.99),
        avg: L.length ? L.reduce((a, b) => a + b, 0) / L.length : 0,
        perServer: this.servers.map(s => ({ served: s.served, failed: s.failed, waiting: s.queue.length, busy: s.active.length,
                                            down: s.markedDown, crashed: s.crashed })),
      };
    }

    static run(opts, seconds = 30) { const s = new LoadBalancerSim(opts); s.advance(seconds * 1000); return s.summary(); }
  }

  /* ---------------- Database deadlocks ----------------
     Each transfer locks two account rows, one after the other, does some work, then commits.
     If two transfers each hold the row the other one needs, they wait for each other forever:
     a deadlock. A detector runs every `detectEveryS`, finds cycles in the "waits for" graph and
     aborts the youngest transfer, which retries after a short back-off.
     order "as_written" locks `from` then `to`; "sorted" always locks the lower account first. */
  class DeadlockSim {
    constructor(opts = {}) {
      this.o = Object.assign({
        order: "as_written", rate: 2, accounts: 4, detectEveryS: 1, holdMs: 120, finishMs: 60,
        backoffMs: 80, seed: 3, script: null,
      }, opts);
      this.r = rng(this.o.seed);
      this.names = "ABCDEFGH".slice(0, this.o.accounts).split("");
      this.t = 0;
      this.locks = {};                        // account -> transfer id
      this.txs = [];
      this.nextId = 1;
      this.nextArrival = this.o.rate > 0 ? expo(this.r, 1000 / this.o.rate) : Infinity;
      this.nextDetect = this.o.detectEveryS * 1000;
      this.script = (this.o.script || []).slice();
      this.committed = 0; this.deadlocks = 0; this.waitMs = 0; this.totalMs = 0;
      this.log = [];
      this.lastCycle = null;                  // {t, ids} for highlighting
    }

    spawn(from, to) {
      const order = this.o.order === "sorted" ? [from, to].sort() : [from, to];
      const tx = { id: this.nextId++, from, to, order, stage: 0, waitingFor: null, readyAt: 0, retryAt: 0,
                   startedAt: this.t, attempts: 1, waited: 0 };
      this.txs.push(tx);
      return tx;
    }

    randomTransfer() {
      const n = this.names.length, a = Math.floor(this.r() * n);
      let b = Math.floor(this.r() * (n - 1));
      if (b >= a) b++;
      this.spawn(this.names[a], this.names[b]);
    }

    tryLock(tx, row) {
      const holder = this.locks[row];
      if (holder === undefined || holder === tx.id) { this.locks[row] = tx.id; tx.waitingFor = null; return true; }
      tx.waitingFor = row;
      return false;
    }

    release(tx) { for (const row of tx.order) if (this.locks[row] === tx.id) delete this.locks[row]; }

    findCycles() {
      const holderOf = row => this.locks[row];
      const byId = Object.fromEntries(this.txs.map(x => [x.id, x]));
      const cycles = [], seen = new Set();
      for (const start of this.txs) {
        if (seen.has(start.id) || !start.waitingFor) continue;
        const path = [], pos = new Map();
        let cur = start;
        while (cur && cur.waitingFor && !seen.has(cur.id)) {
          if (pos.has(cur.id)) { cycles.push(path.slice(pos.get(cur.id))); break; }
          pos.set(cur.id, path.length); path.push(cur.id);
          cur = byId[holderOf(cur.waitingFor)];
        }
        for (const id of path) seen.add(id);
      }
      return cycles;
    }

    tick() {
      const t = this.t;
      while (this.script.length && this.script[0].at * 1000 <= t) { const s = this.script.shift(); this.spawn(s.from, s.to); }
      while (this.nextArrival <= t) { this.randomTransfer(); this.nextArrival += expo(this.r, 1000 / this.o.rate); }
      for (const tx of this.txs.slice()) {
        if (tx.retryAt > t) continue;
        if (tx.stage === 0) {
          if (this.tryLock(tx, tx.order[0])) { tx.stage = 1; tx.readyAt = t + this.o.holdMs; }
        } else if (tx.stage === 1 && t >= tx.readyAt) {
          if (this.tryLock(tx, tx.order[1])) { tx.stage = 2; tx.readyAt = t + this.o.finishMs; }
        } else if (tx.stage === 2 && t >= tx.readyAt) {
          this.release(tx);
          this.committed++; this.totalMs += t - tx.startedAt; this.waitMs += tx.waited;
          this.txs.splice(this.txs.indexOf(tx), 1);
        }
        if (tx.waitingFor) tx.waited++;
      }
      if (t >= this.nextDetect) {
        for (const cycle of this.findCycles()) {
          const victimId = Math.max(...cycle);  // youngest = started last
          const v = this.txs.find(x => x.id === victimId);
          this.release(v);
          v.stage = 0; v.waitingFor = null; v.retryAt = t + this.o.backoffMs; v.attempts++;
          this.deadlocks++;
          this.lastCycle = { t, ids: cycle.slice() };
          this.log.push({ t, text: `Deadlock: ${cycle.map(id => "T" + id).join(" ⇄ ")} each waited for the other. ` +
                                   `Aborted T${victimId} (the youngest); it retries.` });
          keepLast(this.log, 50);
        }
        this.nextDetect += this.o.detectEveryS * 1000;
      }
      this.t += 1;
    }

    advance(ms) { const end = this.t + ms; while (this.t < end) this.tick(); }

    summary() {
      return {
        seconds: this.t / 1000, committed: this.committed, deadlocks: this.deadlocks,
        waitingNow: this.txs.filter(x => x.waitingFor).length, inFlight: this.txs.length,
        avgWaitMs: this.committed ? this.waitMs / this.committed : 0,
        avgTotalMs: this.committed ? this.totalMs / this.committed : 0,
      };
    }

    static run(opts, seconds = 30) { const s = new DeadlockSim(opts); s.advance(seconds * 1000); return s.summary(); }
  }

  const api = { rng, pct, LoadBalancerSim, DeadlockSim };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Sims = api;
})(typeof window !== "undefined" ? window : globalThis);
