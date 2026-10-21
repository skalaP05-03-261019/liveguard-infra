FROM node:20-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-noto-cjk ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /render
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
ENV NODE_PATH=/render/node_modules
CMD ["node", "/scripts/v1-browser-smoke.cjs"]
