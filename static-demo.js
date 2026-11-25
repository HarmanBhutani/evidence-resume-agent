/* Online demo mode (static hosting, e.g. GitHub Pages).
   Replaces the server API with precomputed results for the sample repo and the three sample jobs.
   Nothing here calls a model: results were produced by `make site` from recorded live responses
   (labeled REPLAYED) and the offline mock provider. Answer feedback uses the same simple rules as
   the mock provider, ported to JavaScript. */
(function () {
  "use strict";
  const cache = {};
  const load = path => cache[path] || (cache[path] = fetch(path).then(r => {
    if (!r.ok) throw new Error(`Could not load ${path} (${r.status})`);
    return r.json();
  }));
  const norm = s => String(s || "").replace(/\s+/g, " ").trim();
  const jobs = {};

  function citationText(repo, e) {             // same text the verifier uses (verifier.py)
    if (e.kind === "file") {
      const lines = repo.files[e.path];
      if (!lines) throw new Error(`file not in demo repo: ${e.path}`);
      return `${e.path}\n${lines.slice(e.start_line - 1, e.end_line).join("\n")}`;
    }
    const full = e.resolved_commit || e.commit, text = repo.commits[full] || "";
    return `${text.split("\n")[2] || ""}\n${e.quote}`;
  }
  const label = e => e.kind === "file" ? `${e.path}:${e.start_line}-${e.end_line}` : `commit ${(e.resolved_commit || e.commit || "").slice(0, 8)}`;

  function mockFeedback(code, answerRaw) {     // port of MockProvider._feedback + practice.verify_feedback
    const answer = answerRaw.toLowerCase();
    const codeLines = code.split("\n").map(l => l.trim()).filter(l => l && !l.startsWith("# "));
    const names = [];
    for (const l of codeLines) for (const w of l.match(/\b[A-Za-z_][A-Za-z0-9_]{3,}\b/g) || [])
      if ((w.includes("_") || /[A-Z]/.test(w.slice(1))) && !names.includes(w)) names.push(w);
    const hit = names.filter(w => answer.includes(w.toLowerCase()) || answer.includes(w.toLowerCase().replace(/_/g, " ")));
    const miss = names.filter(w => !hit.includes(w)).slice(0, 3);
    const words = answer.split(/\s+/).filter(Boolean).length;
    const why = ["because", "trade", "instead", "cost", "so that"].some(k => answer.includes(k));
    const fail = ["fail", "retry", "error", "crash", "timeout", "duplicate", "lost"].some(k => answer.includes(k));
    return {
      scores: { correctness: Math.min(5, 1 + hit.length), tradeoffs: why ? 4 : 2, failure_modes: fail ? 4 : 2, clarity: words >= 40 && words <= 250 ? 4 : 2 },
      strengths: hit.length ? [`Mentions ${hit.slice(0, 3).join(", ")} from the code.`] : [],
      improve: (why ? [] : ["Say why you chose this design and what it costs."]).concat(fail ? [] : ["Describe what happens when something fails."]),
      missed: miss.map(w => ({ point: `The code uses ${w}; explain its role.`, quote: codeLines.find(l => l.includes(w)) }))
                  .filter(m => norm(code).includes(norm(m.quote))),
      dropped: 0,
      follow_up: miss.length ? `What would break if ${miss[0]} behaved differently?` : "How would you test this under failure?",
      provider: "mock", model: "mock-deterministic (in your browser)", mode: "MOCK", cached: false,
    };
  }

  function fail(status, message) { const e = new Error(message); e.status = status; throw e; }

  window.STATIC_API = async function (url, opts = {}) {
    const u = new URL(url, location.href), path = u.pathname.replace(/^.*\/api\//, "/api/"), q = u.searchParams;
    const body = opts.body ? JSON.parse(opts.body) : {};
    const demo = await load("data/demo.json");
    if (path === "/api/config") return demo.config;
    if (path === "/api/demo") return { repo_path: demo.repo_path, demo_author: demo.demo_author, jds: demo.jds };
    if (path === "/api/authors") return { authors: demo.authors };
    if (path === "/api/run") {
      const jd = demo.jds.find(j => norm(j.text) === norm(body.jd_text));
      if (!jd) fail(400, "The online demo only has the three sample jobs. Choose one from the list, or run the app locally to use your own job description and repo.");
      const prov = body.provider || "replay";
      if (!demo.providers.includes(prov)) fail(400, `The online demo has no '${prov}' results.`);
      const auth = (body.authors || []).includes(demo.demo_author) ? "checked" : "unchecked";
      const id = `${prov}__${jd.id}__${auth}`;
      jobs[id] = load(`data/results/${id}.json`);
      return { job_id: id };
    }
    if (path.startsWith("/api/jobs/")) {
      const id = decodeURIComponent(path.slice("/api/jobs/".length));
      if (!jobs[id]) fail(404, "unknown job");
      const result = await jobs[id];
      const steps = Object.fromEntries(demo.config.steps.map(s => [s, { state: "done", detail: "precomputed" }]));
      return { status: "done", steps, result };
    }
    const repo = await load("data/repo.json");
    if (path === "/api/source") {
      const lines = repo.files[q.get("path")];
      if (!lines) fail(404, "file not in repo");
      const start = +q.get("start"), end = +q.get("end"), a = Math.max(1, start - 6), b = Math.min(lines.length, end + 6);
      return { path: q.get("path"), start, end, lines: Array.from({ length: b - a + 1 }, (_, k) => ({ n: a + k, text: lines[a + k - 1], hit: a + k >= start && a + k <= end })) };
    }
    if (path === "/api/commit") {
      const h = q.get("hash"), full = Object.keys(repo.commits).find(k => k.startsWith(h));
      if (!full) fail(404, "commit not found");
      return { hash: full, text: repo.commits[full] };
    }
    if (path === "/api/feedback") {
      if (body.provider && body.provider !== "mock") fail(400, "The online demo can only give feedback with the offline rules (mock). Run the app locally for feedback from Claude.");
      const answer = (body.answer || "").trim();
      if (!answer) fail(400, "Write an answer first.");
      if (answer.length > 4000) fail(400, "Answer is too long (max 4000 characters).");
      const result = await jobs[body.job_id], qn = result && result.interview[body.question_index];
      if (!qn) fail(404, "unknown question");
      const code = qn.evidence.map(e => `# ${label(e)}\n${citationText(repo, e)}`).join("\n\n");
      return mockFeedback(code, answer);
    }
    fail(404, `not available in the online demo: ${path}`);
  };

  /* ---- adjust the page for demo mode (runs before the main script) ---- */
  const $ = id => document.getElementById(id);
  const banner = document.createElement("div");
  banner.className = "card";
  banner.style.cssText = "margin-bottom:14px;border-left:4px solid #e0a800";
  banner.innerHTML = `<b>Online demo.</b> Nothing here runs a model or reads your files. You can explore precomputed results for a
    synthetic sample repo and three sample jobs: the <b>recorded live Claude run</b> (labeled REPLAYED), the <b>offline rules</b> (MOCK),
    and a <b>fake model that tries to cheat</b> (MOCK, hallucination attack) so you can see the verifier block it.
    Interview feedback uses simple offline rules. To analyse your own repo with Claude,
    <a href="https://github.com/HarmanBhutani/evidence-resume-agent#quick-start" target="_blank" rel="noopener">run it locally</a>.`;
  document.querySelector("main").prepend(banner);
  $("repo").readOnly = true; $("loadAuthors").hidden = true;
  $("provider").innerHTML = `<option value="replay">Recorded live Claude run (REPLAYED)</option>
    <option value="mock">Offline rules (MOCK)</option><option value="mock_attack">Fake model that tries to cheat (MOCK, attack)</option>`;
  $("provider").closest("details").open = true;          // the three result types are the main thing to try
  $("fbProvider").innerHTML = `<option value="mock">offline rules (in your browser)</option>`;
  for (const id of ["cache", "record"]) $(id).closest("label").hidden = true;
  $("useritem").closest(".row").hidden = true; $("addUser").hidden = true;
  $("useritem").closest("details").querySelector('label[for="useritem"]').textContent =
    "Adding your own non-code items (shown as \"user-provided, unverified\") works in the local app.";
  $("jd").readOnly = true; $("jd").placeholder = "Choose a sample job above. Pasting your own job works in the local app.";
})();
