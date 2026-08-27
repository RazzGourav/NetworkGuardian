# NetworkGuardian: Autonomous Self-Healing SDN 🛡️

**NetworkGuardian** is an autonomous, self-healing Software-Defined Network (SDN) built with Ryu and Mininet. It uses a Machine Learning anomaly detection engine (Isolation Forest) to detect network faults and broadcast storms, and a dynamic minimum spanning tree (MST) and shortest-path routing algorithm to automatically recover connectivity in milliseconds.

## 🌟 Overview

Modern networks are highly dynamic and prone to physical link failures. NetworkGuardian provides:
- **Redundant Topology:** A resilient dual-path core network (4 switches, 5 hosts).
- **Intelligent Monitoring:** A distributed Python agent constantly collecting RTT, jitter, and packet loss.
- **AI-Powered Detection:** An Isolation Forest model trained on stable baselines to instantly flag anomalous latency and link degradation.
- **Autonomous Rerouting:** A Ryu OpenFlow 1.3 controller that recalculates active paths via Dijkstra's algorithm and dynamically drops loops using a spanning tree approach when links fail.
- **Real-Time Visualization:** A premium glassmorphism dark-mode NOC dashboard visualizing topology health and live fault events via WebSockets.

## 🏗️ Architecture

```mermaid
graph TD
    subgraph SDN Layer
        C[Ryu Controller] <-->|OpenFlow 1.3| S1(Switch 1)
        C <-->|OpenFlow 1.3| S2(Switch 2)
        C <-->|OpenFlow 1.3| S3(Switch 3)
        C <-->|OpenFlow 1.3| S4(Switch 4)
    end
    
    subgraph Data Plane
        H1(Host 1) --- S1
        H2(Host 2) --- S1
        S1 ---|Primary| S2
        S1 ---|Backup| S4
        S4 --- S3
        S2 --- S3
        S3 --- H3(Host 3)
        S3 --- H4(Host 4)
        S3 --- H5(Host 5)
    end

    subgraph Intelligence Layer
        M[Monitoring Agent] -->|ICMP Ping| Data Plane
        M -->|Metrics| DB[(SQLite / InfluxDB)]
        M -->|Anomaly Detection| ML[Isolation Forest]
        ML -->|Trigger Reroute| C
        ML -->|Trigger Alert| B
    end
    
    subgraph Visualization
        B[Flask Backend] -->|Reads| DB
        B <-->|WebSockets| D[Frontend Dashboard]
    end
```

## 🚀 Getting Started

The entire stack is containerized for seamless deployment.

### Prerequisites
- Docker & Docker Compose
- Windows (WSL2), Linux, or macOS

### 1-Click Startup

Simply run the following command to bring up the Mininet topology, Ryu controller, Monitoring Agent, and the live Dashboard:

```bash
docker compose up -d
```

### Accessing the Dashboard
Once the stack is running, navigate to:
**http://localhost:5000**

## 📊 Performance Results

We simulated link failures (bringing down the primary `s1-s2` link) dynamically to measure the system's resilience.

| Metric | Measured Value | Target | Status |
|--------|----------------|--------|--------|
| **Mean Time to Recover (MTTR)** | ~0.01 seconds | < 5.0 seconds | ✅ PASS |
| **False Positive Rate (FPR)** | 0.60% | < 10% | ✅ PASS |
| **Detection Latency (MTTD)** | ~1.5 seconds | < 2.0 seconds | ✅ PASS |

## 🎥 Demonstration

![Dashboard fault simulation](docs/dashboard_demo.webp)

## 📖 Documentation
- For detailed product requirements, see the [PRD (p1.md)](p1.md).
- For step-by-step development progress, see [PROGRESS.md](PROGRESS.md).
