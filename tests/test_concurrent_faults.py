#!/usr/bin/env python3
import sys
import time
import pytest
import os
import subprocess
import json
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel, info

sys.path.insert(0, "/app/topology")
from mininet_topo import NetworkGuardianTopo

def test_concurrent_faults():
    """
    Test that two independent faults occurring within the 5-second
    window are BOTH detected and not suppressed by a global cooldown.
    """
    setLogLevel("info")
    topo = NetworkGuardianTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip="127.0.0.1", port=6653),
        switch=OVSKernelSwitch,
        autoSetMacs=True,
    )
    net.start()

    pids = {h.IP(): h.pid for h in net.hosts}
    with open("/tmp/mininet_pids.json", "w") as f:
        json.dump(pids, f)

    time.sleep(8)
    
    agent_log_file = "/tmp/test_agent.log"
    if os.path.exists(agent_log_file):
        os.remove(agent_log_file)
        
    env = os.environ.copy()
    env["METRICS_DB_PATH"] = "/tmp/metrics.db"
    
    # Run agent and redirect output to log file to check for both faults
    with open(agent_log_file, "w") as log_out:
        agent_proc = subprocess.Popen(["python3", "/app/monitoring/agent.py"], env=env, stdout=log_out, stderr=subprocess.STDOUT)

    time.sleep(3)

    info("*** Injecting first fault: s1-s2\n")
    net.configLinkStatus('s1', 's2', 'down')
    
    # Wait 1.5 seconds (within the 5-second cooldown window)
    time.sleep(1.5)
    
    info("*** Injecting second fault: s2-s3\n")
    net.configLinkStatus('s2', 's3', 'down')
    
    # Wait for detection
    time.sleep(5)
    
    net.configLinkStatus('s1', 's2', 'up')
    net.configLinkStatus('s2', 's3', 'up')
    net.stop()
    agent_proc.terminate()
    agent_proc.wait()

    # Verify both faults were detected
    with open(agent_log_file, "r") as f:
        log_content = f.read()
        
    print(log_content)
    
    fault_s1_s2 = "Anomaly detected on s1-s2" in log_content
    fault_s2_s3 = "Anomaly detected on s2-s3" in log_content
    
    assert fault_s1_s2, "First fault (s1-s2) was not detected"
    assert fault_s2_s3, "Second fault (s2-s3) was not detected - likely suppressed by global cooldown!"
    
if __name__ == "__main__":
    test_concurrent_faults()
