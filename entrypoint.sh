#!/bin/bash
# NetworkGuardian — Container entrypoint
#
# Starts OVS, the Ryu controller, and then Mininet with the custom topology.
# Supports two modes:
#   - interactive (default): drops into mininet CLI
#   - test:  runs pingall via our custom test script
#
# Usage:
#   docker compose up                          → interactive
#   docker compose run mininet-controller      → interactive (tty)
#   docker compose run mininet-controller --test pingall   → custom pingall test

set -e

echo "=== NetworkGuardian: starting services ==="

# ── 1. Start Open vSwitch ────────────────────────────────────────────
echo "[1/3] Starting Open vSwitch..."
service openvswitch-switch start
# Wait for OVS to be ready
ovs-vsctl --timeout=10 show > /dev/null 2>&1
echo "      OVS is ready."

# ── 2. Start Ryu controller in background ────────────────────────────
echo "[2/3] Starting Ryu controller..."
ryu-manager /app/controller/ryu_app.py \
    --ofp-tcp-listen-port 6653 \
    --verbose \
    > /app/logs/ryu.log 2>&1 &
RYU_PID=$!

# Give the controller a moment to bind
sleep 3

if kill -0 "$RYU_PID" 2>/dev/null; then
    echo "      Ryu controller is running (PID $RYU_PID)."
else
    echo "ERROR: Ryu controller failed to start. Logs:"
    cat /app/logs/ryu.log
    exit 1
fi

# ── 3. Start Mininet / test ──────────────────────────────────────────────
echo "[3/3] Starting Mininet topology..."

# If arguments are passed and they match "--test pingall", use our custom test script
# If they match "--test fault", use the fault injection test script
# Otherwise, pass arguments through to mn
if [ "$#" -eq 2 ] && [ "$1" = "--test" ] && [ "$2" = "pingall" ]; then
    echo "      Running custom pingall test..."
    cd /app/topology
    python3 test_pingall.py
    TEST_EXIT=$?
    echo "=== NetworkGuardian: shutting down ==="
    kill "$RYU_PID" 2>/dev/null || true
    service openvswitch-switch stop 2>/dev/null || true
    exit $TEST_EXIT
elif [ "$#" -eq 2 ] && [ "$1" = "--test" ] && [ "$2" = "fault" ]; then
    set +e  # Disable set -e for the test so we can safely catch errors
    echo "      Cleaning up old Mininet state..."
    mn -c >/dev/null 2>&1
    echo "      Running fault injection test..."
    cd /app
    TEST_EXIT=0
    python3 -m pytest tests/test_fault_injection.py -v -s
    TEST_EXIT=$?
    if [ $TEST_EXIT -ne 0 ]; then
        echo "Pytest failed. Ryu logs:"
        cat /app/logs/ryu.log
    fi
    service openvswitch-switch stop 2>/dev/null || true
    exit $TEST_EXIT
elif [ "$#" -gt 0 ]; then
    echo "      Running with args: $@"
    mn --custom /app/topology/mininet_topo.py \
       --topo networkguardian \
       --controller remote,ip=127.0.0.1,port=6653 \
       --switch ovsk,protocols=OpenFlow13 \
       "$@"
else
    echo "      Launching interactive CLI..."
    mn --custom /app/topology/mininet_topo.py \
       --topo networkguardian \
       --controller remote,ip=127.0.0.1,port=6653 \
       --switch ovsk,protocols=OpenFlow13
fi

echo "=== NetworkGuardian: shutting down ==="
kill "$RYU_PID" 2>/dev/null || true
service openvswitch-switch stop 2>/dev/null || true
