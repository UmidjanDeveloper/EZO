# syntax=docker/dockerfile:1
# EZO web image. Build context: the repository root (needs the pnpm workspace).
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS deps
ARG NODE_USE_ENV_PROXY
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/ui/package.json packages/ui/
COPY packages/shared/package.json packages/shared/
COPY packages/avatar/package.json packages/avatar/
COPY packages/perception-client/package.json packages/perception-client/
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    pnpm install --frozen-lockfile --filter @ezo/web...

FROM deps AS build
COPY packages ./packages
COPY apps/web ./apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @ezo/web build

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The server needs only node: npm, corepack and yarn (and their vulnerable bundled
# packages) are removed from the runtime image.
# Apply signed stable-repository security fixes (including zlib); retain the package
# database so scanners still see every installed package and remaining advisory.
RUN --mount=type=secret,id=system_ca \
    if [ -f /run/secrets/system_ca ]; then export SSL_CERT_FILE=/run/secrets/system_ca; fi; \
    apk upgrade --no-cache \
    && addgroup -S ezo && adduser -S ezo -G ezo \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
        /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
        /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-*
COPY --from=build --chown=ezo:ezo /repo/apps/web/.next/standalone ./
COPY --from=build --chown=ezo:ezo /repo/apps/web/.next/static ./apps/web/.next/static
USER ezo
EXPOSE 3000
# EZO_API_URL (runtime) tells the browser where the API is.
CMD ["node", "apps/web/server.js"]
