# Handoff — item `L6-02-h-csv-url-geojson-kml` (backend + dados + adversário)

**Estado: entregue.** Todas as cláusulas do portão passam com medida gravada.

**Ramo:** `wt/t602h` · **worktree:** `/home/dev/plataforma/wt/t602h` (criado de `master` 13b419f nesta passagem)
**Trilha de banco:** `t602h` (schema `plat_tt602h`, **APAGADO ao fim do turno**; recriar com
`bash laco/trilha_ambiente.sh t602h` + a migração deste item) · **commits:** `1e5e4b6`, `e4174c8`, `323f271`

> Por que um worktree novo em vez do `wt/valida` do prompt: `wt/valida` estava em `cb66d92`, ANTES da entrega
> do L6-02-a — não tinha `app/conexao/` nenhum, que é a dependência inteira deste item. Trabalhar lá seria
> reimplementar a dependência. O ramo novo sai de `master`, onde `app/conexao/` e a ingestão do L0-04 já estão.

## O que foi construído

| arquivo | o que é |
|---|---|
| `app/conexao/arquivo_url.py` (novo) | baixa condicional (ETag/Last-Modified), formato pelos BYTES, conversão para GeoJSON, conferência de faixa de coordenada |
| `app/conexao/tarefas_arquivo.py` (novo) | job `conexoes.arquivo_sincronizar` (`somente_sistema`) e periódico `conexoes.arquivo_sincronizar_vencidas` |
| `db/migracoes/20260906T1549391_conexao_arquivo_url.sql` (novo) | `plat.conexao_arquivo` (RLS) + 3 funções SECURITY DEFINER + evento_tipo |
| `app/conexao/rotas.py` | 3 rotas novas: `PUT/GET /api/conexoes/{id}/arquivo`, `POST /api/conexoes/{id}/arquivo/sincronizar` |
| `app/conexao/modelos.py` | `ArquivoUrlEntrada` / `ArquivoUrlEstado` |
| `app/conexao/seguranca.py` | `ResultadoBusca.cabecalhos` + credencial não atravessa host no redirecionamento |
| `app/conexao/periodicos.py`, `app/jobs/tipos.py` | registro do periódico e do módulo de tarefas |
| `app/limites.py`, `docs/LIMITES.md` | bloco `CONEXAO_ARQUIVO_*` e `INGESTAO_EPSILON_ENVOLTORIA` |
| `app/ingestao/carregar.py` | dois consertos de camada de UM ponto (ver abaixo) |
| `tests/servidor_arquivo.py` (novo) | servidor HTTP de prova no ENDEREÇO PÚBLICO da máquina |
| `tests/unit/test_conexao_arquivo_url.py` (novo) | 42 testes |
| `tests/api/conexao/test_arquivo_url.py` (novo) | 13 testes ponta a ponta com worker de verdade |
| `tests/api/cruzado_casos.py` | 3 casos novos A→B para as 3 rotas |
| `MANUAL.md` §18.2.1, `docs/adr/0018-arquivo-por-url-publica.md`, `docs/PARIDADE.md`, `CHANGELOG.md` | documentação |

**Nome da migração usado: `20260906T1549391_conexao_arquivo_url.sql`** (carimbo UTC + 3 hex, ADR 0014; nenhum
número reservado). Declara `-- depende: 036_conexao_saude_e_camada.sql`. Aplicada no schema da trilha via
`trilha_reescrever.py` + psql e registrada em `plat_tt602h.versao_migracao`. **Não foi aplicada em `plat` de
produção** — `db/migrar.sh` continua travado no `030_conexao` desde o turno passado (bloqueio herdado,
descrito no handoff do L6-02-l; não é deste item).

## Portão de pronto — cláusula por cláusula

Portão literal: *"4 formatos por URL pública viram camada; atualização agendada detecta arquivo inalterado
(ETag) e não recarrega (teste); CSV com vírgula decimal reconhecido."*

| cláusula | prova | veredito |
|---|---|---|
| 4 formatos por URL pública viram camada | `tests/api/conexao/test_arquivo_url.py::test_formato_por_url_publica_vira_camada` — **6** formatos (csv, geojson, kml, kmz, georss, gpx), cada um baixado de um servidor no IP público desta máquina, carregado por worker de verdade, virando `camada_vetorial` com tabela PostGIS. Medidas em `tests/medidas/L6-02-h-csv-url-geojson-kml.json` (`camada_csv` … `camada_gpx`: formato, feições, SRID, bytes, item_id) | **passa** |
| atualização agendada detecta arquivo inalterado (ETag) e não recarrega (teste) | `test_atualizacao_agendada_com_etag_nao_recarrega_arquivo_inalterado`: 3 passagens na mesma URL — 200 (carrega) / 304 (não recarrega, `item_id` e `sha256` intactos, `If-None-Match` conferido no servidor) / 200 com conteúdo novo (recarrega). Contadores: `sincronizacoes` 3 × `recargas` 2. Reforço: `test_servidor_que_ignora_o_condicional_tambem_nao_recarrega` (200 com o mesmo corpo → `motivo: sha256_igual`) | **passa** |
| CSV com vírgula decimal reconhecido | `test_csv_com_virgula_decimal_e_ponto_e_virgula_reconhecido` (separador `;`, decimal `,`, colunas lat/lon achadas) + o caso `csv` do teste ponta a ponta (2 feições, SRID 4674) | **passa** |
| **agendamento** (parte da hipótese, não do portão literal) | periódico `conexoes.arquivo_sincronizar_vencidas` (`*/15 * * * *`); `plat.conexao_arquivo_candidatas` cruza inquilinos só no inquilino técnico `plataforma` e enfileira no inquilino DONO. **Disparo pelo relógio OBSERVADO** no banco da trilha: execução de 16:00:24 `concluido`. A de 16:16:09 falhou com `memória excedida (limite 256 MB)` — o filho já carrega o app inteiro (~107 MB de RSS só de import) antes de rodar uma linha; **limite subido para 512 MB**, com o motivo escrito no código. O que NÃO foi observado: uma conexão agendada vencendo e sendo recarregada pelo relógio de ponta a ponta (exigiria esperar o intervalo mínimo de 15 min) | **passa o disparo; a volta completa pelo relógio fica declarada como não observada** |
| endereço → geocodificação de CSV sem lat/lon | fora: depende de o L2-11 estar ligado ao fluxo de ingestão. CSV sem coordenada vira tabela sem geometria | **fora, declarado** |

## Segurança — as três provas que o gerente pediu

Todas contra `app/conexao/seguranca.buscar_seguro` (nenhuma requisição crua neste item):

1. **Endereço interno recusado**: `test_endereco_interno_recusado_na_entrada` — 127.0.0.1, `[::1]`, 10.0.0.5,
   192.168.1.10, 169.254.169.254, 100.64.0.1 (CGNAT) e `file://`. Todos `ok=False` com
   `url_insegura:ip_bloqueado:<categoria>`. Na rota, a URL interna nem chega a virar conexão
   (`test_endereco_interno_recusado_pela_rota_e_pelo_job`: 422 no `POST /api/conexoes`).
2. **Redirecionamento para endereço interno recusado**: `test_redirecionamento_para_endereco_interno_e_recusado`
   e `..._para_loopback_...` (unidade) + `test_redirecionamento_para_endereco_interno_falha_o_job` (ponta a
   ponta): a URL cadastrada é um host público real; o `Location` aponta para `169.254.169.254`; o salto 0 é
   aceito e o salto 1 recusado, o job falha e `recargas` fica em 0.
3. **Nome que resolve para a rede local recusado**: `test_nome_que_resolve_para_a_rede_local_e_recusado` com
   `localtest.me` (→ 127.0.0.1) e `10.0.0.1.nip.io` (→ 10.0.0.1) — nomes de DNS **públicos**, a forma clássica
   de furar lista de host. O validador não olha o nome, olha o IP resolvido. (O teste dá `skip` se a máquina
   não tiver DNS externo no momento; o caso por IP literal cobre o mecanismo de qualquer jeito.)

**Achado do adversário do L6-02-a consertado aqui**: `Authorization`/`Cookie`/`Proxy-Authorization`/`X-Api-Key`
seguiam no redirecionamento para qualquer host. Agora `_sem_credencial_em_outro_host` remove esses cabeçalhos
quando muda host, muda porta, ou cai de https para http. Provado dos dois lados
(`test_credencial_nao_segue_para_outro_host_no_redirecionamento` — o segundo servidor recebe o pedido SEM o
cabeçalho; `test_credencial_segue_no_redirecionamento_para_o_mesmo_host_e_porta`), mais 6 casos de tabela em
`test_origem_de_confianca`. **Isto não fecha o L6-02-a**: o outro furo daquele item ("`testar`/`saude` vazam o
Bearer da casa") não foi tocado aqui.

## Refutação exigida

*"adversário passa CSV com lat/lon trocados (lon > 90) e KML com 200 mil pontos."*

- **CSV com lat/lon trocados**: RECUSADO, com o motivo por extenso. Medida gravada
  (`refutacao_lat_lon_trocadas`): `"a coluna de latitude 'lat' tem valor fora da faixa -90..90 (exemplos:
  -146.6333) em 2 linhas lidas. Os valores da coluna de latitude caberiam numa longitude: confira se as duas
  colunas estão trocadas no arquivo de origem. A plataforma não troca as colunas sozinha."` O job vai a
  `falhou`, `recargas` fica 0 e nenhuma camada sobra
  (`test_refutacao_csv_com_lat_lon_trocadas_falha_com_motivo`).
  **Fronteira honesta, com teste próprio** (`test_fronteira_honesta_troca_indetectavel_...`): quando a troca
  deixa os DOIS valores dentro de -90..90 (ex.: lat −47,88 / lon −15,79), nenhuma faixa é violada e o arquivo
  passa. Não existe sinal no dado para distinguir isso de um arquivo correto. A conferência de faixa pega a
  troca só quando ela produz valor impossível — nunca prometer mais que isso.
- **KML com 200 mil pontos**: não é recusado; foi **medido, ponta a ponta**. Medida gravada
  (`refutacao_kml_200mil`): **20.984.171 bytes** baixados, **200.000 feições** carregadas, **14,2 s** do pedido
  de sincronização ao job `concluido`, sem erro — a camada existe no catálogo com as 200 mil feições.
  Medição isolada do gargalo, feita antes de escolher os limites (GDAL 3.8.4, `/usr/bin/time -v`, KML de 35,5 MB
  com atributos): `ogr2ogr -f GeoJSON` em **2,42 s** com **417 MiB de RSS** — razão ~12× o tamanho do arquivo,
  porque o driver KML lê o documento XML inteiro na memória. **Foi daí que saiu o teto próprio dos formatos
  XML** (`CONEXAO_ARQUIVO_XML_MAX_BYTES` = 40 MiB): com o teto geral de 64 MiB o pico passaria de 780 MiB e
  estouraria o `INGESTAO_MEMORIA_MB` (768) do job. O teste ponta a ponta está marcado **`lento`** (fora de
  `pytest -m "not lento"`) porque gera o arquivo no próprio processo e, com 6 trilhas disputando a máquina,
  atrasa o turno inteiro; rode-o sozinho:
  `pytest -m lento tests/api/conexao/test_arquivo_url.py`.

## Dois defeitos de terceiros consertados de caminho (`app/ingestao/carregar.py`, L0-04)

Camada de UM ponto — o caso mais comum de arquivo pequeno por URL — não carregava:

1. a envoltória era lida do GeoJSON de `ST_Extent`; com um só ponto isso degenera para `{"coordinates":[x,y]}`
   e o código levantava `TypeError: 'float' object is not iterable`. Agora vem de `ST_XMin/ST_YMin/ST_XMax/
   ST_YMax`, que valem para POINT, LINESTRING e POLYGON sem distinção de caso.
2. corrigido isso, o retângulo de largura zero virava `ST_MakeEnvelope` degenerado — um POLYGON com 5 vértices
   iguais, `ST_IsValid = false` — e o CHECK `item_extent_check` de `plat.item` recusava a linha, derrubando a
   carga inteira. Agora o lado nulo é afastado em `INGESTAO_EPSILON_ENVOLTORIA` (1e-7 grau, ~1 cm no equador).
   **Só o retângulo guardado no item muda; a geometria da feição continua exatamente a do arquivo.**

Isso é mudança em arquivo que a árvore principal também mexe — está localizada em um bloco de ~10 linhas mais
uma função nova, e vale para qualquer camada de um ponto, não só para este item.

## Como o adversário reproduz

```bash
cd /home/dev/plataforma/wt/t602h
bash /home/dev/plataforma/laco/trilha_ambiente.sh t602h     # se o schema plat_tt602h não existir mais
TRILHA=t602h /home/dev/plataforma/laco/trilha_reescrever.py \
  db/migracoes/20260906T1549391_conexao_arquivo_url.sql | sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f -
sudo -u postgres psql -d iagro_sat -c \
  "GRANT USAGE, CREATE ON SCHEMA d_demo, d_demo2, d_plataforma TO plat_tt602h_app, plat_tt602h_worker"
set -a; source /home/dev/plataforma/laco/var/trilha/t602h.env; set +a
venv/bin/pytest tests/unit/test_conexao_arquivo_url.py tests/unit/test_conexao_seguranca.py -q   # 67 passed
venv/bin/pytest tests/api/conexao/test_arquivo_url.py -q -m "not lento"   # 13 passed
venv/bin/pytest -m lento tests/api/conexao/test_arquivo_url.py            # 1 passed (KML de 200 mil, 14,2 s)
```

Onde atacar primeiro, na minha opinião: (a) o CSV cuja troca cabe nas duas faixas (limitação declarada, não
defeito — mas vale ver se há outro sinal); (b) servidor que devolve `ETag` diferente a cada pedido com o mesmo
corpo (o sha256 deve segurar; há teste, mas com ETag estável); (c) `Location` relativo apontando para outro
caminho do mesmo host com credencial (deve seguir — é o comportamento correto, confira que segue mesmo);
(d) KMZ com muitos `.kml` dentro, ou com um `.kml` que é bomba de descompressão (o zip é aberto por
`zipfile.ZipFile` só para LISTAR nomes; a extração é do GDAL, sem a `conferir_zip` do L0-04 — **este é o buraco
que eu mesmo apontaria**); (e) `Content-Length` mentindo para passar do teto (o teto é aplicado nos bytes
LIDOS, não no cabeçalho — confira).

## Limitações honestas

- **A volta completa pelo relógio não foi observada**: o periódico dispara (visto no banco), mas esperar uma
  conexão agendada vencer o intervalo mínimo de 15 min e recarregar sozinha ficou fora desta janela.
- **Três defeitos meus, achados pelos próprios testes e corrigidos**: (1) o servidor de prova respondia 304 pelo
  `If-Modified-Since` mesmo depois de eu trocar o corpo — servidor mentindo, teste corrigido para trocar também
  o `Last-Modified`; (2) o corpo de erro da casa usa a chave `erro`, não `codigo`; (3) o periódico estourava
  256 MB. Nada disso é do mecanismo do item, mas vale saber que a primeira rodada tinha 3 falhas.
- **`d_demo`/`d_demo2` são compartilhados entre trilhas** (o nome do schema de dado do inquilino não é
  reescrito por `trilha_reescrever.py`, só `plat`). Precisei de `GRANT USAGE, CREATE` para o papel da trilha,
  como outras trilhas já fizeram. As camadas de teste de várias trilhas convivem no mesmo schema (nomes por
  uuid, sem colisão), mas isso não é isolamento de verdade — vale registrar para o dono.
- **`plat.conexao_arquivo` guarda uma camada por conexão**: recarregar cria um item novo e o anterior fica
  para trás (o job devolve `item_anterior`). Substituir a camada NO LUGAR (mesmo item_id, mesma tabela, para
  não quebrar mapa que já a usa) é trabalho de outro item, não foi feito nem prometido.
- **Sem tela.** As 3 rotas existem e estão documentadas; `web/conexoes.html` não ganhou botão nenhum.
- **Sem `db/migrar.sh` em produção** — o bloqueio do `030_conexao` (turno passado) segue de pé.

## `docs/openapi.json` NÃO foi regenerado (de propósito)

As 3 rotas novas não estão no `docs/openapi.json` commitado, então
`tests/api/test_cruzado.py::test_cobertura_100_por_cento` vai listá-las como faltando — junto com as de
outras trilhas, que já faltavam antes deste item. Rodar `make openapi` na minha árvore produziu um diff de
**+4.418 / −2.378 linhas**, ou seja, o arquivo commitado está defasado em relação ao próprio `master` por
motivos alheios a este item; regenerá-lo daqui empurraria mudança de outras trilhas dentro do meu commit e
criaria conflito grande. **Ação para o gerente: rodar `make openapi` UMA vez depois de juntar as trilhas.**
Os 3 casos cruzados A→B correspondentes já estão escritos em `tests/api/cruzado_casos.py`.

## Riscos de merge

**Estado conferido no fim do turno:** `master` avançou depois da minha base (13b419f → 796dc42). Da minha base
até a ponta do meu ramo são **21 arquivos, +1.895 / −10**. Cruzando os arquivos que EU mexi com os que o
`master` mexeu no mesmo período, o único em comum é **`CHANGELOG.md`** (dois blocos novos em pontos
diferentes do arquivo — conflito de contexto, resolução óbvia). Nenhum outro arquivo se cruza.


- `app/conexao/rotas.py`, `app/conexao/modelos.py`, `app/conexao/periodicos.py`, `app/jobs/tipos.py`: acréscimos
  no fim do arquivo / uma linha de import — conflito improvável, resolução óbvia.
- `app/conexao/seguranca.py`: mudança DENTRO de `buscar_seguro` (a variável `cabecalhos_do_salto`). Se outra
  trilha mexeu nessa função, conferir que a remoção de credencial continua no caminho do redirecionamento.
- `app/ingestao/carregar.py`: o bloco de estatísticas/envoltória. A árvore principal está mexendo em L0-04 —
  **este é o arquivo com risco real de conflito**.
- `app/limites.py`, `docs/LIMITES.md`, `MANUAL.md`, `CHANGELOG.md`, `docs/PARIDADE.md`,
  `tests/api/cruzado_casos.py`: acréscimos em ponto único, conflito de contexto no máximo.

## Aviso de vizinhança (custou tempo, registro para não se repetir)

A trilha `t13` está usando a porta **8163** para o worker dela — a mesma porta que este prompt me atribuiu
para uvicorn. Não subi uvicorn (os testes usam `TestClient` em processo), então não houve colisão, mas a
atribuição de portas do laço já não bate com o que roda na máquina.

E: **`pkill -f "pytest tests/api/conexao"` acerta outras trilhas** — a trilha `l602c` tem
`tests/api/conexao/test_wfs_ogcapi.py`. Usei esse padrão uma vez para destravar um teste meu e posso ter
derrubado a rodada de outro agente. Matar só por PID, sempre.
