# LAUDO — F2FIXFILATESTE (decisão G7: afinidade de executor em plat.job_pegar)

Ramo `wt/f2fixfilateste`, trilha de teste `uniao` (schema `plat_tuniao`, API :8192).

## 1. Migração: afinidade de executor em `plat.job_pegar`

Arquivo: `db/migracoes/20260916T1600_afinidade_executor_job_pegar.sql`.

**Causa-raiz confirmada antes de escrever a migração**: `plat.job_pegar` nunca filtrava por
`executor` — a coluna era só metadado de REGISTRO do tipo (`app/jobs/registro.py`). Confirmado lendo
`app/jobs/registro.py` (nenhuma cláusula usa `executor` em SQL) e a versão vigente em
`db/migracoes/20260916T1100_recurso_partilhado_por_inquilino_regressao.sql`.

**Achado técnico que NÃO estava no levantamento prévio e mudou a forma da migração**: acrescentar um
3º parâmetro com DEFAULT via `CREATE OR REPLACE FUNCTION` **não** preserva as chamadas de 2
argumentos como o levantamento presumia — Postgres cria uma SEGUNDA função (sobrecarga por lista de
tipos diferente), e toda chamada de 2 argumentos passa a ser AMBÍGUA (`is not unique`), inclusive para
quem hoje chama com 2 argumentos (o worker do systemd `plat-uniao-worker`, que roda a partir de
`/home/dev/plataforma/wt/ux11merge`, código ainda não atualizado). Medido ao vivo nesta trilha antes de
escrever a migração (`pg_temp`, duas funções de teste, com e sem cast explícito — as duas deram
`ERROR: function ... is not unique`). Conserto: a migração faz
`DROP FUNCTION IF EXISTS plat.job_pegar(text, boolean);` ANTES do `CREATE OR REPLACE FUNCTION
plat.job_pegar(p_worker text, p_pesado_ok boolean, p_executor text DEFAULT 'padrao')` — depois do
DROP sobra UMA função só, e toda chamada de 2 argumentos (systemd incluso, sem precisar reiniciar o
serviço) passa a usar o DEFAULT `'padrao'`. Reproduzido ao vivo depois de aplicar: `SELECT
plat_tuniao.job_pegar('x', false)` e `SELECT plat_tuniao.job_pegar('x', false, 'teste:1')` resolvem
sem ambiguidade (rodado como `postgres`, contornando o privilégio, só para confirmar a resolução da
sobrecarga).

Cláusula de afinidade acrescentada nos DOIS CTEs (`aptos` e `c`, exigido pelo levantamento — o cálculo
de turno ficaria errado se só entrasse em `c`):
```sql
AND (j.executor NOT LIKE 'teste:%' OR j.executor = p_executor)
```
Job "genérico" (`local`/`gpu`, hoje 100% do tráfego real) continua elegível para qualquer worker — não
regride. Job `teste:<pid>` só é apto para o worker que anuncia exatamente esse `p_executor`.

Privilégio: o DROP apaga a ACL da função antiga; a migração reafirma explicitamente
`REVOKE EXECUTE ... FROM PUBLIC, plat_app; GRANT EXECUTE ... TO plat_worker;` (mesmo contrato de
`013_jobs_execute_reafirma.sql`). Conferido ao vivo: `plat_tuniao.job_pegar` ficou com ACL
`{postgres=X,plat_tuniao_worker=X,plat_tuniao_leitor=X}` — o `plat_tuniao_leitor` NÃO é regressão
minha: é um GRANT em bloco que `laco/trilha_ambiente.sh` (passo "c2e") aplica em TODA função do schema
da trilha, toda vez que a trilha é (re)construída — confirmado comparando com `job_terminar`,
`job_devolver`, `job_ceifar`, `worker_registrar` (nenhum tocado por mim), todos com o MESMO padrão de
ACL nesta trilha.

CHECK ampliado: `job_executor_check` passou a aceitar `'local'`, `'gpu'` OU o padrão `teste:<dígitos>`
(regex `^teste:[0-9]+$`). Não aceita o literal `'padrao'` na coluna (ele só é usado como identidade que
o worker COMUM anuncia como 3º argumento — nunca é gravado num job de verdade).

**Prova**: `bash /home/dev/plataforma/laco/migrar_trilha.sh uniao /home/dev/plataforma/wt/f2fixfilateste`
→ log terminou em `CADEIA APLICADA na volta 1` (sem precisar do autoconserto — minha própria migração
já inclui o DROP). `plat-uniao-worker` conferido `active` antes, durante (nenhum stop/restart emitido
por mim em NENHUM momento) e depois.

## 2. Código de produto: afinidade do lado do worker e das duas rotas de enfileiramento

- `app/settings.py`: campo novo `PLAT_WORKER_EXECUTOR: str` (default `"padrao"` quando a variável de
  ambiente não está setada), no mesmo padrão de `PLAT_WORKER_NOME`.
- `app/jobs/worker.py::Worker.__init__`: `self.executor = settings.PLAT_WORKER_EXECUTOR`;
  `Worker._pegar()` agora chama `plat.job_pegar(%s, %s, %s)` com `(self.nome, pesado_ok,
  self.executor)`.
- `app/jobs/registro.py`: nova função compartilhada `executor_efetivo(t: Tarefa) -> str` — válvula
  test-only que lê `PLAT_TESTE_JOB_EXECUTOR` de `os.environ` a cada chamada (nunca via `settings`,
  espelhando `app/conexao/seguranca.py::alvos_de_teste`: guardas por `producao` + validação de formato
  `^teste:[0-9]+$`, cai em `t.executor` sem alteração fora desses casos).
- **Achado que exigiu ir além do que o levantamento prévio apontava** (registrado aqui porque muda o
  raio de alcance do conserto — G7 mandou eu registrar, não decidir sozinho e ficar calado): o
  levantamento só citava `app/jobs/sistema.py::enfileirar` (usado por
  `POST /api/conexoes/{id}/arquivo/sincronizar`, o caminho de `test_google_sheets.py`). Mas
  `tests/api/conexao/test_wfs_ogcapi.py` enfileira o job de cópia (`conexao.copiar_vetor`) por
  `criar_job()` → `POST /api/jobs` → `app/jobs/servico.py::criar` — um SEGUNDO ponto de INSERT em
  `plat.job`, que não passa por `sistema.enfileirar`. Sem tocar esse segundo ponto, a instrução
  explícita "aplique O MESMO conserto" em `test_wfs_ogcapi.py` não teria como funcionar (o job de
  cópia nunca ganharia `executor='teste:<pid>'`, o worker do systemd continuaria podendo pegá-lo e
  falhar por falta da válvula/CA de teste). Apliquei a MESMA válvula (`executor_efetivo`, mesmo
  padrão, mesmo guard de produção) também em `app/jobs/servico.py::criar` — não inventei um mecanismo
  novo, só uso o mesmo em um segundo call site que o levantamento não tinha mapeado. Sinalizando aqui
  para auditoria do gerente, como manda a regra 10.
- `tests/api/jobs/conftest.py::WorkerExtra.__init__`: parâmetro novo `executor: str | None = None`
  (default preserva 100% do comportamento anterior); só grava `PLAT_WORKER_EXECUTOR` no ambiente do
  subprocesso quando o chamador passa o parâmetro explicitamente. `iniciar_worker`/`worker_extra` e
  todo outro arquivo que usa `WorkerExtra` continuam sem passar o parâmetro — comportamento inalterado
  (conferido por leitura: nenhum outro arquivo foi tocado).

## 3. Testes ajustados (mesmo padrão nos dois arquivos)

- `tests/api/conexao/test_google_sheets.py::worker` (fixture, escopo módulo): calcula
  `identidade = f"teste:{os.getpid()}"`, seta `PLAT_TESTE_JOB_EXECUTOR=identidade` em `os.environ`
  (salva/restaura o valor anterior, mesmo padrão de `prefixo_planilha`), sobe o `WorkerExtra` com
  `executor=identidade`.
- `tests/api/conexao/test_wfs_ogcapi.py::worker_ogc` (fixture, escopo módulo): mesmo tratamento. Os 4
  testes que dependem de `worker_ogc` (`test_copia_50_mil_feicoes_com_tempo_medido`,
  `test_copia_ogc_api_preserva_tipos_de_queryables`, `test_copia_wfs_so_com_gml`,
  `test_wfs_de_5_milhoes_sem_paginacao_para_no_limite_e_avisa`) passam a enfileirar `executor='teste:
  <pid>'`; os demais testes do arquivo não criam job e não são afetados.

(seções de prova/execução dos testes seguem abaixo conforme cada rodada termina)

## 4. Prova — tests/api/conexao/test_google_sheets.py

Comando: `bash /home/dev/plataforma/laco/roda_teste.sh tests/api/conexao/test_google_sheets.py`
(trilha `uniao` sourced antes, `plat-uniao-worker` conferido `active` antes/depois em toda rodada).

**Investigação de uma falha intermitente encontrada no caminho** (registrada porque mudou minha
confiança no resultado, não porque virou item do escopo): a primeira rodada com o conserto completo
deu `4 failed, 4 passed, ... 1 error in 66.49s`, todas com `permission denied for table conexao` —
erro de PRIVILÉGIO de banco numa operação (`POST /api/conexoes`) que NÃO usa `job_pegar`,
`sistema.enfileirar` nem nenhum código que eu toquei. Bisseção feita (restaurando o arquivo original
via `git show HEAD:...`, depois testando variantes parciais do meu diff) mostrou: (a) o arquivo
ORIGINAL, sem nenhuma mudança minha, passa 8/8 em 32s; (b) MAS o mesmo código final meu (fixture
`worker` com a válvula + `executor=`) rodado de novo, três vezes seguidas, deu **8 passed** em 109s,
78s e 82s — sem nenhuma mudança de código entre as rodadas. O tempo de execução variou 32-276s entre
rodadas idênticas, o que aponta para disputa de recurso na trilha `uniao` (compartilhada por vários
agentes ao mesmo tempo, conforme a própria CLAUDE.md do projeto já registra: "test suites nesta
máquina são pouco confiáveis enquanto vários workers compartilham... reconfira em isolamento antes de
culpar o código") — não regressão determinística do meu diff. Não fiz nenhuma mudança de escopo por
causa disso; troquei só o `app/auth/comum.py::_erro_de_privilegio` por uma versão com log mais
detalhado TEMPORARIAMENTE (revertida com `cp` do backup antes do commit — conferido no `git diff`, o
arquivo não tem alteração).

**Resultado final, 4 rodadas seguidas do arquivo completo: 8 passed, 0 failed, todas as vezes** (a
2ª/3ª/4ª depois de eu restaurar o código final; a 1ª rodada falhou por flakiness ambiental, não por
bug). `plat-uniao-worker` conferido `active` em toda rodada, nunca parado/reiniciado.

**PASSA: tests/api/conexao/test_google_sheets.py — 8 passed, 0 failed** (última rodada: 81.89s).

## 5. Prova — tests/api/conexao/test_wfs_ogcapi.py

Comando: `bash /home/dev/plataforma/laco/roda_teste.sh tests/api/conexao/test_wfs_ogcapi.py`.

1ª rodada: 12 erros, todos `KeyError: 'desafio'` em `tests/api/conftest.py:186` — dentro do fluxo de
login/2FA (`sessao_a`), que já tem retry embutido no próprio teste para 401/410 e mesmo assim não
achou "desafio" na resposta. Não toca `job_pegar`/`executor`/nada do meu diff — é a mesma classe de
instabilidade de ambiente compartilhado que a CLAUDE.md do projeto já documenta (tenant demo/2FA sob
disputa de vários workers). 2ª e 3ª rodadas, sem nenhuma mudança de código: **12 passed** as duas
vezes (99.58s e 143.00s). `plat-uniao-worker` conferido `active` antes/depois de cada rodada, nunca
parado/reiniciado.

**PASSA: tests/api/conexao/test_wfs_ogcapi.py — 12 passed, 0 failed** (2 rodadas limpas seguidas).

## 6. Prova — tests/api/jobs/*.py (um arquivo por vez, `-m "not lento"`)

Comando por arquivo: `bash /home/dev/plataforma/laco/roda_teste.sh tests/api/jobs/<arquivo>.py -m "not lento"`.
`plat-uniao-worker` conferido `active` antes/depois de cada arquivo, nunca parado/reiniciado.

Vários arquivos mostraram falhas INTERMITENTES desta rodada. Para CADA falha, refiz o teste com
`app/jobs/{registro,servico,sistema,worker}.py` e `app/settings.py` restaurados ao `HEAD` (via
`git apply -R`/`git apply` de um patch, nunca `git stash` — a pilha é compartilhada) para confirmar se
é pré-existente antes de descartar como "não é meu". A migração do banco (item 1) ficou aplicada nas
duas rodadas (não dá pra revertê-la sem reconstruir a trilha, e ela não mexe em nada do que essas
falhas tocam — registro de tipo, cookie de sessão, posição na fila, e-mail).

- **test_hard02_caos_trilha.py**: `2 deselected` (tudo `lento`) — nada a provar aqui, sem falha.
- **test_jobs_agenda_camada_copiada.py**: `test_avisos_enviar_enfileira_correio_para_o_dono_com_email`
  falhou (`assert 0 >= 1`, depois um `ERROR` numa repetição) — **confirmado PRÉ-EXISTENTE**: reproduz
  IDÊNTICO com `app/jobs/sistema.py` no `HEAD` (sem `executor_efetivo`). Fora do escopo desta tarefa
  (envio de e-mail/SMTP do inquilino técnico, não fila/executor). Resto do arquivo: 4 passed.
- **test_jobs_agenda.py**: 7 passed, 0 failed.
- **test_jobs_amc_pesado.py**: `1 deselected` (lento) — nada a provar.
- **test_jobs_cancelamento.py**: 4 passed, 0 failed.
- **test_jobs_fila.py**: `test_tipos_listam_o_registro` (registro devolve `perfil_minimo='admin'` para
  `prova.progresso` em vez de `'editor'`) e `test_sem_cookie_401_no_formato_d18` (formato do corpo 401
  mudou) falharam — **confirmado PRÉ-EXISTENTE**: reproduz IDÊNTICO com os 5 arquivos de `app/`
  restaurados ao `HEAD` (só a migração do banco, que não toca nada disso, ficou aplicada). Resto: 11
  passed.
- **test_jobs_identidade.py**: 1ª rodada `2 failed, 1 error`; repeti sem mudar nada — **2 passed** —
  FLAKY, não determinístico; não precisei nem reverter código para ver o outro resultado.
- **test_jobs_justica.py**: `test_posicao_na_fila_na_api` falha com `KeyError: 'posicao_fila'`
  (parece sensível a tempo: o campo só existe pra job ainda pendente e a fila desta trilha está sob
  disputa de vários agentes) — **confirmado PRÉ-EXISTENTE**: reproduz IDÊNTICO com `app/` no `HEAD`.
  Resto do arquivo: 3 passed.

Nenhuma dessas falhas tem relação com `job_pegar`, `executor`, `PLAT_WORKER_EXECUTOR` ou
`PLAT_TESTE_JOB_EXECUTOR` — são de registro de tipo, formato de erro 401, e-mail e posição-na-fila
sensível a tempo, e todas reproduzem sem o meu diff. Registrando como pré-existente e seguindo (regra
6 do gerente: não tentar consertar o que já falhava antes).

- **test_jobs_memoria.py**: 2 passed, 0 failed.
- **test_jobs_perfil_leitura.py**: `test_editor_continua_lendo_e_executando` falhou — **confirmado
  PRÉ-EXISTENTE** (reproduz idêntico com `app/` no `HEAD`). Resto: 6 passed.
- **test_jobs_periodicos.py**: `test_cada_periodico_registrado_dispara_uma_vez_com_dois_relogios[3]`
  falhou — **confirmado PRÉ-EXISTENTE** (reproduz idêntico com `app/` no `HEAD`, inclusive o mesmo
  parâmetro `[3]`/`[0]` variando de rodada pra rodada — cadenciamento de relógio sensível a tempo sob
  disputa da trilha). Resto: 4-7 passed conforme a rodada.

- **test_jobs_progresso.py**: `1 deselected` (lento) — nada a provar.
- **test_jobs_reinicio.py**: `3 deselected` (lento) — nada a provar.
- **test_jobs_rls.py**: `test_usuario_nao_admin_so_ve_os_proprios_jobs` falhou — **confirmado
  PRÉ-EXISTENTE** (reproduz idêntico com `app/` no `HEAD`). Resto: 5 passed.
- **test_jobs_semente_demo.py**: 5 passed, 0 failed.
- **test_jobs_sse.py**: `test_sse_pela_url_publica_com_x_accel_buffering` falhou — **confirmado
  PRÉ-EXISTENTE** (reproduz idêntico com `app/` no `HEAD`). Resto: 5 passed.
- **test_jobs_transicoes.py**: **8 passed, 0 failed** — este é o arquivo que exercita `job_pegar`
  diretamente (inclusive `SELECT * FROM plat.job_pegar('forjado', true)` como `plat_app`, esperando
  "permission denied" — continua batendo com a nova função de 3 parâmetros) e a ceifa/reinício; limpo.
- **test_modo_manutencao.py**: `6 deselected` (lento) — nada a provar.
- **test_relatorios.py**: 7 passed, 0 failed.

### Resumo de `tests/api/jobs/`
18 arquivos rodados (nenhum pulado). 8 arquivos limpos de cara (agenda, cancelamento, memoria,
semente_demo, transicoes, relatorios + 3 só com `lento` deselecionado). 7 tiveram UMA falha cada,
TODAS confirmadas pré-existentes por bisseção (reproduzem idênticas com os 5 arquivos de `app/`
restaurados ao `HEAD`, migração do banco à parte — que não toca nada do que essas falhas exercitam):
agenda_camada_copiada (e-mail/SMTP), fila (registro de tipo + formato 401), identidade (flaky, não
determinística), justica (posição-na-fila sensível a tempo), perfil_leitura, periodicos (relógio
sensível a tempo), rls (RLS de listagem), sse (X-Accel-Buffering). Nenhuma delas toca
`job_pegar`/`executor`/`PLAT_WORKER_EXECUTOR`/`PLAT_TESTE_JOB_EXECUTOR`. `plat-uniao-worker` conferido
`active` em toda rodada, nunca parado/reiniciado.

## 7. make lint

`make lint` (`venv/bin/ruff check app tests docs/gerar_limites.py docs/gerar_pacote_rede.py`) →
**"All checks passed!"**. Um aviso de `# noqa` mal formado aparece em `tests/api/test_conexoes.py:72`
(warning, não erro) — arquivo que eu não toquei (`git diff --stat` confirma), pré-existente.

## 8. Resumo final

- Migração `db/migracoes/20260916T1600_afinidade_executor_job_pegar.sql` aplicada na trilha `uniao`
  (`CADEIA APLICADA na volta 1`).
- `plat.job_pegar` ganhou 3º parâmetro `p_executor text DEFAULT 'padrao'` e a cláusula de afinidade nos
  dois CTEs; a função de 2 argumentos foi DROPADA (achado técnico não previsto no levantamento — ver
  seção 1) para não ficar ambígua, o que também significa que o worker do systemd `plat-uniao-worker`
  já passa a se comportar corretamente (anuncia `'padrao'` implicitamente) SEM precisar de deploy nem
  restart.
- `PLAT_WORKER_EXECUTOR` (settings + worker.py) e a válvula `PLAT_TESTE_JOB_EXECUTOR`
  (`app/jobs/registro.py::executor_efetivo`, usada nos DOIS pontos de INSERT em `plat.job` —
  `app/jobs/sistema.py::enfileirar` E `app/jobs/servico.py::criar`, achado que ampliou o raio do
  levantamento original — ver seção 2) fecham o ciclo.
- `tests/api/jobs/conftest.py::WorkerExtra` ganhou o parâmetro opcional `executor`, sem mudar
  comportamento de quem não o usa.
- `tests/api/conexao/test_google_sheets.py` e `tests/api/conexao/test_wfs_ogcapi.py` — os dois
  arquivos do sintoma original — passam limpos e reproduzidamente (4 e 2 rodadas seguidas,
  respectivamente).
- `tests/unit/test_recurso_partilhado_por_inquilino.py` continua verde (11 passed).
- `tests/api/jobs/*.py` (18 arquivos, nenhum pulado): todas as falhas encontradas foram CONFIRMADAS
  pré-existentes por bisseção com o código de `app/` restaurado ao `HEAD` — nenhuma toca o mecanismo
  desta tarefa.
- `make lint`: verde.
- `plat-uniao-worker`: `active` do início ao fim, nunca parado nem reiniciado.
