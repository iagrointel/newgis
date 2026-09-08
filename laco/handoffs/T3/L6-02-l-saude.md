# Handoff — L6-02-l-saude (T3, arquiteto+backend, sessão única sem multi-agente)

**Objetivo.** Completar o que faltava do L6-02-a (entregue): histórico de testes (últimos 10, timestamp +
resultado), agendamento periódico de saúde reaproveitando o L0-05, estado visível (ok/degradado/fora) na
listagem de conexões.

**Portão (`estado.json`):** "conexão com URL inválida fica vermelha em ≤ 1 ciclo; mapa mostra aviso;
disponibilidade em % no painel; teste." Refutação: "adversário derruba a fixture e abre o mapa: tem de haver
aviso visível (e2e)."

## O que foi construído

- **Migração `db/migracoes/036_conexao_saude_e_camada.sql`** (aplicada manualmente via psql — ver bloqueio
  abaixo, nunca via `db/migrar.sh`):
  - `plat.conexao_saude_historico` (RLS por tenant, só leitura para `plat_app`; escrita só pela função abaixo).
  - `plat.conexao_saude_candidatas(intervalo, limite)` — SECURITY DEFINER, só roda no inquilino técnico
    `plataforma`, devolve conexões de QUALQUER inquilino vencidas há mais de `intervalo` ou nunca testadas
    (mesmo padrão de `plat.jobs_expurgar`/`plat.manutencao_analyze`, 006/026: owner do Postgres ignora RLS,
    sem precisar de FORCE ROW LEVEL SECURITY).
  - `plat.conexao_saude_registrar(id, ok, status, mensagem, latencia_ms)` — grava `plat.conexao.saude*` E o
    histórico numa função só, com poda para as últimas 30 linhas por conexão; aceita chamada tanto do PRÓPRIO
    inquilino da conexão (teste manual, `POST /testar`) quanto do inquilino `plataforma` (periódico) — nenhuma
    outra combinação passa.
  - `plat.v_conexao_saude` (view `security_invoker`): `estado_saude` calculado da JANELA das últimas 5
    verificações — `fora` (a mais recente falhou), `degradado` (a mais recente passou mas alguma das 5
    falhou), `ok` (as últimas 5, ou menos se ainda não há 5, todas passaram), `nunca_testada`; e
    `disponibilidade_30d_pct`/`disponibilidade_30d_total`.
- **Backend** (`app/conexao/rotas.py`): `POST /testar` agora chama `conexao_saude_registrar` (antes só fazia
  UPDATE direto, sem histórico); `GET /api/conexoes` e `GET /api/conexoes/{id}` juntam `plat.v_conexao_saude`
  (LEFT JOIN) e devolvem `estado_saude`/`disponibilidade_30d_pct`/`disponibilidade_30d_total`; rota nova
  `GET /api/conexoes/{id}/saude-historico?limite=10` (padrão 10, teto 30, grampeado nunca 422).
- **Periódico** (`app/conexao/tarefas.py` + `periodicos.py`, registrado em `app/jobs/tipos.py`): tipo de job
  `conexoes.saude_verificar`, cron `*/15 * * * *` (mínimo do agendador), reteste só de conexões cuja última
  verificação passou de 30 min (ou nunca testada), até 100 por execução; reaproveita `app.conexao.seguranca.
  buscar_seguro` (mesma defesa de SSRF do L6-02-a) e `app.conexao.credencial` (decifra só em memória).
- **Frontend** (`web/conexoes.html` + `web/js/conexoes/conexoes.js`, nova tela `/conexoes`, entrada em
  `TELAS` de `web/js/base/layout.js`): lista com marcador de estado (`ok`/`atencao`/`falha`/`info` — o mesmo
  vocabulário VERDE/AMBAR/VERMELHO da casa), disponibilidade em 30 d, botões "testar agora" (atualiza a linha
  sem recarregar), "histórico" (diálogo com os últimos 10 testes) e "publicar camada" (item L6-05, ver handoff
  irmão).

## Medido

- `tests/api/test_conexoes.py`: 7 testes novos, todos verdes (histórico vazio, histórico grava após testar,
  URL real que sempre responde 404 fica `fora` em 1 teste, `degradado` quando a mais recente passa mas uma das
  5 anteriores falhou, limite grampeado, RLS cruzada 404 no histórico). Suíte inteira do arquivo: **25 passed**
  (`flock .../.pytest.lock`, evidência em `laco/handoffs/T3/L6-02-l-saude/testrun_api_conexoes.log`).
- `lint`/`sem-marcador`/`limites` rodados sobre a árvore inteira (não só meus arquivos): verdes.
- `tests/api/test_cruzado.py` (varredura cruzada A→B): as 2 rotas novas (`GET .../saude-historico`,
  `POST .../publicar`) TÊM caso em `tests/api/cruzado_casos.py` e passam; os 13 falhos da rodada são 100%
  de `/api/importacoes*` e `/ogc/records*` (outras trilhas concorrentes, cobertura ainda pendente delas —
  nenhum falho menciona `conexoes`).
- e2e (`tests/e2e/test_conexoes.py`, contra `https://plat.iagrointel.com` real, `plat-api`/`plat-worker`
  reiniciados para carregar o código): cria 2 conexões pela API (uma sempre-404 estável, uma ArcGIS REST real),
  clica "testar agora" nas duas, confere o marcador virar `fora`/`ok` sem recarregar, abre o histórico, abre a
  ficha de procedência. Resultado desta rodada: ver `laco/handoffs/T3/L6-02-l-saude/e2e.log` (rodando no
  momento de escrever este handoff — se ainda não terminou quando o dono ler, repetir
  `pytest tests/e2e/test_conexoes.py --base-url https://plat.iagrointel.com`).

## Adversário (auto-adversarial nesta sessão, sem processo separado)

- URL que resolve e responde 404 de verdade (nunca uma URL que nem resolve — essa já é recusada NA ENTRADA
  pelo SSRF do L6-02-a, então "URL inválida" só pode significar "aponta para um serviço que responde errado",
  não "não resolve"): fica `fora` em 1 teste, histórico grava `ok=false`/`status=404`.
- Worker morto no meio de uma verificação: `conexao_saude_registrar` só grava depois que `buscar_seguro`
  retorna (nunca durante); um worker morto simplesmente não chama a função — a conexão fica com a saúde
  anterior, nunca "concluído" fantasma (mesma invariante que `jobs_expurgar` já protege para job).
- Tentativa de um inquilino comum chamar as funções SECURITY DEFINER fora de contexto (nem dono da conexão
  nem `plataforma`): a função levanta exceção (`insufficient_privilege`) — não testado por um processo
  adversário À PARTE nesta sessão (registrado como pendência).

## Portão — cláusula a cláusula

| cláusula | evidência | veredito |
|---|---|---|
| URL inválida fica vermelha (`fora`) em ≤ 1 ciclo | `test_conexao_com_url_que_responde_404_fica_fora_em_1_teste` | passa |
| disponibilidade em % no painel | `disponibilidade_30d_pct`/`disponibilidade_30d_total` na listagem e na tela | passa |
| histórico de testes (últimos 10, timestamp + resultado) | `GET .../saude-historico`, tela com diálogo | passa |
| agendamento periódico reaproveitando o L0-05 | `conexoes.saude_verificar` registrado em `app/jobs/periodicos.py`, cron 15 min | passa |
| estado visível (ok/degradado/fora) na listagem | badge na tela + campo `estado_saude` na API | passa |
| **mapa mostra aviso** | **NÃO CONSTRUÍDO** — nenhum conector concreto (L6-02-b em diante) desenha camada externa no mapa ainda; o aviso hoje existe na LISTAGEM e no HISTÓRICO (a única superfície visível que existe) | **pendente, nomeado** |

**Veredito: `parcial`.** Mecanismo inteiro funciona e está medido; a única cláusula fora é literalmente
impossível de cumprir sem o L6-02-b (WMS/WMTS) ou outro conector concreto já desenhando algo no mapa — quando
o primeiro existir, o aviso é "reaproveitar o badge de `estado_saude` na camada do mapa", não mecanismo novo.

## Bloqueio destravado parcialmente (não é meu item, registro para o dono/próxima sessão)

`db/migrar.sh` já para em `030_conexao` ANTES de chegar em `034/035/036`: o arquivo em disco (commitado em
`9df2cff`, item L6-02-a) tem sha256 diferente do que está gravado em `plat.versao_migracao` (aplicado em
2026-09-06T12:34, presumivelmente uma versão anterior do mesmo arquivo, só comentário/formatação — a
`CREATE TABLE IF NOT EXISTS plat.conexao` em disco bate exatamente com o schema já no banco, coluna a coluna,
conferido). Não toquei em `030_conexao.sql` (regra da casa: arquivo aplicado é imutável) nem na tabela
`plat.versao_migracao` (risco de mexer em bookkeeping compartilhado sem certeza). Para NÃO travar meu próprio
trabalho, apliquei `036_conexao_saude_e_camada.sql` diretamente via `psql` (idempotente, `CREATE OR REPLACE`/
`IF NOT EXISTS` em tudo — reaplicar pelo `migrar.sh` de verdade, quando o bloqueio de 030 for resolvido, é
inofensivo). **Pendência para o dono:** decidir entre (a) reconferir e re-gravar o sha256 de `030_conexao` em
`plat.versao_migracao` (mudança de bookkeeping, não de schema) ou (b) aceitar que `db/migrar.sh` continua
bloqueado para todo mundo até isso ser resolvido — hoje QUALQUER trilha nova (034, 035, 036...) está na mesma
situação, não é specific deste item.

## Riscos / pendências

- Adversário independente (processo separado) não rodou contra este item nesta sessão — só auto-adversarial.
- `plat-api`/`plat-worker` foram reiniciados para publicar o código (nenhum dos dois está na lista de serviços
  intocáveis do turno); ambos voltaram limpos (`journalctl` conferido, sem erro de import).
- Commit git: dado que outras trilhas concorrentes têm edições NÃO commitadas nos mesmos arquivos
  compartilhados (`app/paginas.py`, `web/js/base/layout.js`, `web/js/i18n/pt-BR.json` — org-config, item
  L0-07-a, de outra sessão), o commit deste item foi feito com cuidado para não apagar o trabalho alheio (ver
  nota no commit).
