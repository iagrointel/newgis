VENV=venv/bin
# nunca ~/.local: a suíte prova o que a venv + dpkg fornecem, igual à unidade systemd
export PYTHONNOUSERSITE=1
URL_PUBLICA=$(shell grep ^PLAT_URL_PUBLICA .env 2>/dev/null | cut -d= -f2)
# PLAT_SECRET, PLAT_DSN_WORKER, PLAT_DSN, PLAT_GARAGE_ADMIN_TOKEN e PLAT_SECRET_ANTERIOR não vão mais no
# .env (item L7-19: LoadCredential do systemd, /etc/plat/segredos, dono root, 0600); fora do systemd só
# root lê, por isso o `sudo cat` — mesmo privilégio que install.sh e `make migrar` já exigem, nunca em
# argumento de linha de comando visível em `ps` (só o valor lido entra no ambiente do pytest/uvicorn
# filho, como já era com o .env). Só exporta quando o credential existe e não é vazio: numa máquina que
# ainda não rodou a migração (arquivo ausente, `sudo cat` devolve vazio) isso NÃO pisa no que ainda
# estiver no `.env`; PLAT_SECRET_ANTERIOR/PLAT_GARAGE_ADMIN_TOKEN ficam de fora quando vazios de propósito
# (arquivo vazio é o estado normal fora de uma rotação/sem admin_token — settings.py trata como ausente).
SEGREDOS=PLAT_SECRET=$$(sudo cat /etc/plat/segredos/PLAT_SECRET 2>/dev/null); \
	PLAT_SECRET_ANTERIOR=$$(sudo cat /etc/plat/segredos/PLAT_SECRET_ANTERIOR 2>/dev/null); \
	PLAT_DSN_WORKER=$$(sudo cat /etc/plat/segredos/PLAT_DSN_WORKER 2>/dev/null); \
	PLAT_DSN=$$(sudo cat /etc/plat/segredos/PLAT_DSN 2>/dev/null); \
	PLAT_GARAGE_ADMIN_TOKEN=$$(sudo cat /etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN 2>/dev/null); \
	[ -n "$$PLAT_SECRET" ] && export PLAT_SECRET; \
	[ -n "$$PLAT_SECRET_ANTERIOR" ] && export PLAT_SECRET_ANTERIOR; \
	[ -n "$$PLAT_DSN_WORKER" ] && export PLAT_DSN_WORKER; \
	[ -n "$$PLAT_DSN" ] && export PLAT_DSN; \
	[ -n "$$PLAT_GARAGE_ADMIN_TOKEN" ] && export PLAT_GARAGE_ADMIN_TOKEN;

.PHONY: check check-rapido lint sem-marcador sem-agpl teste e2e medidas migrar openapi vendor limites seguranca-deps homolog

check: lint sem-marcador sem-agpl limites teste e2e  ## suíte inteira (portão P3)

check-rapido: lint sem-marcador sem-agpl limites teste  ## o que o driver roda

lint:
	$(VENV)/ruff check app tests docs/gerar_limites.py

limites:                                    ## docs/LIMITES.md == app/limites.py (item L0-12); falha se divergir
	$(VENV)/python docs/gerar_limites.py --check

privilegios:                                 ## docs/PRIVILEGIOS.md == plat.privilegio no banco (item L0-07-b); GERA (não confere) — make check confere via tests/api/test_privilegios_doc.py
	$(VENV)/python docs/gerar_privilegios.py

sem-marcador:                               ## mesma expressão do laco/driver.sh (tests/marcadores.regex); inclui os .md da raiz e docs/
# 07/09: a guarda estava reprovando A SI MESMA e travou a fila de junção a noite inteira --
# batia no dump gerado db/estrutura (variável de terceiro chamada `placeholder` numa função de
# busca textual) e nos documentos que DESCREVEM a regra (SISTEMA.md, CONTRIBUIR.md, e comentários
# que citam a palavra ao explicar por que ela é proibida). Marcador de verdade é código morto,
# não prosa sobre código morto. Por isso: dump gerado fora, e linha que cite a palavra dentro de
# comentário explicativo sai por `marcadores.excecoes` (lista curta, com motivo em cada entrada).
	! grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git \
	    --exclude-dir=venv --exclude-dir=estrutura \
	    -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md \
	  | grep -vE -f tests/marcadores.excecoes

sem-agpl:                                   ## item L2-09-c: nenhum arquivo com licença AGPL no repositório
# A spec veta AGPL na pilha (DOC.md 22: o visualizador de BIM do SIG de teste interno é AGPL e por isso NÃO
# entrou; o lugar dele foi ocupado por three.js e deck.gl, os dois MIT, mais OGC 3D Tiles, que é padrão
# aberto). Esta guarda varre CÓDIGO e MANIFESTO de dependência — é onde um texto de licença de fato cai — e
# ignora linha de comentário, porque licença nunca é declarada dentro de comentário e porque o próprio
# arquivo que EXPLICA a regra cita a sigla. Documento em prosa (docs/, *.md) fica fora de propósito: ali a
# sigla aparece explicando a decisão, e reprovar por isso seria a guarda batendo em si mesma (o mesmo
# incidente que a `sem-marcador` já teve em 07/09).
	! grep -rnI --exclude-dir=.git --exclude-dir=venv --exclude-dir=node_modules --exclude-dir=estrutura \
	    -E '(^|[^A-Za-z-])(AGPL|Affero General Public License)' \
	    app web db deploy scripts install.sh requirements.txt package-lock.json \
	  | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#'

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
