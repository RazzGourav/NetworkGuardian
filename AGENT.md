# NetworkGuardian — Agent Development Guide
### For use with Claude Code, Antigravity, or any autonomous coding agent

This file is the **operating brain** for the coding agent building this project.
Place it at the repo root as `AGENT.md` (or `CLAUDE.md` if using Claude Code) so
the agent reads it automatically at the start of every session.

---

## 0. Agent Operating Rules (Read First, Every Session)

1. **Read this file fully before writing any code.** Re-read the "Current Phase"
   section at the top before resuming work after any break.
2. **Work phase by phase, in order.** Do not start Phase N+1 until Phase N's
   acceptance criteria are all met and committed.
3. **Commit and push after every completed phase — directly to `main`.**
   No feature branches, no PRs. This is a solo portfolio project; the priority
   is a clean, incremental commit history on `main` that shows real progress.
   ```bash
   git add .
   git commit -m "Phase N: <short description>"
   git push origin main
   ```
4. **Never push broken code.** Before every push: run the phase's test/verify
   command (listed per phase below) and confirm it passes. If it fails, fix it
   first — do not push and fix later.
5. **Update `PROGRESS.md`** after each phase with: what was built, what was
   tested, any deviations from the PRD, and any known issues.
6. **Keep Docker working at all times.** After any dependency change, rebuild
   the Docker image locally and confirm `docker compose up` still starts the
   full stack before pushing.
7. **If blocked** (missing credentials, ambiguous requirement, environment
   issue that can't be resolved autonomously), stop and clearly report the
   blocker instead of guessing silently or skipping the step.
8. **Do not over-engineer.** Build exactly what the current phase requires.
   Future-phase features go in code only when their phase arrives.
9. **Every phase must leave the repo in a runnable state** — `docker compose up`
   should always successfully start whatever has been built so far, even if
   later phases aren't implemented yet.

---

## 1. Repository Setup (Run Once, Before Phase 1)

```bash
mkdir NetworkGuardian && cd NetworkGuardian
git init -b main
git remote add origin <YOUR_GITHUB_REPO_URL>
```

Create the base structure immediately:

```
NetworkGuardian/
├── AGENT.md                  # this file
├── PROGRESS.md               # running log, updated every phase
├── README.md
├── .gitignore
├── docker-compose.yml
├── requirements.txt
├── topology/
├── controller/
├── monitoring/
├── detection/
├── backend/
├── frontend/
├── logs/
├── tests/
└── docs/
```

`.gitignore` should include: `__pycache__/`, `*.pyc`, `.env`, `venv/`,
`node_modules/`, `logs/*.log`, `*.db`, `.DS_Store`.

First commit:
```bash
git add .
git commit -m "Phase 0: Initialize repo structure"
git push -u origin main
```

---

## 2. Docker Strategy (Applies to Every Phase)

Use Docker from Phase 1 onward so the whole system is reproducible with one
command. Structure:

- `docker-compose.yml` at root, orchestrating separate services as they're
  added: `mininet-controller`, `monitoring-agent`, `backend`, `influxdb` (or
  sqlite volume), `frontend`.
- Each service gets its own `Dockerfile` inside its folder
  (e.g., `backend/Dockerfile`).
- Mininet requires privileged mode + host networking — isolate it in its own
  container with `privileged: true`.
- Add a `Makefile` (or `justfile`) with shortcuts:
  ```
  make build   # docker compose build
  make up      # docker compose up
  make down    # docker compose down
  make test    # run test suite inside containers
  ```
- **Every phase's Docker setup must be tested with a clean `docker compose up`
  before pushing** — not just "it ran once in a warm environment."

---

## 3. Progress Log Template (`PROGRESS.md`)

Append this block after every phase:

```markdown
## Phase N — <Name> — <date>
**Status:** Complete
**What was built:** ...
**Tested:** ...
**Deviations from PRD:** ...
**Known issues / follow-ups:** ...
**Commit:** <commit hash>
```

---

## 4. Phase-Wise Development Instructions
> Read NetworkGuardian_PRD.md and follow and check if something left
> Current Phase: **Phase 1** *(agent: update this line as you progress)*

---

### **Phase 1 — Foundation & Topology Setup**

**Goal:** A working simulated network with an SDN controller talking to it, fully dockerized.

**Tasks:**
1. Write `topology/mininet_topo.py` defining a 6–8 node topology with at least
   one redundant path between two hosts (needed later for rerouting demo).
2. Set up Ryu controller skeleton in `controller/ryu_app.py` that connects to
   the topology and can install basic flow rules.
3. Write `topology/Dockerfile` and `controller/Dockerfile`.
4. Add both services to `docker-compose.yml`.
5. Verify: from inside the Mininet container, `pingall` succeeds across the
   whole topology via the controller.

**Acceptance criteria:**
- `docker compose up` starts both containers without error.
- `pingall` in Mininet CLI shows 0% packet loss.
- Controller logs show it registering switches and installing flows.

**Verify command:**
```bash
docker compose run mininet-controller mn --custom topology/mininet_topo.py --test pingall
```

**Commit & push:**
```bash
git add .
git commit -m "Phase 1: Mininet topology + Ryu controller, dockerized"
git push origin main
```

---

### **Phase 2 — Monitoring Layer**

**Goal:** Continuous collection of link health metrics into a time-series store.

**Tasks:**
1. `monitoring/agent.py` — polls each link every ≤2 seconds for latency,
   packet loss, jitter (use `ping`/Scapy probes between hosts).
2. `monitoring/metrics_store.py` — writes readings to InfluxDB (or SQLite if
   simplifying). Include timestamp, link ID, metric values.
3. Add `influxdb` (or sqlite volume) and `monitoring-agent` service to
   `docker-compose.yml`.
4. Write `tests/test_monitoring.py` — asserts the agent writes at least one
   valid reading per link within 5 seconds of startup.

**Acceptance criteria:**
- Metrics visibly accumulate in the DB while the stack runs.
- Test suite passes.
- Agent recovers gracefully (doesn't crash) if a link is briefly unreachable.

**Verify command:**
```bash
docker compose run backend pytest tests/test_monitoring.py
```

**Commit & push:**
```bash
git add .
git commit -m "Phase 2: Monitoring agent + time-series metrics storage"
git push origin main
```

---

### **Phase 3 — Fault Detection Engine**

**Goal:** Detect faults/degradation from the metrics stream in near real time.

**Tasks:**
1. `detection/train_baseline.py` — generates/collects "normal" traffic data
   and trains an Isolation Forest (scikit-learn) baseline model. Save model
   artifact to `detection/model.pkl`.
2. `detection/anomaly_model.py` — loads the model, scores incoming metrics in
   real time, exposes a simple function `is_anomalous(reading) -> (bool, score)`.
3. Add a threshold-based fallback (e.g., packet loss >20% = fault) so the
   system doesn't rely solely on ML — more robust for demo conditions.
4. `tests/test_detection.py` — feed synthetic "fault" and "normal" readings,
   assert correct classification.

**Acceptance criteria:**
- Detection latency (reading ingested → flagged) is under 2 seconds.
- False positive rate on stable synthetic data is under 10% (log this in
  `PROGRESS.md`).
- Both ML and threshold paths are covered by tests.

**Verify command:**
```bash
docker compose run backend pytest tests/test_detection.py
```

**Commit & push:**
```bash
git add .
git commit -m "Phase 3: Fault detection engine (ML + threshold fallback)"
git push origin main
```

---

### **Phase 4 — Auto-Rerouting Engine**

**Goal:** On detected fault, automatically recompute and push a new path.

**Tasks:**
1. `controller/reroute_engine.py` — build the topology as a graph (networkx),
   implement Dijkstra shortest-path recomputation excluding the failed link.
2. Wire detection engine (Phase 3) to reroute engine: on fault, reroute engine
   computes new path and controller pushes updated OpenFlow rules.
3. `tests/test_fault_injection.py` — programmatically bring a link down in
   Mininet, assert: (a) fault is detected, (b) new flow rules are installed,
   (c) connectivity between affected hosts is restored, and (d) measure and
   log recovery time.

**Acceptance criteria:**
- End-to-end recovery time under 5 seconds in test runs.
- Connectivity is fully restored after simulated link failure.
- Recovery time is logged to `PROGRESS.md` with at least 3 test runs averaged.

**Verify command:**
```bash
docker compose run mininet-controller pytest tests/test_fault_injection.py
```

**Commit & push:**
```bash
git add .
git commit -m "Phase 4: Auto-rerouting engine (detection -> controller -> new path)"
git push origin main
```

---

### **Phase 5 — Dashboard & Visualization**

**Goal:** Live web UI showing topology health, metrics, and event log.

**Tasks:**
1. `backend/app.py` — Flask + Flask-SocketIO app exposing:
   - `GET /api/topology` — current topology + link status
   - `GET /api/metrics` — recent metrics for charts
   - WebSocket channel pushing live events (fault detected / rerouted)
2. `frontend/` — dashboard rendering topology graph (D3.js or Chart.js),
   color-coded by health (green/amber/red), plus a live event log panel.
3. Add `backend` and `frontend` services to `docker-compose.yml`, with
   frontend served either statically by Flask or via a lightweight Node
   server.
4. Confirm dashboard updates within ~1 second of a real event via WebSocket
   (no manual refresh needed).

**Acceptance criteria:**
- `docker compose up` serves the dashboard at a fixed local port (e.g. `:8080`).
- Killing a link in Mininet visibly updates the dashboard in real time.
- Event log shows timestamped detect/reroute events.

**Verify command:**
Manual verification — document steps taken and screenshot/GIF in
`docs/dashboard_demo.gif`, referenced in `PROGRESS.md`.

**Commit & push:**
```bash
git add .
git commit -m "Phase 5: Live dashboard (topology view, metrics, event log)"
git push origin main
```

---

### **Phase 6 — Testing, Demo & Documentation**

**Goal:** Polish, quantify results, and make the project presentable.

**Tasks:**
1. Run the full failure-recovery scenario at least 5 times; record MTTD
   (mean time to detect), MTTR (mean time to recover), and false-positive
   rate. Put these in a results table in `README.md`.
2. Record a demo video/GIF of the full flow (stable → fault → detect →
   reroute → recovered) and save to `docs/`.
3. Write the final `README.md`: project overview, architecture diagram,
   setup instructions (`docker compose up` as the single entry point),
   results table, and a link to the PRD.
4. Clean up dead code, add docstrings/comments to core modules.
5. Final Docker validation: clone the repo fresh into a clean directory and
   confirm `docker compose up` works with zero manual steps beyond that.

**Acceptance criteria:**
- README is self-contained — a stranger could clone and run the project
  from it alone.
- Demo asset exists in `docs/`.
- Results table with real measured numbers is present.

**Commit & push:**
```bash
git add .
git commit -m "Phase 6: Final testing, results, documentation, demo assets"
git push origin main
```

---

## 5. Definition of Done (Whole Project)

- All 6 phases committed individually to `main`, in order, each buildable
  and demoable at the point it was committed.
- `docker compose up` from a clean clone brings up the entire stack with no
  manual configuration.
- README contains real, measured MTTD/MTTR numbers — not placeholders.
- A recorded demo exists showing the fault → detect → reroute flow end to end.

---

## 6. Notes for the Agent on Judgment Calls

- If InfluxDB setup proves too heavy for the environment, fall back to
  SQLite and note this as a deviation in `PROGRESS.md` — do not silently
  swap it without logging why.
- If ONOS/Ryu installation issues block progress in the sandboxed
  environment, document the exact error before switching tools.
- Prioritize a working, honestly-measured demo over a feature-complete but
  untested system. A smaller working Phase 4 beats a broken Phase 6.
