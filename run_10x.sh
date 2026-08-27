#!/bin/bash
for i in {1..10}; do
    echo "=== RUN $i ==="
    docker compose run --rm mininet-controller pytest tests/test_fault_injection.py -s
done
