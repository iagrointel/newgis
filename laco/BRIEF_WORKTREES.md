# Brief comum — trilhas paralelas em worktree (06/09/2026, sessão 2)

Contexto: laço PLATAFORMA ENTERPRISE (`/home/dev/plataforma/laco/estado.json`, 505 itens). Outra sessão
Claude segue com 6 agentes na árvore principal `/home/dev/plataforma/enterprise` (L0-04 ingest, L0-09
metadado, L0-02-e/f, L6-01/02, L5-05/L7-15). Para não colidir, cada trilha desta sessão trabalha num
GIT WORKTREE próprio, ramo `wt/<nome>`, e só volta a `master` por fast-forward feito pelo gerente.

## Regras (custaram caro — não negociáveis)
1. Trabalhe SÓ dentro do seu worktree. Nunca edite `/home/dev/plataforma/enterprise` nem `laco/estado.json`,
   `PAINEL.md`, `DIARIO.md` (o gerente atualiza). Nunca toque fora de `/home/dev/plataforma/`.
2. `git add <arquivo>` explícito, nunca `git add -A`. Commit em português, sem emoji, rodapé:
   `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Commits pequenos e frequentes no seu ramo.
3. NUNCA `systemctl restart/stop plat-api plat-worker`, nunca `pkill -f`. Para testar API com seu código:
   suba `venv/bin/uvicorn app.main:app --port <SUA PORTA>` a partir do worktree (porta atribuída no seu
   prompt), com `set -a; source .env; set +a` e os segredos de `/etc/plat/` se a app exigir (ver
   `app/settings.py` e `deploy/`), e passe `--base-url http://127.0.0.1:<porta>` ao pytest. Mate SÓ pelo PID.
4. Todo `pytest`/`make`: `flock /home/dev/plataforma/laco/.pytest.lock <comando>`. Prefira rodar só os seus
   arquivos de teste (`pytest tests/unit/test_x.py`), não a suíte inteira (leva 10+ min sob fila).
5. Banco compartilhado `iagro_sat`, schema `plat` (`sudo -u postgres psql -d iagro_sat`). Migração nova
   NUNCA usa número sequencial: o nome é `db/migracoes/YYYYMMDDTHHMM_<slug>.sql` com carimbo de tempo UTC
   (`date -u +%Y%m%dT%H%M`), ver a seção "Nome de migração" abaixo. Idempotente (IF NOT EXISTS). **NUNCA aplique migração de trilha no schema `plat` de produção.** A instrução antiga mandava rodar
   `sudo -u postgres PLAT_MIGRACOES=$PWD/db/migracoes bash db/migrar.sh`, que escreve em PRODUÇÃO — e foi
   por isso que, em 06/09, `plat` ganhou as tabelas `raster_item`, `tenant_bucket` e `amc_modelo` de três
   ramos que ainda NÃO tinham sido juntados, e o registro de versão ficou com 4 linhas órfãs depois das
   renumerações (apagadas, cópia em `laco/vivo/migracoes_orfas_apagadas_20260906.csv`). O certo é aplicar
   só na SUA base: `bash /home/dev/plataforma/laco/trilha_ambiente.sh <nome>`, que reescreve o schema. Copie o padrão de RLS/GRANT das
   migrações existentes (ex. `db/migracoes/02*.sql`), role `plat_app`, tenant por `current_setting`.
6. `pip install` no venv compartilhado só ADITIVO: rode `venv/bin/pip install --dry-run <pkg>` antes; se o
   resolvedor quiser mudar versão de fastapi/starlette/pydantic/psycopg2/uvicorn/rasterio, PARE e registre
   no handoff em vez de instalar. Disco a 98 %: nada acima de 500 MB novos; `df -h /` antes de baixar.
7. Sem placeholder: `TODO`/`FIXME`/mock/rota com dado fixo reprova (`make sem-marcador`; regex em
   `tests/marcadores.regex`). Sem nome de cliente/parceiro em código ou dado (usar "SIG de teste interno").
8. RAM: 2-3 GB livres, load 5-8. Nada de processamento em memória sem limite; `free -g` antes de pesado.
9. Idioma do código/testes/docs: português (nomes de função, mensagens de erro), como o resto do repo.
10. Documentação: ADR curto em `docs/adr/NNNN-*.md` quando decidir arquitetura; MANUAL.md/ARQUITETURA.md
    só se o item pedir; CHANGELOG.md ganha uma entrada por item (na seção "turno 3").

## Como fechar o item
- Siga o `portao_de_pronto` LITERAL do item (está no seu prompt). Cada cláusula vira teste ou medida
  gravada em `tests/medidas/<item>.json`. Não marque nada que não tenha passado.
- Ao terminar, escreva `/home/dev/plataforma/laco/handoffs/T3/<item-id>.md` com: o que foi construído
  (arquivos), cada cláusula do portão → prova (comando + resultado), o que ficou de fora e por quê,
  limitações honestas, comandos para o adversário reproduzir, lista dos commits do ramo.
- Depois relate ao gerente em ≤ 25 linhas: ramo, commits, cláusulas passadas/pendentes, riscos de merge
  (arquivos que a árvore principal também mexe: app/main.py, app/jobs/tipos.py, app/limites.py,
  app/catalogo/rotas_itens.py, MANUAL/ARQUITETURA/CHANGELOG — nesses, faça mudanças MÍNIMAS e localizadas).

## Nome de migração — carimbo de tempo, não número (regra fixa, ADR 0014)

O nome do arquivo de migração é CHAVE em `plat.versao_migracao`, não etiqueta. Renumerar um arquivo já
aplicado faz o aplicador tratá-lo como novo e reaplicá-lo em toda base onde a versão antiga rodou. Em
06/09 o mesmo arquivo foi renumerado três vezes (031 → 037 → 044 → 045) por trilhas que não se falavam.
A antiga reserva fixa de números (garage=034, stac=035, valida=036, amc=037) está **OBSOLETA** e foi
removida deste brief.

- **Migração nova**: `db/migracoes/YYYYMMDDTHHMM_<slug>.sql`, carimbo UTC de `date -u +%Y%m%dT%H%M`.
  Se outra trilha já criou uma no MESMO minuto, acrescente 3 hexadecimais logo após o minuto:
  `20260906T1742a3f_<slug>.sql` (`openssl rand -hex 2 | cut -c1-3`). Não precisa consultar ninguém,
  não precisa olhar o `ls` das outras árvores, não existe número a reservar.
- **Legado `001_*` a `048_*`**: FECHADO e IMUTÁVEL. Não renomeie, não crie arquivo novo com três
  dígitos (`tests/unit/test_migracoes_nome_e_dependencia.py` reprova). Todo o legado é aplicado ANTES
  de qualquer carimbo; dentro de cada família vale a ordem lexicográfica.
- **Dependência entre duas do mesmo minuto**: quem depende declara no cabeçalho, uma linha por
  dependência, `-- depende: 20260906T1730_camada.sql`. O teste reprova se o alvo não existir ou vier
  depois na ordem. O conserto é renomear a SUA migração (ainda não aplicada), nunca a outra.
- **Correção de migração já aplicada**: sempre em arquivo NOVO. Editar arquivo aplicado faz `migrar.sh`
  parar com código 3.
- Quem lista migrações em código usa `app.migracoes.listar` (Python) ou a função `listar_migracoes` de
  `db/migrar.sh` (bash). Nunca escreva o glob `[0-9][0-9][0-9]_*.sql` de novo em lugar nenhum.

## Adendo — retomada após queda por cota
A sessão anterior de agentes caiu por limite de cota da API, não por erro. O trabalho está em disco,
sem commit, no seu worktree. Comece por `git status --short` e `git diff --stat`, leia o que já existe,
e CONTINUE de onde parou — não recomece do zero, não apague o que está lá.

## Adendo 06/09 tarde — três regras nascidas de incidente na mesma hora
1. **UM agente por worktree.** Dois agentes na mesma árvore compartilham o ÍNDICE do git: um deles
   achou arquivos de outra trilha já preparados para commit e teve de commitar com índice privado
   (`GIT_INDEX_FILE` + `commit-tree` + `update-ref` com troca condicional) para não levar trabalho
   alheio. Se precisar mesmo dividir uma árvore, use essa receita e diga no repasse.
2. **Número de ADR colide igual ao de migração.** Duas trilhas escreveram `0018` no mesmo minuto.
   Vale a mesma regra do nome de migração: `docs/adr/YYYYMMDDTHHMM-<assunto>.md`, ou conferir
   `ls docs/adr | tail -1` NO INSTANTE de criar, sabendo que ramos não juntados não aparecem ali.
3. **Porta é recurso partilhado da máquina.** Um alocador que só evita as portas que ele mesmo
   distribuiu não basta: tem de pular toda porta que está ESCUTANDO agora (`ss -ltnH`). Aconteceu
   hoje: uma trilha subiu servidor na porta já prometida a outra, e o risco não é erro de conexão,
   é um agente MEDIR a aplicação do outro e o teste passar medindo a coisa errada. `vigia.sh` agora
   detecta porta com duas árvores diferentes e devolve DESCE.
4. **Orçamento de conexão.** `max_connections` do Postgres é 100 e o banco é compartilhado com
   dezenas de projetos da casa. Cada trilha agora nasce com `PLAT_POOL_MIN=1`/`PLAT_POOL_MAX=2`
   (era 8). Derrube o servidor da trilha pelo identificador de processo assim que o teste acabar;
   servidor ocioso segurando pool foi o que levou as conexões a 72 de 100 em 06/09.

## Defeito conhecido do gancho de commit (06/09, achado ao usá-lo)
O gancho `pre-commit` que barra arquivo fora da lista do item escolhe o arrendamento MAIS RECENTE em
`laco/vivo/leases/`, não o arrendamento de QUEM está commitando. Resultado: um commit legítimo do
gerente foi barrado contra a declaração de outro agente (`destrava`). Enquanto não for consertado,
o gancho vale como aviso confiável e a saída é `git commit --no-verify` com o motivo escrito na
mensagem. Conserto certo: o arrendamento é escolhido pelo diretório de trabalho do commit (a árvore),
não pelo horário do arquivo.

## Não editar script bash que está rodando (incidente da fila, 06/09)
O processador da fila de junção ficou 3 h em laço com 5.552 rodadas de "bisseção": ele havia sido
lançado com a versão do script em que as mensagens de progresso iam para stdout — o MESMO canal que a
função usa para DEVOLVER o ramo culpado — e o conserto entrou no arquivo ENQUANTO ele rodava. Bash lê
o script aos poucos; editar arquivo em execução mistura versões. Regra: conserto em `laco/*.sh` só
depois de confirmar `pgrep -af <script>` vazio, ou o processo em curso é encerrado pelo PID antes.

## `make teste`/`make openapi`/`make e2e` injetam os segredos de PRODUÇÃO (06/09 19:50)
Esses alvos do Makefile prependem `$(SEGREDOS)` = `sudo cat /etc/plat/segredos/*`, que SOBRESCREVE o
ambiente da sua trilha (PLAT_DSN_WORKER de produção não casa com o prefixo `plat_t<nome>_worker` e a
aplicação recusa). Em base de trilha, rode os comandos DIRETO: `venv/bin/pytest ...` e a geração do
openapi por `venv/bin/python -c ...`, depois de `set -a; source laco/var/trilha/<nome>.env; set +a`.
Só `make lint`, `make sem-marcador`, `make limites` e `make vendor` são secos e seguros em trilha.

## Modelo do dono: Kimi K3 (06/09 20:30)
A cota da conta Anthropic derrubou agentes em massa três vezes num dia. O dono forneceu chave própria
da Moonshot, e o laço passou a poder rodar agentes nela:

    bash /home/dev/plataforma/laco/lanca_kimi.sh <id-do-item>   # um agente no prompt já gerado

Medido em 06/09: `kimi-k3` responde pelo endpoint compatível com Anthropic
(`https://api.moonshot.ai/anthropic`), usa as ferramentas do Claude Code (leu `estado.json` e acertou
os números) e declara **janela de 1.048.576 tokens** (lida de `/v1/models`, gravada em
`CLAUDE_CODE_MAX_CONTEXT_TOKENS`; sem ela o Claude Code assume 200k e compacta cedo demais).
Modelos disponíveis: `kimi-k3` (1 Mi), `kimi-k2.7-code`, `kimi-k2.7-code-highspeed`, `kimi-k2.6` (256k).

A chave vive em `laco/var/kimi.env`, modo 600, **fora do git** — `laco/var/` está no `.gitignore` e o
repositório é público. Nunca commitar, nunca ecoar em log. O `driver.sh` (turno autônomo) e o
`supervisor.py` (função `ambiente_do_agente`) carregam esse arquivo sozinhos quando ele existe, e
removem `ANTHROPIC_API_KEY` do ambiente do filho — a chave da conta anularia a do dono.

O Claude Code avisa `unrecognized_model` para esses nomes; é só o catálogo local não os conhecer, e
não impede nada.
