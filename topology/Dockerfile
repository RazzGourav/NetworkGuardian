# NetworkGuardian — Mininet + Ryu Controller Container
#
# This container runs both Mininet and the Ryu controller in a single image
# because Mininet requires privileged access to the host networking stack
# (OVS kernel module, network namespaces, veth pairs). Running them together
# avoids cross-container OVS complications.
#
# Based on Ubuntu 22.04 with Mininet, Open vSwitch, and Ryu pre-installed.

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1

# ── System dependencies ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        mininet \
        openvswitch-switch \
        openvswitch-common \
        iproute2 \
        iputils-ping \
        net-tools \
        python3 \
        python3-pip \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies (Ryu controller) ─────────────────────────────
# Install Ryu + eventlet, then patch the Ryu wsgi module.
# Ryu 4.34 imports eventlet.wsgi.ALREADY_HANDLED which was removed in
# eventlet ≥ 0.31. We inject the constant back via a sitecustomize patch.
RUN pip3 install --no-cache-dir ryu eventlet

# Patch: restore ALREADY_HANDLED for Ryu compatibility
RUN python3 -c "\
import eventlet.wsgi, inspect, pathlib; \
src = pathlib.Path(inspect.getfile(eventlet.wsgi)); \
txt = src.read_text(); \
marker = 'ALREADY_HANDLED'; \
txt = (marker + \" = b''\n\" + txt) if marker not in txt else txt; \
src.write_text(txt); \
print('Patched', src)"

# ── Application code ────────────────────────────────────────────────
WORKDIR /app
COPY topology/  /app/topology/
COPY controller/ /app/controller/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 6653 6633 8080

ENTRYPOINT ["/app/entrypoint.sh"]
