# ADR 20260907T1300 — compose único, dois perfis (`hospedado`/`appliance`)

Item: `L7-01-a-compose-perfis`.

## Contexto

O plat só tinha uma forma de instalação, `install.sh` (systemd, medida em 6-9 s, ADR 0001) e um
executor alternativo containerizado do worker (`deploy/docker-compose.worker.yml`, ADR 0010). Este
item pede uma SEGUNDA forma de instalação inteira — `docker compose --profile appliance up -d` numa
máquina que só tem Docker, sem nada da casa instalado — a partir dos MESMOS arquivos do repositório
(app/, requirements.txt, migrações), nunca uma reescrita paralela.

## Decisão

Um único `deploy/compose/docker-compose.yml` com dois perfis (`profiles:` do Compose, não dois
arquivos):

- **`hospedado`**: `api` e `worker` em contêiner, `network_mode: host` (mesmo mecanismo já medido em
  `docker-compose.worker.yml`/ADR 0010), enxergando Postgres/Garage/Martin/TiTiler já rodando na
  máquina via `install.sh`. nginx continua sendo o do sistema operacional (com certbot) — não
  duplicado aqui.
- **`appliance`**: `db`, `garage`, `martin`, `titiler`, `api-appliance`, `worker-appliance`, `nginx`
  numa rede-ponte própria (`interna`), sem nada do host. Único ponto de entrada é o `nginx` do
  compose (porta publicada).

Cada serviço tem seu próprio `Dockerfile.<nome>` em `deploy/`. `Dockerfile.api` é NOVO neste item,
irmão direto de `Dockerfile.worker` (mesma base `python:3.12-slim-bookworm`, mesmo padrão de
usuário sem privilégio + entrypoint que solta root depois de ler segredo).

## O que foi MEDIDO neste turno (disco a 95-96%, ver o comentário no topo do próprio
docker-compose.yml e tests/medidas/L7-01-a-compose-perfis.json)

1. **As dependências ocultas da API foram achadas por AST, não por tentativa.** Um script
   (`ast.walk` sobre toda a árvore `app/`) listou todo import de topo de módulo que não é stdlib.
   Depois de subtrair o que `requirements.txt` já resolve, sobraram 7 pacotes que hoje só existem
   no host por acidente (dpkg ou pip global de outro produto da casa, o mesmo padrão que o
   comentário de `requirements.txt` já registrava para `shapely`): `uvicorn`, `psycopg2`,
   `cryptography`, `python-magic`, `pyproj`, `lxml`, além dos dois que `Dockerfile.worker` já havia
   achado (`jsonschema`, `Pillow`). Sem essa varredura, a imagem quebraria em produção na primeira
   rota que tocasse `app.rede` (pyproj), `app.catalogo.metadado` (lxml) ou `app.ingestao.inspecionar`
   (pyproj de novo) — bugs que só apareceriam faseados, rota por rota, exatamente como aconteceu
   durante a construção deste item (3 rebuilds, 3 `ModuleNotFoundError`/`ErroConfiguracao` distintos,
   cada um corrigido e registrado no Dockerfile).
2. **O healthcheck original tinha um defeito de desenho, não só deste item**: ele lia
   `PLAT_URL_PUBLICA` (o domínio HTTPS público da instalação) para sondar `/saude` de DENTRO do
   próprio contêiner — de dentro, esse domínio não resolve DNS nem fala TLS com ninguém. Corrigido
   para sondar sempre `http://127.0.0.1:$PLAT_API_PORTA/saude`. Isso vale também para a unidade
   systemd hipotética que algum dia sondasse a própria API pelo domínio público — não é um bug
   introduzido pelo Compose, é um bug que o Compose expôs primeiro.
3. **`osrm/proveniencia.json` (728 B) é lido na IMPORTAÇÃO do módulo `app.rede.rotas`**, mas os
   arquivos de grafo `.osrm.*` (61 MB) ao lado NUNCA são tocados pela API (são servidos por um
   processo OSRM à parte, `PLAT_OSRM_URL`). O `.dockerignore` original ignorava a pasta inteira;
   ajustado para deixar passar só o arquivo de 728 B.
4. **`web/` também não entrava no contexto de build** (o `.dockerignore` de `Dockerfile.worker`
   nunca precisou dele, porque o worker não serve página nenhuma) — a API serve `/` e `/static/` a
   partir de `web/`; acrescentado à lista de permissão.
5. **Porta de teste real: 8150/8153 (produção nesta máquina) colidiram com o primeiro `docker
   compose up`** — o contêiner morreu com `Address already in use` e um `curl` na mesma porta
   respondeu, mas de OUTRO processo (a API de produção), não do contêiner. Corrigido usando a porta
   atribuída a este item no prompt (8272) e um worker de teste isolado (8278) via um arquivo de
   override SÓ desta prova (`docker-compose.teste-trilha.override.yml`, nunca citado por
   `install.sh` nem pelo README).
6. **Build de `plat-api:0.1.0` do zero (`--no-cache`, base já em cache) levou 77,4 s** com carga da
   máquina 7,7-9,5 — bem dentro do teto de 10 min do portão, mesmo sob disputa.
7. **Comparação byte a byte**: o MESMO Dockerfile.api, rodando em contêiner (porta 8272) e como
   `venv/bin/python -m uvicorn` fora de contêiner (porta 8279), contra o MESMO banco de trilha e o
   MESMO processo de worker de teste, devolveu `/saude` idêntico (removendo só os campos que variam
   por definição: `tempo_ms`, `em`, `fila.ultimo_heartbeat`).

## O que ficou PENDENTE (nomeado, não escondido)

`Dockerfile.db` (Postgres+PostGIS+pgRouting+pgstac), `Dockerfile.garage`, `Dockerfile.martin`,
`Dockerfile.titiler` e `Dockerfile.nginx` têm definição de serviço completa e válida no compose
(`docker compose config` confere as duas listas de perfil sem erro), mas SÓ o `Dockerfile.api` foi
de fato construído e subido. Motivo, registrado dentro de cada `Dockerfile.*`:

- `db`: pgRouting **não está instalada nem em produção** nesta máquina (ADR 0007, medido
  05/09/2026) e nenhuma migração usa pgRouting/pgstac hoje — construir a imagem seria compilar uma
  pilha que a própria produção ainda não tem, sem nada para testar contra ela.
- `garage`/`martin`: binário vendorizado do host (garage v2.3.0, martin 1.15.0, ambos estáticos),
  mas a imagem em si não foi construída neste turno (priorização de tempo, não bloqueio técnico).
- `titiler`: exigiria baixar/instalar `rasterio`+GDAL (centenas de MB) — o app HTTP em si hoje mora
  em `plataforma/pipeline/app.py` (produto irmão, "copiar, não editar" pela regra da casa).
- `nginx`: a base oficial `nginx:1.27-alpine` não está em cache local — baixar uma base nova viola a
  regra do handoff da trilha (disco a 95-96%).

Ver `tests/medidas/L7-01-a-compose-perfis.json` para a lista completa de cláusulas do portão,
cada uma com resultado (`passou`/`parcial`/`não medida`) e o motivo exato.

## Consequência

Quando o disco tiver folga (ou o dono decidir compilar pgRouting/trocar nginx por uma base já
cacheada), o próximo turno só precisa construir as 5 imagens que faltam — a estrutura, os nomes de
serviço, a rede, os volumes e os segredos do perfil `appliance` já estão escritos e validados por
`docker compose config`.
