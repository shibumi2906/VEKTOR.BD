.PHONY: up stop check
up:
	docker compose up --build -d
stop:
	docker compose stop
check:
	docker compose run --rm --no-deps api uv run --frozen --group dev ruff check .
	docker compose run --rm --no-deps api uv run --frozen --group dev ruff format --check .
	docker compose run --rm --no-deps api uv run --frozen --group dev pytest -q
