VENV=venv/bin
# nunca ~/.local: a suíte prova o que a venv + dpkg fornecem, igual à unidade systemd
export PYTHONNOUSERSITE=1
URL_PUBLICA=$(shell grep ^PLAT_URL_PUBLICA .env 2>/dev/null | cut -d= -f2)

.PHONY: check check-rapido lint sem-marcador teste e2e medidas migrar openapi vendor

check: lint sem-marcador teste e2e          ## suíte inteira (portão P3)

check-rapido: lint sem-marcador teste       ## o que o driver roda

lint:
	$(VENV)/ruff check app tests

sem-marcador:                               ## mesma expressão do laco/driver.sh (tests/marcadores.regex); inclui os .md da raiz e docs/
	! grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git --exclude-dir=venv -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md

teste:
	$(VENV)/pytest -m "not lento"

e2e:
	$(VENV)/pytest -m lento --base-url $(URL_PUBLICA)

medidas:                                    ## suíte inteira gravando tests/medidas/<item>.json (ADR 0001 seção 10)
	PLAT_GRAVAR_MEDIDAS=1 $(VENV)/pytest --base-url $(URL_PUBLICA)

vendor:                                     ## confere sha256 de web/vendor contra VERSOES.txt
	cd web/vendor && grep -v '^\#' VERSOES.txt | awk '{print $$3"  "$$1}' | sha256sum -c

migrar:
	sudo bash db/migrar.sh

openapi:
	$(VENV)/python -c "import json; from app.main import app; json.dump(app.openapi(), open('docs/openapi.json','w'), ensure_ascii=False, indent=1)"
