# HANDOFF — para quem retomar este trabalho em outra ferramenta (Codex CLI ou qualquer agente)

Gerado por Claude Code em 06/09/2026 ~01:00 UTC, turno 2 do laço PLATAFORMA ENTERPRISE.
Isto NÃO é a conversa anterior — é o estado no disco, que é a única coisa que qualquer
agente novo pode herdar. Leia este arquivo inteiro antes de tocar em qualquer coisa.

## O que é isto

Construção de um produto chamado internamente **`plat`** (codinome; nome público ainda
não decidido — D18 em aberto): uma plataforma SIG corporativa própria, 100% pilha aberta,
que substitui o ArcGIS Enterprise. Dono: iAgroSat/iAgroIntel. Máquina: este servidor
(Vultr, `/home/dev`), Postgres 16 + PostGIS local, RAM total 23 GB (**tipicamente só
2-3 GB livres — não assuma folga**), disco a 98% (13 GB livres).

## Onde está tudo (leia nesta ordem)

1. `/home/dev/CLAUDE.md` — regras da CASA INTEIRA (não só deste produto). Se você vai
   tocar em QUALQUER outra pasta além de `plataforma/`, leia antes — há dezenas de
   outros projetos no mesmo servidor com regras próprias (nunca mexer, nomes de
   cliente proibidos, etc.).
2. `/home/dev/.claude/skills/plataforma-enterprise/SKILL.md` — a especificação
   completa do laço: papéis (gerente, arquiteto, esri, backend, frontend, testador,
   adversário, cronista), o turno passo a passo, os 9 portões gerais (P1-P9), as
   regras que já custaram caro (pkill, migração numerada na hora, flock no pytest).
   **Isto é o "system prompt" do trabalho — trate como instrução, não como histórico.**
3. `/home/dev/plataforma/laco/estado.json` — o estado vivo: 504 itens de backlog,
   cada um com hipótese, portão de pronto (verificável, literal) e refutação exigida.
   Campo `estado` de cada item: `pendente | tentando | parcial | entregue | refutado`.
4. `/home/dev/plataforma/laco/PAINEL.md` — placar e fronteira (o que o produto FAZ
   hoje, frase por frase, e o que NÃO faz ainda), gerado por `gera_painel.py`.
5. `/home/dev/plataforma/laco/DIARIO.md` — o diário corrido: linha do tempo por
   commit, ledger, vereditos de adversário, números medidos, decisões abertas.
   Gerado por `gera_diario.py`. **Leia este para saber o que já aconteceu.**
6. `/home/dev/plataforma/laco/handoffs/T<n>/` — comunicação entre papéis do turno
   atual, um arquivo por etapa (`20_arquitetura.md`, `30_backend.md`, `40_testes.md`,
   `refutacao.json`, `99_veredito.md`). O turno 2 (`T2`) está em andamento agora.
7. `/home/dev/plataforma/enterprise/` — o repositório do produto (git). `docs/adr/`
   tem 5 decisões de arquitetura já tomadas e comitadas (0001-fundação, 0002-
   identidade, 0003-fila de jobs, 0004-catálogo, 0005-ingestão vetorial).
8. `/home/dev/plataforma/laco/decomposicao/*_CONCEITO.md` — 147 decisões de conceito
   por linha de produto (L0-L7), cada uma com opções, custo de mudar depois e
   recomendação. **Não redecidir o que já está aqui sem motivo forte.**

## Estado exato agora (turno 2)

- **L0-01-repo**: `entregue`. Instalação do zero em 6s, 82 testes, adversário PASSA
  2 rodadas (incluindo reinstalação destrutiva).
- **L0-02-tenant-auth**: `parcial`. Adversário PASSA 2 rodadas (73/73 rotas sem
  vazamento cruzado, RLS 22/22, 2FA, tokens com escopo). Falta só: suíte inteira
  verde (P3) + fechamento da documentação (P9).
- **L0-05-jobs**: `parcial`. Adversário PASSA (kill -9 x4, forja por SQL bloqueada,
  1.614 jobs/min). Os 3 consertos pedidos pelo testador já foram commitados
  (semeadura de demo, privilégio `jobs.ver`, Cache-Control único). Falta: suíte
  inteira verde.
- **L0-03-catalogo**: backend fechado (612/612 testes, 10 bugs reais corrigidos,
  2 de privacidade), adversário **PASSA** (5 ataques essenciais, todos resistiram).
  **Testador ainda rodando `make medidas` contra a URL real** — pode já ter
  terminado quando você ler isto; confira `handoffs/T2/L0-03-catalogo/40_testes.md`.
- Serviços vivos: `systemctl status plat-api plat-worker` (ambos devem estar `active`).
- URL interna: `https://plat.iagrointel.com` (noindex, nunca linkar de lugar público).

## O que fazer a seguir (se você for continuar o laço)

1. Se `40_testes.md` do L0-03 existe e passa: os TRÊS itens (L0-02, L0-05, L0-03)
   podem fechar para `entregue` — rode a suíte inteira (`make check` sob
   `flock /home/dev/plataforma/laco/.pytest.lock`), escreva `99_veredito.md` para
   L0-03, atualize `estado.json` (os 3 itens → `entregue`), rode `gera_painel.py` e
   `gera_diario.py`, comite.
2. Depois disso, turno 3 abre as próximas trilhas: `L0-04-ingest-vetor` (ADR 0005
   já escrito) e `L0-06-backup-status`, mais qualquer item da linha L1/L2 sem
   dependência aberta. Ver `estado.json` para o portão exato de cada um.
3. **Item novo pendente de direção do dono**: `L0-14-identidade-visual` — as telas
   atuais são funcionais mas sem identidade visual própria ("parece IA genérica",
   palavras do dono). Ele ainda não escolheu a direção (instrumento escuro denso /
   documento de campo claro / algo com mais atitude). NÃO comece a construir esse
   item sem essa direção — pergunte, não invente.

## Regras que NÃO podem ser esquecidas (custaram caro)

- **Nunca** editar nada fora de `/home/dev/plataforma/` sem ler o `CLAUDE.md` da
  raiz primeiro — o servidor tem dezenas de outros projetos do mesmo dono.
- **Nunca** `pkill -f uvicorn` (mata serviços de outros projetos no mesmo servidor).
  Serviço só por `systemctl`.
- Toda migração nova: `ls db/migracoes | tail -1` para pegar o próximo número
  ANTES de criar o arquivo — não reservar número no ADR (já colidiu uma vez).
- Todo `pytest`/`make check`/`make medidas`: dentro de
  `flock /home/dev/plataforma/laco/.pytest.lock <comando>` — dois em paralelo na
  mesma árvore invalidam sessões de demo e disputam o único slot do worker (medido).
- Sem placeholder: `TODO`/`FIXME`/mock/rota que devolve dado fixo = erro de build.
  A varredura em `Makefile` (`make sem-marcador`) reprova por isso.
- Sem nome de cliente/parceiro em código ou dado de exemplo (regra da casa) — usar
  "SIG de teste interno", "motor logístico", etc.
- Commit em português, sem emoji, com o rodapé de atribuição do momento (pergunte
  ao dono qual modelo/atribuição usar se não estiver óbvio na sessão).
- Disco a 98%: nunca baixar/gerar > algumas centenas de MB sem checar `df -h`.

## Se você (Codex) só quer OLHAR, não construir

Rode, sem tocar em nada:
```
cat /home/dev/plataforma/laco/PAINEL.md
cat /home/dev/plataforma/laco/DIARIO.md
python3 -c "import json;e=json.load(open('/home/dev/plataforma/laco/estado.json'));print(e['placar'])"
systemctl status plat-api plat-worker --no-pager
```
