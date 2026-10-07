# ── Build stage: Vue-less React + Vite + Tailwind v4 + shadcn ──
FROM node:22-alpine AS build

WORKDIR /app

# Install dependencies from the lockfile for reproducible builds
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Build the app (TypeScript check + Vite production bundle)
COPY frontend/ ./
RUN npm run build

# ── Serve stage: static assets behind nginx ──
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend-static/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
