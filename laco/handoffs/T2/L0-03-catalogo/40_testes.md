# T2 · L0-03-catalogo · 40_testes — testador

## Objetivo

Conferir, de forma independente, o que o backend (`30_backend.md`) afirmou sobre o catálogo de conteúdo: suíte
inteira, varredura cruzada A→B, e2e contra a URL real e medidas — antes de o item ir ao adversário.

## O que fiz

1. `flock /home/dev/plataforma/laco/.pytest.lock make check` (lint + sem-marcador + teste "not lento").
2. Reproduzi as duas falhas isoladas para descartar interferência de ordem.
3. `flock … pytest tests/api/test_cruzado.py` isolado, para confirmar a varredura cruzada por fora do `make check`.
4. Li 4 capturas e2e existentes (`L0-03_lista.png`, `_detalhe.png`, `_compartilhar.png`, `_lixeira.png`).
5. `flock … make medidas` (suíte inteira, sem filtro de marcador, contra `https://plat.iagrointel.com`) — 21m28s,
   inclui os e2e "lento" (login, 2FA, tokens, papéis, grupos, log de acesso, conteúdo, o job de 5 min do L0-05).
6. Medi a query da política de leitura direto no banco (`EXPLAIN ANALYZE`, como `plat_app`) para separar "o código
   está lento" de "a máquina está lenta".
7. Conferi `docs/openapi.json` (paths/ops totais e do catálogo) e `/saude` da URL pública.

## Evidência (comando + saída literal)

```
$ flock /home/dev/plataforma/laco/.pytest.lock make check
lint: All checks passed!
sem-marcador: (sem saída — 0 marcadores)
teste: 2 failed, 610 passed, 25 deselected, 188.47s
  FAILED tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95 — AssertionError: 161.8 (assert 161.8 < 100)
  FAILED tests/api/jobs/test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel — assert 6 == 0
make: *** [Makefile:19: teste] Error 1   (e2e não chega a rodar: o alvo "teste" falhou antes)

$ flock … pytest tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95 \
             tests/api/jobs/test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel -q
tests/api/jobs/test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel  PASSOU sozinho
tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95  FALHOU sozinho também: 198.2 (assert < 100)

$ flock … pytest tests/api/test_cruzado.py -v
124 passed, 1 warning in 16.32s   (0 falhas; 0×200 confirmado — nenhuma rota do catálogo em test_cruzado devolveu
   200 para a sessão B contra recurso de A)

$ PGPASSWORD=*** psql -h 127.0.0.1 -U plat_app -d iagro_sat -c "
  set plat.tenant_id='1'; set plat.usuario_id='1';
  explain (analyze, buffers, timing) select * from plat.item where tipo='mapa' order by modificado_em desc limit 50;"
  Execution Time: 20.672 ms   Planning Time: 3.112 ms   Buffers: shared hit=2628 (consistente com o plano que o
  backend citou — 4.428 buffers/12,6 ms — a política em si não regrediu)

$ flock /home/dev/plataforma/laco/.pytest.lock make medidas
(suíte inteira, sem marcador "not lento", contra a URL pública, 21m28s)
4 failed, 633 passed, 5 warnings in 1288.36s (0:21:28)
  FAILED tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95
  FAILED tests/api/jobs/test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel
  FAILED tests/e2e/test_log_acesso.py::test_log_filtro_csv_e_eventos[chromium] — playwright TimeoutError 20000ms
      esperando navegação pós-login (não é do catálogo)
  FAILED tests/e2e/test_papeis.py::test_papel_criar_editar_apagar[chromium] — mesmo TimeoutError, mesma causa
make: *** [Makefile:25: medidas] Error 1
(tests/e2e/test_conteudo.py — o e2e do L0-03 — NÃO está na lista de falhas: passou 2/2, com as 10 capturas
 L0-03_*.png reescritas às 00:25:03-07 UTC e tests/medidas/L0-03-catalogo.json regravado no mesmo instante)

$ cat tests/medidas/L0-03-catalogo.json   (regravado 2026-09-06T00:25:07Z, git_sha 65a9fc2c0869)
  busca_p95_ms = 109.0            (portão ADR 0004 ≤ 200 ms — PASSA)
  busca_trgm_p95_ms = 171.0       (sem portão numérico — fronteira)
  lista_tipo_p95_ms = 203.0       (portão ADR 0004 "L0-03-a" < 100 ms — NÃO CONFIRMADO nesta rodada)
  facetas_p95_ms = 25.8
  revogacao_nega_ms = 15.3
  expurgo_s = 0.32
  miniatura_job_s = 0.33
  usado_por_medio_ms = 11.6       (portão "L0-03-i" < 50 ms — PASSA)
  versao_custo_ms = 0.347
  pagina_conteudo_ms = 231.8 · primeira_pintura_conteudo_ms = 16 · soma_modulos_kb = 229.6

$ ps -o pid,etime; uptime; free -h   (durante a rodada de make check e de make medidas)
  load average: 6.4-7.4 (12 vCPU) · Mem: 23Gi total, 598Mi-970Mi livres · Swap: 8,0Gi/8,0Gi quase cheio
  ps aux | grep claude: 20 sessões "claude --dangerously-skip-permissions" concorrentes na mesma máquina

$ venv/bin/python -c "import json; d=json.load(open('docs/openapi.json')); ..."
  paths totais 92 · caminhos do catálogo 36 · operações do catálogo 48 (confere com o handoff do backend)

$ curl -s https://plat.iagrointel.com/saude
  {"migracoes_pendentes":0,"ultima_migracao":"018_item_ler_durante_transferencia","banco":"ok",
   "servicos":{"garage":"ok","worker":"ok"}, "fila":{"workers_vivos":1}}
```

## O que bateu com o backend

- Migração 011-018 aplicada, sem pendência (`/saude`).
- `plat.item` com RLS, grants explícitos, versões imutáveis com sha256, relações, pastas, favoritos, lixeira,
  transferência: os 249 testes de `tests/api/catalogo` + `tests/unit` fecham 0 falha (rodei dentro de `make check`).
- **Varredura cruzada A→B: 124 casos, 0 falha, 0×200** — confirmado isolado, exatamente como o backend registrou.
- 0 marcador em código entregue (P2).
- OpenAPI: 92 caminhos/123 operações no total, 36/48 do catálogo — números conferem.
- e2e do item (`tests/e2e/test_conteudo.py`, os dois testes) passou 2/2 **contra a URL pública real**, com as 10
  capturas `L0-03_*.png` regeradas e 0 erro de console (a fixture `Tela` reprova sozinha se houver `console.error`
  ou `pageerror` — o teste não falhou, logo não houve).
- Capturas lidas (lista, detalhe, compartilhar/link por token com revogação, lixeira com restaurar/apagar):
  telas funcionam, sem placeholder visual, sem dado de cliente.
- `expurgo_s`, `miniatura_job_s`, `revogacao_nega_ms`, `usado_por_medio_ms`, `versao_custo_ms`, `facetas_p95_ms`,
  `busca_p95_ms` — todos dentro do que o próprio ADR 0004 declara como portão.

## O que NÃO bateu (achado do testador)

**`lista_tipo_p95_ms`: portão do ADR 0004 pede < 100 ms; medi 161,8 / 198,2 / 203,0 ms em três rodadas
independentes (isolada, dentro do `make check`, dentro do `make medidas`) — sempre acima do limite, nunca perto
dos 48,6 ms que o backend registrou às 21h07 de ontem.** Isso não é interferência de ordem de teste (rodei o teste
sozinho e ele falhou do mesmo jeito). Separei duas hipóteses — código ou máquina — e a evidência aponta para
**máquina**: (a) o mesmo predicado, medido direto no banco com `EXPLAIN ANALYZE` fora do pytest, executa em 20,7 ms
(perto dos 12,6 ms que o backend citou do plano); (b) nesta mesma rodada de `make medidas`, dois testes e2e sem
nenhuma relação com o catálogo (`test_log_acesso`, `test_papeis`) falharam por **timeout de navegação do Playwright
(20 s) logo após o login** — sintoma de máquina sobrecarregada, não de rota lenta; (c) a máquina estava com
`load average` 6,4-7,4 em 12 vCPU, RAM praticamente zerada (598 Mi-970 Mi livres de 23 Gi) e swap quase cheio, com
20 sessões `claude` concorrentes rodando (`ps aux`). Não decreto isto como "passa" nem "falha": é uma medida real,
tirada agora, acima do portão, e o motivo mais provável é ambiente compartilhado, não regressão de código. Fica
para o próximo turno **remedir em janela mais silenciosa** antes de fechar esta cláusula.

**`test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel`** (item L0-05-jobs, não L0-03): falhou
dentro de `make check` e de `make medidas`, mas passou sozinho quando rodado isolado — efeito colateral de outro
teste (provavelmente do próprio arquivo de jobs) que deixa `plat_trabalho.passos` sujo. Não é do catálogo; registro
aqui porque impede a suíte inteira de fechar 100% verde (portão P3, que vale para todo item). Fica nomeado para a
trilha do L0-05-jobs.

## Riscos

1. **Portão P3 (suíte inteira verde) não fechou nesta rodada**: 4 falhas (1 do catálogo — desempenho, sob suspeita
   de ambiente; 3 fora do catálogo — 1 de jobs por sujeira entre testes, 2 de e2e por timeout de máquina). Nenhuma
   delas reabre uma regressão funcional que eu tenha visto — mas a cláusula literal do Makefile (`check: teste e2e`)
   não fechou 0 falha nesta execução.
2. A `lista_tipo_p95_ms` é a única medida de desempenho do item fora do portão; todas as outras (busca, facetas,
   revogação, expurgo, miniatura, usado-por, versão) confirmaram dentro do limite mesmo sob esta carga — o que
   reforça que o problema é specífico da consulta mais pesada (`Seq Scan` de 11 mil linhas sob CPU disputada), não
   generalizado.
3. Não tentei isolar a máquina (matar as outras sessões `claude`) para remedir limpo — não é decisão minha; fica
   registrado para quem tiver autoridade de liberar RAM/CPU.
4. Escala de 50 mil itens e teto de rajada do pool (pendências que o backend deixou para mim) **não foram medidos
   neste turno** — o tempo foi para a suíte inteira e o e2e completo (21m28s), que já não é rápido nesta máquina.
5. `docs/PARIDADE.md` ainda não tem a seção do L0-03-catalogo (a paridade-alvo de 18 linhas está em
   `laco/handoffs/T1/21_esri.md`, para o cronista transcrever depois do adversário).

## Pendências

- Adversário (50): cláusula a cláusula das migrações 017/018 (política de leitura e transferência), o roteiro do
  L0-03-e (revogar/reabrir link, token curto, compartilhar item de outro) e a paridade contra o alvo de 18 linhas
  do `21_esri.md`.
- Remedir `lista_tipo_p95_ms` numa janela sem outras sessões pesadas rodando, antes de considerar esta cláusula
  fechada ou reaberta como defeito real.
- L0-05-jobs: investigar a sujeira em `plat_trabalho.passos` que reprova `test_jobs_rls` quando roda junto com o
  resto da suíte (não investiguei além de confirmar que é de ordem, não do catálogo).
- Cronista (60): escrever a seção L0-03-catalogo em `docs/PARIDADE.md` a partir do alvo já escrito pelo esri.

## Para o próximo papel (adversário, 50)

1. O mecanismo de segurança (RLS, cruzado A→B, link revogado) está confirmado por mim de forma independente —
   ataque essas superfícies primeiro, principalmente a janela da migração 018 (leitura durante transferência).
2. Não repita a bateria de desempenho sem saber que a máquina estava sob `load average` 6-7 nesta janela: se seu
   ataque incluir medir `lista_tipo_p95_ms`, registre `uptime`/`free -h` junto, porque o número sozinho hoje não
   distingue código de contenção de ambiente.
3. `tests/e2e/capturas/L0-03_*.png` e `tests/medidas/L0-03-catalogo.json` estão frescos (00:25 UTC, git_sha
   65a9fc2c0869) — não precisa refazer o e2e para conferir a tela, só ler as capturas.

## Resumo em 5 linhas

1. `make check` isolado: 610 passed/2 failed (não os 612/0 que o backend registrou); reproduzi as duas falhas fora
   do `make check` e uma delas (`test_jobs_rls`, fora do catálogo) passou sozinha — a outra (`lista_tipo_p95_ms`)
   falhou sozinha também, em 3 rodadas independentes (161,8/198,2/203,0 ms, portão < 100 ms).
2. Varredura cruzada A→B confirmada isolada: 124 casos, 0 falha, 0×200 — bate exatamente com o backend.
3. e2e do item passou 2/2 contra a URL pública real, 10 capturas novas, 0 erro de console; `make medidas` completo
   (21m28s, com o job de 5 min do L0-05) fechou 633 passed/4 failed, e o catálogo só aparece na falha de desempenho.
4. `EXPLAIN ANALYZE` direto no banco (20,7 ms) e dois e2e não-relacionados que também deram timeout de navegação
   na mesma janela indicam que a lentidão medida é da máquina (load 6-7, RAM/swap no limite, 20 sessões `claude`
   concorrentes), não uma regressão da política de leitura — mas registro o número medido, não decreto a causa.
5. Veredito proposto por cláusula: tabela/RLS/versões/pastas/lixeira/compartilhamento/e2e/OpenAPI/cruzado = PASSA
   confirmado; desempenho de `lista_tipo_p95_ms` = pendência (remedir em ambiente mais silencioso); paridade contra
   Portal Content = alvo escrito, falta o adversário cobrar e o cronista transcrever para `docs/PARIDADE.md`.
