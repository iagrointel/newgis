---
name: plataforma-enterprise
description: Um turno blindado do laço PLATAFORMA ENTERPRISE — construir, testar, refutar e entregar em produção a plataforma SIG própria (pilha aberta) que substitui o ArcGIS Enterprise, com organização de agentes por papel (gerente, pesquisador, arquiteto, especialista Esri, cartógrafo, redes de utilidades, raster, dados, backend, frontend, testador, adversário, cronista). Usar quando o laço acordar, quando o driver lançar um turno, ou quando pedirem para construir/entregar a plataforma.
---

# PLATAFORMA ENTERPRISE — um turno do laço

Estado vivo: `/home/dev/plataforma/laco/estado.json` (objetivo, produto, guardrails, papéis,
backlog com PORTÃO DE PRONTO e REFUTAÇÃO por item, ledger, decisões do dono, placar). **Toda
leitura-modificação-escrita deste arquivo (inclusive por outra sessão Claude no mesmo laço) tem de
rodar dentro de `flock /home/dev/plataforma/laco/.estado.lock <comando>`** — sem isso, duas sessões
escrevendo quase ao mesmo tempo perdem a escrita uma da outra silenciosamente (T3: uma decisão nova
gravada como D37 por outra sessão sumiu, sobrescrita por uma escrita minha que não sabia dela;
achado e corrigido só porque as duas sessões compararam o arquivo por mensagem depois).
Repositório do produto: `/home/dev/plataforma/enterprise/` (git). Handoffs entre papéis:
`laco/handoffs/T<turno>/`. Driver determinístico (cron 30 min): `laco/driver.sh` → `driver.log`,
`placeholders.txt`, `ultimo_check.txt`. Herda `/home/dev/CLAUDE.md` inteiro e a METODOLOGIA do
`rs-coop/tracado-lt` (ausência de dado nunca vira medição; número nunca digitado; portão congelado;
quem produz não aprova; erro nunca é sucesso).

## O alvo, em uma frase

Um produto em produção, 100 % pilha aberta, que um cliente de ArcGIS Enterprise usa no lugar
dele sem achar buraco: imagens (L1), plataforma de dado do cliente (L2), motor multicritério (L3),
rede de utilidades (L4), construtores arrasta-e-solta (L5), acervo e conectores (L6), operação (L7).
Sem limite de turnos, sem limite de tempo, sem placeholder. O dono não quer ser consultado no
meio; o que exige decisão dele vai para `decisoes_do_dono` e o laço segue por outro item.

## A organização (quem faz o quê)

O turno é dirigido pelo **GERENTE** (a sessão que roda esta skill). Os demais papéis são agentes
lançados com a ferramenta Agent (subagent_type `general-purpose`, contexto próprio), um prompt por
papel, sempre com: o item inteiro copiado do estado (hipótese, portão, refutação), o caminho do
repositório, os guardrails, os handoffs anteriores do turno que precisa ler e o caminho do handoff
que deve escrever. **Ninguém fala por contexto compartilhado; tudo por arquivo.**

| papel | entrega | arquivo |
|---|---|---|
| gerente | plano do turno, integração, julgamento do portão, ledger, commit | `00_plano.md`, `99_veredito.md` |
| pesquisador | fontes datadas com URL testada por HTTP; "o que muda no item" | `10_pesquisa.md` |
| arquiteto | ADR em `docs/adr/NNNN-*.md`, contrato de API, esquema, biblioteca escolhida por medição/doc | `20_arquitetura.md` |
| esri | o que o ArcGIS faz EXATAMENTE nessa capacidade (doc Esri, data); tabela de paridade feito/parcial/fora; expectativa do usuário Esri | `21_esri.md` |
| cartografo / redes / raster / dados | especialista do domínio do item: regras, armadilhas, o que medir | `22_<papel>.md` |
| **designer** | identidade visual do produto: tokens, tipografia, densidade, ícone, estado, movimento; toda tela nova nasce do sistema de `web/estilo/`, nunca de um painel genérico. Regra do dono 05/09: "sem vida, parece coisa de IA" — tela sem identidade é erro de build, como placeholder | `23_design.md` |
| backend / frontend | código + testes no repositório; handoff com comandos e saídas | `30_backend.md`, `31_frontend.md` |
| testador | testes independentes (pytest + e2e playwright), números medidos, capturas em `tests/e2e/capturas/` | `40_testes.md` |
| adversario | contexto próprio, NÃO lê os handoffs 30/31, só o item, o portão, o repositório e a URL; instrução: derrubar; escreve `refutacao.json` | `50_refutacao.md` + `refutacao.json` |
| cronista | MANUAL.md (seção da tela), CHANGELOG.md, ARQUITETURA.md, página interna do laço | `60_documentacao.md` |

Modelo de handoff (obrigatório): `Objetivo · O que fiz · Evidência (comando + saída literal) ·
Riscos · Pendências · Para o próximo papel`. Handoff sem evidência literal é inválido.

Paralelismo (regra do dono, 05/09: "não esperar passo a passo; o que não depende roda junto"):
os agentes de papel são subagentes em processo (não são sessões novas), por isso o limite de RAM
da casa (20 sessões derrubaram o Postgres) vale para PROCESSOS — `claude -p` do driver, jobs de
máquina, playwright — e não para o número de subagentes. Limites: **até 12 subagentes ao mesmo
tempo**, **1 job pesado de máquina por vez**, **1 reinstalação destrutiva por vez** (quem apaga
schema/role avisa por handoff e espera). ⚠️ **TETO CONJUNTO ATIVO desde 06/09 (combinado entre esta
sessão e a sessão wt/garage,stac,valida,amc): 4 agentes de cada lado, 8 no total**, medido com dados
reais — CPU só 1,1% ocupada (agentes gastam o tempo esperando inferência, não processando), mas RAM
disponível caiu a ~300 MB com swap 100% cheio; mais máquina não acelera nada, só RAM importa. Reveja
este teto com a outra sessão (via SendMessage) quando `free -h` mostrar folga real, não por conta
própria. Dentro de uma trilha, 10/20/21/22 rodam em paralelo; 30 e
31 depois deles (podem rodar juntos se o contrato de API já está no ADR); 40 depois de 30/31; 50
depois de 40; 60 junto com 50. Entre trilhas, tudo em paralelo.

## Trilhas paralelas (várias frentes por turno)

Um turno trabalha **N itens ao mesmo tempo, um por trilha**, N = quantos itens pendentes existem
sem dependência aberta e sem colisão de área (mesmos arquivos/tabelas/serviço). O gerente:
- escolhe as trilhas em `laco/handoffs/T<turno>/00_plano.md` (tabela: item · área tocada · papéis ·
  o que colide com quem) e cria `laco/handoffs/T<turno>/<item>/` para cada uma;
- lança as etapas de cada trilha assim que a etapa anterior DELA termina, sem esperar as outras;
- mantém `laco/handoffs/T<turno>/trilhas.json` = `{item: {etapa_atual, agentes_lançados, iniciado,
  terminado}}` atualizado a cada notificação (é o que sobrevive se a sessão morrer);
- colisão de área real (dois itens editando o mesmo arquivo) resolve-se por ORDEM: a trilha que
  chegou primeiro comita; a segunda rebase-a e roda `make check` de novo antes do adversário;
- o turno fecha quando TODAS as trilhas chegaram ao veredito (99_veredito.md por item); trilha
  que travou (agente morto, bloqueio externo) fecha como `pendente` com o bloqueio nomeado e não
  segura as outras;
- pesquisa e arquitetura dos PRÓXIMOS itens (10/20/21/22) podem rodar durante o turno atual como
  trilhas de preparação, para o turno seguinte começar já em 30.

## O turno (nunca pular etapa)

1. **LER** `estado.json`, os 3 últimos registros do ledger, `driver.log` (tail), `placeholders.txt`,
   `ultimo_check.txt`. Se `estado` != ATIVO, parar. Gravar `laco/.turno_ativo` = `{"inicio": ISO,
   "sessao": "<nome>"}`. Se houver item `tentando` de sessão morta com trabalho no disco (handoffs,
   commits), **colher antes de começar coisa nova**.
2. **ESCOLHER AS TRILHAS**: todos os itens pendentes sem dependência aberta, ordenados por
   prioridade (empate: o que destrava mais itens; depois o que dá função visível), até onde não
   haja colisão de área. Item `refutado` volta com hipótese nova, nunca com o mesmo caminho.
   Marcar cada um `tentando`, `tentando_desde`, `turno`, `tentativas += 1`. Bumpar `turno` do
   estado. Criar `laco/handoffs/T<turno>/` e um subdiretório por item.
3. **PLANEJAR** em `00_plano.md`: tabela das trilhas (item · área · papéis · colisões) e, por
   trilha, portão copiado literalmente; ordem dos papéis; o que cada um recebe e entrega; o que
   será medido; o que NÃO se faz neste turno. Item grande demais para um
   turno → dividir em sub-itens no backlog (ids `<id>-a`, `<id>-b`), o item-pai vira `parcial` com as
   partes como dependência.
4. **DESTRAVAR BLOQUEANTES PRIMEIRO**: dependência externa (extensão de banco, binário, biblioteca,
   porta, pg_hba, nginx) instala-se agora, com evidência. Instalação que precisa de apt/sudo é feita
   pelo gerente. Disco e RAM conferidos antes.
5. **PESQUISA + ARQUITETURA + ESPECIALISTAS** (paralelo, quando o item abre domínio novo ou o
   handoff anterior pediu). Item de continuação pode pular para 6 se o ADR já existe.
6. **CONSTRUIR** (backend/frontend): código no repositório, migração em `db/migracoes/NNN_*.sql`
   idempotente, testes ao lado do código, OpenAPI atualizado, unidade systemd `plat-*` e nginx quando
   houver serviço novo. **Sem placeholder**: botão que não faz nada, rota que devolve dado fixo,
   `TODO` em código entregue — tudo é erro de build. O que não couber no turno não aparece na tela.
7. **TESTAR** (testador): roda a suíte INTEIRA (`make check`), não só a do item; e2e playwright na
   URL interna real com captura; mede o que o portão pede (ms, contagens, taxas); escreve os números
   em `tests/medidas/<item>.json` (é daí que qualquer documento cita número).
8. **REFUTAR** (adversário): recebe só item + portão + repositório + URL, com a instrução da coluna
   `refutacao` do item e "o padrão é achar problema". Escreve `refutacao.json`
   `{"item","veredito": "PASSA|REFUTADO|PARCIAL","evidencia":[...],"o_que_nao_prova":[...]}`.
   O gerente não discute com o adversário: conserta e roda de novo, ou registra REFUTADO.
9. **JULGAR** o portão cláusula a cláusula em `<item>/99_veredito.md` (cláusula → evidência → passa/não).
   O portão não se move; se reprovar por motivo errado, conserta-se a leitura, não o limiar.
   Estado do item: `entregue` (todas as cláusulas + adversário PASSA) · `parcial` (mecanismo
   funciona, cláusula pendente nomeada) · `refutado` (motivo) · `pendente` (bloqueio nomeado, ou
   `decisoes_do_dono` novo). Paridade Esri do item vai para `docs/PARIDADE.md` (tabela viva).
10. **DOCUMENTAR** (cronista): MANUAL.md ganha a seção da tela com captura real; CHANGELOG.md;
    ARQUITETURA.md; `python3 laco/gera_painel.py` (placar + fronteira) e `python3 laco/gera_diario.py`
    (**DIARIO.md — o log corrido que o dono lê**: linha do tempo por commit, ledger, vereditos,
    números medidos, decisões abertas). Os dois são gerados, nunca escritos à mão.
11. **REGISTRAR** no ledger: `{turno, item, quando, papeis, construido, medicoes, adversario,
    portao, proximo_passo, custo_aproximado}`; atualizar `placar`. **COMMIT** no repositório
    (português, sem emoji, Co-Authored-By). Apagar `laco/.turno_ativo`.
12. **TERMINAIS**: todos os itens `entregue` e `L7-05-producao-final` passou → `estado=DELIVERED`
    e escrever `laco/ENTREGA.md` para o dono (o que é, onde está, como demonstrar, o que ficou
    fora, decisões abertas). 5 turnos seguidos sem cláusula nova passando → `estado=STALLED` com
    diagnóstico. Item que depende só de decisão do dono não trava o laço: pula-se para o próximo.
    Erro nunca é sucesso; sessão que morre no meio deixa o item para o driver devolver.
13. **PRÓXIMO TURNO**: se esta sessão está em `/loop`, agendar o próximo com `ScheduleWakeup`
    em 60-120 s (o trabalho é contínuo; o único freio é RAM/disco). Se não está, o driver lança o
    próximo turno em ≤ 30 min (autoturno) — nada a fazer.

## Portões congelados (valem para TODO item, além do portão próprio)

- **P1 FUNCIONA NO NAVEGADOR.** Toda função visível tem e2e playwright na URL interna com captura;
  0 erro de console.
- **P2 SEM PLACEHOLDER.** `driver.sh` varre o repositório; contagem > 0 em código entregue = reprova.
- **P3 SUÍTE INTEIRA VERDE.** `make check` (pytest + e2e + lint) passa completo, não só o item.
- **P4 PARIDADE DECLARADA E TESTADA.** Tabela feito/parcial/fora contra a capacidade Esri, escrita
  pelo papel `esri` e conferida pelo adversário; paridade com Pro/AGOL reais só quando o parceiro
  testar (registrar como pendente, nunca como feito).
- **P5 REPRODUTÍVEL.** Migrações + `install.sh` recriam do zero; nada manual fora de script.
- **P6 MULTI-INQUILINO E SEGURANÇA.** RLS em toda tabela com `tenant_id`; teste cruzado A→B falha
  em toda rota; token com escopo e log.
- **P7 DADO ABERTO, SEM NOME DE CLIENTE, SEM PII.** Demonstração só com dado aberto; nenhum nome de
  cliente/parceiro/piloto no produto, UI, docs ou dado de exemplo; nada identificável.
- **P8 ADVERSÁRIO INDEPENDENTE NÃO REFUTOU.**
- **P9 DOCUMENTADO.** MANUAL + OpenAPI + ARQUITETURA + CHANGELOG atualizados no mesmo turno.

## Recursos e limites desta máquina (medidos 05/09/2026)

12 vCPU · 23 GB RAM (≈ 3 GB livres em uso normal) · disco `/` e `/mnt/pgdata` a **98 %**
(13-17 GB livres). GPU box (`ssh gpu`): RTX 4000 20 GB, 62 GB RAM, disco 100 % (16 GB).
Postgres 16 + PostGIS 3.6 no `iagro_sat` (5432; 6432 é PgBouncer sem `public`). Instalados:
GDAL/ogr2ogr, playwright (chromium), node/npm, docker, tippecanoe em `~/tools`. **Faltam** (instalar
no item que precisar): pgRouting, pgstac/pypgstac, Martin, Garage já roda (`plataforma-garage`
:3900), TiTiler só na venv de `plataforma/pipeline`, k6, pgBackRest, pytest, ezdxf, rio-cogeo.
Portas reservadas 8150-8159. Serviços que NUNCA se tocam: sigcorp 8125, cbresig 8126, geoapp 8091,
plataforma-titiler 8131, cbre 8127-8134, fgrdoc 8135, corp360 8141.

## Regras que já custaram caro na casa (não reaprender)

- role nova sem linha no `pg_hba.conf` sobe e quebra na 1ª consulta; `sites-enabled/iagrosat-db`
  não é symlink (editar o de `sites-available` não dá erro e não faz nada).
- `psql -v ON_ERROR_STOP=1` sempre; SQL por stdin; `reltuples` mente, número sai de `COUNT(*)`.
- nunca `?v=` em import de módulo js (duas instâncias, app morre); cache resolve-se com `no-store`.
- pool psycopg2 devolve conexão morta depois de OOM: repetir só a preparação.
- `ST_MakeValid` + `ST_ReducePrecision` antes de operação booleana em massa; coluna geom tipada.
- **migração numerada na hora**: nunca reservar número no ADR; `ls db/migracoes | tail -1` e usar o próximo livre no momento de criar (T2: 009 colidiu entre identidade e catálogo).
- **pytest serializado**: qualquer `pytest`/`make check`/`make medidas` roda dentro de `flock /home/dev/plataforma/laco/.pytest.lock …`; dois em paralelo na mesma árvore invalidam sessões de demo e disputam o único slot do worker (T2: 5 falhas de interferência).
- pkill com padrão que não case com o próprio comando (`[u]vicorn --port 8150`), nunca `pkill -f uvicorn`.
- **commit sempre escopado por pathspec**: `git commit -- <arquivo específico>` (ou `git commit <arquivo>`), nunca `git commit -m` genérico depois de um `git add` pontual — o índice é compartilhado pela árvore inteira, e outro agente pode ter arquivo seu staged no mesmo instante; um commit sem pathspec varre TUDO que está staged, não só o que você acabou de adicionar (T3: commit de um fix de 1 arquivo varreu 11 arquivos em progresso de outro agente; corrigido sem perda com `git reset --soft HEAD~1` + `git restore --staged` nos arquivos alheios, mas quase juntou trabalho incompleto sob mensagem errada).
- **`CursorSchemaAmbiente` só reescreve `str`**: qualquer chamada que gere a consulta como `bytes` (ex. `psycopg2.extras.execute_values`, hoje só em `app/amc/unidades.py::gravar_feicoes`) passa direto sem reescrever `plat.`/`plat_trabalho.`, furando o isolamento de schema (homologação do L7-31 e qualquer base por trilha de `trilha_ambiente.sh`) e batendo na produção com `permission denied for schema plat` disfarçado de erro de inquilino. Em produção (schema padrão) é inofensivo — o bug só aparece fora do schema padrão. Ao escrever SQL em massa (bulk insert), prefira gerar a consulta como `str` (multi-VALUES parametrizado) em vez de `execute_values`/`mogrify` que devolvem bytes, ou confirme que passou pelo caminho de reescrita antes de usar fora do schema `plat` padrão.
- caminhos absolutos em setsid/nohup; log sempre; nada pesado em paralelo.
- `reltuples`/estimativa nunca vai para documento; `ab`/k6 com URL errada "passa" medindo 404.
- terrain-RGB nunca reamostrado; comprimento geodésico; CRS explícito em toda comparação.
- **extração de OSM/geodado nunca em modo padrão em memória** (osmium extract sem limite derrubou o Postgres por 14 min, T3 06/09 — mesma classe do incidente de 30/08): usar ferramenta com streaming/baixo consumo (`ogr2ogr` com `--config OGR_INTERLEAVED_READING YES`, ou `osmium extract` só com `--config` de memória explícita e `ulimit -v`), e checar `free -g` antes de qualquer extração de área.
- documento para fora segue a regra de escrita de 03/09 (jornalista de ciência; sem metáfora; número
  com universo, base e fonte; revisor separado).
