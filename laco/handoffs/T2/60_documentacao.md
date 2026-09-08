# T2 · 60_documentacao — cronista · itens L0-02-tenant-auth e L0-05-jobs

## Objetivo

Fechar o portão P9 (documentado no mesmo turno) para os dois itens do turno 2: `MANUAL.md` com uma seção por tela e
a captura real do e2e, `ARQUITETURA.md` com identidade e fila como existem no repositório, `CHANGELOG.md` com a
entrada 0.2.0 (o que entrou, medições, vereditos, commits), `docs/PARIDADE.md` com as 16 linhas de identidade do
`21_esri.md` seção 3.1 e as linhas da fila, `README.md` ajustado, `laco/PAINEL.md` regenerado. Sem nome de cliente,
sem marcador de pendência, sem emoji, número só de `tests/medidas/*.json` e de `refutacao.json`, com o comando.
Não tocar `app/`, `db/`, `web/`, `tests/`.

## O que fiz

1. Li a skill (papel cronista, P9), `estado.json` (itens L0-01/L0-02/L0-03/L0-05, ledger, decisões), os handoffs
   `L0-02-tenant-auth/{20,30,31,40,50,99}.md` e `refutacao.json`, `L0-05-jobs/{20,30,31,40}.md` (o 40 ainda em
   escrita: 214 linhas, até a seção 6), os ADRs 0002 (seções 5-11, 14, 17) e 0003 (seções 2, 4-12), `21_esri.md`
   seção 3, `tests/medidas/L0-02-tenant-auth.json` e `L0-05-jobs.json` (árvore de trabalho, 17:28 UTC, `90d03c0`),
   as 13 capturas de `tests/e2e/capturas/` (lidas a olho), `db/migracoes/` (cabeçalhos e sha256), `deploy/`,
   `install.sh`, `app/{main,paginas,limites,settings}.py`, `app/jobs/worker.py`, `web/js/base/layout.js`,
   `web/js/i18n/pt-BR.json`, `docs/openapi.json` (74 rotas, 55 caminhos), `/saude` e `:8153/saude` ao vivo,
   `plat.versao_migracao` e as unidades systemd.
2. `MANUAL.md` (536 linhas): 1 saúde (com `fila` e `worker`), 2 Entrar (senha, bloqueio por usuário e por IP,
   segundo fator, sessão), 3 Minha conta, 4 Usuários, 5 Grupos, 6 Papéis e privilégios, 7 Tokens, 8 Log, 9 Tarefas
   (lista, detalhe/log/cancelar/repetir, tipos, agendas), 10 Administração da plataforma (superadmin, inquilinos,
   `config.auth`, cotas), 11 Instalação (passos a-j com h2), 12 limites conhecidos. Cada tela cita o arquivo da
   captura e o teste que a gera.
3. `ARQUITETURA.md` (635 linhas): componentes e portas (api 8150, worker 8153; 8151/8152 inexistentes),
   repositório, roles `plat_app`/`plat_worker`, tabelas e RLS, contexto, identidade (sessão, senha, TOTP, token,
   log particionado, eventos, superadmin, funções seguras em dois grupos), fila (`plat.job`, correção 006 em três
   camadas, máquina de estados com 008, worker e filho, unidade, SSE, agendas, API), migrações 001-011 com sha256 e
   o que cada uma faz (005 não existe; 011 em construção; 012/013 em construção sem commit), instalador, systemd e
   nginx, contratos, `.env`, log, testes, medidas, front, convenções, o que não existe.
4. `CHANGELOG.md`: entrada `0.2.0 — turno 2` com o que entrou por item, correções 006/008/010/007 por achados, duas
   tabelas de medições com comando, vereditos (L0-02 adversário PASSA em 2 rodadas, gerente `parcial` só por P3/P9;
   L0-05 cláusulas medidas, achado 2 aberto com correção em curso), ressalvas, 24 commits do turno.
5. `docs/PARIDADE.md`: 16 linhas de identidade (estado real feito/parcial/fora, "testado por" testador/adversário
   T2, data 2026-09-05, coluna Pro/AGOL real = pendente D20) e 12 linhas da fila (referência = job de GP e tarefas
   agendadas, do ADR 0003; testado só pelo testador; linha de sobrevivência marcada parcial pelo achado 2).
6. `README.md`: o que existe por turno, tabela de arquivos, comandos, contas de demonstração.
7. `laco/gera_painel.py`: frases em `FUNCOES` para `L0-02-tenant-auth` (7) e `L0-05-jobs` (6, inclusive a cláusula
   aberta) e rótulo para item `pendente` com código no repositório; `python3 laco/gera_painel.py` regerou
   `PAINEL.md` (717 linhas).
8. Conferências: 0 marcador de pendência nos 5 `.md` e no painel; 0 nome de cliente/parceiro; 0 emoji; 13 de 13
   capturas referenciadas existem em disco; `make sem-marcador` rc=0 na árvore inteira antes do commit.
9. Commit `7cd0327` só dos cinco `.md` (`git commit --only`), com o rodapé pedido. Não toquei `app/`, `db/`, `web/`,
   `tests/`, `VERSAO`.
10. **Passe 2**: logo depois do meu commit a trilha B comitou `9be9c6a` (migrações 012 e 013, `worker.py`,
    `test_jobs_identidade.py`; 12 migrações aplicadas, última `013`). Atualizei ARQUITETURA (3.1, 5.3, 5.4, 6, 10.1,
    13), MANUAL (12), CHANGELOG (correções e commits) e PARIDADE (linha de sobrevivência) para descrever 012/013 como
    comitadas e aplicadas, sem veredito; `gera_painel.py` e `PAINEL.md` regerados; commit `4037164` (4 `.md`).

## Evidência (comando + saída literal)

```
$ ls /home/dev/plataforma/laco/handoffs/T2/L0-02-tenant-auth/ ; wc -l .../L0-05-jobs/40_testes.md
20_arquitetura.md 30_backend.md 31_frontend.md 40_testes.md 50_refutacao.md 99_veredito.md refutacao.json
214 /home/dev/plataforma/laco/handoffs/T2/L0-05-jobs/40_testes.md      (sem refutacao.json nem 99_veredito.md no L0-05)

$ python3 -c "import json;d=json.load(open('tests/medidas/L0-02-tenant-auth.json'));print(d['git_sha'],d['gerado_em'],len(d['medidas']))"
90d03c07da0c 2026-09-05T17:28:54Z 35
$ python3 -c "import json;d=json.load(open('tests/medidas/L0-05-jobs.json'));print(d['git_sha'],d['gerado_em'],len(d['medidas']))"
90d03c07da0c 2026-09-05T17:28:50Z 14
$ git show 12b2c2e:tests/medidas/L0-02-tenant-auth.json | python3 -c "..."   (versão comitada, para registro da diferença)
ffedc053429b 2026-09-05T17:13:57Z {'rotas_total': 73, 'rotas_cobertas': 73, 'custo_log_acesso_ms': 0.67, 'latencia_login_ms': 128.7, 'latencia_auth_token_ms': 3.16}

$ curl -sS https://plat.iagrointel.com/saude
{"versao":"0.1.0","git_sha":"abbb03d02920","ambiente":"producao","banco":"ok","migracoes_aplicadas":10,"migracoes_pendentes":0,
 "ultima_migracao":"011_catalogo","servicos":{"martin":"ausente","titiler":"ausente","garage":"ok","worker":"ok"},
 "fila":{"pendentes":5,"rodando":1,"workers_vivos":1,"ultimo_heartbeat":"2026-09-05T17:36:51Z"},"tempo_ms":3.7,"em":"2026-09-05T17:36:58Z"}
$ systemctl is-active plat-api plat-worker → active active · plat-worker NRestarts=6 (kill -9 do test_jobs_reinicio)
$ sudo -u postgres psql -d iagro_sat -Atc "select nome, left(sha256,12) from plat.versao_migracao order by 1"
001_fundacao|74fcdc90a28c 002_identidade|418736611e8a 003_identidade_acesso|725192af189b 004_jobs|ddc21b358ed9
006_jobs_transicoes|3b181c883a16 007_jobs_eventos|558bc552b15c 008_jobs_tentativa|92357250951c 009_inquilino_apagar|68f4506b5a41
010_jobs_gatilhos_execute|ef54d52b29c5 011_catalogo|34c960aa24dd   (arquivo em disco da 011: b997b0c26d8a — trilha ainda editando)

$ ls -la --time-style=+%H:%M tests/e2e/capturas/ | awk '{print $6, $7}'
17:27 L0-01-repo_inicio.png · 17:26 L0-02-tenant-auth_2fa.png · 17:27 conta · grupos · login_erro · login · log · papeis · 17:28 tokens · usuarios
17:28 L0-05-jobs_agendas.png · 17:28 L0-05-jobs_detalhe.png · 17:27 L0-05-jobs_lista.png

$ grep -nE -f tests/marcadores.regex README.md ARQUITETURA.md MANUAL.md CHANGELOG.md docs/PARIDADE.md /home/dev/plataforma/laco/PAINEL.md; echo rc=$?
rc=1
$ grep -niE 'fgr|cbre|novaterra|certel|certaja|sicredi|neoenergia|daiichi|arayara|ineep|corporate|gestao 360|edp|state grid|jamel|robson|potiragu|iagrosat-db' <os 5 .md + PAINEL.md>; echo rc=$?
rc=1
$ for f in $(grep -ohE 'tests/e2e/capturas/[A-Za-z0-9_.-]+\.png' MANUAL.md | sort -u); do [ -f "$f" ] && echo ok $f; done | wc -l
13
$ make sem-marcador >/dev/null 2>&1; echo rc=$?
rc=0     (às 17:4x UTC estava rc=2 por três ocorrências da palavra da expressão de marcadores em web/js/catalogo/*.js não comitados da trilha L0-03; a trilha corrigiu antes do meu commit)

$ python3 /home/dev/plataforma/laco/gera_painel.py
/home/dev/plataforma/laco/PAINEL.md: 717 linhas · entregue 1 · parcial 1 · tentando 1 · refutado 0 · pendente 498

$ git commit -q --only README.md ARQUITETURA.md MANUAL.md CHANGELOG.md docs/PARIDADE.md -F -
$ git log --oneline -1
7cd0327 Documentação do turno 2 (cronista): MANUAL por tela, ARQUITETURA de identidade e fila, CHANGELOG 0.2.0, PARIDADE preenchida, README
$ git show --stat HEAD | tail -6
 ARQUITETURA.md | 951 ++++---  CHANGELOG.md | 167 +-  MANUAL.md | 574 +++--  README.md | 86 +-  docs/PARIDADE.md | 55 +-
 5 files changed, 1308 insertions(+), 525 deletions(-)

# passe 2 (17:54 UTC)
$ sudo -u postgres psql -d iagro_sat -Atc "select nome, left(sha256,12), aplicada_em::timestamp(0) from plat.versao_migracao where nome >= '011' order by 1"
011_catalogo|b997b0c26d8a|17:42:03 · 012_jobs_identidade_worker|a5ff04ed9343|17:40:28 · 013_jobs_execute_reafirma|81b94d28421c|17:51:06
$ curl -sS https://plat.iagrointel.com/saude | python3 -c "..."   → abbb03d02920 12 0 013_jobs_execute_reafirma {'pendentes': 0, 'rodando': 1, 'workers_vivos': 1}
$ curl -s http://127.0.0.1:8153/saude | python3 -c "..."          → worker <host>:3177982 · nome_base <host> · git_sha a06ca71e6e4e
$ make sem-marcador >/dev/null 2>&1; echo rc=$?                     → rc=0
$ git log --oneline -3
4037164 Documentação do turno 2, passe 2 (cronista): absorve as migrações 012 e 013 do commit 9be9c6a
9be9c6a Correção T2 (2) da fila (L0-05, achado do testador): identidade do worker por processo e ceifa só por heartbeat
7cd0327 Documentação do turno 2 (cronista): MANUAL por tela, ARQUITETURA de identidade e fila, CHANGELOG 0.2.0, PARIDADE preenchida, README
```

## Riscos

1. **Árvore de trabalho compartilhada e em mutação durante o passe.** Enquanto eu escrevia: a trilha L0-03 comitou
   `41c1dd9` e `a06ca71` (tela Conteúdo e e2e) e tem `011_catalogo` aplicada no banco com sha diferente do arquivo em
   disco (o sha do arquivo mudou duas vezes durante o passe); a trilha L0-05 comitou `9be9c6a` (012, 013,
   `worker.py`, `test_jobs_identidade.py`) e o passe 2 absorveu isso. Os documentos descrevem o HEAD `9be9c6a` e
   marcam a 011 como "em construção". Quando a trilha L0-03 comitar a 011 e quando testador/adversário derem
   veredito à correção 012/013, `ARQUITETURA.md` seções 3.1, 6 e 13, `MANUAL.md` seção 12, `CHANGELOG.md` (veredito
   do L0-05) e `PARIDADE.md` (linha "sobrevivência a reinício") precisam de outro passe curto.
2. **Regressão de segurança registrada (corrigida pela 013 em `9be9c6a`, aplicada 17:51 UTC):** a 011 faz
   `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app` e devolvia a `plat_app` as funções do worker,
   inclusive `via_worker_ligar`, desfazendo a 006 no banco vivo depois da reinstalação destrutiva. Está escrito em
   `ARQUITETURA.md` 3.1 e no `CHANGELOG.md`. Se a trilha L0-03 reaplicar a 011 editada, o `GRANT ON ALL` volta a
   rodar antes da 013 só numa instalação do zero (a ordem lexicográfica é 011 → 013); numa reaplicação avulsa da 011
   sobre banco vivo a regressão reaparece até a 013 rodar de novo. O gerente decide se a 011 troca o `GRANT ON ALL`
   por grants explícitos antes do commit dela.
3. **Medidas citadas vêm da árvore de trabalho, não do commit.** `tests/medidas/L0-02-tenant-auth.json` e
   `L0-05-jobs.json` estão modificados e não comitados (gerados 17:28 UTC sobre `90d03c0`); a versão comitada do
   L0-02 (`12b2c2e`) difere por décimos de milissegundo (73/73 rotas, 128,7 ms, 0,67 ms, 3,16 ms). Escrevi a
   diferença no ARQUITETURA 10.4. Quem comitar as medidas deve conferir que os documentos continuam batendo.
4. `VERSAO` continua `0.1.0`; a entrada do CHANGELOG é `0.2.0`. Não alterei o arquivo (commit só de `.md`); o
   gerente sobe a versão no fechamento e reinicia `plat-api` (o `git_sha` de `/saude` é `abbb03d`, dois commits
   atrás do HEAD atual).
5. O `40_testes.md` do L0-05 estava incompleto (termina na seção 6; a seção 7, "e2e extra" e a tabela cláusula →
   veredito ainda não existiam). Usei o que há; a medida `primeira_pintura_tarefas_ms` não está no JSON e o manual
   diz isso.
6. Não há `refutacao.json` nem `99_veredito.md` para o L0-05; o CHANGELOG e a PARIDADE dizem "adversário não rodou"
   e "item devolvido a pendente pelo driver às 17:30". Se o gerente fechar o item neste turno, esses dois arquivos
   mudam.
7. `laco/gera_painel.py` e `laco/PAINEL.md` não estão em git (o `laco/` não é repositório): a única cópia é o
   disco.

## Pendências

- Gerente: `99_veredito.md` do L0-05 (ou confirmação de que fica para o T3); `estado.json` (estado dos itens,
  placar `parciais`, ledger com os dois registros de fechamento, `custo_aproximado`); subir `VERSAO` para `0.2.0`;
  reiniciar `plat-api`; reavaliar P3 quando a suíte inteira rodar verde numa rodada única; depois `python3
  laco/gera_painel.py`.
- Gerente/trilha B: comitar 012/013 + `worker.py` + `test_jobs_identidade.py` e pedir o passe curto do cronista
  (lista de seções no risco 1).
- Testador: comitar `tests/medidas/L0-02-tenant-auth.json` e `L0-05-jobs.json` da árvore (ou regravar sobre o HEAD)
  para que os números dos documentos apontem para um arquivo comitado.
- Próximo cronista (L0-03): `docs/PARIDADE.md` ganha a seção do catálogo a partir do `21_esri.md` seção 3.2 só
  depois do testador e do adversário daquele item; `README.md` e `ARQUITETURA.md` já dizem "em construção".
- Decisão do dono: nenhuma nova. D20 (credencial Pro/AGOL) continua sendo o que mantém a coluna "Pro/AGOL real" em
  `pendente`.

## Para o próximo papel (gerente)

1. P9 do L0-02: MANUAL (seções 2-8 e 10), ARQUITETURA (seções 3, 4, 6-10), CHANGELOG 0.2.0, PARIDADE (16 linhas) e
   README estão comitados em `7cd0327`; a cláusula "paridade escrita" (P4) está preenchida com estado real e
   "testado por" = testador/adversário T2, Pro/AGOL real = pendente (D20).
2. P9 do L0-05: MANUAL seção 9 e 12, ARQUITETURA seção 5 e 6, CHANGELOG e PARIDADE (12 linhas) escritos sobre o
   HEAD; o achado 2 e a correção em curso estão nomeados em todos eles. O veredito do item é seu.
3. `laco/PAINEL.md` mostra L0-02 `parcial` com 7 frases de função e L0-05 `pendente` com 6 frases (inclusive a
   cláusula aberta), como está no `estado.json`.

## Resumo em 6 linhas

1. Cinco documentos escritos e comitados em `7cd0327` (1.308 linhas inseridas) e atualizados em `4037164` (passe 2): MANUAL por tela com 13 capturas reais, ARQUITETURA de identidade e fila com migrações 001-011, CHANGELOG 0.2.0, PARIDADE (16 + 12 linhas), README.
2. Números só de `tests/medidas/L0-02-tenant-auth.json` (35 chaves) e `L0-05-jobs.json` (14) da árvore, mais `refutacao.json` do L0-02; a diferença para a versão comitada das medidas está registrada.
3. Vereditos como estão: L0-02 adversário PASSA em 2 rodadas (gerente `parcial` só por P3/P9); L0-05 com correções 006/008/010 e, para o achado 2, 012/013 comitadas em `9be9c6a` sem veredito do testador e do adversário.
4. Regressão registrada para o gerente: a 011 (catálogo, em construção) refaz `GRANT ON ALL FUNCTIONS` e desfazia a separação `plat_app`/`plat_worker` da 006; a 013 corrige (comitada e aplicada), mas a 011 ainda não comitada deve trocar o `GRANT ON ALL` por grants explícitos.
5. `laco/PAINEL.md` regenerado (717 linhas; entregue 1 · parcial 1 · tentando 1 · pendente 498) com as funções reais dos dois itens.
6. Pendências do gerente: `99_veredito.md` do L0-05 (agora com 012/013 comitadas, veredito do testador e do adversário sobre a correção), `estado.json` e ledger, `VERSAO` 0.2.0 + reinício da API (`/saude` diz `abbb03d`, HEAD é `4037164`), commit das medidas pelo testador, passe curto do cronista quando a 011 entrar.
