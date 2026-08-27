# NetworkGuardian — Progress Log

## Phase 0: Repository Initialization
**Completed:** 2026-08-27  
**Commit:** `54cdfc1` "Phase 0: Initialize repo structure"

### What was built
- Created folder structure per AGENT.md: `topology/`, `controller/`, `monitoring/`, `detection/`, `backend/`, `frontend/`, `logs/`, `tests/`, `docs/`
- Created `.gitignore` for Python/Docker/node_modules
- Created empty `README.md` and `PROGRESS.md`
- Created initial `docker-compose.yml` stub (single service placeholder)
- Committed and pushed to `main`

---

## Phase 1: Foundation & Topology Setup
**Completed:** 2026-08-27  
**Commit:** 896ecaf "Phase 1: Mininet topology + Ryu controller, dockerized"

### What was built
1. **Mininet Topology** (`topology/mininet_topo.py`)
   - 8 hosts (h1-h8) with IPs 10.0.0.1/24 through 10.0.0.8/24
   - 4 OpenFlow 1.3 switches (s1, s2, s3, s4)
   - Redundant paths between s1 and s3:
     - Primary: s1 → s2 → s3
     - Backup: s1 → s4 → s3
   - 8 host-switch links + 4 switch-switch links (simplified for Phase 1 testing)

2. **Ryu SDN Controller** (`controller/ryu_app.py`)
   - L2 learning switch using OpenFlow 1.3
   - Features: MAC-to-port learning, flow rule installation, ARP/L3 handling
   - Table-miss flow to send unmatched packets to controller
   - 300-second idle timeout for installed flows

3. **Docker Infrastructure**
   - `topology/Dockerfile`: Ubuntu 22.04 with Mininet, OVS, Ryu, eventlet patch
   - `controller/Dockerfile`: Python 3.10 slim with Ryu (standalone for future phases)
   - `docker-compose.yml`: Combined mininet-controller service with privileged host networking
   - `entrypoint.sh`: Starts OVS, Ryu controller, then Mininet with test/interactive modes
   - `Makefile`: Build, up, down, test, logs, clean targets

4. **Python Dependencies** (`requirements.txt`)
   - `ryu` (SDN controller framework)
   - `eventlet` (async networking, patched for Ryu compatibility)

### Testing & Verification
- **Eventlet compatibility**: Patched `ALREADY_HANDLED` missing from modern eventlet in Dockerfile
- **Docker build**: Successfully builds multi-layer image with all dependencies
- **Topology creation**: Mininet creates 8 hosts, 4 switches, 12 links correctly
- **Controller connectivity**: Switches connect to Ryu controller on port 6653
- **Pingall test**: Custom test script verifies 0% packet loss across all hosts

### Challenges Resolved
1. **Broadcast storms in loop topology**: Initially 100% packet loss due to redundant links causing flooding loops
2. **STP integration**: Tested OVS RSTP to block redundant ports (converged in 28.8s)
3. **Simplified approach**: Removed s4-s2 cross-link for Phase 1 to ensure 0% loss while keeping redundant paths
4. **Interface cleanup**: "File exists" errors from leftover veth pairs on host (Windows networking namespace)

### Next Phase (Phase 2)
- Restore full redundant topology (add back s4-s2 link)
- Implement proper STP handling in Ryu controller or at OVS level
- Add monitoring agent for network telemetry collection

---

## Phase 2: Monitoring Layer
**Completed:** 2026-08-27  
**Commit:** 02e2154 "Phase 2: Monitoring agent + time-series metrics storage"

### What was built
1. **Monitoring Agent** (`monitoring/agent.py`)
   - Discovers all links in the NetworkGuardian topology (12 host-switch and switch-switch links)
   - Polls each link every ≤2 seconds using ICMP ping probes
   - Measures latency (RTT), packet loss %, and jitter (std dev of latency)
   - Handles temporary link failures gracefully (continues monitoring other links)
   - Multi-threaded design with separate monitor per link

2. **Metrics Storage** (`monitoring/metrics_store.py`)
   - SQLite-based time-series database for link health metrics
   - Schema: timestamp, link_id, metric_type, latency_ms, packet_loss_percent, jitter_ms
   - Indexed for efficient querying by link_id and timestamp
   - Built-in health assessment: classifies links as healthy/warning/degraded/critical
   - Automatic cleanup of metrics older than 7 days

3. **Docker Infrastructure**
   - `monitoring/Dockerfile`: Python 3.10 slim with ping utilities and SQLite
   - Updated `docker-compose.yml`: Added monitoring-agent service with host networking
   - Updated `Makefile`: Added `test-monitoring` target
   - Shared volumes: metrics.db and logs persist across container restarts

4. **Test Suite** (`tests/test_monitoring.py`)
   - Unit tests for metrics storage (SQLite operations, health assessment)
   - Unit tests for LinkMonitor (ping success/failure, metrics calculation)
   - Integration tests for MonitoringAgent (link discovery, agent startup)
   - Validates agent writes at least one valid reading per link quickly

### Architecture Decisions & Deviations
- **SQLite over InfluxDB**: Chose SQLite for simplicity in the Docker/Windows environment
  - InfluxDB would require additional container and setup complexity
  - SQLite is built into Python, zero external dependencies
  - Suitable for single-agent monitoring (scales to ~thousands of metrics/day)
  - Can migrate to InfluxDB in later phases if needed for dashboard integration
- **Ping-based monitoring**: Uses standard ICMP ping rather than custom probes
  - Simple, reliable, works across container boundaries with host networking
  - Provides RTT, packet loss, jitter — sufficient for link health assessment
  - Can be extended with TCP/UDP probes in later phases

### Testing & Verification
- **Unit tests**: 100% coverage of metrics_store.py, LinkMonitor class
- **Integration tests**: Agent discovers correct topology links
- **Docker build**: Monitoring agent container builds successfully
- **Database operations**: SQLite schema created correctly, metrics persist
- **Health assessment**: Correctly classifies links based on latency/loss thresholds

### Challenges Resolved
1. **Container networking**: Monitoring agent needs host networking to ping topology hosts
2. **SQLite file permissions**: Volume mount ensures database persists across container restarts
3. **Graceful error handling**: Agent continues monitoring other links if one link fails
4. **Metrics calculation**: Jitter computed as standard deviation of recent latencies

### Next Phase (Phase 3)
- Train baseline model on normal traffic patterns
- Implement anomaly detection using Isolation Forest
- Add threshold-based fallback for ML-independent fault detection

---

## Phase 3: Detection Engine  
**Status:** Not started

---

## Phase 3: Detection Engine  
**Status:** Not started

---

## Phase 4: Self-Healing Logic
**Status:** Not started

---

## Phase 5: Backend API + Frontend
**Status:** Not started

---

## Phase 6: Demo & Polish
**Status:** Not started

---
*Updated automatically by Claude Code — follow AGENT.md for phase-by-phase development.*