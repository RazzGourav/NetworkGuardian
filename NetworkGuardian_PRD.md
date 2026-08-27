# Product Requirements Document (PRD)
## NetworkGuardian — Intelligent Network Monitoring, Fault Detection & Auto-Rerouting System

**Version:** 1.0
**Author:** Gourav Ojha
**Purpose:** Academic/portfolio project for Nokia Internship Application
**Domain:** Network Automation, SDN, Fault Tolerance, AI-driven Monitoring

---

## 1. Executive Summary

NetworkGuardian is a self-healing network management system that continuously monitors network health, detects faults or performance degradation using anomaly detection, and automatically reroutes traffic through a Software-Defined Networking (SDN) controller — minimizing downtime without human intervention.

It mirrors real-world telecom priorities: high availability, low latency recovery, and intelligent automation — directly aligned with Nokia's positioning as "a global leader in connectivity for the AI era."

---

## 2. Problem Statement

Traditional networks rely on static routing and manual fault response, causing:
- Delayed fault detection (minutes, sometimes longer)
- Manual, error-prone rerouting
- Downtime that cascades across dependent services

**Goal:** Build a system that detects a fault within seconds and reroutes traffic automatically, with zero manual intervention — demonstrating the shift toward autonomous, AI-assisted networks.

---

## 3. Objectives

| Objective | Success Metric |
|---|---|
| Real-time network monitoring | Poll interval ≤ 2 seconds |
| Fault detection accuracy | >90% detection rate on simulated failures |
| Auto-rerouting speed | Recovery time < 5 seconds |
| Visualization | Live dashboard reflecting topology + health |
| False positive control | <10% false alarms on stable links |

---

## 4. Phase-Wise Development Plan

### **Phase 1: Foundation & Topology Setup (Week 1–2)**
- Set up Mininet virtual network topology (6–8 nodes, redundant links)
- Install and configure SDN controller (Ryu or ONOS)
- Establish baseline connectivity and manual flow rules
- Deliverable: Working simulated network with controller communication

### **Phase 2: Monitoring Layer (Week 3–4)**
- Build a polling agent using Scapy/SNMP to collect: latency, packet loss, jitter, bandwidth utilization
- Store metrics in a time-series database (InfluxDB or SQLite)
- Deliverable: Continuous data collection pipeline with logs

### **Phase 3: Fault Detection Engine (Week 5–6)**
- Define threshold-based rules (baseline) for link failure/degradation
- Layer in a lightweight ML anomaly detector (Isolation Forest / Z-score baselining) trained on "normal" traffic patterns
- Deliverable: Module that flags anomalies in real time with confidence score

### **Phase 4: Auto-Rerouting Engine (Week 7–8)**
- Integrate detection engine with SDN controller
- On fault trigger, controller computes alternate path (Dijkstra/shortest-path re-computation) and pushes new flow rules
- Deliverable: End-to-end fault → detect → reroute pipeline

### **Phase 5: Dashboard & Visualization (Week 9)**
- Build a Flask/Django backend serving REST APIs for topology + health data
- Frontend with Chart.js/D3.js showing live topology, link health (color-coded), and event logs
- Deliverable: Live web dashboard

### **Phase 6: Testing, Demo & Documentation (Week 10–11)**
- Simulate link failures (kill interface), measure recovery time
- Record before/after latency, packet loss metrics
- Write documentation, architecture diagrams, README
- Deliverable: Demo-ready project + report

---

## 5. System Architecture

```
                     ┌─────────────────────────┐
                     │      Dashboard (UI)      │
                     │   Flask/Django + Chart.js│
                     └────────────┬─────────────┘
                                  │ REST API
                     ┌────────────▼─────────────┐
                     │     Application Layer     │
                     │  (Orchestration Service)  │
                     └───┬───────────────────┬───┘
                         │                   │
           ┌─────────────▼───────┐   ┌──────▼──────────────┐
           │  Monitoring Agent    │   │  Fault Detection     │
           │  (Scapy/SNMP polling)│   │  Engine (ML/Rules)   │
           └─────────────┬────────┘   └──────┬───────────────┘
                         │                    │
                         ▼                    ▼
                  ┌──────────────┐    ┌───────────────────┐
                  │ Time-Series  │    │  SDN Controller    │
                  │  DB (Influx) │    │  (Ryu / ONOS)      │
                  └──────────────┘    └─────────┬───────────┘
                                                 │ OpenFlow
                                       ┌─────────▼───────────┐
                                       │  Mininet Topology    │
                                       │  (Switches + Hosts)  │
                                       └───────────────────────┘
```

**Data flow:** Monitoring Agent polls the Mininet topology → metrics stored in DB → Fault Detection Engine analyzes stream → on anomaly, signals SDN Controller → Controller recalculates path → pushes new OpenFlow rules → Dashboard reflects updated topology in real time.

---

## 6. Wireframe Model (Dashboard)

```
┌──────────────────────────────────────────────────────────┐
│  NetworkGuardian                          [●] System: OK  │
├──────────────────────────────────────────────────────────┤
│                                                            │
│   ┌───────────────┐        ┌───────────────────────────┐ │
│   │               │        │  Link Health               │ │
│   │  Live Topology│        │  H1-S1  ●  Latency: 12ms   │ │
│   │   (graph view)│        │  S1-S2  ●  Latency: 18ms   │ │
│   │               │        │  S2-H2  ▲  Degraded         │ │
│   │  ● = healthy  │        │  S1-S3  ✕  DOWN — rerouted  │ │
│   │  ▲ = warning  │        └───────────────────────────┘ │
│   │  ✕ = down     │                                       │
│   └───────────────┘        ┌───────────────────────────┐ │
│                             │  Event Log                 │ │
│   ┌───────────────┐        │  10:32:01 Fault detected    │ │
│   │ Metrics Chart │        │  10:32:03 Reroute complete  │ │
│   │ (latency/time)│        │  10:31:58 Baseline stable   │ │
│   └───────────────┘        └───────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 7. Design Guide

- **Color coding:** Green (healthy), Amber (degraded/warning), Red (down/fault)
- **Typography:** Clean sans-serif (Inter/Roboto) for readability of technical data
- **Layout:** Split-pane — topology graph on left, metrics/logs on right, so recovery events are visible alongside the visual reroute
- **Real-time feel:** Use WebSockets (Flask-SocketIO) instead of polling the frontend, so the dashboard updates instantly during a demo
- **Minimalism:** Avoid clutter — this is a NOC (Network Operations Center)-style tool, not a consumer app

---

## 8. Core Features

1. **Live Topology Visualization** — auto-updating graph of nodes/links with health status
2. **Real-Time Metrics Collection** — latency, jitter, packet loss, throughput
3. **Anomaly-Based Fault Detection** — ML model flags deviations from baseline behavior
4. **Automatic Path Recomputation** — SDN controller reroutes via shortest healthy path
5. **Event Logging & Alerts** — timestamped log of detections and recovery actions
6. **Historical Analytics** — graph of network health/recovery time trends
7. **Manual Override Mode** — allows an operator to accept/reject a suggested reroute (shows human-in-the-loop design awareness)

---

## 9. Demo Plan

**Live demo sequence (5 minutes):**
1. Show stable topology on dashboard — all links green.
2. Kill a link manually in Mininet (`link s1 s3 down`).
3. Dashboard shows real-time detection (link turns red, event log updates).
4. Controller recalculates path — new flow rules pushed; traffic reroutes.
5. Show recovered topology and a metrics chart comparing latency before/after.
6. Present final report: "Recovery achieved in X.XX seconds with zero manual intervention."

This before/after quantified result is the single most memorable part of the demo for an interview panel.

---

## 10. Technical Approach & Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Network simulation | Mininet | Industry-standard SDN emulator, lightweight |
| SDN Controller | Ryu (Python-based) | Easier integration with Python ML/monitoring stack than ONOS |
| Packet monitoring | Scapy / SNMP (pysnmp) | Fine-grained packet-level visibility |
| Anomaly detection | scikit-learn (Isolation Forest) | Lightweight, explainable, doesn't need GPU |
| Time-series storage | InfluxDB (or SQLite for simplicity) | Optimized for metrics over time |
| Backend/API | Flask + Flask-SocketIO | Simple, real-time capable |
| Frontend | React or plain JS + D3.js/Chart.js | Graph visualization + live charts |
| Routing algorithm | Dijkstra's shortest path (networkx) | Standard, explainable rerouting logic |

---

## 11. File Structure

```
NetworkGuardian/
│
├── topology/
│   └── mininet_topo.py          # Custom Mininet topology definition
│
├── controller/
│   ├── ryu_app.py               # SDN controller logic (Ryu app)
│   └── reroute_engine.py        # Dijkstra-based path recomputation
│
├── monitoring/
│   ├── agent.py                 # Polls network for latency/loss/jitter
│   └── metrics_store.py         # Writes to InfluxDB/SQLite
│
├── detection/
│   ├── anomaly_model.py         # Isolation Forest / threshold logic
│   └── train_baseline.py        # Trains model on "normal" traffic
│
├── backend/
│   ├── app.py                   # Flask app + REST + WebSocket endpoints
│   └── routes/
│       ├── topology.py
│       └── events.py
│
├── frontend/
│   ├── index.html
│   ├── dashboard.js
│   └── styles.css
│
├── logs/
│   └── events.log
│
├── tests/
│   └── test_fault_injection.py  # Simulated link failure tests
│
├── docs/
│   ├── architecture_diagram.png
│   └── demo_recording.mp4
│
├── requirements.txt
└── README.md
```

---

## 12. Networking Concepts Used, Where, and Why

| Concept | Where Applied | Relevance |
|---|---|---|
| **OSI Layer 2/3 switching & routing** | Mininet topology, flow rules | Core foundation of how packets move; needed to design realistic topology |
| **SDN (Software-Defined Networking)** | Controller-topology separation | Nokia builds SDN/NFV-based network infrastructure for telecom operators |
| **OpenFlow protocol** | Controller ↔ switch communication | Industry-standard protocol for programmable networks |
| **Shortest Path Routing (Dijkstra)** | Rerouting engine | Same principle behind dynamic routing protocols (OSPF) |
| **Network telemetry/SNMP** | Monitoring agent | Real ISPs/telecoms use SNMP for device health polling |
| **Latency, jitter, packet loss (QoS metrics)** | Metrics collection | These are the exact KPIs telecom NOC teams track for SLAs |
| **Fault tolerance & self-healing networks** | Overall system design | Core theme in 5G/6G network architecture — self-organizing networks (SON) |
| **Anomaly detection in time-series data** | ML detection engine | Reflects Nokia's "AI for connectivity" direction — predictive maintenance |
| **Network topology graphs** | Visualization | Understanding of graph theory as applied to networking |

---

## 13. Relevance to Nokia

- Nokia's core business spans **fixed, mobile, and transport networks** — this project directly touches routing, fault tolerance, and telemetry, which are foundational to all three.
- Nokia's tagline, "connectivity for the AI era," reflects a push toward **AI-driven network automation** — this project's anomaly detection engine is a small-scale demonstration of that exact concept (predictive fault detection, not just reactive).
- Nokia Bell Labs researches **self-organizing networks (SON)** and **autonomous network healing** for 5G/6G — NetworkGuardian is a simplified, working prototype of that same philosophy.
- Demonstrating SDN/OpenFlow experience signals readiness for Nokia's work in **network virtualization (NFV)** and cloud-native network functions.

---

## 14. Real-World Impact & Applications

- **Telecom operators** — reduces mean-time-to-recovery (MTTR) for backbone link failures, directly improving SLA compliance.
- **Data centers** — auto-rerouting minimizes service disruption during hardware failures.
- **Enterprise networks** — smaller-scale deployment could reduce reliance on manual NOC monitoring.
- **5G edge networks** — the same detect-and-reroute logic underpins resilience in distributed, low-latency edge infrastructure.
- **Cost impact** — every minute of network downtime has measurable financial cost in enterprise/telecom settings; automated recovery directly reduces this.

---

## 15. Evaluation Metrics (For Your Report)

- Mean Time to Detect (MTTD) fault
- Mean Time to Recover (MTTR) after fault
- False positive rate of anomaly detector
- Latency/packet loss before vs. after rerouting
- System overhead (CPU/memory usage of monitoring agent)

---

## 16. Future Enhancements (Good talking points in interviews)

- Extend from single-domain SDN to multi-domain orchestration
- Predictive fault detection (forecast failure before it happens, not just react)
- Integration with real hardware (Raspberry Pi cluster) instead of pure simulation
- Reinforcement learning for optimal path selection under multiple simultaneous faults

---

## 17. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Mininet/Ryu environment setup complexity | Use Docker container with pre-configured environment |
| ML model overfitting on synthetic "normal" traffic | Inject varied traffic patterns during baseline training |
| Demo failure during live presentation | Pre-record a backup demo video alongside live version |
| Scope creep (too many features, not finished) | Treat Phases 1–4 as MVP; Phases 5–6 as polish |

---

## 18. Summary

NetworkGuardian is scoped to be buildable solo in ~10–11 weeks, uses tools genuinely relevant to Nokia's domain (SDN, OpenFlow, telemetry, AI-based detection), and produces a demoable, quantifiable result — the strongest combination for making an internship application stand out.
