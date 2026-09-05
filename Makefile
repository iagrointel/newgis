VENV=venv/bin
URL_PUBLICA=$(shell grep ^PLAT_URL_PUBLICA .env 2>/dev/null | cut -d= -f2)

.PHONY: check check-rapido lint sem-marcador teste e2e migrar openapi

check: lint sem-marcador teste e2e          ## suíte inteira (portão P3)

check-rapido: lint sem-marcador teste       ## o que o driver roda

lint:
	$(VENV)/ruff check app tests

sem-marcador:
	! grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git --exclude-dir=venv -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile

teste:
	$(VENV)/pytest -m "not lento"

e2e:
	$(VENV)/pytest -m lento --base-url $(URL_PUBLICA)

migrar:
	sudo bash db/migrar.sh

openapi:
	$(VENV)/python -c "import json; from app.main import app; json.dump(app.openapi(), open('docs/openapi.json','w'), ensure_ascii=False, indent=1)"
