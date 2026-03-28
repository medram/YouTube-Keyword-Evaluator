.PHONY: help install dev prod cli clean

.DEFAULT_GOAL := help

# ─────────────────────────────────────────────────────────
#  YouTube Keyword Evaluator Makefile
# ─────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "YouTube Keyword Evaluator - Available Commands"
	@echo "────────────────────────────────────────────"
	@echo ""
	@echo "  make install      Install dependencies"
	@echo "  make dev          Run Streamlit app (development mode)"
	@echo "  make prod         Run Streamlit app (production mode)"
	@echo "  make cli          Run CLI script (requires --keyword and --api-key)"
	@echo "  make clean        Clean cache and compiled files"
	@echo ""

install:
	uv sync --no-dev
	@echo "✓ Dependencies installed (via uv)"

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

cli:
	@echo "📋 Running CLI script..."
	@echo "   Usage: make cli KEYWORD='your keyword' API_KEY='your_api_key'"
	@echo ""
	uv run python main.py --keyword="$(KEYWORD)" --api-key="$(API_KEY)"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .streamlit/config.toml 2>/dev/null || true
	@echo "✓ Cleaned cache and compiled files"