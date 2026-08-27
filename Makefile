.PHONY: build up down test test-monitoring test-detection clean logs

build:
	docker compose build

up:
	docker compose up

down:
	docker compose down

test:
	docker compose run --rm mininet-controller --test pingall

test-monitoring:
	docker compose run --rm monitoring-agent python -m pytest tests/test_monitoring.py -v

test-detection:
	docker compose run --rm monitoring-agent python -m pytest tests/test_detection.py -v

logs:
	docker compose logs -f

clean:
	docker compose down -v --rmi local
