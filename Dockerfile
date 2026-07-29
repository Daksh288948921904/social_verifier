# ---- stage 1: build the frontend ----
FROM node:22-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: backend runtime, serving the built frontend too ----
FROM python:3.13-slim

# ffmpeg/ffprobe for clip cutting + compilation; build-essential because
# webrtcvad compiles a small C extension at pip-install time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-build /src/frontend/dist /app/frontend_dist

ENV STATIC_DIR=/app/frontend_dist

# Render (and most PaaS platforms) inject the port to bind via $PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8787}"]
