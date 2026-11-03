SERVICES := api agent extractor gateway risk

up:            ## start the whole stack
	docker compose up --build
down:
	docker compose down
test:          ## run contracts + all service tests
	cd contracts && pytest -q
	@for s in $(SERVICES); do echo "== $$s =="; (cd services/$$s && pytest -q) || exit 1; done
test-%:        ## make test-gateway
	cd services/$* && pytest -q
lint:
	ruff check contracts services eval
eval:          ## ASR experiment: gateway off vs on (owner: M4 Ziad)
	python eval/run_asr.py
