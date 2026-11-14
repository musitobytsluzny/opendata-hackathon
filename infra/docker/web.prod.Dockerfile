FROM node:24-bookworm-slim AS build

WORKDIR /app
COPY web/package*.json ./
RUN npm ci
COPY web/ ./

ARG VITE_API_URL=/api
ARG VITE_USE_MOCK_AUTH=false
ENV VITE_API_URL=${VITE_API_URL} VITE_USE_MOCK_AUTH=${VITE_USE_MOCK_AUTH}
RUN npm run build

FROM nginx:1.28-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY infra/nginx/prod.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
