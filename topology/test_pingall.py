#!/usr/bin/env python3
"""
NetworkGuardian — Automated pingall test.

This script:
  1. Creates the Mininet network with the NetworkGuardian topology.
  2. Runs pingall and reports the result.
  3. Exits with code 0 on 0% packet loss, code 1 otherwise.
"""

import sys
import time
import subprocess

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel, info, error

# Import our topology
sys.path.insert(0, "/app/topology")
from mininet_topo import NetworkGuardianTopo


def run_test():
    """Run the NetworkGuardian pingall test."""
    setLogLevel("info")

    info("*** Creating NetworkGuardian topology\n")
    topo = NetworkGuardianTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip="127.0.0.1", port=6653),
        switch=OVSKernelSwitch,
        autoSetMacs=True,
    )
    net.start()

    # Give the controller time to install initial flows
    info("*** Waiting 5s for controller to connect to switches...\n")
    time.sleep(5)

    # Run the pingall test
    info("*** Running pingall (timeout=10s)\n")
    drop_pct = net.pingAll(timeout="10")

    net.stop()

    if drop_pct == 0:
        info("*** SUCCESS: 0%% packet loss — all hosts reachable!\n")
        return 0
    else:
        error("*** FAIL: %.0f%% packet loss\n" % drop_pct)
        return 1


if __name__ == "__main__":
    sys.exit(run_test())
