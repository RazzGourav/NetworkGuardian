#!/bin/bash
# NetworkGuardian — Container entrypoint
#
# Starts OVS, the Ryu controller, and then Mininet with the custom topology.
# Supports multiple modes:
#   - interactive (default): drops into mininet CLI
#   - --test pingall:        runs custom pingall test
#   - --test fault:          runs fault injection pytest suite
#   - mn [args]:             runs mn directly with the given args
#   - pytest [args]:         runs pytest directly (after Mininet cleanup)
#
# Usage:
#   docker compose up                                                → interactive
#   docker compose run mininet-controller                            → interactive (tty)
#   docker compose run mininet-controller --test pingall             → custom pingall test
#   docker compose run mininet-controller --test fault               → fault injection test
#   docker compose run mininet-controller mn --custom ... --test ... → mn directly
#   docker compose run mininet-controller pytest tests/...           → pytest directly

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

if [ "$#" -eq 2 ] && [ "$1" = "--test" ] && [ "$2" = "pingall" ]; then
    # --test pingall: custom pingall test script
    echo "      Running custom pingall test..."
    cd /app/topology
    python3 test_pingall.py
    TEST_EXIT=$?
    echo "=== NetworkGuardian: shutting down ==="
    kill "$RYU_PID" 2>/dev/null || true
    service openvswitch-switch stop 2>/dev/null || true
    exit $TEST_EXIT

elif [ "$#" -eq 2 ] && [ "$1" = "--test" ] && [ "$2" = "fault" ]; then
    # --test fault: fault injection pytest suite
    set +e  # Disable set -e so we can catch errors
    echo "      Cleaning up old Mininet state..."
    mn -c >/dev/null 2>&1
    echo "      Running fault injection test..."
    cd /app
    python3 -m pytest tests/test_fault_injection.py -v -s
    TEST_EXIT=$?
    if [ $TEST_EXIT -ne 0 ]; then
        echo "Pytest failed. Ryu logs:"
        cat /app/logs/ryu.log
    fi
    service openvswitch-switch stop 2>/dev/null || true
    exit $TEST_EXIT

elif [ "$#" -gt 0 ] && [ "$1" = "mn" ]; then
    # 'mn' passed as the first argument — run mn directly with the
    # remaining args.  This supports AGENT.md Phase 1 verify command:
    #   docker compose run mininet-controller mn --custom topology/mininet_topo.py --test pingall
    shift  # remove the leading 'mn'
    echo "      Running: mn $@"
    mn --custom /app/topology/mininet_topo.py \
       --topo networkguardian \
       --controller remote,ip=127.0.0.1,port=6653 \
       --switch ovsk,protocols=OpenFlow13 \
       "$@"

elif [ "$#" -gt 0 ] && [ "$1" = "pytest" ]; then
    # 'pytest' passed as the first argument — run pytest directly.
    # This supports AGENT.md Phase 4 verify command:
    #   docker compose run mininet-controller pytest tests/test_fault_injection.py
    set +e
    echo "      Cleaning up old Mininet state..."
    mn -c >/dev/null 2>&1
    echo "      Running: $@"
    cd /app
    python3 -m "$@"
    TEST_EXIT=$?
    if [ $TEST_EXIT -ne 0 ]; then
        echo "Pytest failed. Ryu logs:"
        cat /app/logs/ryu.log
    fi
    service openvswitch-switch stop 2>/dev/null || true
    exit $TEST_EXIT

elif [ "$#" -gt 0 ]; then
    # Any other args — pass through to mn
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
