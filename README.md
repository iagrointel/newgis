# plat — plataforma SIG corporativa, pilha aberta (0.1.0)

Codinome `plat`. Objetivo do laço que o constrói: substituir o ArcGIS Enterprise para o cliente, em pilha
100 % aberta. Este README descreve só o que EXISTE no repositório; o que ainda não existe está em
`/home/dev/plataforma/laco/PAINEL.md` e na seção final de `ARQUITETURA.md`, nunca aqui.

Estado: análise / beta privado. URL interna `https://plat.iagrointel.com` (noindex, nunca linkar de
lugar público).

## O que existe em 0.1.0

- Serviço `plat-api` (FastAPI, 127.0.0.1:8150) com `/saude`, `/api/versao`, página inicial e `/api/docs`.
- nginx com HTTPS, `noindex` e HSTS em toda resposta, estático servido do disco; `/api/docs` sem CDN.
- Schema `plat` no banco `iagro_sat`: role `plat_app`, tabelas de inquilino, usuário, sessão, token de
  serviço e log de acesso, todas com RLS; funções de autenticação prontas no banco (a API ainda não as
  chama).
- Migrações versionadas por sha256 (`db/migrar.sh`), instalador idempotente (`install.sh`), dependências
  fixadas em `requirements.txt`, suíte `make check` (ruff, varredura de marcador, 81 testes rápidos,
  1 e2e playwright).

## Arquivos

| arquivo | conteúdo |
|---|---|
| `ARQUITETURA.md` | componentes e portas, schema `plat`, migrações, `install.sh` passo a passo, systemd, nginx, contrato de `/saude`, convenções, o que ainda não existe |
| `MANUAL.md` | acesso e saúde do serviço; instalação e atualização (com a captura do e2e) |
| `CHANGELOG.md` | uma entrada por turno, com medições e commits |
| `docs/adr/0001-fundacao.md` | decisões da fundação e seus motivos |
| `docs/openapi.json` | gerado por `make openapi`; comitado |
| `docs/PARIDADE.md` | tabela viva contra o ArcGIS Enterprise (só cabeçalho: nenhuma capacidade de usuário ainda) |
| `install.sh` | `sudo bash install.sh <dominio> [porta]`; idempotente |
| `Makefile` | `check`, `check-rapido`, `lint`, `sem-marcador`, `teste`, `e2e`, `medidas`, `vendor`, `migrar`, `openapi` |
| `app/` | API |
| `db/` | `migrar.sh` e `migracoes/NNN_*.sql` |
| `deploy/` | modelos da unidade systemd e do bloco nginx |
| `web/` | página inicial (módulos ES, sem bundler) e `vendor/` (MapLibre 4.7.1, Swagger UI 5.32.15) com versão no nome, sha256 e licença |
| `tests/` | `unit/`, `api/`, `e2e/`, `medidas/<item>.json` (único lugar de onde documento cita número) |

## Comandos

```
sudo bash install.sh plat.iagrointel.com 8150   # instala ou atualiza
make check                                       # suíte inteira
curl -sS https://plat.iagrointel.com/saude       # 200 e banco ok
```

Construído pelo laço `/home/dev/plataforma/laco/` (estado, portões, adversário, ledger, handoffs por
turno). Regras do laço: `~/.claude/skills/plataforma-enterprise/SKILL.md`.
