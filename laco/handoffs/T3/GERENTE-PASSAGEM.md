# Repasse do gerente — consolidação da orquestração na sessão wt/* (06/09/2026)

Escrito pela sessão `a44f35ad` (gerente até agora) no momento da decisão do dono de
consolidar toda a eleição/lançamento/junção de ramos na sessão das worktrees
(`/home/dev/plataforma/wt/{garage,stac,valida,amc}`, alcunha "dev-41" /
"enterprise-automation-loop-speedup"). A partir daqui esta sessão vira ADVERSÁRIO
dedicado; não lança mais agentes construtores.

## Placar no momento deste repasse

`entregues: 40 · parciais: 20 · refutados: 3 · pendentes: ~443 · total: 506 · turno: 3`
(conferir `python3 -c "import json;print(json.load(open('estado.json'))['placar'])"` para o número exato agora — os 4 agentes abaixo ainda estavam fechando quando este arquivo foi escrito).

## O que ficou pela metade (os 4 agentes do último lançamento)

Todos os 4 sofreram `429 rate_limit` (limite de sessão do modelo, não erro de código) e
foram RETOMADOS via `SendMessage` para o mesmo agentId assim que a cota resetou
(3h20 UTC). Ao escrever este repasse, ainda estavam terminando:

| item | estado no disco (git status) | o que faltava quando parou |
|---|---|---|
| `L0-04-a-upload-arquivo` | `app/uploads/`, `db/migracoes/046_upload_retomavel.sql`, `tests/api/uploads/`, `tests/e2e/test_uploads.py`, `web/uploads.html`, `web/js/uploads/` — **tudo `??` (não commitado)** | estava rodando o e2e de verdade quando cortou; commit ainda não feito |
| `L0-07-d-smtp-convites` | `app/auth/modelos_convite.py`, `modelos_redefinicao.py`, `rotas_convites.py`, `rotas_redefinicao.py`, `app/correio/`, `db/migracoes/047_smtp_convites_redefinicao.sql`, `tests/api/test_smtp_convites.py`, `web/aceitar_convite.html`, `web/redefinir_senha.html` — **tudo `??` (não commitado)** | estava escrevendo `docs/adr/0017-smtp-convites-redefinicao.md` (confirmou que 0017 está livre) quando cortou |
| `L0-07-b-papeis-privilegios` | já tem 3 commits em master (`2520afd`, `1b0ad94`, `90ab545`) | estava conferindo se `MANUAL.md`/`docs/PARIDADE.md` ficaram limpos depois do commit do geocodificador de outro agente (arquivos compartilhados, risco de conflito de edição) |
| `L2-11-b-geocodificador-brasil` | já commitado (`3a69591`) | estava re-rodando a suíte com o estado committado pra confirmar que sha bate (nenhuma mudança de código pendente, só verificação) |

**Se esta sessão herdar o laço antes desses 4 terminarem**: as duas migrações novas
acima (`046_upload_retomavel.sql`, `047_smtp_convites_redefinicao.sql`) ainda não
foram commitadas — confira `ls db/migracoes | tail -5` antes de qualquer nova migração
para não colidir com elas quando commitarem.

## Arquivos que esta sessão tocou nas últimas horas (fora dos itens de backlog)

- `/home/dev/.claude/skills/plataforma-enterprise/SKILL.md` — adicionadas 4 regras novas hoje: commit sempre escopado por pathspec; `CursorSchemaAmbiente` só reescreve `str` (bytes/`execute_values` fura o isolamento de schema fora do padrão); teto conjunto de agentes (histórico, já superado pela decisão de hoje); `flock` obrigatório em toda leitura-modificação-escrita de `estado.json`.
- `tests/api/conftest.py` (commit `a34e745`) — `PLAT_CREDENCIAIS_TOTP_ARQUIVO` parametrizado (mesmo padrão de `PLAT_CREDENCIAIS_ARQUIVO`); sem isso, todo ambiente escreve no mesmo `tests/credenciais_totp.txt` do repo e trilhas concorrentes se atropelam ligando 2FA quase ao mesmo tempo.
- `laco/gera_painel.py` — vários acréscimos ao dicionário `FUNCOES` (uma frase por item entregue/parcial); rodar `python3 gera_painel.py` sempre avisa se algum item ficou sem frase.
- `laco/estado.json` — dezenas de atualizações de ledger/placar/notas/decisoes_do_dono (D39, D40 novos).

## Armadilhas que só esta sessão viu hoje (não estão em nenhum outro lugar ainda)

1. **Exaustão de cota de token do usuário demo (falso alarme de regressão)**: um `make check-rapido` deu 36 failed/165 errors, TODOS em `test_cruzado.py`, por `usuario_id=1` (admin do inquilino demo) ter batido no limite de 20 tokens ativos — uma trilha criou 16 tokens `smoke-ingestao` numa rajada de 3 minutos sem revogar. Não é regressão de código. Se isso reaparecer: `SELECT usuario_id, count(*) FROM plat.token_servico WHERE revogado_em IS NULL AND (expira_em IS NULL OR expira_em > now()) GROUP BY usuario_id` e revogar o excesso.
2. **Migração 030 tinha sha divergente do registrado** — já reconciliado (arquivo é idempotente, tabela já batia, só o hash registrado em `plat.versao_migracao` estava desatualizado). Se `db/migrar.sh` reclamar de novo do 030, é o mesmo padrão: confira se o schema já bate antes de desconfiar do arquivo.
3. **Quase perdi trabalho alheio com `git commit -m` sem pathspec**: nesta árvore compartilhada, um `git commit -m "..."` sem arquivo varre TUDO que está staged, não só o que você acabou de adicionar. Aconteceu comigo, corrigi sem perda (`git reset --soft HEAD~1` + `git restore --staged` nos arquivos alheios), registrado no SKILL.md. **Todo commit daqui pra frente tem de ser `git commit -- <arquivo> -m "..."`.**
4. **Lock ausente em `estado.json` causou perda silenciosa de escrita**: a outra sessão registrou uma decisão (D37 na numeração dela) que sumiu porque minha escrita concorrente sobrescreveu sem nenhum dos dois travar o arquivo. Mesclei o conteúdo perdido dentro do meu D40. **Toda edição de `estado.json` agora tem de rodar dentro de `flock /home/dev/plataforma/laco/.estado.lock <comando>`** — já é regra no SKILL.md.
5. **Bloqueio de login (423) do superadmin real `plataforma`**: aconteceu 3 vezes hoje entre as duas sessões, por corrida de trilhas testando 2FA no mesmo usuário real de operação. Desbloqueio: `UPDATE plat.usuario SET bloqueado_ate=NULL, falhas_login=0, falhas_desde=NULL WHERE bloqueado_ate IS NOT NULL;`. É estrutural (D40 em aberto para o dono: superadmin de teste dedicado vs. migrar tudo para `trilha_ambiente.sh`), não conserte sozinho sem decisão do dono.
6. **`CursorSchemaAmbiente.execute` só reescreve consultas tipo `str`** — `psycopg2.extras.execute_values` (e qualquer coisa que gere bytes) passa direto e fura o isolamento de schema fora do padrão (homologação, `trilha_ambiente.sh`). Inofensivo em produção (schema padrão). Conserto vindo do lado da outra sessão (`wt/amc`).

## Para quem herda a orquestração

- `estado.json`, `PAINEL.md`, `DIARIO.md` estão atualizados até este ponto (rodar `python3 gera_painel.py && python3 gera_diario.py` depois que os 4 últimos itens fecharem, sob o flock).
- Migrações em master terminam em `045` (conferir `ls db/migracoes | tail -1` na hora — os 2 novos itens acima ainda vão trazer `046`/`047` quando commitarem).
- Esta sessão passa a atacar por LINHA, na ordem: identidade/sessão/2FA → isolamento entre inquilinos → dado de cliente/arquivo enviado → fila de trabalhos/catálogo. Laudos em `handoffs/T3/<linha>-ADVERSARIO.md`.
