# plat — plataforma SIG corporativa, pilha aberta

Codinome `plat`. Objetivo do laço que o constrói: substituir o ArcGIS Enterprise para o cliente, em pilha 100 %
aberta. Este README descreve só o que EXISTE no repositório no fim do turno 2 (setembro de 2026); o que ainda não
existe está em `/home/dev/plataforma/laco/PAINEL.md` e na seção final de `ARQUITETURA.md`, nunca aqui.

Estado: análise / beta privado. URL interna `https://plat.iagrointel.com` (noindex, nunca linkar de lugar público).
`VERSAO` diz `0.1.0`; a entrada `0.2.0` do `CHANGELOG.md` descreve o turno 2 e o gerente sobe o arquivo no
fechamento.

## O que existe

- **Fundação (turno 1)**: serviço `plat-api` (FastAPI, 127.0.0.1:8150) com `/saude`, `/api/versao`, `/api/docs`
  sem CDN; nginx com HTTPS, `noindex` e HSTS em toda resposta; migrações por sha256 (`db/migrar.sh`); instalador
  idempotente (`install.sh`); dependências fixadas; `make check`.
- **Identidade e acesso (turno 2, item L0-02)**: inquilinos isolados por RLS em toda tabela com `tenant_id`;
  login com senha (pbkdf2, política por inquilino, bloqueio 5/15 min por usuário e 10 r/min por IP), segundo
  fator TOTP com códigos de recuperação, sessão por cookie com hash no banco, tokens de serviço com escopo,
  restrição de origem e IP, rotação e revogação imediata; 46 privilégios, 4 perfis, papéis personalizados, grupos;
  log de acesso por requisição (inclusive por token, com IP, rota e bytes) e eventos de domínio, particionados por
  mês; superadmin em inquilino técnico `plataforma` (2FA obrigatório) com API de inquilinos; telas Entrar, Minha
  conta, Usuários, Grupos, Papéis, Tokens e Log.
- **Fila de trabalhos (turno 2, item L0-05)**: `plat.job` com RLS, worker `plat-worker` (unidade systemd,
  `MemoryMax=2G`) que executa cada job num processo filho com limite de memória, cancelamento, retentativa,
  sobrevivência a reinício (retoma ou marca falha, nunca some), role `plat_worker` exclusiva para mudar estado,
  progresso em tempo real por SSE, agendas por cron com fuso, cotas por inquilino, periódico de expurgo; tela
  Tarefas; 6 tipos de diagnóstico.
- Em construção nesta árvore por outra trilha: catálogo de conteúdo (item L0-03, ADR 0004, migração 011).

## Arquivos

| arquivo | conteúdo |
|---|---|
| `ARQUITETURA.md` | componentes e portas, repositório, roles e tabelas, identidade (sessão, senha, TOTP, token, log, superadmin), fila (job, worker, transições, SSE, agendas), migrações 001-011, instalador, systemd, nginx, contratos, configuração, testes, front, convenções, o que ainda não existe |
| `MANUAL.md` | uma seção por tela, com a captura do e2e: saúde, Entrar, Minha conta, Usuários, Grupos, Papéis, Tokens, Log, Tarefas, administração da plataforma, instalação, limites conhecidos |
| `CHANGELOG.md` | uma entrada por turno, com medições, vereditos e commits |
| `docs/adr/` | 0001 fundação · 0002 identidade e acesso · 0003 fila de jobs · 0004 catálogo (preparação) · 0005 ingestão vetorial (preparação) |
| `docs/openapi.json` | gerado por `make openapi`, comitado; 74 rotas em 55 caminhos, cada uma com `x-auth` e `x-privilegio` |
| `docs/PARIDADE.md` | tabela viva contra o ArcGIS Enterprise: 16 linhas de identidade e 12 da fila, com estado, quem testou e data; Pro/AGOL reais pendentes (D20) |
| `install.sh` | `sudo bash install.sh <dominio> [porta]`; idempotente; passos a-j |
| `Makefile` | `check`, `check-rapido`, `lint`, `sem-marcador`, `teste`, `e2e`, `e2e-worker`, `medidas`, `vendor`, `migrar`, `openapi`, `worker` |
| `app/` | API (`auth/`, `jobs/`, `erros.py`, `paginas.py`, `limites.py`, ...) |
| `db/` | `migrar.sh` e `migracoes/NNN_*.sql` |
| `deploy/` | modelos de `plat-api.service`, `plat-worker.service` e do bloco nginx |
| `web/` | telas (módulos ES sem bundler, base reutilizável em `js/base/`, dicionário `js/i18n/pt-BR.json`) e `vendor/` com versão no nome, sha256 e licença |
| `tests/` | `unit/`, `api/`, `api/jobs/`, `e2e/` (capturas em `e2e/capturas/`, fora do git), `medidas/<item>.json` (único lugar de onde documento cita número) |

## Comandos

```
sudo bash install.sh plat.iagrointel.com 8150   # instala ou atualiza (api + worker + nginx)
make check                                       # suíte inteira (ruff, marcadores, testes rápidos, e2e)
make e2e-worker                                  # testes lentos da fila (job de 5 min, reinício, kill -9)
curl -sS https://plat.iagrointel.com/saude       # 200, banco ok, fila.workers_vivos >= 1
```

Contas de demonstração: inquilinos `demo` e `demo2` (administrador `admin`), inquilino técnico `plataforma`
(operador `admin`, superadmin, 2FA obrigatório); senhas em `tests/credenciais.txt` (modo 600, fora do git), geradas
pelo `install.sh`.

Construído pelo laço `/home/dev/plataforma/laco/` (estado, portões, adversário, ledger, handoffs por turno).
Regras do laço: `~/.claude/skills/plataforma-enterprise/SKILL.md`.
