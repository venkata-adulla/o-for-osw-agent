# Build the dashboard, then serve the static bundle from nginx.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
# Empty by default: lib/api.ts then talks to same-origin relative paths
# (/api/..., /health) instead of a baked-in absolute host. nginx below proxies
# those to the backend container, so the exact same built image works whether
# it's opened as http://localhost:3010 or through a public tunnel URL --
# there is no "localhost" baked into the bundle to go stale behind a tunnel.
# Only override this if the frontend is ever served from a different origin
# than its own backend.
ARG VITE_API_BASE=
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
