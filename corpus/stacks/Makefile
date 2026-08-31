# Everything below runs from this directory. No target reaches above this tree:
# the seed file, the database, and the port are all local.

API_DIR  := api
APP_DIR  := app
BIN      := $(API_DIR)/bin/stacksd
SEED     := testdata/catalog_seed.mrk
ADDR     := :8300

.PHONY: run build test tidy clean smoke ui ui-test dev

## run — start the API on :8300, seeding from the in-tree .mrk file on first boot
run:
	cd $(API_DIR) && STACKS_SEED_PATH=$(SEED) STACKS_ADDR=$(ADDR) go run ./cmd/stacksd

## build — compile a static binary; pure-Go SQLite means no C toolchain
build:
	cd $(API_DIR) && CGO_ENABLED=0 go build -o bin/stacksd ./cmd/stacksd

## test — Go test suite
test:
	cd $(API_DIR) && go test ./...

## tidy — refresh go.mod/go.sum, both of which are committed
tidy:
	cd $(API_DIR) && go mod tidy && gofmt -l .

## clean — drop build output and the developer database; never touches testdata
clean:
	rm -rf $(API_DIR)/bin $(API_DIR)/data $(APP_DIR)/dist

## smoke — hit the two probes and one search against a running API
smoke:
	curl -fsS http://localhost:8300/healthz && echo
	curl -fsS http://localhost:8300/readyz && echo
	curl -fsS 'http://localhost:8300/holdings/search?title=whale&limit=5' && echo

## ui — Vite dev server on :5300, proxying /api to the API on :8300
ui:
	cd $(APP_DIR) && npm run dev

## ui-test — SPA test suite
ui-test:
	cd $(APP_DIR) && npm test

## dev — API and SPA together
dev:
	npm run dev
