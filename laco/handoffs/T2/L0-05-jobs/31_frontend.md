# T2 · trilha B · L0-05-jobs · 31_frontend (frontend)

## Objetivo

Construir a tela "Tarefas" contra o contrato do ADR 0003 (seções 5, 9, 10 e 12) sem esperar o backend: `web/tarefas.html`
+ `web/js/jobs/*.js` (lista do inquilino com filtro por estado/tipo/quem/período e paginação; progresso em tempo real por
SSE `/api/jobs/{id}/eventos` com polling de reserva; detalhe com log ao vivo, cancelar, repetir, resultado com link ao
item; agendas listar/criar com cron e fuso/pausar/retomar/rodar agora/apagar; item "Tarefas" na barra lateral) e os
e2e playwright `tests/e2e/test_tarefas.py` (capturas, 0 erro de console, `primeira_pintura_tarefas_ms` pela fixture
`medida`). Regra recebida: esperar a base reutilizável da trilha A (`web/js/base/`) e USÁ-LA em vez de duplicar.

Item copiado do estado: portão "job de 5 min mostra progresso em tempo real, pode ser cancelado, sobrevive a reinício do
serviço (retoma ou marca falha, nunca some); 1 worker por padrão com limite de RAM declarado; tela Tarefas por inquilino;
teste automatizado"; refutação "adversário mata o worker no meio de um job e reinicia: job não pode aparecer como concluído".

## O que fiz

1. Esperei a base da trilha A (laço de 60 s): `web/js/base/` apareceu na árvore de trabalho às 13:51Z (vazia) e com
   arquivos às 13:54Z (`api.js`, `dom.js`, `estado.js`, `i18n.js`, `layout.js`, `componentes/{aviso,busca,dialogo,
   formulario,paginacao,tabela}.js`) mais `web/js/auth/sessao.js`. **Está tudo na árvore de trabalho, ainda não comitado
   pela trilha A** (a trilha A e a B compartilham o mesmo diretório de trabalho, não há worktree separado).
2. Reescrevi os meus módulos em cima dela — nada duplicado:
   - `web/js/jobs/api.js` (2,7 kB): `chamar`/`consulta` de `base/api.js`; erro D18 vira `ErroApi` com `status/codigo/
     detalhe/reqId`; 401 chama o tratador registrado (`irParaLogin` de `auth/sessao.js`).
   - `web/js/jobs/eventos.js` (4,1 kB): `EventSource` por job, vários ouvintes por assinatura (lista e detalhe partilham a
     conexão), 2 erros seguidos ou conexão recusada (`readyState CLOSED`) → polling de 3 s em `obter` + `log(apos)`;
     limite de 10 assinaturas por página (`assinar` devolve `false` e a lista faz polling da lista).
   - `web/js/jobs/formato.js` (5,2 kB, puro): datas pt-BR ("hoje 14:02", "ontem 18:11", "05/09 03:30"), durações
     `mm:ss`/`h:mm:ss`, estados com símbolo + texto, texto da coluna progresso, CSV, checagem de cron (5 campos) e fuso
     (`Intl.DateTimeFormat`).
   - `web/js/jobs/util.js` (1,4 kB): só o que a base não tem (`porId`, `baixar`, `opcoes`, `aviso` sobre `<plat-aviso>`).
   - `web/js/jobs/lista.js` (13,3 kB): tabela própria (linhas mudam uma a uma ao vivo e o cabeçalho ordena — o
     `<plat-tabela>` re-renderiza tudo e não ordena), `<plat-paginacao>` da base, `confirmar()` da base no cancelar,
     resumo a cada 10 s (contador na barra + releitura da 1ª página quando muda o nº de ativos), relógio de duração 1 s,
     CSV da página no navegador, filtro "quem" só para `perfil = admin`.
   - `web/js/jobs/detalhe.js` (10,3 kB): abre por clique ou `/tarefas/<id>` (`history.pushState`/`popstate`); assina o
     SSE ANTES de ler o log (linha que chega no intervalo é deduplicada pelo id); filtro de nível; `baixar log` = `log(id,
     0, 2000)` em `text/plain`; blocos parâmetros/resultado/proveniência; link `/conteudo/<item_id>` quando existe.
   - `web/js/jobs/agendas.js` (10,2 kB): `<plat-tabela>` (colunas + ações) e `<plat-formulario>` da base; validação
     no navegador (JSON, campos `required` do `parametros_schema`, 5 campos de cron, fuso IANA) e erros 422 do servidor
     campo a campo (`detalhe` como lista pydantic, dicionário ou texto), 409 no nome, 413/403 como mensagem.
   - `web/js/jobs/tarefas.js` (4,2 kB): entrada — `carregar()` do i18n, `GET /api/eu` (401 → `irParaLogin`; 200 →
     usuário, `loja`, pendências; outro status → a tela segue só com a API de jobs e avisa), `montarLayout` da base com
     `ativo: '/tarefas'` e o contador `#tarefas-ativas` pendurado no item, `cabecalho('Tarefas')`, `pronto()`.
   - `web/tarefas.html` (6,3 kB) no mesmo esqueleto de `conta.html` (`body.tela`, `.app > aside#lateral + main#principal`,
     `.cartao`, `<plat-aviso>`, `<plat-paginacao>`, `<plat-tabela>`, `<plat-formulario>`); `web/tarefas.css` (5,2 kB) só com
     o que a folha comum não tem (estados, barra de progresso, log, grade lista | detalhe ≥ 1200 px).
3. Item "Tarefas" na barra lateral: **uma linha em `web/js/base/layout.js`** (`TELAS`: `{ caminho: '/tarefas', chave:
   'nav.tarefas' }` logo abaixo de Início) e **uma chave em `web/js/i18n/pt-BR.json`** (`"nav.tarefas": "Tarefas"`). São
   arquivos da trilha A, ainda não comitados por ela; se a trilha A regravar esses arquivos, as duas linhas somem e a tela
   ainda funciona (o `tarefas.js` acrescenta o item ao menu quando não o encontra em `TELAS`), mas as OUTRAS telas deixam
   de mostrar "Tarefas". Aviso para o frontend de identidade: manter as duas linhas no commit dele.
4. `tests/e2e/test_tarefas.py` (5 provas, `lento` + `e2e`): cookie `plat_sessao` por `tests/jobs_sessao.py` do backend
   quando existe (existe, na árvore de trabalho) e por função própria como reserva (já com o contexto do inquilino e
   `p_max_dias` da 003); pula com razão escrita enquanto `/api/openapi.json` não lista `/api/jobs`.
5. Como o backend não subiu `/api/jobs` na URL pública, validei o front e os testes contra um **servidor de rascunho**
   com o contrato da seção 9 (jobs em memória, SSE, agendas, `/api/eu`), fora do repositório:
   `<scratchpad>/stub_api.py` (porta 18158). Capturas geradas contra o stub ficaram em `<scratchpad>/capturas_stub/` e
   NÃO no repositório (`tests/e2e/capturas/` só recebe captura da URL real, do testador).
6. Commit `1668d76` só com os meus arquivos (`web/tarefas.html`, `web/tarefas.css`, `web/js/jobs/*`,
   `tests/e2e/test_tarefas.py`; 11 arquivos, 1.892 linhas).

## Evidência (comando + saída literal)

```
$ git log --oneline -1 -- web/js/base web/js/auth   (13:51Z, laço de 60 s, iteração 3)
(vazio: diretórios existem na árvore, sem commit)          $ ls web/js → auth base core.js i18n
$ find web/js/base -name '*.js' -size +0 | wc -l          → 4 (13:54Z) … 10 (14:00Z)

$ for f in web/js/jobs/*.js; do cp $f chk.mjs; node --check chk.mjs && echo "sintaxe ok $f"; done
sintaxe ok agendas.js api.js detalhe.js eventos.js formato.js lista.js tarefas.js util.js
$ wc -c web/js/jobs/*.js web/tarefas.html web/tarefas.css
10240 agendas.js · 2746 api.js · 10314 detalhe.js · 4089 eventos.js · 5178 formato.js · 13314 lista.js · 4199 tarefas.js
· 1441 util.js · 6348 tarefas.html · 5247 tarefas.css · 63116 total   (orçamento 60 kB por módulo: maior = 13,3 kB)
$ grep -rn '?v=' web/tarefas.html web/js/jobs | grep -v 'NUNCA ?v='   → nada
$ grep -rnI -E -f tests/marcadores.regex web/tarefas.html web/tarefas.css web/js/jobs tests/e2e/test_tarefas.py; echo $?
1   (nenhum marcador)
$ PYTHONNOUSERSITE=1 venv/bin/ruff check tests/e2e/test_tarefas.py
All checks passed!

# stub: PYTHONNOUSERSITE=1 venv/bin/python <scratchpad>/stub_api.py 18158 1200   (1.200 jobs concluídos semeados)
$ PYTHONNOUSERSITE=1 venv/bin/pytest tests/e2e/test_tarefas.py --base-url http://127.0.0.1:18158 -k "not mil" -q
....                                                                     [100%]
   (test_lista_progresso_ao_vivo_e_detalhe · test_cancelar_pela_tela · test_filtro_por_estado_bate_com_api ·
    test_agendas_criar_pausar_retomar_apagar; 0 erro de console; capturas L0-05-jobs_{lista,detalhe,agendas}.png)
   1ª rodada reprovou em agendas por "console.error: Failed to load resource: 422" (o Chromium grava isso para toda
   resposta não-2xx, aqui a 422 que o teste provoca de propósito) → conferir_limpo aceita SÓ esse texto quando uma
   resposta tolerada com o mesmo status foi registrada (mesma regra da classe Tela de tests/e2e/apoio.py da trilha A).
   O teste "mil" (semeia 1.000 jobs por SQL no plat.job real) não foi rodado contra o stub de propósito.

$ PYTHONNOUSERSITE=1 venv/bin/pytest tests/e2e/test_tarefas.py --base-url https://plat.iagrointel.com -q -rs   (15:02Z)
SKIPPED [5] tests/e2e/test_tarefas.py: o backend ainda não publicou /api/jobs no OpenAPI; testes prontos, esperando a trilha do backend
$ curl -s https://plat.iagrointel.com/api/openapi.json | python3 -c "...paths..."   → sem /api/jobs (2 rotas: /api/versao, /saude)
$ curl -s -o /dev/null -w "%{http_code}" https://plat.iagrointel.com/tarefas   → 404
   (vigia de 45 min a partir de 13:49Z: /api/jobs não apareceu na URL pública; app/jobs/ e db/migracoes/004_jobs.sql
    existem na árvore de trabalho, sem install.sh rodado)

$ PYTHONNOUSERSITE=1 make lint sem-marcador; venv/bin/pytest -m "not lento" -q     (árvore INTEIRA, 14:12Z)
lint: Found 41 errors (todos em arquivos das outras trilhas: tests/unit/test_politica.py, app/auth/…, app/jobs/…) → make: *** [lint] Error 1
sem-marcador: ok
pytest: FAILED tests/api/test_saude.py::test_saude_200_com_json_do_contrato · FAILED tests/unit/test_settings.py::test_opcionais_vazias…
   (arquivos do backend/identidade em edição; nenhum dos dois toca web/ ou tests/e2e/test_tarefas.py)
$ free -g → available 3 GB (playwright rodado com 1 chromium, sequencial); df -h / → 98 %
```

O que as capturas do stub mostram (`<scratchpad>/capturas_stub/`): barra lateral com Início · Tarefas (contador "1") ·
Minha conta · Usuários · Grupos · Tokens · Log; resumo "0 na fila · 1 rodando · 1.200 concluídas em 24 h"; linha
"● rodando prova.progresso admin hoje 14:07 00:10 [barra] 16 % passo 5 de 30 [cancelar] [abrir]"; 1–50 de 1.201;
detalhe à direita com "✓ concluído · 100 % · tentativa 1 de 3 · worker stub", parâmetros, resultado com "abrir item",
log 9 linhas com nível. (Na captura o item ainda dizia "nav.tarefas" porque o `pt-BR.json` só apareceu depois; a chave
foi acrescentada às 14:15Z.)

## Riscos

1. **Dependência de arquivos não comitados da trilha A** (`web/js/base/*`, `web/js/auth/sessao.js`, `web/style.css`,
   `web/js/i18n/pt-BR.json`). Se a trilha A renomear exportações (`chamar`, `consulta`, `h`, `limpar`, `montarLayout`,
   `cabecalho`, `pronto`, `irParaLogin`, `lembrarInquilino`, `marcarSessao`, `caminhoPendencia`, `loja`, `confirmar`) ou
   as classes CSS (`.app`, `.lateral`, `.principal`, `.cartao`, `.filtros`, `.tabela`, `.marcador`, `.acoes-linha`,
   `.botoes`, `.form`), a tela quebra na importação. Quem comitar por segundo roda o e2e de novo.
2. Ordem de deploy: `GET /tarefas` e `/tarefas/{id}` são servidas pelo `app/jobs/rotas.py` do backend (ADR passo 15); sem
   o backend deployado a página é 404 e o e2e pula. A tela também assume `GET /api/eu` da trilha A: sem ela mostra o aviso
   "dados da sessão indisponíveis (…)" e segue (o filtro "quem" e o corte por perfil da seção de agendas ficam de fora).
3. Chromium registra `console.error` para qualquer resposta não-2xx; o e2e tolera SÓ `Failed to load resource … status
   of N` quando N veio de uma URL da lista `TOLERADAS` (`/api/eu` 404, `pt-BR.json` 404, `/api/agendas` 422/409). As duas
   primeiras são transitórias e devem sair da lista quando a trilha A estiver no ar.
4. `test_primeira_pintura_com_mil_jobs` insere 1.000 linhas em `plat.job` como `plat_app` (contexto do inquilino demo,
   `parametros.semente_e2e = 1`) e apaga no `finally`; se a 004 tiver política que impeça DELETE em estado final, as
   linhas ficam e o expurgo diário as apaga em 90 dias — o testador confere o `count(*)` depois da rodada.
5. Limite de 10 SSE por usuário POR PROCESSO da API (ADR 5) × 10 assinaturas por página no front: duas abas do mesmo
   usuário podem receber 429 no 11º job ativo; a tela cai para polling e avisa "mais de N tarefas ativas: lista atualizada
   a cada 3 s". Não é falha, mas o testador deve ver a mensagem.
6. Paginação da base é "1–50 de N + Anterior/Próxima", não os números "‹ 1 2 3 … 20 ›" do wireframe (seção 10). Decisão
   consciente: reuso do `<plat-paginacao>` em vez de um segundo componente; se o dono quiser números, é evolução da base.

## Pendências

- Backend/gerente: `install.sh` + deploy para `/api/jobs` e `/tarefas` existirem na URL pública; só então o e2e roda.
- Trilha A (frontend de identidade): manter `{ caminho: '/tarefas', chave: 'nav.tarefas' }` em `layout.js` e
  `"nav.tarefas"` em `pt-BR.json` no commit dela (já avisado pelo gerente).
- Gerente: `make check` na árvore inteira está vermelho por arquivos das outras trilhas (lint 41 erros; 2 testes de
  saúde/settings); o escopo desta trilha passa (ruff, marcadores, e2e contra o stub). Rebase feito sobre `1540c84`;
  nenhum commit novo das outras trilhas até 15:02Z, então não houve conflito a resolver.
- Quando `/api/eu` estiver no ar: trocar as 8 linhas de `tarefas.js` que tratam o `GET /api/eu` por `exigirSessao()`
  de `auth/sessao.js` (que hoje apaga o `<main>` em qualquer status ≠ 200/401 — por isso não foi usado ainda).
- Sem decisão nova do dono.

## Para o próximo papel (testador, 40)

1. Pré-requisito: `curl -s https://plat.iagrointel.com/api/openapi.json | grep -c '"/api/jobs"'` = 1 e
   `curl -o /dev/null -w '%{http_code}' https://plat.iagrointel.com/tarefas` = 200. Sem isso a suíte pula (mensagem
   literal na saída do pytest) e o item fica `pendente` com o bloqueio nomeado.
2. Rodar: `PYTHONNOUSERSITE=1 PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/e2e/test_tarefas.py --base-url
   https://plat.iagrointel.com -q -rs` (≈ 3 min sem fila; até 8 min se um job de 5 min de outro teste ocupar o worker —
   o teste espera até 480 s pelo primeiro progresso). RAM: 1 chromium, `free -g` antes.
3. O que sai: `tests/e2e/capturas/L0-05-jobs_{lista,detalhe,mil,agendas}.png` (regra do repositório
   `<item>_<tela>.png`, como `L0-01-repo_inicio.png`; o pedido dizia `L0-05_*.png` — se o gerente preferir esse prefixo,
   é um `sed` em `ITEM`) e, em `tests/medidas/L0-05-jobs.json`: `pagina_tarefas_pronta_ms`, `linha_nova_aparece_s`
   (≤ 10 s + carga: resumo a cada 10 s), `progresso_valores_distintos` (≥ 2), `cancelamento_tela_s`,
   `primeira_pintura_tarefas_ms` (portão: ≤ 1.000 com 1.000 jobs semeados; o teste ASSERTA isso),
   `pagina_tarefas_mil_pronta_ms`.
4. Conferir à mão o que o e2e não prova: (a) o modo de reserva — `sudo systemctl stop plat-api`? não: derrubar só o
   SSE é impossível sem tocar na API; alternativa: abrir 11 jobs de 120 s e ver o marcador "atualização a cada 3 s" no
   detalhe do 11º e a mensagem "mais de 10 tarefas ativas" na lista; (b) `X-Accel-Buffering: no` chega pela URL pública
   (`curl -N -D - https://plat.iagrointel.com/api/jobs/<id>/eventos -H 'Cookie: plat_sessao=…' | head`); (c) reinício do
   worker no meio do job de 5 min com a tela aberta: a linha tem de voltar a `pendente` e depois `rodando` sem recarregar
   (evento `estado`), nunca `concluído` antes do fim; (d) usuário `editor` (criar por `tests/jobs_sessao.py:
   criar_usuario_temporario`) não vê o filtro "quem" nem os jobs do admin; `visualizador` não vê a seção de agendas.
5. Depois da rodada: `SELECT count(*) FROM plat.job WHERE parametros->>'semente_e2e' = '1'` como plat_app no
   contexto demo tem de ser 0.
6. O stub `<scratchpad>/stub_api.py` (não versionado; scratchpad desta sessão) reproduz o contrato para depurar o front
   sem worker: `venv/bin/python stub_api.py 18158 1200` e `--base-url http://127.0.0.1:18158 -k "not mil"`.

---

Resumo em 8 linhas:
1. Tela Tarefas construída contra o contrato (ADR 0003 §5/9/10) e comitada em `1668d76`: 8 módulos ES (maior 13,3 kB, sem `?v=`, sem marcador), `tarefas.html`, `tarefas.css`.
2. Base da trilha A apareceu na árvore (não em commit) às 13:54Z e foi USADA: `chamar/consulta`, `h/limpar`, `<plat-aviso>`, `<plat-paginacao>`, `<plat-tabela>`, `<plat-formulario>`, `confirmar`, `montarLayout`, `irParaLogin`; nada duplicado além de 3 utilidades.
3. Item "Tarefas" na barra lateral = 1 linha em `base/layout.js` + 1 chave em `i18n/pt-BR.json` (arquivos da trilha A, ainda não comitados por ela: têm de sobreviver ao commit dela).
4. Progresso em tempo real: EventSource compartilhado por job, limite 10, reserva por polling de 3 s; linha nova sem recarregar pelo resumo de 10 s; cancelar com confirmação e botão travado até o evento `estado`.
5. e2e `tests/e2e/test_tarefas.py`: 5 provas; 4 passaram contra um stub com o contrato (`....`), a 5ª (1.000 jobs por SQL → `primeira_pintura_tarefas_ms`) só roda no banco real.
6. Contra `https://plat.iagrointel.com` a suíte PULA com razão escrita: `/api/jobs` não entrou no OpenAPI público em 45 min (vigia 13:49–14:34Z) e `/tarefas` dá 404 — deploy do backend é o bloqueio.
7. `make check` na árvore inteira está vermelho por arquivos das outras trilhas (lint 41 erros, 2 testes de saúde/settings); o escopo desta trilha passa.
8. Para o testador: rodar com `PLAT_GRAVAR_MEDIDAS=1` quando o pré-requisito do passo 1 valer; conferir à mão reinício do worker com a tela aberta e o modo de reserva com 11 jobs.
