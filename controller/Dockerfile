# NetworkGuardian — Standalone Ryu Controller
#
# This Dockerfile builds the Ryu controller as a standalone service.
# In Phase 1, the controller runs inside the combined mininet-controller
# container (see topology/Dockerfile), but this image is available for
# later phases where the controller may run separately.

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir ryu eventlet

# Patch: restore ALREADY_HANDLED for Ryu compatibility
RUN python3 -c "\
import eventlet.wsgi, inspect, pathlib; \
src = pathlib.Path(inspect.getfile(eventlet.wsgi)); \
txt = src.read_text(); \
marker = 'ALREADY_HANDLED'; \
txt = (marker + \" = b''\n\" + txt) if marker not in txt else txt; \
src.write_text(txt); \
print('Patched', src)"

WORKDIR /app
COPY controller/ /app/controller/

EXPOSE 6653 6633 8080

CMD ["ryu-manager", "/app/controller/ryu_app.py", \
     "--ofp-tcp-listen-port", "6653", "--verbose"]
