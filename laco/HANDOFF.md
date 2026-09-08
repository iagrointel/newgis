# HANDOFF — para quem retomar este trabalho em outra ferramenta/chat/agente

Gerado por Claude Code em 06/09/2026 ~12:20 UTC, turno 3 do laço PLATAFORMA ENTERPRISE.
Isto NÃO é a conversa anterior — é o estado no disco, a única coisa que qualquer
agente novo pode herdar. **Leia este arquivo inteiro antes de tocar em qualquer coisa.**

## O que é isto

Construção de **`plat`** (codinome; nome público não decidido — D18 em aberto): uma
plataforma SIG corporativa própria, 100% pilha aberta, que substitui o ArcGIS
Enterprise. Dono: iAgroSat/iAgroIntel. Servidor: Vultr, `/home/dev`, Postgres 16 +
PostGIS local. **RAM tipicamente só 2-3 GB livres, load average 5-8 — servidor
COMPARTILHADO com ~99 processos de outras sessões não relacionadas. Disco a 98%
(11-13 GB livres em / e /mnt/pgdata).**

## Estado exato agora

- **32 entregue · 7 parcial · 466 pendente, de 505 itens.** 75 commits, 27 migrações,
  ~19.700 linhas Python/SQL, ~8.750 linhas web.
- Serviços vivos: `systemctl status plat-api plat-worker` (ambos `active`).
- URL interna: `https://plat.iagrointel.com` (noindex, nunca linkar publicamente).
- **Frequentemente há 5-10 agentes rodando em paralelo neste exato momento** —
  confira `laco/handoffs/T3/` por arquivos recém-criados e `git log` antes de
  presumir que algo não foi feito.

## Onde está tudo (leia nesta ordem)

1. `/home/dev/CLAUDE.md` — regras da CASA INTEIRA. Dezenas de outros projetos no
   mesmo servidor, cada um com regras próprias (nunca mexer sem ler).
2. `/home/dev/.claude/skills/plataforma-enterprise/SKILL.md` — especificação do
   laço inteira: papéis, o turno passo a passo, portões P1-P9, trilhas paralelas,
   regras que já custaram caro (migração numerada na hora, flock no pytest,
   extração de OSM/geodado nunca em memória sem limite).
3. `/home/dev/plataforma/laco/estado.json` — 505 itens de backlog, cada um com
   hipótese, portão de pronto verificável e refutação exigida.
4. `/home/dev/plataforma/laco/PAINEL.md` — o que o produto FAZ hoje, frase por
   frase, e a fronteira do que NÃO faz. `laco/DIARIO.md` — log corrido por
   commit/ledger/veredito/número medido. **Ambos gerados por `gera_painel.py`/
   `gera_diario.py` — nunca editar à mão, rodar os scripts.**
5. `/home/dev/plataforma/laco/handoffs/T3/` — comunicação entre papéis do turno
   atual, um arquivo por item conforme termina.
6. `/home/dev/plataforma/enterprise/` — o repositório (git). `docs/adr/` tem
   ~10 decisões de arquitetura tomadas e comitadas.
7. `/home/dev/plataforma/laco/decomposicao/*_CONCEITO.md` — ~150 decisões de
   conceito por linha de produto (L0-L7). **Não redecidir sem motivo forte.**
8. **Sistema de identidade visual "instrumento"** (decisão do dono 06/09):
   `web/estilo/tokens.css` — fundo quase preto, acento âmbar (nunca azul de
   sistema), Big Shoulders Display para rótulos, IBM Plex Sans/Mono para texto e
   dado, moldura com tique de canto. Só a tela de entrada usa isso hoje; as
   outras telas ainda migram uma a uma (item `L0-14-identidade-visual`, parcial).

## O que já roda (real, testado, com adversário)

- **Identidade**: login/2FA/tokens/grupos/papéis/LDAP-AD, RLS em toda tabela,
  73+ rotas sem vazamento cruzado, adversário PASSA.
- **Fila de jobs**: progresso por SSE, cancelamento, sobrevive a restart/kill -9,
  1.614 jobs/min, 5 periódicos, worker também em contêiner Docker (opcional).
- **Catálogo de conteúdo**: itens/pastas/tags/busca/compartilhamento/lixeira/
  versões imutáveis, 612+ testes, adversário PASSA, 10 bugs reais corrigidos
  (2 de privacidade).
- **Arquivos/objetos**: Garage por inquilino, sha256, multipart.
- **Primeira tela de mapa**: MapLibre + PMTiles local (OSM/Guarulhos), sem
  serviço externo.
- **Parser de expressão** (núcleo, tipo Arcade): Python+JS concordantes, sem
  eval/exec.
- **Rota/matriz/isócrona**: OSRM isolado, próprio, dado pequeno.
- **Segurança/operação**: segredos fora do `.env` (LoadCredential systemd),
  assinatura Ed25519 de release, ambiente de homologação isolado (schema
  `plat_homolog`), scanner de CVE (pip-audit).
- **O que NÃO existe ainda**: quase todo L1 (imagens/COG/STAC), L2 (mapa
  completo/edição/FeatureServer), L3 (motor multicritério), L4 (rede de
  utilidades), L5 (construtores). Ver `laco/PAINEL.md` para a lista exata.

## Regras que NÃO podem ser esquecidas (custaram caro)

- **Nunca** editar nada fora de `/home/dev/plataforma/` sem ler `CLAUDE.md` primeiro.
- **Nunca** `pkill -f uvicorn`/`pkill -f` com padrão largo — mata serviços de
  outros projetos no mesmo servidor. Serviço só por `systemctl`.
- Toda migração nova: `ls db/migracoes | tail -1` para o próximo número ANTES de
  criar o arquivo — já colidiu mais de uma vez com trilhas concorrentes.
- Todo `pytest`/`make check`: dentro de `flock /home/dev/plataforma/laco/.pytest.lock
  <comando>` — dois em paralelo invalidam sessões de demo e disputam o único
  slot do worker. **Isso significa fila real: rodar a suíte inteira pode levar
  10+ minutos com várias trilhas concorrentes — não é bug, é o preço da
  segurança de dado compartilhado.**
- Extração de OSM/geodado NUNCA em modo padrão em memória — já derrubou o
  Postgres uma vez (`osmium extract` sem limite). Usar streaming/baixo consumo
  e checar `free -g` antes.
- Numa árvore com várias trilhas: `git add <arquivo específico>`, NUNCA
  `git add -A` — outros agentes têm trabalho não commitado na mesma árvore.
- Sem placeholder: `TODO`/`FIXME`/mock/rota com dado fixo = erro de build
  (`make sem-marcador` reprova).
- Sem nome de cliente/parceiro em código ou dado de exemplo — usar "SIG de
  teste interno", "motor logístico", etc.
- Commit em português, sem emoji, com o rodapé de atribuição do momento.

## Como continuar

Se for um agente Claude Code com a skill instalada: `/plataforma-enterprise`
retoma o laço direto. Se for outra ferramenta: leia `estado.json`, escolha um
item `pendente` sem dependência aberta (campo `dependencias`, todas precisam
estar `entregue`), siga o portão de pronto literal, registre no ledger.

## Se você só quer OLHAR, não construir

```
cat /home/dev/plataforma/laco/PAINEL.md
cat /home/dev/plataforma/laco/DIARIO.md
python3 -c "import json;e=json.load(open('/home/dev/plataforma/laco/estado.json'));print(e['placar'])"
systemctl status plat-api plat-worker --no-pager
```
