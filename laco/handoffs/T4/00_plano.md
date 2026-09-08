# T4 — plano do turno (autoturno, sessão plataforma-d7 [229ec3])

Contexto que muda o papel desta sessão: o driver disparou o PRIMEIRO autoturno do laço às 16:00
(o `claude` sem caminho absoluto vinha falhando desde 05:00). Ao abrir, a sessão
`enterprise-automation-loop-speedup` (dev-41) informou decisão do dono: **supervisor único é ela**.
Portanto esta sessão NÃO elege itens, NÃO junta ramo e NÃO bumpa `turno` no estado; ela executa a
faixa exclusiva que o supervisor atribuiu e devolve ramos prontos para o supervisor juntar.
`laco/.turno_ativo` fica gravado só para impedir um segundo autoturno concorrente.

Faixa atribuída (sem interseção com o que o supervisor tem em voo): L1-01-ingest-raster ·
L0-07-admin-org · L0-08-sso · L3-19-multiescala · L6-01-h-frescor-verificacao · L6-01-j-multi-servidor ·
L7-20-trilha-auditoria · L7-08-d-portal-api-chaves · L0-05-e-justica-entre-inquilinos.

## Trilhas deste turno

| item | área tocada | worktree/ramo | porta | base de teste | papéis | colide com |
|---|---|---|---|---|---|---|
| L7-20-trilha-auditoria | `app/auditoria/` (novo), migração `plat.auditoria`, middleware de escrita, `web/auditoria.html` | `wt/t4aud` | 8171 | `plat_tt4aud` | dados, backend, frontend, testador, adversário | `app/main.py` (registro de rota) — mudança mínima |
| L6-01-h-frescor-verificacao | `app/acervo/frescor.py` (novo), periódico próprio, ficha da fonte | `wt/t4fres` | 8172 | `plat_tt4fres` | backend, testador, adversário | `app/acervo/*` — o supervisor NÃO tem L6-01-h em voo (tem L6-01-b, outro arquivo) |
| L7-08-d-portal-api-chaves | `web/vendor/` (Scalar), `app/auth/chaves*.py`, escopo `x-plat-escopo` no OpenAPI | `wt/t4port` | 8173 | `plat_tt4port` | backend, frontend, testador, adversário |`app/main.py`, `docs/openapi.json` — mudança mínima |

Descartado de propósito: **L0-07-c-cotas-uso**, apesar de estar na faixa. As três dependências dele
(`L0-04-c-tabela-camada`, `L0-11-arquivos-objetos`, `L0-05-d-periodicos`) estão REFUTADAS e estão
sendo consertadas AGORA pelo supervisor; construir cota sobre `d_<slug>` e sobre a agenda periódica
enquanto as duas mudam produz conflito de merge, não produto. Fica para o turno seguinte.
Descartado também **L0-08-a-oidc**: exige Keycloak em contêiner (imagem nova com disco a 91 %) e as
duas dependências dele também estão refutadas; é item de turno inteiro, não de trilha paralela.

## Ordem e paralelismo

Teto combinado de agentes: 4-6 desta sessão (`vigia.sh` deu SOBE às 16:04: RAM 7.356 MB, pressão 0,00,
49/100 conexões, carga 16,93). Levas: (1) 3 construtores em paralelo, um por trilha; (2) 3 adversários
independentes em paralelo, cada um em contexto próprio, sem ler o handoff do construtor.

## O que será medido (vai para `tests/medidas/<item>.json`)

- L7-20: nº de rotas de escrita do OpenAPI cobertas / total; tempo do expurgo; contagem exportada × contagem em tabela.
- L6-01-h: nº de camadas verificadas e minutos do job; nº de endpoints testados e vivos; nº de verificações no histórico.
- L7-08-d: nº de rotas do OpenAPI com `x-plat-escopo`; nº de recursos externos carregados pelo portal (tem de ser 0); segundos entre revogar e 403.

## O que NÃO se faz neste turno

Não se junta nada em `master` (o supervisor junta). Não se aplica migração no schema `plat` de
produção. Não se mexe em `laco/estado.json` a não ser por `marcar_item.py` (que trava). Não se
reinicia `plat-api`/`plat-worker`. Não se toca em worktree alheio nem nos itens em voo do supervisor.

## Desvios registrados durante o turno (16:00-16:20)

1. **Papel desta sessão mudou no meio**: o supervisor confirmou a decisão do dono (supervisor único) e
   pediu que esta sessão fosse EXECUTOR da fila dele. `.turno_ativo` fica gravado por acordo explícito
   dele, só para impedir um segundo autoturno; não é reivindicação de turno. `estado.json` não é
   editado por esta sessão (nem `turno`, nem placar); os itens são marcados só depois do adversário.
2. **`prompt_item.py` passou a descobrir trilha do disco** (pedido do supervisor): `TRILHAS` sai de
   `laco/var/trilha/*.env`; portas novas saem de 8165-8199 e ficam gravadas em
   `laco/var/trilha/portas.json`; as quatro históricas continuam cravadas. Cópia do arquivo original
   em `/tmp/prompt_item.py.bak`.
3. **Colisão de porta real, achada e evitada**: a primeira versão do alocador entregou 8171/8172/8173
   (portas já em mão dos meus três agentes) a g4fix/l09a/l208a. Conserto: o alocador pula toda porta
   que está ESCUTANDO agora (`ss -ltnH`), não só as que ele mesmo distribuiu. E a colisão não era
   hipótese: `wt/stac` subiu um servidor de e2e com TLS na 8172 às 16:07 (pid 2489722), depois de eu
   ter dado a 8172 ao agente do L6-01-h. O agente foi movido para **8190**. Porta de rede é recurso
   partilhado da máquina sem dimensão de trilha — mesma família do achado que derrubou 38 itens hoje.
4. **`t4cota` abortado no meio e schema derrubado**: sobra da escolha de item descartada; não é resíduo.
5. **pg_cron vira regra escrita**: o agente do L7-20 recebeu ordem de pôr a mitigação no ADR como
   regra para quem vier depois (nome do job derivado de `current_schema()`, agendamento idempotente,
   desagendar ao fim, nome de job tratado como recurso partilhado), com teste que prove a regra.
6. **Faixa seguinte acordada com o supervisor**: L3-19-multiescala e L6-01-j-multi-servidor podem
   começar assim que houver folga de agente; **L0-05-e-justica-entre-inquilinos fica bloqueado** até o
   supervisor commitar o conserto da dimensão de inquilino da fila (achado do adversário G3) e passar
   o sha — construir contra o conserto, e não em cima dele, seria trabalho jogado fora.
