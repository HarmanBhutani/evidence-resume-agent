VENV ?= .venv
# use the venv made by `make setup` when it exists, otherwise the system python3
PY ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)

.PHONY: eval setup run demo test test-fast test-live record samples sample-repo clean

eval:             ## quickest look, no Claude login needed: UI on recorded live outputs
	LLM_PROVIDER=replay $(PY) -m resume_agent serve

setup:            ## create venv + install deps
	$(PY) -m venv $(VENV) && $(VENV)/bin/pip install -r requirements.txt

sample-repo:      ## (re)build demo/sample_repo with deterministic git history
	$(PY) demo/build_sample_repo.py

run:              ## start the UI on http://127.0.0.1:8000 (provider from LLM_PROVIDER, default claude_cli)
	$(PY) -m resume_agent serve

demo:             ## run the 3 sample JDs end to end, print results, write out/<mode>/<jd>/
	$(PY) -m resume_agent demo

test:             ## everything (live test auto-skips if CLI missing/logged out; SKIP_LIVE=1 to force skip)
	$(PY) -m pytest -v -rs --tb=short 2>&1 | tee test-report.txt

test-fast:
	SKIP_LIVE=1 $(PY) -m pytest -q

record:           ## FRESH live run on the 3 sample JDs; saves responses to samples/recorded/ and outputs to samples/outputs/live
	rm -rf .cache samples/recorded/*.json samples/outputs/live
	LLM_PROVIDER=claude_cli $(PY) -m resume_agent demo --record --out samples/outputs

samples:          ## regenerate offline sample outputs (mock + mock hallucination attack)
	rm -rf samples/outputs/mock samples/outputs/mock_hallucination_attack
	LLM_PROVIDER=mock $(PY) -m resume_agent demo --no-cache --out samples/outputs
	LLM_PROVIDER=mock MOCK_HALLUCINATE=1 $(PY) -m resume_agent demo --no-cache --out samples/outputs/_attack
	mv samples/outputs/_attack/mock samples/outputs/mock_hallucination_attack && rm -rf samples/outputs/_attack

clean:
	rm -rf .cache out test-report.txt .pytest_cache
