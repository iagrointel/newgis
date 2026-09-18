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

.PHONY: check check-rapido lint tokens sem-marcador teste e2e medidas migrar openapi vendor limites seguranca-deps varredura-cve correcoes seguranca seguranca-gravar seguranca-zap ferramentas homolog pacote-rede conformidade conformidade-conferir videos videos-validar manual manual-validar

check: lint tokens sem-marcador limites seguranca teste e2e  ## suíte inteira (portão P3); seguranca = item HARD-01

check-rapido: lint tokens sem-marcador limites teste  ## o que o driver roda

lint:
	$(VENV)/ruff check app tests docs/gerar_limites.py docs/gerar_pacote_rede.py

tokens:                                     ## item L0-14 (identidade visual): 0 literal de cor em css/html fora de web/estilo/tokens.css, orçamento contado no js que não resolve var(), toda tela carrega tokens.css 1º, família única de ícones sem emoji e página viva /estilo gerada dos tokens; -p no:base_url tira a dependência de PLAT_DSN (só lê arquivo, não bate no banco)
	$(VENV)/pytest tests/unit/test_tokens_cor.py tests/unit/test_telas_carregam_tokens.py \
	  tests/unit/test_estilo_tokens.py tests/unit/test_tokens_visuais.py -p no:base_url

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

teste:
	$(SEGREDOS) $(VENV)/pytest -m "not lento"

e2e:
	$(SEGREDOS) $(VENV)/pytest -m lento --base-url $(URL_PUBLICA)

conformidade:                               ## item L2-04-j: roda as provas dos serviços Esri/OGC e regrava tests/esri/conformidade.json + a seção de docs/PARIDADE.md
	$(SEGREDOS) $(VENV)/python tests/esri/conformidade.py

conformidade-conferir:                      ## reprova se docs/PARIDADE.md divergir da matriz gerada (mesmo que make check confere por teste)
	$(VENV)/python tests/esri/conformidade.py --conferir

medidas:                                    ## suíte inteira gravando tests/medidas/<item>.json (ADR 0001 seção 10)
	$(SEGREDOS) PLAT_GRAVAR_MEDIDAS=1 $(VENV)/pytest --base-url $(URL_PUBLICA)

pacote-rede:                                ## docs/PACOTE_REDE.md == app/rede_utilidades/pacotes/*.json (item L4-01-a); GERA (o `make check` confere via tests/unit/test_rede_pacote.py)
	$(VENV)/python docs/gerar_pacote_rede.py

vendor:                                     ## confere sha256 de web/vendor contra VERSOES.txt
	cd web/vendor && grep -v '^\#' VERSOES.txt | awk '{print $$3"  "$$1}' | sha256sum -c

seguranca-deps:                             ## item L7-03-f: só o pip-audit (docs/SEGURANCA.md seção 7); `seguranca` abaixo já o inclui
	$(VENV)/python scripts/varredura_dependencias.py --json var/seguranca/pip_audit.json

varredura-cve:                              ## item L7-03-f (seção 7.6): pip-audit + npm audit, grava plat.varredura_cve/plat.vulnerabilidade; roda a mesma varredura do timer diário deploy/plat-varredura-cve.*
	$(SEGREDOS) $(VENV)/python scripts/varredura_cve.py

correcoes:                                  ## item L7-03-f: gera docs/CORRECOES.md a partir de plat.vulnerabilidade (`--check` confere sem escrever)
# FORA de `check`/`check-rapido` por decisão explícita (mesmo espírito da nota em `seguranca-deps` acima):
# a geração bate no banco vivo (plat.vulnerabilidade) para ficar com o estado mais recente das CVE abertas —
# no `check`, que roda em série com o resto da suíte numa máquina com Postgres compartilhado por cliente
# pagante, isso é uma consulta extra em toda passagem só para um documento que muda quando uma varredura
# nova roda, não a cada commit. `tests/unit/test_varredura_cve.py` já cobre a renderização (determinística,
# com dados fixos, sem tocar banco); rodar `make correcoes` continua sendo manual, ou de
# deploy/plat-varredura-cve.timer no dia em que grava uma varredura nova.
	$(SEGREDOS) $(VENV)/python docs/gerar_correcoes.py

# item HARD-01 (docs/SEGURANCA.md seção 9): bandit + pip-audit + npm audit + gitleaks (histórico) + trivy, política de
# bloqueio e exceções com prazo em docs/excecoes_seguranca.json; depois confere que a seção gerada do doc bate com a
# medida versionada. Seco: não toca banco nem produção. Rede: OSV.dev (com cache), registry.npmjs.org, e o download
# único das ferramentas binárias fixadas (cache do usuário). Sai 1 = achado bloqueante; 2 = ferramenta não rodou.
seguranca: ferramentas
	$(VENV)/python scripts/varredura_seguranca.py
	$(VENV)/python scripts/varredura_seguranca.py --check-doc

seguranca-gravar: ferramentas               ## roda tudo (com ZAP, exige ambiente de trilha) e regrava tests/medidas/HARD-01-seguranca.json + docs/SEGURANCA.md seção 9
	$(VENV)/python scripts/varredura_seguranca.py --com-zap --gravar

seguranca-zap: ferramentas                  ## só o baseline do ZAP: sobe uvicorn + nginx (deploy/nginx.conf) da trilha corrente numa porta 8800-8899 e derruba ao fim; recusa PLAT_SCHEMA=plat
	$(VENV)/python scripts/varredura_seguranca.py --ferramentas zap

ferramentas:                                ## instala (sha256 conferido) gitleaks/trivy/zap de deploy/ferramentas_binarias.txt em ~/.cache/plat/ferramentas
	bash scripts/ferramentas_seguranca.sh

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

videos:                                     ## item L7-04-d: >= 10 vídeos de tarefa gravados do e2e com narração pt-BR (piper) e legendas pt/en/es; precisa da bancada no ar (PLAT_URL_PUBLICA) e do piper (~/tools/piper)
	$(VENV)/python scripts/videos/gerar.py

videos-validar:                             ## confere o que está gerado (10+ vídeos, vídeo+áudio, duração <= 3 min, 3 legendas, seção do manual)
	$(VENV)/python scripts/videos/gerar.py --validar

# semáforo de testes do laço (fora do repositório; nas trilhas passe RODA_TESTE=<caminho absoluto>)
RODA_TESTE ?= $(abspath ../laco/roda_teste.sh)

manual:                                     ## item L7-04-a: valida o conjunto, regenera as capturas pelo e2e (semáforo), monta docs/manual (HTML+PDF) e web/dados/manual.json; captura de versão antiga REPROVA
	$(VENV)/python docs/gerar_manual.py --validar
	bash $(RODA_TESTE) $$($(VENV)/python docs/gerar_manual.py --arquivos-e2e) -m lento --base-url $(URL_PUBLICA) -q
	$(VENV)/python docs/gerar_manual.py $(if $(findstring 1,$(MANUAL_SEM_PDF)),--sem-pdf,)

manual-validar:                             ## confere o manual gerado (toda tela do e2e tem seção, toda seção tem captura da versão atual)
	$(VENV)/python docs/gerar_manual.py --validar
