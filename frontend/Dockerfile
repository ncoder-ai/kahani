# Multi-stage build for Next.js frontend

# ============================================
# Dependencies stage
# ============================================
FROM node:20-alpine AS deps

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# ============================================
# Builder stage
# ============================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source files
COPY . .

# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Build application
RUN npm run build

# ============================================
# Production stage
# ============================================
FROM node:20-alpine AS production

# Set environment variables
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install dumb-init for proper signal handling and curl for health checks
RUN apk add --no-cache dumb-init curl

# Create non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Set working directory
WORKDIR /app

# Copy built application from builder stage
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/package*.json ./

# Create public directory if it doesn't exist (optional for Next.js)
RUN mkdir -p ./public

# Install only production dependencies
RUN npm ci --production --ignore-scripts

# Switch to non-root user
USER nextjs

# Set default port (can be overridden via environment variable)
ENV PORT=3000

# Health check (uses PORT env var)
HEALTHCHECK --interval=30s --timeout=30s --start-period=40s --retries=3 \
    CMD sh -c "curl -f http://localhost:${PORT}/ || exit 1"

# Expose port (respects PORT env var)
EXPOSE ${PORT}

ENV HOSTNAME="0.0.0.0"

# Use dumb-init to handle signals properly
ENTRYPOINT ["dumb-init", "--"]

# Start the application (npm start respects PORT env var from package.json)
CMD ["npm", "start"]