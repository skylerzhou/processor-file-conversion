.PHONY: help build run clean test schemas

SERVICE_NAME ?= processor-file-conversion
SCHEMAS_DIR ?= schema

.DEFAULT: help

help:
	@echo "Make Help for $(SERVICE_NAME)"
	@echo ""
	@echo "make build   - build the Docker image (clones + builds mef2streamer)"
	@echo "make run     - build and run the processor via docker-compose on data/input"
	@echo "make test    - run the unit test suite"
	@echo "make schemas - regenerate $(SCHEMAS_DIR)/converters.json from the registry"
	@echo "make clean   - remove output files"

build:
	docker-compose build

run:
	docker-compose down --remove-orphans
	docker-compose build
	docker-compose up --exit-code-from processor

test:
	python3 -m pytest tests/ -q

schemas:
	mkdir -p $(SCHEMAS_DIR)
	python3 -m processor.schema --out $(SCHEMAS_DIR)

clean:
	rm -rf data/output/*
