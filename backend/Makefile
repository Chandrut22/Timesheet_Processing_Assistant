# Backend commands for both services (needs make: Git Bash, WSL, or `choco install make`).
.PHONY: up down logs build check check-core check-auth validate audit migrate

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:  # make logs s=core-worker
	docker compose logs -f $(s)

check: check-auth check-core

validate: validate-auth validate-core

audit: audit-auth audit-core

check-auth:
	$(MAKE) -C auth-service check

check-core:
	$(MAKE) -C core-service check

validate-auth:
	$(MAKE) -C auth-service validate

validate-core:
	$(MAKE) -C core-service validate

audit-auth:
	$(MAKE) -C auth-service audit

audit-core:
	$(MAKE) -C core-service audit

migrate:
	$(MAKE) -C auth-service migrate
	$(MAKE) -C core-service migrate


