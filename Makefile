.PHONY: setup demo test up smoke down monitor
setup:
	uv sync --frozen --python 3.12
demo:
	uv run python -m scripts.demo
test:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q
	uv run python -m scripts.evaluate
up:
	docker compose up -d --build --wait
smoke:
	uv run python -m scripts.smoke
down:
	docker compose down
monitor:
	docker compose --profile monitoring up -d
