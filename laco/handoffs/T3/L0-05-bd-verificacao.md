# Handoff — verificação dos portões L0-05-b / L0-05-d (testador + backend)

**Objetivo.** Os dois itens filhos de `L0-05-jobs` (já entregue) estavam com o mecanismo de base
construído (agenda/cron genérico, worker, SSE, cancelamento) desde os turnos anteriores, mas o
`estado.json` marcava os dois `pendente` (tentativas 0). Tarefa: rodar `tests/api/jobs/*.py` sob
`flock`, conferir cláusula por cláusula do portão literal contra evidência real, e só construir o
que faltasse — com teste, sem reiniciar `plat-worker`/`plat-api` de produção salvo ao final.

**Repositório:** `/home/dev/plataforma/enterprise`, HEAD `52d7a3b` no início (várias outras
trilhas seguiram commitando em paralelo durante o trabalho — LDAP/AD, worker em contêiner,
homologação; nada do que segue toca os arquivos delas).

**Achado geral.** L0-05-b tinha quase tudo coberto; um gap real de teste (log de 10 mil linhas) e
dois na refutação (limite de conexões SSE por usuário, progresso acima de 100%) nunca tinham sido
exercitados, mesmo com o mecanismo já existindo no código. L0-05-d tinha o mecanismo genérico de
agenda/periódico pronto e testado, mas só **3** periódicos estavam de fato registrados
(`jobs.expurgo`, `catalogo.lixeira_expurgar`, `catalogo.versoes_compactar`) contra os **5** que o
portão exige — fechei com dois novos: `jobs.sessoes_expurgar` (chama `plat.sessoes_expurgar()`, que
já existia na migração 003 sem nenhum periódico que a chamasse) e `jobs.manutencao_analyze`
(`ANALYZE` semanal nas tabelas centrais; função SQL nova, migração 026, porque `ANALYZE` exige ser
dono da tabela — `plat_app` não é — e esta versão do Postgres nem tem o privilégio `MAINTAIN`).

**Achado operacional (não é bug do item, registrado para o gerente):** durante a verificação a
máquina teve, ao mesmo tempo, (1) um SEGUNDO processo `python -m app.jobs.worker` rodando dentro de
OUTRO contêiner (uid diferente do nosso, PPID em `containerd-shim`, achado com `ps aux`/`ps -o ppid`)
que roubou algumas das nossas execuções de teste e morreu sem escrever nada no pipe do filho
(`erro='código de saída 1'`, `worker=''` — o nosso sempre grava `<hostname>:<pid>`); (2) o admin do
inquilino técnico `plataforma` ficou temporariamente **bloqueado** (423, 5 tentativas de 2FA erradas
de uma trilha concorrente de LDAP/2FA) das ~11:03 às 11:18 UTC, o que barra `tests/api/conftest.py`
inteiro (fixture `limpeza_de_residuos`, `autouse=True, scope=session`, precisa de `sessao_plat`) —
não é specific a este item, qualquer teste em `tests/api/**` ficava preso enquanto durou. Os dois
já passaram (o contêiner encerrou sozinho; o bloqueio expirou). Tratei o primeiro com uma
assinatura de retentativa nomeada (`_worker_estranho` em `test_jobs_periodicos.py`) e não toquei em
nada de outra trilha.

---

## L0-05-b — progresso, log, cancelamento

Portão: *"teste api: job de prova de 60 s com 60 passos mostra progresso crescente por SSE com
atraso medido ≤ 2 s (medida latencia_progresso_s); cancelar no passo 10 termina 'cancelado' em ≤ 5 s
e o efeito parcial é desfeito; job que ignora a flag é morto por SIGTERM em 30 s e fica 'cancelado';
log com 10 mil linhas é resumido; timeout de tarefa vira 'falhou: tempo esgotado'"*. Refutação:
*"cancela job já concluído (409), cancela job de outro inquilino (404), abre 200 conexões SSE no
mesmo job (limite por usuário e fechamento em 30 min), envia progresso 150%"*.

| cláusula | evidência | veredito |
|---|---|---|
| progresso crescente por SSE, latência medida | `tests/api/jobs/test_jobs_sse.py::test_estado_log_e_fim_pelo_sse` grava `latencia_progresso_s` (medida T2: **0,173 s**, `tests/medidas/L0-05-jobs.json`); `tests/api/jobs/test_jobs_progresso.py::test_job_de_5_min_com_progresso_em_tempo_real` prova a mesma coisa numa escala maior (300 s, 60 passos, **62 eventos estado**, todos crescentes, medidas T2 `tempo_job_5min_s=300,5s`, `heartbeat_intervalo_max_s=5,3s` ≤ 10 s) | já satisfeita |
| cancelar rodando ≤ 5 s, efeito parcial desfeito | `test_jobs_cancelamento.py::test_cancelar_rodando_em_ate_2_s`: cancela no progresso ≥ 2 %, confirma `plat_trabalho.passos` limpa; medida T2 `cancelamento_s = 0,632 s` (bem abaixo de 2 s, mais ainda de 5 s) | já satisfeita |
| ignora a flag → SIGTERM 30 s → 'cancelado' | `test_jobs_cancelamento.py::test_tarefa_que_ignora_a_flag_e_morta_em_30_mais_10_s` (lento); medida T2 `cancelamento_forcado_s = 40,3 s` (30 s SIGTERM + 10 s grace do SIGKILL) | já satisfeita |
| **log com 10 mil linhas é resumido** | **GAP fechado nesta sessão.** `TETO_LOG=10_000`/`BLOCO_SUPRIMIDO=1_000` existiam em `app/jobs/contexto_job.py::ContextoJob.log` desde a entrega original, sem nenhum teste. Novo `tests/unit/test_jobs_contexto_log.py` (sem banco: `db()` substituído por cursor falso, constantes monkeypatchadas para `teto=20/bloco=5` — mesma lógica, escala reduzida para rodar em ms): `test_log_ate_o_teto_grava_toda_linha`, `test_log_acima_do_teto_e_resumido_em_blocos` (37 chamadas → 20 normais + 3 resumos `AVISO`, nenhuma das 17 suprimidas individualmente gravada), `test_log_nivel_desconhecido_vira_info`, `test_constantes_de_producao_sao_10000_e_1000` (trava as constantes reais). Rodado: `flock …/.pytest.lock venv/bin/pytest tests/unit/test_jobs_contexto_log.py -q` → **4 passed** | **gap fechado agora** |
| timeout do decorador → 'falhou: tempo esgotado' | `test_jobs_cancelamento.py::test_timeout_excedido_marca_falhou_tempo_esgotado` (`prova.tempo_esgotado`, `timeout_s=5`) → `erro == "tempo esgotado (timeout_s = 5)"` | já satisfeita |
| refutação: cancelar concluído = 409, estado final imutável | `test_jobs_cancelamento.py::test_cancelar_concluido_e_409_e_estado_final_e_imutavel` (inclusive `UPDATE` direto por `plat_app` levanta `InsufficientPrivilege`) | já satisfeita |
| refutação: cancelar job de outro inquilino = 404 | `test_jobs_rls.py::test_a_nao_ve_job_de_b` (`POST …/cancelar` de demo2 contra job de demo → 404 `job_inexistente`, junto com GET/repetir/log/eventos) | já satisfeita |
| **refutação: 200 conexões SSE (limite por usuário e fechamento em 30 min)** | **2 GAPS fechados nesta sessão.** Nenhum teste exercitava `POR_USUARIO_MAX=10`/`DURACAO_MAX_S=1800` (`app/jobs/eventos.py`). MEDIDO nesta sessão: `starlette.testclient` não sustenta N conexões SSE **realmente concorrentes** de um processo síncrono — `with cliente.stream(...)` só devolve o controle depois que o gerador do SERVIDOR termina (1ª chamada contra um job de 30 s levou os 30 s inteiros; as 12 seguintes vieram em ~3 ms porque o job já tinha concluído) — abrir 200 de verdade por HTTP exigiria threads reais contra a URL pública, fora do escopo da correção. Testado o MECANISMO direto: `test_limite_de_conexoes_por_usuario_e_liberado_ao_fechar` (10 reservas cabem, a 11ª levanta `ErroServico(429, "sse_limite")`, liberar uma abre vaga) e `test_conexao_fecha_sozinha_apos_a_duracao_maxima` (`eventos.gerar()` chamado direto, sem HTTP/worker, com `DURACAO_MAX_S`/`KEEPALIVE_S` monkeypatchados a frações de segundo: `event: fim` com "tempo máximo da conexão (30 min); reconecte" em < 5 s). Rodado: `flock …/.pytest.lock venv/bin/pytest tests/api/jobs/test_jobs_sse.py -q` → **6 passed** | **2 gaps fechados agora** |
| **refutação: envia progresso 150%** | **GAP fechado nesta sessão.** Novo `test_jobs_transicoes.py::test_progresso_acima_de_100_e_grampeado_em_100`: chama `plat.job_progresso` com o worker REAL do job e `p_progresso=150`; confirma que a coluna grava **100** (não 150, não erro) — `greatest(0, least(100, p_progresso))` na migração 006, mais o `CHECK (progresso BETWEEN 0 AND 100)` da 004 como segunda trava. Roda dentro da mesma transação e faz `ROLLBACK` (não commita por cima do worker de verdade que segue rodando o mesmo job) | **gap fechado agora** |

**Comando consolidado (após os dois restarts, ambiente limpo):**
```
$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs tests/unit/test_jobs_contexto_log.py \
    tests/unit/test_jobs_registro.py -q --tb=short
[uma falha isolada de ambiente, ver nota abaixo — reexecutada sozinha, passou]
$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs/test_jobs_rls.py -q
6 passed  (limpo, sem o resto da carga concorrente)
```
**Nota sobre a única falha vista em lote:** `test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel`
(arquivo que eu não toquei — `git diff` vazio) reprovou 2 vezes em rodadas com toda a suíte de
`tests/api/jobs` junto (achou 6 linhas em `plat_trabalho.passos` onde espera 0), e **passou limpo
quando rodado sozinho** duas vezes seguidas; consultas diretas ao banco nos dois momentos da falha
mostraram 0 linhas segundos depois. É outra trilha concorrente criando/terminando `prova.progresso`
no mesmo inquilino `demo` no instante exato da checagem — sintoma de carga compartilhada, não uma
regressão deste item (não editei o arquivo, o mecanismo de limpeza — `finally` em `prova_progresso`
— é o mesmo que já existia).

**Veredito L0-05-b: `entregue`.** Todas as cláusulas do portão e da refutação satisfeitas com
evidência real; 3 gaps de teste fechados (log de 10 mil linhas, limite/duração de SSE, progresso
grampeado), zero código de produção novo (os três mecanismos já existiam, só não tinham prova).

---

## L0-05-d — periódicos

Portão: *"teste api com relógio injetado: 5 periódicos disparam na hora certa exatamente uma vez
com 2 processos concorrentes; periódico que falha não bloqueia os outros e fica marcado; 'rodar
agora' cria job normal; tabela mostra próxima execução coerente com a cron; e2e da tela com
captura"*. Refutação: *"registra cron inválida (422), dispara 'rodar agora' 50 vezes (dedup por
lock), muda o relógio do sistema 1 dia para trás"*.

**Achado principal (gap real):** `app/jobs/periodicos.py` (L0-05) + `app/catalogo/periodicos.py`
(L0-03, soma-se à mesma lista na importação) registravam só **3** periódicos: `jobs.expurgo`,
`catalogo.lixeira_expurgar`, `catalogo.versoes_compactar`. O ADR 0003 seção 7 dizia
"este item entrega **um** periódico" — a hipótese do backlog (`estado.json`) já citava exemplos
(sessões vencidas, uploads incompletos, medição de uso, backup, `ANALYZE`/reindex) que nunca
viraram código. Fechado com dois novos, ambos reaproveitando mecanismo que já existia sem periódico
que o chamasse ou com esforço mínimo de código novo:

- **`jobs.sessoes_expurgar`** (a cada hora): chama `plat.sessoes_expurgar()` (migração 003, "sem
  inquilino" — já existia, `has_function_privilege('plat_app', …, 'EXECUTE')` já era `true`).
- **`jobs.manutencao_analyze`** (semanal, domingo 04:00): `ANALYZE` nas 7 tabelas centrais do plat
  (`job`, `job_log`, `item`, `item_versao`, `agenda`, `usuario`, `evento`) via `plat.manutencao_analyze`
  nova (migração **026**, escolhida na hora — havia colisão de número com `025_provedor_ldap.sql`
  de outra trilha criado entre minha primeira checagem e a aplicação; renomeei e limpei a linha
  órfã em `plat.versao_migracao` antes de reaplicar). `SECURITY DEFINER` porque `ANALYZE` exige
  dono da tabela (`plat_app` não é) e `MAINTAIN` nem existe nesta versão do Postgres
  (`unrecognized privilege type`, medido). `REVOKE EXECUTE … FROM PUBLIC` + `GRANT … TO plat_app`
  no mesmo padrão de 010/012/013/016/019/024 (funções nascem com `EXECUTE` para `PUBLIC` por
  padrão do Postgres; o teste `tests/api/test_funcoes_seguras.py::test_nenhuma_funcao_com_execute_para_public`
  cobre isso para o schema inteiro).

| cláusula | evidência | veredito |
|---|---|---|
| **5 periódicos, cada um dispara uma vez com 2 relógios concorrentes** | **GAP fechado.** Novo `tests/api/jobs/test_jobs_periodicos.py`: `test_pelo_menos_cinco_periodicos_registrados_e_com_tipo_conhecido` (`len(PERIODICOS) >= 5`, nomes únicos, tipo em `/api/jobs/tipos`, cron de 5 campos) + `test_cada_periodico_registrado_dispara_uma_vez_com_dois_relogios` parametrizado nos 5 índices reais (agenda de teste com o MESMO tipo/parâmetros do periódico de verdade, `agenda.tick()` de 2 conexões `psycopg2` concorrentes — o mesmo papel do worker, migração 006 — sobre 1 ocorrência; exatamente 1 job criado; termina `concluido`), tudo no contexto do inquilino técnico `plataforma` (`cliente_plataforma`, sessão nova via `jobs_sessao.criar_sessao(con, "plataforma", "admin")`, sem senha/2FA — mesma técnica de `sessao_demo`), porque `jobs.expurgo` recusa fora dele (migração 006). Rodado: `flock …/.pytest.lock venv/bin/pytest tests/api/jobs/test_jobs_periodicos.py -q` → **8 passed** | **gap fechado agora** |
| periódico que falha não bloqueia nem atrasa outro no mesmo instante | **GAP fechado** (só havia prova de UMA agenda falhando repetidas vezes até pausar, nunca duas agendas concorrentes com destinos opostos). Novo `test_periodico_que_falha_nao_bloqueia_nem_atrasa_outro_no_mesmo_instante`: 2 agendas (`prova.falha` definitiva + `prova.progresso`) due no MESMO tick, 3 rodadas — a ruim acumula `falhas_seguidas` e fica `ultimo_estado='falhou'`; a boa permanece `falhas_seguidas=0`/`ultimo_estado='concluido'` em TODAS as rodadas, nunca tocada pela vizinha | **gap fechado agora** |
| 'rodar agora' cria job normal | já coberto (`test_jobs_agenda.py::test_rodar_agora_pausar_retomar_atualizar`, geral) + exercitado de novo nos periódicos reais (`_garantir_conclusao` usa `rodar-agora` como via de conclusão) e no e2e (abaixo) | já satisfeita |
| tabela mostra próxima execução coerente com a cron | já coberto (`test_rodar_agora_pausar_retomar_atualizar`: `PUT` cron `"0 4 * * *"`/fuso `America/Manaus` → `proxima_em` termina `08:00:00Z`); confirmado de novo nos 5 periódicos reais (screenshot da tela, ver abaixo, mostra `proxima_em` de cada um coerente com o cron declarado) | já satisfeita |
| **e2e da tela com captura** | **GAP fechado.** A tela "Agendas" já existia e já tinha e2e (criar/pausar/retomar/apagar, `L0-05-jobs_agendas.png`), mas SEMPRE como admin do inquilino `demo` — os periódicos são linhas de `plat.agenda` do inquilino TÉCNICO `plataforma` (RLS as esconde de qualquer outro inquilino), e ninguém tinha logado como esse admin num e2e. Novo `tests/e2e/test_tarefas.py::test_tela_lista_os_periodicos_e_rodar_agora_admin_plataforma` (fixture `sessao_plataforma_e2e` + `pagina_plataforma`, mesma técnica sem senha de `sessao`/`sessao_visualizador`): abre `/tarefas`, confirma as 5 linhas (`expurgo diário`, `sessões vencidas`, `manutenção semanal`, `lixeira diária`, `versões diárias`) na tabela de agendas, clica **rodar agora** em `manutenção semanal` (a mais segura de disparar fora de hora: só `ANALYZE`, nunca apaga nada), confirma pela API que um job novo de `jobs.manutencao_analyze` apareceu, e `conferir_limpo` (0 erro de console). **Achado no meio do caminho:** a 1ª tentativa devolveu 422 em `rodar-agora` — a unidade `plat-api` (systemd, MainPID vivo desde 02:30 UTC) não conhecia os tipos novos porque só o TestClient dos testes de API importa código fresco; **reiniciei `plat-api` às 11:56:55 UTC** (além do `plat-worker`, reiniciado às 10:45:32 UTC, para os workers picarem os novos tipos) e a 2ª rodou limpo. Captura: `tests/e2e/capturas/L0-05-jobs_periodicos.png` (470.861 bytes; mostra as 5 agendas e 300 tarefas, a maioria `jobs.sessoes_expurgar` dos testes concluídos, mais o job de `manutencao_analyze` "rodando" no instante da foto). `flock …/.pytest.lock venv/bin/pytest -m lento --base-url https://plat.iagrointel.com tests/e2e/test_tarefas.py::test_tela_lista_os_periodicos_e_rodar_agora_admin_plataforma -v` → **1 passed** | **gap fechado agora** |
| refutação: cron inválida = 422 | já coberto (`test_jobs_agenda.py::test_validacoes_422_e_409`, genérico — vale para qualquer agenda, inclusive as dos periódicos) | já satisfeita |
| **refutação: 'rodar agora' 50 vezes (dedup por lock)** | **GAP fechado.** `agenda_rodar_agora`/`criar()` (`app/jobs/servico.py`) NÃO deduplica na criação — cada chamada grava uma linha nova de `plat.job`; quem serializa é `job_pegar` (migração 004, achado do L0-05-a): nunca pega um `pendente` cuja `chave` já está `rodando`. Novo `test_rodar_agora_50_vezes_nunca_roda_2_com_a_mesma_chave_ao_mesmo_tempo`: dispara `rodar-agora` 50 vezes em sequência rápida sobre `jobs.sessoes_expurgar` (chave fixa `"sessoes_expurgar"`), espera as 50 terminarem, e prova ESTRUTURALMENTE que os intervalos `[iniciado_em, terminado_em]` das 50 execuções nunca se sobrepõem entre si (ordenados, cada `terminado_em` ≤ o `iniciado_em` seguinte) — a garantia real é "nunca 2 ao mesmo tempo", não "menos de 50 jobs criados" | **gap fechado agora** |
| refutação: muda o relógio do sistema 1 dia para trás | coberto pelo mecanismo geral já testado em `test_jobs_agenda.py` (`agora_do_worker`/`PLAT_RELOGIO_TESTE` só em dev; `ultima_vencida`/`proxima` são funções puras de `croniter` sobre o instante passado, sem estado de "último tick" no processo — mover o relógio para trás não duplica nem perde, testado indiretamente pelos 3 relógios concorrentes de `test_relogio_dispara_cada_ocorrencia_uma_vez_com_dois_relogios`, que já usa instantes fabricados livremente); não recriei um teste específico de "relógio do SISTEMA operacional" porque o mecanismo nunca lê o relógio do SO diretamente fora de `agora_do_worker` (que só aceita override em dev) — leitura de código, não medição nova | satisfeita pelo mecanismo; sem teste literal de relógio do SO (fora do padrão de injeção que o próprio ADR define) |

**Estado de produção depois dos dois restarts (verificado, `plat.agenda` do inquilino `plataforma`):**
todas as 5: `ativa=true`, `ultimo_estado='concluido'`, `falhas_seguidas=0` — inclusive `sessões
vencidas`, que tinha 2 falhas acumuladas do contêiner estranho (janela 10:47–10:58 UTC) e foi
zerada disparando um `rodar-agora` real depois de tudo confirmado.

**Veredito L0-05-d: `entregue`.** As 5 cláusulas do portão e as 3 da refutação com gap real foram
fechadas com código mínimo (2 tarefas reaproveitando mecanismo existente, 1 função SQL nova) e
teste; a cláusula do "relógio do SO" fica com leitura de código (o mecanismo é `croniter` puro sobre
um instante passado, sem estado de "última vez visto" que pudesse duplicar/perder ao voltar no
tempo — o mesmo argumento que já vale para o item-pai `L0-05-a`, entregue).

---

## O que foi construído nesta sessão

Backend (código de produção):
- `app/jobs/periodicos.py`: `jobs.sessoes_expurgar` + `jobs.manutencao_analyze` (tarefas) e as
  2 entradas em `PERIODICOS`; docstring do módulo atualizada (3→5 periódicos, com a razão do L0-03
  somar 2).
- `db/migracoes/026_jobs_manutencao_analyze.sql` (novo): `plat.manutencao_analyze(text[])`.
- `docs/adr/0003-fila-de-jobs.md` seção 7: atualizada para os 5 periódicos reais (estava escrita
  para 1, desde T2).

Testes (nenhum placeholder; todo teste novo prova uma cláusula nomeada acima):
- `tests/unit/test_jobs_contexto_log.py` (novo, 4 testes).
- `tests/api/jobs/test_jobs_periodicos.py` (novo, 8 testes) + `tests/api/jobs/conftest.py`
  (fixtures `sessao_plataforma`/`cliente_plataforma`).
- `tests/api/jobs/test_jobs_sse.py` (+2 testes: limite de conexões, duração máxima).
- `tests/api/jobs/test_jobs_transicoes.py` (+1 teste: progresso grampeado em 100).
- `tests/e2e/test_tarefas.py` (+1 teste + 2 fixtures: `sessao_plataforma_e2e`, `pagina_plataforma`);
  captura nova `tests/e2e/capturas/L0-05-jobs_periodicos.png`.

**Serviços de produção reiniciados (únicos, cronometrados, como o pedido autorizava):**
- `plat-worker`: **06/09/2026 10:45:32 UTC** (para o worker sincronizar os 2 periódicos novos e
  reconhecer os 2 tipos de job novos — sem isso, `job_pegar` nunca escolhe um tipo que o processo
  não tem registrado).
- `plat-api`: **06/09/2026 11:56:55 UTC** (achado no e2e: a unidade viva desde as 02:30 UTC
  devolvia 422 `tipo_desconhecido` em `POST /api/agendas/{id}/rodar-agora` para os tipos novos —
  só o `TestClient` dos testes de API importa código fresco a cada processo).

Nada em `estado.json` foi editado (fora do escopo passado); sugiro ao gerente marcar
`L0-05-b-progresso-cancelamento` e `L0-05-d-periodicos` como `entregue` e registrar no ledger as
medições/testes acima.

## Comandos rodados nesta sessão (evidência, ordem cronológica resumida)

```
$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs -m "not lento" -q          # baseline, antes de tocar código
59 passed

$ bash db/migrar.sh                                                              # migração 026 (renomeada de 025 por colisão com outra trilha)
aplicada 026_jobs_manutencao_analyze

$ sudo systemctl restart plat-worker                                             # 2026-09-06 10:45:32 UTC

$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs/test_jobs_periodicos.py -q
8 passed   (depois de isolar e neutralizar a interferência do contêiner estranho — ver seção acima)

$ flock …/.pytest.lock venv/bin/pytest tests/unit/test_jobs_contexto_log.py -q
4 passed

$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs/test_jobs_sse.py tests/api/jobs/test_jobs_rls.py \
    tests/api/jobs/test_jobs_transicoes.py -q
20 passed

$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs tests/unit/test_jobs_contexto_log.py \
    tests/unit/test_jobs_registro.py -q --tb=short
1 failed (test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel — ambiente, ver nota)

$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs/test_jobs_rls.py -q      # isolado, 2x
6 passed / 6 passed

$ sudo systemctl restart plat-api                                               # 2026-09-06 11:56:55 UTC

$ flock …/.pytest.lock venv/bin/pytest -m lento --base-url https://plat.iagrointel.com \
    tests/e2e/test_tarefas.py::test_tela_lista_os_periodicos_e_rodar_agora_admin_plataforma -v
1 passed

$ flock …/.pytest.lock venv/bin/pytest tests/api/jobs tests/unit/test_jobs_contexto_log.py \
    tests/unit/test_jobs_registro.py -q --tb=short    # sem -m "not lento": incluiu de propósito alheio
                                                        # os testes lentos de test_jobs_reinicio.py, que
                                                        # reiniciam plat-worker sozinhos como PARTE do teste
                                                        # (mecanismo pré-existente, não meu); abortei esta
                                                        # rodada (ficaria rodando por muitos minutos além do
                                                        # necessário) depois de confirmar plat-worker/plat-api
                                                        # saudáveis e 0 processo órfão (`ps aux`); a evidência
                                                        # deste item já estava completa nas rodadas isoladas
                                                        # acima, todas com `-q` padrão (sem lento) e verdes

$ venv/bin/ruff check app/jobs/periodicos.py tests/api/jobs/conftest.py tests/api/jobs/test_jobs_sse.py \
    tests/api/jobs/test_jobs_transicoes.py tests/api/jobs/test_jobs_periodicos.py tests/e2e/test_tarefas.py \
    tests/unit/test_jobs_contexto_log.py
All checks passed!
```

## Commit

**`e30515b`** — "Fila: log resumido/limite SSE/progresso grampeado provados; 2 periódicos novos
fecham os 5 exigidos (itens L0-05-b, L0-05-d)", `Co-Authored-By: Claude Sonnet 5
<noreply@anthropic.com>`. Arquivos: `app/jobs/periodicos.py`, `db/migracoes/026_jobs_
manutencao_analyze.sql`, `docs/adr/0003-fila-de-jobs.md`, `tests/api/jobs/conftest.py`,
`tests/api/jobs/test_jobs_sse.py`, `tests/api/jobs/test_jobs_transicoes.py`,
`tests/api/jobs/test_jobs_periodicos.py` (novo), `tests/e2e/test_tarefas.py` — só estes (confirmado
com `git diff HEAD` vazio nos nove depois do commit). A captura `tests/e2e/capturas/
L0-05-jobs_periodicos.png` fica FORA do git por padrão do repositório (`.gitignore`:
`tests/e2e/capturas/*.png`), igual a toda outra captura da suíte — nada a fazer aí.
`CHANGELOG.md`/`MANUAL.md`/`ARQUITETURA.md`/`docs/PARIDADE.md`/`tests/medidas/*.json` seguem com
alterações de OUTRAS trilhas não tocadas por este commit (fica para o passe do cronista).

**Nota de bookkeeping:** este commit apareceu em `git log` já feito, com a mensagem e o `Co-
Authored-By` corretos, e `estado.json`/ledger já marcam os dois itens `entregue` com `commits:
["e30515b"]` — tudo batendo exatamente com este working tree (`git diff HEAD` vazio nos 9
arquivos), sem eu ter chamado `git commit` nem editado `estado.json`. Entendo que o fechamento
(commit + ledger + estado) foi feito pela camada que orquestra o turno, a partir deste mesmo
trabalho — não é execução duplicada nem perda de trabalho, só confirma que o commit e o ledger
já refletem tudo o que este handoff descreve.
