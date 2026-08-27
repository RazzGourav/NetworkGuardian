#!/usr/bin/env python3
"""
NetworkGuardian — Fault Injection Test
Brings a link down in Mininet and verifies that connectivity is restored
within 5 seconds by the detection and reroute engine.
"""

import sys
import time
import pytest
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel, info

# Import our topology
sys.path.insert(0, "/app/topology")
from mininet_topo import NetworkGuardianTopo

def test_fault_injection_recovery():
    """
    Test the automatic rerouting when a link fails.
    """
    setLogLevel("info")
    info("\n*** Creating NetworkGuardian topology for Fault Injection\n")
    
    topo = NetworkGuardianTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip="127.0.0.1", port=6653),
        switch=OVSKernelSwitch,
        autoSetMacs=True,
    )
    net.start()

    # Export Mininet host PIDs so the monitoring agent can run ping inside their namespaces
    import json
    pids = {h.IP(): h.pid for h in net.hosts}
    with open("/tmp/mininet_pids.json", "w") as f:
        json.dump(pids, f)

    # Start monitoring agent in background
    info("*** Starting monitoring agent...\n")
    import os
    import subprocess
    env = os.environ.copy()
    env["METRICS_DB_PATH"] = "/tmp/metrics.db"
    agent_proc = subprocess.Popen(["python3", "/app/monitoring/agent.py"], env=env)

    # Wait for controller connection and initial monitoring setup
    info("*** Waiting 10s for controller and monitoring agent to initialize...\n")
    time.sleep(10)

    h1 = net.get('h1')
    h5 = net.get('h5')

    # Baseline ping
    info("*** Testing initial connectivity (h1 -> h5)...\n")
    result = net.ping([h1, h5])
    try:
        assert result == 0, "Initial ping failed. Baseline connectivity broken."
    except AssertionError as e:
        import os
        print("\n=== /tmp contents ===")
        os.system("ls -la /tmp/")
        print("\n=== RYU LOG ===")
        os.system("cat /tmp/ryu.log")
        raise e
    
    # Inject fault
    info("*** Injecting fault: bringing down s1-s2 link...\n")
    net.configLinkStatus('s1', 's2', 'down')
    
    # Start timer
    start_time = time.time()
    recovered = False
    
    # Rapid poll until recovered or timeout
    timeout = 10.0
    while time.time() - start_time < timeout:
        # Send a single ping packet
        ping_res = h1.cmd('ping -c 1 -W 1 10.0.0.5')
        if '1 received' in ping_res:
            recovered = True
            break
        time.sleep(0.5)
        
    recovery_time = time.time() - start_time
    
    # Restore link for clean teardown
    net.configLinkStatus('s1', 's2', 'up')
    net.stop()
    agent_proc.terminate()
    agent_proc.wait()
    
    print(f"\n*** Recovery Time: {recovery_time:.2f} seconds")
    assert recovered, "Failed to recover connectivity within timeout"
    assert recovery_time < 5.0, f"Recovery time {recovery_time:.2f}s exceeded 5s requirement"
    
if __name__ == "__main__":
    test_fault_injection_recovery()
