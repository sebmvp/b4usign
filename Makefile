.PHONY: up down migrate api web test seed

up:
	docker compose up -d
	docker compose exec db pg_isready -U bys -d before_you_sign

down:
	docker compose stop

migrate:
	uv run --project backend alembic upgrade head

api:
	uv run --project backend uvicorn bys.api.app:app --host 127.0.0.1 --port 8000

web:
	npm --prefix apps/web run dev -- --host 127.0.0.1 --port 5173

test:
	uv run --project backend pytest -q

seed:
	uv run --project backend python -m bys.cli seed
