# ─────────────────────────────────────────────────────────────────────────────
#  YouTube Keyword Evaluator — Multi-service Dockerfile
#  Runs Streamlit (8501) and FastAPI + MCP (8000, MCP at /mcp)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifest first for layer caching
COPY pyproject.toml ./

# Install production dependencies only
RUN uv sync --no-dev --no-install-project

# Copy application code
COPY . .

# Expose service ports (FastAPI+MCP on 8000, Streamlit on 8501)
EXPOSE 8000 8501

# Start both servers in parallel
CMD uv run uvicorn api:app --host 0.0.0.0 --port 8000 & \
    uv run streamlit run app.py \
        --server.address=0.0.0.0 \
        --server.port=8501 \
        --client.showErrorDetails=false \
        --logger.level=warning \
        --server.runOnSave=false & \
    wait
