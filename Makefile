SERVICES := api agent extractor gateway risk

up:            ## start the whole stack
	docker compose up --build
down:
	docker compose down
test:          ## run contracts + all service tests
	cd contracts && pytest -q
	@for s in $(SERVICES); do echo "== $$s =="; (cd services/$$s && pytest -q) || exit 1; done
test-ai:       ## AI tests across services (offline, fake LLMs)
	python -m pytest -q tests
eval-ai:       ## AI evaluation with the real LLM from .env (costs a little)
	python eval/ai_eval/run_ai_eval.py
llm-check:     ## providers, fallback order and quota (free; ARGS=--call sends one tiny request per provider)
	python -m ai_core.llm_check $(ARGS)
jev-check:     ## is Jev Router usable with this key? (free; add ARGS=--call for one tiny test request)
	python -m ai_core.jev_check $(ARGS)
test-%:        ## make test-gateway
	cd services/$* && pytest -q
lint:
	ruff check contracts services eval
eval:          ## ASR experiment: gateway off vs on (owner: M4 Ziad)
	python eval/run_asr.py
