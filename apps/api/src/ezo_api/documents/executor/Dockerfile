# Operator builds against an already built, reviewed API image ID. Never pulled here.
ARG API_IMAGE=ezo-api:ci
FROM ${API_IMAGE}
USER root
# Fixed OCR (Tesseract: osd + eng/uzb/uzb_cyrl/rus) and Office (LibreOffice) binaries
# exist ONLY in this executor image, never in the production API image. They run
# inside the verified per-document workload below (no network, read-only root,
# cgroup limits, UID 10001 without capabilities), never in the API or controller.
# Installed at operator build time; nothing is fetched or installed at run time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-osd tesseract-ocr-eng tesseract-ocr-rus \
        tesseract-ocr-uzb tesseract-ocr-uzb-cyrl \
        libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
        libseccomp2 \
    && rm -rf /var/lib/apt/lists/* /root/.cache
COPY --chmod=0555 src/ezo_api/documents/executor /app/src/ezo_api/documents/executor
HEALTHCHECK NONE
# Root watchdog cannot be signalled by the unprivileged parser. PID namespace
# teardown kills detached descendants when timeout/tini exits, even if controller dies.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/bin/timeout", "--foreground", "--signal=KILL", "--kill-after=2", "25s", "/usr/bin/setpriv", "--reuid=10001", "--regid=10001", "--clear-groups", "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs", "/opt/venv/bin/python", "-m", "ezo_api.documents.executor.child"]
CMD []
