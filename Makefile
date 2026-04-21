.PHONY: help install dev start cli api api-dev mcp mcp-sse typecheck clean

.DEFAULT_GOAL := help

# ─────────────────────────────────────────────────────────
#  YouTube Keyword Evaluator Makefile
# ─────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "YouTube Keyword Evaluator — Available Commands"
	@echo "────────────────────────────────────────────────────────"
	@echo ""
	@echo "  ── Setup ──────────────────────────────────────────────"
	@echo "  make install      Install all dependencies (via uv)"
	@echo ""
	@echo "  ── Streamlit UI ───────────────────────────────────────"
	@echo "  make dev          Run Streamlit app (auto-reload on)"
	@echo "  make start        Run Streamlit app (production mode)"
	@echo ""
	@echo "  ── REST API (FastAPI) ──────────────────────────────────"
	@echo "  make api          Run REST API  → http://localhost:8000"
	@echo "  make api-dev      Run REST API with auto-reload"
	@echo "                    Swagger UI → http://localhost:8000/docs"
	@echo ""
	@echo "  ── MCP Server (FastMCP) ────────────────────────────────"
	@echo "  make mcp          Run MCP server (stdio — for Claude Desktop)"
	@echo "  make mcp-sse      Run MCP server (SSE → http://localhost:8001)"
	@echo ""
	@echo "  ── CLI ─────────────────────────────────────────────────"
	@echo "  make cli KEYWORD='lofi study music' API_KEY='AIza...'"
	@echo ""
	@echo "  ── Misc ────────────────────────────────────────────────"
	@echo "  make clean        Remove __pycache__ and .pyc files"
	@echo ""
	@echo "  Tip: Copy .env.example → .env and set YOUTUBE_API_KEY"
	@echo "       so you don't have to pass it on every command."
	@echo ""

install:
	uv sync
	@echo "✓ Dependencies installed (via uv)"

# ── Streamlit ─────────────────────────────────────────────────────────────────

dev:
	@echo "🚀 Starting Streamlit app in DEVELOPMENT mode..."
	@echo "   → Server: http://localhost:8501"
	@echo "   → Auto-reload: ENABLED"
	@echo ""
	uv run streamlit run app.py --logger.level=debug

start:
	@echo "🚀 Starting Streamlit app in PRODUCTION mode..."
	@echo "   → Server: http://localhost:8501"
	@echo "   → Auto-reload: DISABLED"
	@echo ""
	uv run streamlit run app.py \
		--client.showErrorDetails=false \
		--client.showPyplotGlobalUse=false \
		--logger.level=warning \
		--server.runOnSave=false

# ── REST API ──────────────────────────────────────────────────────────────────

api:
	@echo "🌐 Starting REST API (production)..."
	@echo "   → API:     http://localhost:8000"
	@echo "   → Docs:    http://localhost:8000/docs"
	@echo "   → ReDoc:   http://localhost:8000/redoc"
	@echo "   → Health:  http://localhost:8000/health"
	@echo ""
	uv run uvicorn api:app \
		--host $${API_HOST:-0.0.0.0} \
		--port $${API_PORT:-8000} \
		--workers $${API_WORKERS:-1}

api-dev:
	@echo "🌐 Starting REST API (development, auto-reload)..."
	@echo "   → API:     http://localhost:8000"
	@echo "   → Docs:    http://localhost:8000/docs"
	@echo ""
	uv run uvicorn api:app \
		--host $${API_HOST:-0.0.0.0} \
		--port $${API_PORT:-8000} \
		--reload \
		--log-level debug

# ── MCP Server ────────────────────────────────────────────────────────────────

mcp:
	@echo "🤖 Starting MCP server (stdio mode)..."
	@echo "   → Add to Claude Desktop config (see README)"
	@echo ""
	uv run python mcp_server.py --transport stdio

mcp-sse:
	@echo "🤖 Starting MCP server (SSE mode)..."
	@echo "   → SSE endpoint: http://localhost:$${MCP_PORT:-8001}"
	@echo ""
	uv run python mcp_server.py \
		--transport sse \
		--host $${MCP_HOST:-0.0.0.0} \
		--port $${MCP_PORT:-8001}

# ── CLI ───────────────────────────────────────────────────────────────────────

cli:
	@echo "📋 Running CLI script..."
	@if [ -z "$(KEYWORD)" ]; then echo "❌  Usage: make cli KEYWORD='your keyword' API_KEY='AIza...'"; exit 1; fi
	uv run python main.py --keyword="$(KEYWORD)" --api-key="$(or $(API_KEY),$(YOUTUBE_API_KEY))"

# ── Misc ──────────────────────────────────────────────────────────────────────

typecheck:
	uv run mypy .

format:
	uv run ruff format .

lint:
	uv run ruff check --fix .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✓ Cleaned cache and compiled files"