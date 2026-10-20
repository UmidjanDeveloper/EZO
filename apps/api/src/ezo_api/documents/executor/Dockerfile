# Operator builds against an already built, reviewed API image ID. Never pulled here.
ARG API_IMAGE=ezo-api:ci
FROM ${API_IMAGE}
USER root
COPY --chmod=0555 src/ezo_api/documents/executor /app/src/ezo_api/documents/executor
HEALTHCHECK NONE
# Root watchdog cannot be signalled by the unprivileged parser. PID namespace
# teardown kills detached descendants when timeout/tini exits, even if controller dies.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/bin/timeout", "--foreground", "--signal=KILL", "--kill-after=2", "25s", "/usr/bin/setpriv", "--reuid=10001", "--regid=10001", "--clear-groups", "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs", "/opt/venv/bin/python", "-m", "ezo_api.documents.executor.child"]
CMD []
