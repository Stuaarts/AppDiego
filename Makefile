.PHONY: install dev lint format test migrate seed scrape docker-build docker-run

install:
	python -m pip install --upgrade pip
	python -m pip install -r requirements-dev.txt
	python -m pip install -e .

dev:
	streamlit run app.py --server.address=0.0.0.0 --server.port=$${PORT:-8501}

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	pytest -v

migrate:
	alembic upgrade head

seed:
	python -m price_monitor.cli seed-demo

scrape:
	python -m price_monitor.cli scrape --all --trigger manual_cli

docker-build:
	docker build -t price-monitor-dashboard .

docker-run:
	docker run --rm --env-file .env -p 8501:8501 price-monitor-dashboard
