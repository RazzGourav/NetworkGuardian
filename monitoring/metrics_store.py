#!/usr/bin/env python3
"""
NetworkGuardian — Metrics Storage

Persists link health metrics (latency, packet loss, jitter) to SQLite database
with timestamps. Designed for simplicity and low overhead compared to InfluxDB.

Database schema:
  CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,           -- ISO 8601 timestamp
    link_id TEXT NOT NULL,             -- e.g., "h1-s1", "s1-s2"
    metric_type TEXT NOT NULL,         -- "host-switch", "switch-switch"
    latency_ms REAL,                   -- average RTT in milliseconds
    packet_loss_percent REAL,          -- packet loss percentage
    jitter_ms REAL                     -- jitter (std dev of latency)
  );

Indexed on (link_id, timestamp) for efficient querying.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path

LOG = logging.getLogger("NetworkGuardian.MetricsStore")


import threading

class MetricsStore:
    """SQLite-based time-series metrics storage for network link health."""

    def __init__(self, db_path: str = "/app/data/metrics.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.lock = threading.Lock()
        LOG.info("MetricsStore initialized for %s", db_path)

    def connect(self) -> sqlite3.Connection:
        """Establish database connection."""
        if self.conn is None:
            # Ensure parent directory exists
            db_path_obj = Path(self.db_path)
            db_path_obj.parent.mkdir(parents=True, exist_ok=True)

            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Return dict-like rows
            LOG.debug("Connected to SQLite database at %s", self.db_path)

        return self.conn

    def initialize(self):
        """Create tables if they don't exist."""
        conn = self.connect()
        cursor = conn.cursor()

        with self.lock:
            # Create metrics table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                link_id TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                latency_ms REAL,
                packet_loss_percent REAL,
                jitter_ms REAL
            )
        """)

            # Create indexes for efficient querying
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_link_timestamp
            ON metrics (link_id, timestamp)
        """)

            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
            ON metrics (timestamp)
        """)

            conn.commit()
            LOG.info("Database initialized with metrics table")

            # Check existing metrics count
            cursor.execute("SELECT COUNT(*) as count FROM metrics")
            count = cursor.fetchone()["count"]
            LOG.info("Existing metrics in database: %d", count)

    def write_metric(self, link_id: str, metric_type: str, metrics: Dict):
        """
        Write a single metric reading to the database.

        Args:
            link_id: Unique identifier for the link (e.g., "h1-s1")
            metric_type: Type of link ("host-switch", "switch-switch")
            metrics: Dictionary with keys:
                - timestamp (ISO 8601 string)
                - latency_ms (float or None)
                - packet_loss_percent (float)
                - jitter_ms (float or None)
        """
        conn = self.connect()
        cursor = conn.cursor()

        try:
            with self.lock:
                cursor.execute("""
                INSERT INTO metrics
                (timestamp, link_id, metric_type, latency_ms, packet_loss_percent, jitter_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                metrics.get("timestamp", datetime.utcnow().isoformat()),
                link_id,
                metric_type,
                metrics.get("latency_ms"),
                metrics.get("packet_loss_percent"),
                metrics.get("jitter_ms")
            ))

            conn.commit()
            LOG.debug("Written metric for link %s: %.2f ms, %.1f%% loss",
                      link_id, metrics.get("latency_ms", 0),
                      metrics.get("packet_loss_percent", 0))

        except Exception as e:
            LOG.error("Error writing metric for link %s: %s", link_id, str(e))
            conn.rollback()

    def get_recent_metrics(self, link_id: Optional[str] = None,
                          limit: int = 100) -> List[Dict]:
        """
        Retrieve recent metrics, optionally filtered by link_id.

        Args:
            link_id: If provided, only return metrics for this link
            limit: Maximum number of records to return

        Returns:
            List of metric dictionaries sorted by timestamp (newest first)
        """
        conn = self.connect()
        cursor = conn.cursor()

        try:
            with self.lock:
                if link_id:
                    cursor.execute("""
                    SELECT * FROM metrics
                    WHERE link_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (link_id, limit))
                else:
                    cursor.execute("""
                    SELECT * FROM metrics
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                
                rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            LOG.error("Error reading metrics: %s", str(e))
            return []

    def get_summary_stats(self, hours: int = 1) -> Dict:
        """
        Generate summary statistics for the last N hours.

        Args:
            hours: Lookback period in hours

        Returns:
            Dictionary with summary statistics per link
        """
        conn = self.connect()
        cursor = conn.cursor()

        cutoff_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        try:
            with self.lock:
                cursor.execute("""
                SELECT
                    link_id,
                    metric_type,
                    COUNT(*) as readings,
                    AVG(latency_ms) as avg_latency_ms,
                    AVG(packet_loss_percent) as avg_loss_percent,
                    MIN(latency_ms) as min_latency_ms,
                    MAX(latency_ms) as max_latency_ms,
                    MAX(timestamp) as last_reading
                FROM metrics
                WHERE timestamp >= ?
                GROUP BY link_id, metric_type
                ORDER BY link_id
            """, (cutoff_time,))

            rows = cursor.fetchall()
            summary = {
                "period_hours": hours,
                "cutoff_time": cutoff_time,
                "total_readings": 0,
                "links": []
            }

            for row in rows:
                link_summary = dict(row)
                summary["links"].append(link_summary)
                summary["total_readings"] += link_summary["readings"]

            return summary

        except Exception as e:
            LOG.error("Error generating summary stats: %s", str(e))
            return {"error": str(e)}

    def get_link_health(self, link_id: str, minutes: int = 5) -> Dict:
        """
        Get health status for a specific link.

        Args:
            link_id: Link to check
            minutes: Lookback period in minutes

        Returns:
            Dictionary with health assessment
        """
        cutoff_time = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()

        conn = self.connect()
        cursor = conn.cursor()

        try:
            with self.lock:
                # Get recent metrics for this link
                cursor.execute("""
                SELECT
                    AVG(latency_ms) as avg_latency,
                    AVG(packet_loss_percent) as avg_loss,
                    COUNT(*) as readings_count
                FROM metrics
                WHERE link_id = ? AND timestamp >= ?
            """, (link_id, cutoff_time))

            row = cursor.fetchone()
            if not row or row["readings_count"] == 0:
                return {
                    "link_id": link_id,
                    "status": "unknown",
                    "reason": "no_recent_readings",
                    "readings_count": 0
                }

            avg_latency = row["avg_latency"] or 0
            avg_loss = row["avg_loss"] or 0

            # Determine health status
            if avg_loss > 50.0:
                status = "critical"
                reason = "high_packet_loss"
            elif avg_loss > 20.0:
                status = "degraded"
                reason = "elevated_packet_loss"
            elif avg_latency > 100.0:  # 100ms threshold
                status = "degraded"
                reason = "high_latency"
            elif avg_loss > 5.0:
                status = "warning"
                reason = "moderate_packet_loss"
            elif avg_latency > 50.0:
                status = "warning"
                reason = "moderate_latency"
            else:
                status = "healthy"
                reason = "normal"

            return {
                "link_id": link_id,
                "status": status,
                "reason": reason,
                "avg_latency_ms": round(avg_latency, 2),
                "avg_loss_percent": round(avg_loss, 1),
                "readings_count": row["readings_count"],
                "last_minutes": minutes
            }

        except Exception as e:
            LOG.error("Error assessing link health for %s: %s", link_id, str(e))
            return {
                "link_id": link_id,
                "status": "error",
                "reason": str(e)
            }

    def cleanup_old_metrics(self, days_to_keep: int = 7):
        """
        Delete metrics older than N days to prevent database bloat.

        Args:
            days_to_keep: Number of days of data to retain
        """
        cutoff_time = (datetime.utcnow() - timedelta(days=days_to_keep)).isoformat()

        conn = self.connect()
        cursor = conn.cursor()

        try:
            with self.lock:
                cursor.execute("""
                DELETE FROM metrics WHERE timestamp < ?
            """, (cutoff_time,))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                LOG.info("Cleaned up %d metrics older than %s", deleted, cutoff_time)
            else:
                LOG.debug("No old metrics to clean up")

            return deleted

        except Exception as e:
            LOG.error("Error cleaning up old metrics: %s", str(e))
            conn.rollback()
            return 0

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            LOG.info("Database connection closed")

    def __del__(self):
        """Destructor to ensure connection is closed."""
        self.close()


# Utility functions for testing and debugging
def print_recent_metrics(db_path: str = "/app/monitoring/metrics.db", limit: int = 10):
    """Print recent metrics for debugging."""
    store = MetricsStore(db_path)
    store.connect()

    metrics = store.get_recent_metrics(limit=limit)
    print(f"\nRecent metrics (last {limit}):")
    print("-" * 80)
    for metric in metrics:
        print(f"{metric['timestamp']} | {metric['link_id']:8} | "
              f"Latency: {metric['latency_ms'] or 'N/A':6} ms | "
              f"Loss: {metric['packet_loss_percent']:5.1f}% | "
              f"Jitter: {metric['jitter_ms'] or 'N/A':6} ms")


if __name__ == "__main__":
    # Simple test/demo
    import sys
    logging.basicConfig(level=logging.INFO)

    store = MetricsStore("test_metrics.db")
    store.initialize()

    # Write a test metric
    test_metric = {
        "timestamp": datetime.utcnow().isoformat(),
        "latency_ms": 12.5,
        "packet_loss_percent": 0.0,
        "jitter_ms": 1.2
    }
    store.write_metric("test-link", "test-type", test_metric)

    # Read it back
    metrics = store.get_recent_metrics()
    print(f"Written and retrieved {len(metrics)} metrics")

    # Print summary
    summary = store.get_summary_stats(hours=24)
    print(f"Summary: {json.dumps(summary, indent=2)}")

    store.close()
    print("\nMetrics store test complete.")