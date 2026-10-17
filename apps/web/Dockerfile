# EZO web image. Build context: the repository root (needs the pnpm workspace).
FROM node:22-alpine AS deps
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/ui/package.json packages/ui/
COPY packages/shared/package.json packages/shared/
RUN pnpm install --frozen-lockfile --filter @ezo/web...

FROM deps AS build
COPY packages ./packages
COPY apps/web ./apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @ezo/web build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S ezo && adduser -S ezo -G ezo
COPY --from=build --chown=ezo:ezo /repo/apps/web/.next/standalone ./
COPY --from=build --chown=ezo:ezo /repo/apps/web/.next/static ./apps/web/.next/static
USER ezo
EXPOSE 3000
# EZO_API_URL (runtime) tells the browser where the API is.
CMD ["node", "apps/web/server.js"]
