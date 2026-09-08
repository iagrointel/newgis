# T1 — plano do turno · item L0-01-repo (gerente)

## Portão de pronto (literal)
git com README/ARQUITETURA/MANUAL/CHANGELOG; `install.sh` cria schema+role+pg_hba (com linha em pg_hba.conf) e sobe
`plat-api` (:8150) sem erro em máquina que nunca viu o repo; `make check` roda pytest verde; URL interna HTTPS com
noindex responde 200 em /saude com JSON de versão; `docs/adr/0001-fundacao.md` escrito.

## Refutação (literal)
adversário apaga schema `plat` e role, roda install.sh de novo, confere que sobe e que /saude e um pytest completo
passam; confere noindex no cabeçalho.

## Papéis e ordem
1. arquiteto (20) — ADR 0001: layout do repositório, pilha (FastAPI + psycopg2 + PostGIS; front MapLibre em módulos ES
   sem bundler pesado OU Vite — decidir por medição de RAM/disco e pelo que já roda em fgr/sig), esquema `plat` base
   (tenant, usuario, sessao, token, log_acesso, item de catálogo mínimo), contrato de /saude e /api/versao, Makefile,
   estrutura de testes (pytest + e2e playwright na venv do repo), convenções (migrações idempotentes NNN_*.sql,
   settings por .env, logs). Pode ler fgr/sig para copiar padrões — NUNCA editar.
2. backend (30) — implementa o ADR: `install.sh` (idempotente: schema, role com senha em .env 600, pg_hba via sudo +
   reload, migrações, venv, unidade systemd plat-api :8150, nginx server block plat.iagrointel.com + certbot, noindex),
   `app/` mínimo com /saude e /api/versao (JSON com git sha, versão, banco ok, migrações aplicadas), `Makefile` com
   `check` (pytest + lint) e `tests/` com teste de /saude, de migração idempotente e de RLS ativa nas tabelas base.
3. testador (40) — roda install.sh do zero (drop schema) + make check + curl HTTPS; mede tempo de instalação; escreve
   tests/medidas/L0-01-repo.json.
4. adversário (50) — instrução de refutação literal.
5. cronista (60) — ARQUITETURA.md, MANUAL.md (tela nenhuma ainda: só "acesso e saúde"), CHANGELOG, laco/PAINEL.md.

## Gerente faz antes (bloqueantes)
- venv do repo com pytest (feito) · DNS A plat.iagrointel.com DNS-only via Cloudflare API (D19 = precedente da casa) ·
  certbot · linha pg_hba (o install.sh faz com sudo; conferido pelo gerente) · confirmar porta 8150 livre.

## O que NÃO se faz neste turno
Nenhuma tela de produto além de /saude; nenhum dado; nenhuma camada. L0-02 (auth/tenant) é o próximo item.

## Medições
tempo de install.sh do zero; nº de testes; latência /saude; cabeçalho X-Robots-Tag; RAM do serviço.
