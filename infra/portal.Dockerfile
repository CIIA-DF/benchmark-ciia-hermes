FROM node:22-bookworm-slim AS build
WORKDIR /app/portal
COPY portal/package.json portal/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY portal ./
COPY docs /app/docs
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
USER node
EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
