# Reconstruir este sistema em outra máquina

O repositório tem TUDO que é código, regra e plano. O que NÃO está aqui e como se reconstrói:

| o que | por que não está | como reconstruir |
|---|---|---|
| dado do banco (`plat`, `plat_trabalho`) | dado vivo e segredos de usuário não se versionam | `sudo bash install.sh <dominio> <porta>` cria schema, papéis e `pg_hba`; `db/migrar.sh` aplica as migrações em ordem; `db/estrutura/plat_estrutura.sql` é o retrato só-estrutura (18 mil linhas, sem uma linha de dado) para conferir o resultado |
| dado de demonstração | é gerado | semeador do item L0-13 (`make semear-demo` ou o script que o handoff `laco/handoffs/T3/L0-13-dado-demonstracao.md` indica) |
| objetos no armazenamento (Garage) | binários de teste | `web/dados/basemap/guarulhos.pmtiles` (18 MB) ESTÁ no repositório; as cenas de satélite de prova (2 GB) vêm do pipeline em `laco/` com a fonte declarada na procedência de cada item |
| segredos (`.env`, `/etc/plat/segredos/`) | nunca | `.env.exemplo` lista as chaves; `install.sh` gera `PLAT_SECRET` e o DSN do worker |
| catálogo de imagens (`pgstac`) | instalado por ferramenta | `db/migrar_pgstac.sh` (item L1-01-a) |
| ambiente Python | reproduzível | `python3 -m venv venv && venv/bin/pip install -r requirements.txt`; GDAL 3.8 do sistema |
| serviços (`plat-api`, `plat-worker`, nginx) | configuração de máquina | unidades e blocos de nginx em `deploy/`, aplicados pelo `install.sh` |

Ordem: clonar → venv → `install.sh` → `db/migrar.sh` → semear demo → `make check`. Depois, `laco/LEIA-ME.md` diz como retomar a construção.
