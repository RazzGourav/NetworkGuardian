.PHONY: build up down test clean logs

build:
	docker compose build

up:
	docker compose up

down:
	docker compose down

test:
	docker compose run --rm mininet-controller --test pingall

logs:
	docker compose logs -f

clean:
	docker compose down -v --rmi local
