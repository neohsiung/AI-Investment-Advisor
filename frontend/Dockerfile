# ─── Stage 1: Install Dependencies ───────────────────────────────────────────
FROM public.ecr.aws/docker/library/node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --network-timeout=1000000 --fetch-retries=5 --no-audit --no-fund

# ─── Stage 2: Build ───────────────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
# Accept BACKEND_URL as build arg so next.config.ts rewrites() can resolve the proxy destination at build time
ARG BACKEND_URL=http://mcp_server:8000
ENV BACKEND_URL=$BACKEND_URL
RUN npm run build

# ─── Stage 3: Runner (Lean Production Image) ──────────────────────────────────
FROM public.ecr.aws/docker/library/node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user for security (Matches mcp_server pattern)
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone output and static assets
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
