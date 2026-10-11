FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=10000
EXPOSE 10000
CMD ["sh", "-c", "mkdir -p /data/workflow && mkdir -p /app/.eve && ln -sfn /data/workflow /app/.eve/.workflow-data && npm exec -- eve start --host 0.0.0.0"]
