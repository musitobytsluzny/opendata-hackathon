FROM node:24-bookworm-slim
WORKDIR /app
COPY web/package*.json ./
RUN npm ci
RUN sha256sum package.json package-lock.json > node_modules/.kartogram-deps.sha256
COPY web/ ./
EXPOSE 5173
CMD ["sh", "/app/dev-entrypoint.sh", "npm", "run", "dev", "--", "--host", "0.0.0.0"]
