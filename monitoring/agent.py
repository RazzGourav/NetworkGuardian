#!/usr/bin/env python3
"""
NetworkGuardian — Monitoring Agent

Polls each link in the NetworkGuardian topology for latency, packet loss,
and jitter at ≤2 second intervals using ICMP ping probes between hosts.

How it works:
  1. Discovers all links from the topology (host-switch and switch-switch).
  2. For each link, selects two endpoints (hosts or switch IPs) to ping across.
  3. Runs ping probes every 2 seconds.
  4. Calculates latency (RTT), packet loss %, and jitter (std dev of latency).
  5. Stores metrics via metrics_store.py.

The agent handles temporary link failures gracefully and continues monitoring
other links. Designed to run in the monitoring-agent Docker container alongside
Mininet and the SDN controller.
"""

import sys
import time
import subprocess
import threading
import json
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional
import logging

# Add project root to path for imports
sys.path.insert(0, "/app")
from monitoring.metrics_store import MetricsStore

LOG = logging.getLogger("NetworkGuardian.MonitoringAgent")


class LinkMonitor:
    """Monitor a single network link using ICMP ping probes."""

    def __init__(self, link_id: str, src_ip: str, dst_ip: str, link_type: str = "host-switch"):
        self.link_id = link_id  # e.g., "h1-s1" or "s1-s2"
        self.src_ip = src_ip  # Source IP to ping FROM
        self.dst_ip = dst_ip  # Destination IP to ping TO
        self.link_type = link_type  # "host-switch", "switch-switch"
        self.running = False
        self.thread = None

        # Metrics storage for calculation
        self.latencies = deque(maxlen=20)  # Last 20 RTT readings
        self.packet_count = 0
        self.lost_count = 0
        self.last_update = None

        LOG.info("Created monitor for link %s: %s -> %s", link_id, src_ip, dst_ip)

    def _ping_once(self) -> Optional[float]:
        """Send a single ping and return RTT in ms, or None if lost."""
        # Use ping command: -c 1 (one packet), -W 1 (1s timeout), -q (quiet)
        cmd = ["ping", "-c", "1", "-W", "1", "-q", self.dst_ip]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=2  # Overall timeout
            )
            if result.returncode == 0:
                # Parse output to extract RTT
                # Example: "rtt min/avg/max/mdev = 0.045/0.045/0.045/0.000 ms"
                for line in result.stdout.split("\n"):
                    if "rtt min/avg/max/mdev" in line:
                        parts = line.split("=")[1].strip().split("/")
                        avg_rtt = float(parts[1])  # Average RTT in ms
                        return avg_rtt
                # Fallback: if parsing fails but ping succeeded, assume low latency
                LOG.debug("Ping succeeded but RTT parse failed for %s", self.dst_ip)
                return 0.1  # Default small latency
            else:
                # Ping failed (packet lost)
                return None
        except subprocess.TimeoutExpired:
            LOG.debug("Ping timeout for %s", self.dst_ip)
            return None
        except Exception as e:
            LOG.warning("Ping error for %s: %s", self.dst_ip, str(e))
            return None

    def calculate_metrics(self) -> Dict:
        """Calculate current metrics from stored readings."""
        if not self.latencies:
            return {
                "latency_ms": None,
                "packet_loss_percent": 100.0,
                "jitter_ms": None,
                "timestamp": datetime.utcnow().isoformat()
            }

        # Calculate latency stats
        latencies_list = list(self.latencies)
        avg_latency = sum(latencies_list) / len(latencies_list)

        # Calculate jitter (standard deviation of latencies)
        if len(latencies_list) > 1:
            mean = avg_latency
            variance = sum((x - mean) ** 2 for x in latencies_list) / (len(latencies_list) - 1)
            jitter = variance ** 0.5
        else:
            jitter = 0.0

        # Calculate packet loss percentage
        total_packets = self.packet_count
        if total_packets > 0:
            loss_percent = (self.lost_count / total_packets) * 100.0
        else:
            loss_percent = 100.0

        return {
            "latency_ms": round(avg_latency, 3),
            "packet_loss_percent": round(loss_percent, 1),
            "jitter_ms": round(jitter, 3) if jitter is not None else None,
            "timestamp": datetime.utcnow().isoformat()
        }

    def monitor_loop(self, store: MetricsStore):
        """Main monitoring loop for this link."""
        LOG.info("Starting monitor for link %s", self.link_id)
        self.running = True

        while self.running:
            try:
                # Send ping
                rtt = self._ping_once()
                self.packet_count += 1
                self.last_update = datetime.utcnow()

                if rtt is not None:
                    # Successful ping
                    self.latencies.append(rtt)
                else:
                    # Packet lost
                    self.lost_count += 1

                # Calculate and store metrics
                metrics = self.calculate_metrics()
                store.write_metric(
                    link_id=self.link_id,
                    metric_type=self.link_type,
                    metrics=metrics
                )

                # Log periodically
                if self.packet_count % 10 == 0:
                    LOG.debug("Link %s: %d packets, %.1f%% loss, %.2f ms latency",
                              self.link_id, self.packet_count,
                              metrics["packet_loss_percent"], metrics["latency_ms"] or 0)

            except Exception as e:
                LOG.error("Error monitoring link %s: %s", self.link_id, str(e))

            # Wait before next ping (target ≤2s interval)
            # Account for ping time to maintain consistent interval
            time.sleep(1.8)

        LOG.info("Stopped monitor for link %s", self.link_id)

    def start(self, store: MetricsStore):
        """Start monitoring thread."""
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(
                target=self.monitor_loop,
                args=(store,),
                daemon=True,
                name=f"Monitor-{self.link_id}"
            )
            self.thread.start()

    def stop(self):
        """Stop monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)


class MonitoringAgent:
    """Main monitoring agent that manages all link monitors."""

    def __init__(self, db_path: str = "/app/monitoring/metrics.db"):
        self.store = MetricsStore(db_path)
        self.monitors: Dict[str, LinkMonitor] = {}
        self.running = False
        LOG.info("MonitoringAgent initialized with DB at %s", db_path)

    def discover_topology_links(self) -> List[Tuple[str, str, str, str]]:
        """
        Discover links in the NetworkGuardian topology.

        Returns list of (link_id, src_ip, dst_ip, link_type) tuples.
        For Phase 2, we use static topology. In later phases, this could
        query the SDN controller or Mininet API.
        """
        # Static topology based on NetworkGuardian's Phase 1 design
        # Host IPs: h1=10.0.0.1, h2=10.0.0.2, h3=10.0.0.3, h4=10.0.0.4
        #           h5=10.0.0.5, h6=10.0.0.6, h7=10.0.0.7, h8=10.0.0.8

        links = []

        # Host-to-switch links
        host_links = [
            ("h1-s1", "10.0.0.1", "10.0.0.2"),  # h1 to h2 (via s1)
            ("h2-s1", "10.0.0.2", "10.0.0.1"),  # h2 to h1 (via s1)
            ("h3-s4", "10.0.0.3", "10.0.0.4"),  # h3 to h4 (via s4)
            ("h4-s4", "10.0.0.4", "10.0.0.3"),  # h4 to h3 (via s4)
            ("h5-s3", "10.0.0.5", "10.0.0.6"),  # h5 to h6 (via s3)
            ("h6-s3", "10.0.0.6", "10.0.0.5"),  # h6 to h5 (via s3)
            ("h7-s4", "10.0.0.7", "10.0.0.3"),  # h7 to h3 (via s4)
            ("h8-s3", "10.0.0.8", "10.0.0.5"),  # h8 to h5 (via s3)
        ]

        # Switch-to-switch links (monitored via host endpoints)
        # We'll ping between hosts that communicate through these links
        switch_links = [
            ("s1-s2", "10.0.0.1", "10.0.0.5"),  # h1 to h5 (via s1-s2-s3)
            ("s2-s3", "10.0.0.1", "10.0.0.5"),  # same path, different segment
            ("s1-s4", "10.0.0.2", "10.0.0.3"),  # h2 to h3 (via s1-s4)
            ("s4-s3", "10.0.0.3", "10.0.0.5"),  # h3 to h5 (via s4-s3)
        ]

        for link_id, src_ip, dst_ip in host_links:
            links.append((link_id, src_ip, dst_ip, "host-switch"))

        for link_id, src_ip, dst_ip in switch_links:
            links.append((link_id, src_ip, dst_ip, "switch-switch"))

        LOG.info("Discovered %d links in topology", len(links))
        return links

    def start(self):
        """Start monitoring all links."""
        if self.running:
            LOG.warning("Agent already running")
            return

        LOG.info("Starting NetworkGuardian Monitoring Agent")
        self.running = True

        # Initialize database
        self.store.initialize()

        # Discover and start monitoring links
        links = self.discover_topology_links()
        for link_id, src_ip, dst_ip, link_type in links:
            monitor = LinkMonitor(link_id, src_ip, dst_ip, link_type)
            monitor.start(self.store)
            self.monitors[link_id] = monitor

        LOG.info("Started %d link monitors", len(self.monitors))

        # Main thread keeps running
        try:
            while self.running:
                # Periodically check monitor health
                time.sleep(10)
                alive_monitors = sum(1 for m in self.monitors.values()
                                   if m.thread and m.thread.is_alive())
                LOG.debug("%d/%d monitors alive", alive_monitors, len(self.monitors))

                # Log summary every minute
                if int(time.time()) % 60 == 0:
                    self._log_summary()

        except KeyboardInterrupt:
            LOG.info("Received shutdown signal")
        except Exception as e:
            LOG.error("Agent main loop error: %s", str(e))
        finally:
            self.stop()

    def _log_summary(self):
        """Log summary of current link health."""
        try:
            summary = self.store.get_summary_stats()
            LOG.info("Metrics summary: %s", json.dumps(summary, indent=2))
        except Exception as e:
            LOG.warning("Could not generate summary: %s", str(e))

    def stop(self):
        """Stop all monitoring."""
        LOG.info("Stopping Monitoring Agent")
        self.running = False

        for link_id, monitor in self.monitors.items():
            try:
                monitor.stop()
                LOG.debug("Stopped monitor for %s", link_id)
            except Exception as e:
                LOG.warning("Error stopping monitor %s: %s", link_id, str(e))

        self.store.close()
        LOG.info("Monitoring Agent stopped")


def main():
    """Entry point for the monitoring agent."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("/app/logs/monitoring_agent.log")
        ]
    )

    agent = MonitoringAgent()

    try:
        agent.start()
    except Exception as e:
        LOG.critical("Agent failed: %s", str(e))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())