VENV=venv/bin
# nunca ~/.local: a suíte prova o que a venv + dpkg fornecem, igual à unidade systemd
export PYTHONNOUSERSITE=1
URL_PUBLICA=$(shell grep ^PLAT_URL_PUBLICA .env 2>/dev/null | cut -d= -f2)
# PLAT_SECRET e PLAT_DSN_WORKER não estão mais no .env (item L7-19: LoadCredential do systemd,
# /etc/plat/segredos, dono root, 0600); fora do systemd só root lê, por isso o `sudo cat` — mesmo
# privilégio que install.sh e `make migrar` já exigem, nunca em argumento de linha de comando visível
# em `ps` (só o valor lido entra no ambiente do pytest/uvicorn filho, como já era com o .env). Só
# exporta quando o credential existe: numa máquina que ainda não rodou a migração (arquivo ausente,
# `sudo cat` devolve vazio) isso NÃO pisa no PLAT_SECRET/PLAT_DSN_WORKER que ainda estiverem no `.env`.
SEGREDOS=PLAT_SECRET=$$(sudo cat /etc/plat/segredos/PLAT_SECRET 2>/dev/null); PLAT_DSN_WORKER=$$(sudo cat /etc/plat/segredos/PLAT_DSN_WORKER 2>/dev/null); [ -n "$$PLAT_SECRET" ] && export PLAT_SECRET; [ -n "$$PLAT_DSN_WORKER" ] && export PLAT_DSN_WORKER;

.PHONY: check check-rapido lint sem-marcador teste e2e medidas migrar openapi vendor limites seguranca-deps homolog

check: lint sem-marcador limites teste e2e  ## suíte inteira (portão P3)

check-rapido: lint sem-marcador limites teste  ## o que o driver roda

lint:
	$(VENV)/ruff check app tests docs/gerar_limites.py

limites:                                    ## docs/LIMITES.md == app/limites.py (item L0-12); falha se divergir
	$(VENV)/python docs/gerar_limites.py --check

sem-marcador:                               ## mesma expressão do laco/driver.sh (tests/marcadores.regex); inclui os .md da raiz e docs/
	! grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git --exclude-dir=venv -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md

teste:
	$(SEGREDOS) $(VENV)/pytest -m "not lento"

e2e:
	$(SEGREDOS) $(VENV)/pytest -m lento --base-url $(URL_PUBLICA)

medidas:                                    ## suíte inteira gravando tests/medidas/<item>.json (ADR 0001 seção 10)
	$(SEGREDOS) PLAT_GRAVAR_MEDIDAS=1 $(VENV)/pytest --base-url $(URL_PUBLICA)

vendor:                                     ## confere sha256 de web/vendor contra VERSOES.txt
	cd web/vendor && grep -v '^\#' VERSOES.txt | awk '{print $$3"  "$$1}' | sha256sum -c

seguranca-deps:                             ## item L7-03-f: pip-audit em requirements.txt; reprova com CVE crítico/alto sem exceção viva em docs/excecoes_cve.json (docs/SEGURANCA.md seção 7); OPCIONAL, ainda não bloqueia `check`
	$(VENV)/python scripts/varredura_dependencias.py --json var/seguranca/ultima_varredura.json

migrar:
	sudo bash db/migrar.sh

openapi:
	$(SEGREDOS) $(VENV)/python -c "import json; from app.main import app; json.dump(app.openapi(), open('docs/openapi.json','w'), ensure_ascii=False, indent=1)"

worker:                                     ## worker da fila em primeiro plano (desenvolvimento; em produção é a unidade plat-worker)
	$(SEGREDOS) $(VENV)/python -m app.jobs.worker

e2e-worker:                                 ## testes lentos da fila (reinício por systemctl, morte do pai, job de 5 min)
	$(SEGREDOS) $(VENV)/pytest -m lento tests/api/jobs

homolog:                                    ## item L7-31 (docs/HOMOLOGACAO.md): migra plat_homolog, sobe API+worker em :8154 e roda o e2e isolado; derruba tudo ao final
	bash scripts/homolog_e2e.sh
