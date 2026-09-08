# L2-11-c-rota-matriz-isocrona — turno 3 (sessão única: arquiteto+backend)

**Objetivo do turno** (recorte dado pelo gerente, MENOR que a hipótese completa do backlog): confirmar se já
havia um OSRM útil na máquina (havia, mas de outra frente — não tocado), subir um OSRM ISOLADO só com o
recorte pequeno de Guarulhos (mesma área do mapa-base `L2-01-a`), e construir `POST /api/rota`,
`POST /api/matriz` e `POST /api/isocrona`. pgRouting, `/mais-proximo`, `/ajuste-de-trajeto`, perfis pé/
bicicleta, NAServer Esri-compatível, UI no mapa e os testes de escala do portão completo (1.000×1.000,
200 pontos amostrados) **ficam para a continuação do item** — ver "Estado do item" no fim.

## Portão do item no backlog (para referência; não fechado nesta trilha)

> rota entre 2 pontos da demo com instruções em português e geometria (e2e com captura); matriz 10×10 em
> ≤ 1 s e 1.000×1.000 em tempo medido; isócrona de 15/30/45 min: ≥ 95 % de 200 pontos amostrados dentro do
> polígono de 30 min têm tempo roteado ≤ 30 min e ≥ 95 % dos pontos entre 30 e 45 têm > 30 (teste contra a
> própria matriz); pgRouting instalado (`SELECT pgr_version()`) e `drivingDistance` na rede de demonstração
> confere com Dijkstra independente (networkx) em 20 origens; QGIS/JS consomem o NAServer (QGIS medido;
> Pro PENDENTE D20); versão do `.pbf` e do perfil na proveniência.

## O que fiz

### 1. Verificação do que já existia (antes de tocar em qualquer coisa)

`ps aux | grep osrm` + `docker ps -a` + mapeamento pid→cgroup→container confirmaram **4 contêineres
`osrm/osrm-backend` já ativos** nesta máquina, nenhum meu:
`buslog-osrm` (5000, `rio_metro.osrm`) · `osrm-cbre` (5001, `area_estudo.osrm`) · **`osrm-cbre-polos`
(5002, `rmsp_camp_santos.osrm` — o "RMSP/Campinas/Santos" citado no pedido; NÃO TOCADO em momento algum,
nem processo nem porta)** · `osrm-edpes` (5003, `es.osrm`). Reaproveitei só o PADRÃO documentado
(`/home/dev/cbre/osm/osrm/build_osrm.sh`: `osrm-extract -p car.lua` → `osrm-partition` → `osrm-customize`
→ `osrm-routed --algorithm mld`, cada passo num `docker run` descartável), nunca o processo.

### 2. Dado: recorte de Guarulhos ≤ 50 MB, sem novo download

Mesma bbox do mapa-base (`-46.62,-23.53,-46.42,-23.38`, `web/dados/basemap/PROVENIENCIA.md`), mesma
origem (`/home/dev/cbre/osm/area_estudo.osm.pbf`, 135 MB, já na máquina). **`osmium extract` (direto e
`--strategy=simple`) morreu de OOM sob `ulimit -v` de 1,2/1,8/2,4 GB três vezes** (RAM disponível ~2,5 GB,
swap cheio; nenhuma tentativa tocou processo do sistema — o `ulimit` mata só o próprio processo). Caminho
que funcionou: `ogr2ogr` (mesmo padrão medido seguro no `L2-01-a`, 310 MB de RSS, 3,2 s) extraindo só
`highway IS NOT NULL` em GeoJSON, depois `osrm/gerar_osm_xml.py` (script novo, 255 MB de RSS, 1,2 s) —
sintetiza um `.osm` XML válido deduplicando nó por coordenada exata, sem depender de `osmium`/`osmconvert`
no arquivo grande. `osmium cat` converteu XML→PBF (arquivo já pequeno, sem problema). Resultado:
`osrm/guarulhos.osm.pbf`, **1.669.892 bytes (1,6 MiB)**, 210.065 nós, 42.720 vias, 0 nó de via faltando
(`osmium check-refs`). Proveniência completa (o que foi tentado, o que falhou e por quê, comandos exatos,
sha256) em `osrm/PROVENIENCIA.md` + `osrm/proveniencia.json` (o que a API embute em cada resposta).

### 2b. Build OSRM (MLD) e serviço

`docker run --memory=1200m/800m` (teto do CONTÊINER, não do sistema) para `osrm-extract -p car.lua` →
`osrm-partition` → `osrm-customize`: picos de RAM relatados pelo próprio OSRM 156/82/63 MB — nenhum perto
do teto. Diretório `osrm/` final: 61 MB. Serviço `plat-osrm-guarulhos` em **127.0.0.1:5010** (nunca
5000-5003), unidade systemd própria `deploy/plat-osrm-guarulhos.service` — decisão: **manter vivo**
(memória medida ~40 MB em uso; mesmo padrão "sempre ligado" dos outros 4 contêineres da casa; job sob
demanda pagaria alguns segundos de partida fria do `.osrm*` do disco a cada primeira chamada, sem ganho
real de recurso). Instalado e testado no systemd real desta máquina (`systemctl status` ativo,
`docker stats` ~40 MB); `install.sh` ganhou o passo "h3" (idempotente, falha se `osrm/guarulhos.osrm`
não existir, com a mensagem apontando para `osrm/PROVENIENCIA.md`).

### 3. API (`app/rede/`, novo pacote)

- `osrm.py`: cliente HTTP fixo em `settings.PLAT_OSRM_URL` (nunca URL do chamador — sem SSRF possível
  aqui); traduz `code` do OSRM (`NoRoute` etc.) em 422, timeout/conexão em 503.
- `instrucoes.py`: um resumo em português por passo do OSRM (`maneuver.type`/`modifier`, vocabulário
  fechado da doc v5.24 — depart/arrive/turn/roundabout/fork/end of road/merge/ramp/new name/continue).
- `isocrona.py`: grade de pontos (resolução calculada do raio-alvo e do teto de pontos), 1 chamada a
  `/table` (1 fonte × N destinos), expande o raio 1× se a borda da grade ainda estiver alcançável,
  `shapely.concave_hull` sobre os pontos dentro do orçamento de tempo.
- `rotas.py`: `POST /api/rota`, `POST /api/matriz` (422 `matriz_grande_demais` acima de
  `PLAT_ROTA_MATRIZ_MAX`, padrão 625), `POST /api/isocrona` (422 `isocrona_vazia` com < 3 pontos
  alcançáveis). Autenticação: escopo de token novo **`rota:usar`** (`app/auth/escopos.py`) ou sessão.
- `app/settings.py` ganhou `PLAT_OSRM_URL`/`PLAT_ROTA_MATRIZ_MAX`/`PLAT_ROTA_ISOCRONA_MAX_PONTOS`
  (padrões em `app/limites.py`, únicos — `docs/LIMITES.md` regenerado); `.env`, `.env.exemplo` e
  `install.sh` (bloco novo + loop idempotente de upgrade) ganharam as 3 chaves.
- `docs/openapi.json` regenerado (inclui as rotas novas e as de outras trilhas concorrentes do turno).

### 3b. Integração com os testes TRANSVERSAIS (rodei a suíte inteira em background e corrigi os 3 achados meus)

`pytest -m "not lento"` sobre a árvore inteira (não só o meu item) achou 3 achados MEUS entre as falhas
(o resto — LDAP `/api/org/ldap`, `/api/login/ldap`, `test_expressao_seguranca`, `test_jobs_periodicos` — é
de outras trilhas concorrentes, não mexi): (1) `x-privilegio: "nenhum"` não existe no vocabulário fechado
(`app/auth/privilegios.py` + `plat.privilegio`) — corrigido para `"proprio"` (mesmo valor de `/api/eu`,
`/api/arquivos`: só exige autenticação, sem privilégio nomeado); (2) `tests/api/test_cruzado.py` exige um
`Caso` por rota do OpenAPI — acrescentei os 3 em `tests/api/cruzado_casos.py` como recurso COMPARTILHADO
(`proprio=True`, mesmo padrão de `/api/acervo`: não é de A nem de B, mesma entrada sempre dá a mesma
resposta pública); (3) `tests/api/test_eventos.py` conta todo POST/PUT/DELETE como "escrita" que precisa de
evento declarado — acrescentei `[]` em `tests/api/eventos_esperados.py` com o comentário do motivo (mesma
decisão já usada em `/api/arquivos`: sem escrita em `plat.*`, sem dono humano para narrar). Reconferido:
`tests/api/rede/test_rota.py` + `test_cruzado.py` + `test_eventos.py` + `test_privilegios_declarados.py`
juntos — 0 falha atribuível a este item (as falhas de LDAP continuam, não são minhas).

### 4. Testes (`tests/api/rede/test_rota.py`, 9 casos)

Rota real Guarulhos↔GRU (distância roteada entre a reta e 2,5× a reta — nunca menor que a reta), perfil
inexistente → 422, coordenada inválida → 422, matriz 5×5 sem `null`, matriz 26×26 (676) → 422 antes de
chamar o OSRM, isócrona de 10 min → polígono não vazio com anel válido, isócrona conferida contra a
própria API de rota (ponto a ≤ 10 min de rota cai dentro do polígono), minutos inválido (0 e 99999) → 422,
rota sem autenticação → 401. Todos verdes contra o **OSRM real** via `TestClient` (import direto de
`app.main`, sem tocar o `plat-api` ao vivo — outras 2-3 trilhas do turno editavam `app/` ao mesmo tempo;
restartar o serviço compartilhado no meio do turno teria sido irresponsável). Lint (`ruff`) e
`docs/gerar_limites.py --check` verdes nos meus arquivos.

## Evidência (comando + saída literal)

```
$ curl -s "http://127.0.0.1:5010/route/v1/driving/-46.5330,-23.4628;-46.4730,-23.4356?overview=false"
{"code":"Ok","routes":[{"legs":[{"distance":10752.2,"duration":898.3,...}],"distance":10752.2,"duration":898.3,...}]}

$ osmium check-refs osrm/guarulhos.osm.pbf
There are 210065 nodes, 42720 ways, and 0 relations in this file.
Nodes in ways missing: 0

$ systemctl status plat-osrm-guarulhos   # (sudo)
● plat-osrm-guarulhos.service ... Active: active (running)
   Main PID: ... (docker)
   Memory: ~40M (docker stats, medido depois)

$ flock laco/.pytest.lock venv/bin/pytest -q tests/api/rede/test_rota.py
.........                                                                [100%]

$ venv/bin/ruff check app/rede tests/api/rede docs/gerar_limites.py
All checks passed!

$ venv/bin/python docs/gerar_limites.py --check   # depois de rodar sem --check
(sem saída = ok)
```

## Riscos / pendências

1. **Escopo bem menor que o item completo do backlog** (ver lista no topo) — o item continua `pendente`
   no `estado.json` até a próxima trilha fechar o resto ou o gerente decidir que o recorte atual já é
   "parcial" suficiente para expor no mapa (`L2-05-f`).
2. **`shapely` vem de um pip global de OUTRO projeto** (`/usr/local/lib/.../dist-packages`, não dpkg, não
   neste `requirements.txt`) — `python3-shapely` 2.0.3 existe no apt mas não foi acrescentado a
   `deploy/pacotes_apt.txt` sem decisão do dono (lista fechada, ADR 0007). `install.sh` já falha alto se
   faltar (o self-check final importa `app.main`). Documentado em `requirements.txt`.
3. **Exceção à convenção 5** (`ARQUITETURA.md` §12: "serviço novo = porta 8150-8159"): `plat-osrm-guarulhos`
   fica em 5010 porque fala o protocolo próprio do `osrm-routed`, seguindo a numeração 50xx que as outras
   4 frentes OSRM da casa já usam — documentado em `ARQUITETURA.md` §13 e `osrm/PROVENIENCIA.md`, não é
   porta esquecida.
4. Só perfil `carro` (o único grafo construído); pedir `pe`/`bicicleta` dá 422 claro, não erro silencioso.
5. Isócrona: heurística de raio-guia (40 km/h × 1,5 de margem, 1 expansão) — não é o motor de 200 pontos/
   15-30-45 min do portão completo; testei só a 10 min. Fora dos ~8-11 km do centro do recorte a isócrona
   trunca na borda do grafo (documentado, não escondido).
6. ~~Rodei `pytest -m "not lento"` (suíte inteira, não só o meu item) em background sob o `flock`
   compartilhado — ainda rodando/enfileirando outras trilhas atrás dele quando este handoff foi escrito;
   quem fizer a integração final do turno deve conferir o resultado (não é exclusivamente meu escopo,~~
   **RESOLVIDO**: terminou antes do commit — as únicas falhas restantes são de LDAP (`L0-08-d`, outra
   trilha: `/api/org/ldap`, `/api/login/ldap`, `test_cobertura_100_por_cento` por causa delas), 0 falha
   deste item. Achei e corrigi 3 problemas MEUS que a suíte inteira pegou e o meu `test_rota.py` sozinho
   não pegaria: `x-privilegio: "nenhum"` não existe no vocabulário (corrigido para `"proprio"`), rota sem
   `Caso` em `tests/api/test_cruzado.py` (acrescentei 3, recurso compartilhado tipo `/api/acervo`), e rota
   de escrita sem entrada em `tests/api/eventos_esperados.py` (acrescentei `[]` com o motivo).
7. **Commit cirúrgico**: a árvore de trabalho é compartilhada com 2-3 trilhas concorrentes deste turno
   (LDAP `L0-08-d`, expressão `L2-10-c`, homologação `L7-31`) editando os MESMOS arquivos
   (`app/main.py`, `requirements.txt`, `.env.exemplo`, `docs/openapi.json`) ao mesmo tempo. `app/main.py`
   importa `app.auth.ldap` (arquivo deles, não comitável por mim) — commitar o arquivo misto quebraria o
   `import` de quem só tivesse o MEU commit. Resolvido com `git hash-object` + `git update-index
   --cacheinfo` (nunca `git stash`, que arrancaria o trabalho deles do disco enquanto seus processos
   ainda rodavam): construí a versão "HEAD + só as minhas 2 mudanças" de `app/main.py`,
   `requirements.txt` e `.env.exemplo` num diretório `/tmp`, e regenerei `docs/openapi.json`/
   `docs/LIMITES.md` a partir de um `git checkout-index` isolado desse estado — sem tocar no arquivo real
   da árvore de trabalho em nenhum momento (os outros trilhos continuaram rodando sem interrupção).
   **`app/settings.py` e `app/limites.py` foram comitados no estado MISTO atual** (não separei): são só
   constantes/campos aditivos sem import de arquivo alheio, então não quebram sozinhos; separar ali exigia
   editar a assinatura de uma função no meio de duas mudanças entrelaçadas (`_dsn_worker`, item L7-31) —
   risco de deixar o arquivo sintaticamente quebrado era maior que o benefício da separação. Confirmado com
   `git checkout-index` num diretório limpo + import fresco de `app.main`: importa certo, sem `ldap`, com
   as 3 rotas novas. **Quem comitar depois** (LDAP, expressão, homologação) vai ver `main.py`/
   `requirements.txt`/`.env.exemplo` como "modificado" de novo (o hunk deles nunca foi staged por mim) —
   é esperado, é o próprio conteúdo do trabalho deles ainda não comitado, nada foi perdido.
8. **Disco caiu de 12 GiB para 7,7 GiB livres em `/` durante o turno** (medido 3× ao longo da sessão) — não é meu
   consumo (`osrm/` = 61 MB); provavelmente outras trilhas concorrentes (LDAP, homologação). Registrado
   para quem monitora o guardrail de disco, não investigado por mim (fora do escopo do item).
9. Não criei tela/UI no mapa (fora do pedido desta trilha) — é o `L2-05-f-rede-isocrona-rota-ferramentas`,
   que já lista `L2-11-c` como dependência no `estado.json`.

## Para o próximo papel / próxima trilha

- **pgRouting**: `postgresql-16-pgrouting` 4.0.1 é candidato apt medido (não instalado ainda); entra
  quando alguém precisar de rede PRÓPRIA do inquilino (L4) em vez do OSRM aberto.
- **NAServer Esri-compatível** (`solve`, `solveServiceArea`, `solveClosestFacility`, OD cost matrix): pode
  ser uma fachada fina sobre `/api/rota`, `/api/isocrona`, `/api/matriz` — contrato ainda não desenhado.
- **UI no mapa** (`L2-05-f`): clicar 2 pontos → `/api/rota`; clicar 1 ponto + minutos → `/api/isocrona`.
- **Escala**: para o portão completo (1.000×1.000, 5.000×5.000 do adversário) o recorte de Guarulhos não
  tem malha viária suficiente — vai exigir um `.pbf` maior (D28 do dono, disco) ou aceitar que o teto de
  escala seja medido num recorte maior antes de prometer o número do portão.
