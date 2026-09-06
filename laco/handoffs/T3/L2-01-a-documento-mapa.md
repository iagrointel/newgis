# L2-01-a-documento-mapa — documento de mapa com esquema publicado

Trilha `stac`, worktree `/home/dev/plataforma/wt/stac`, ramo `wt/stac`, commit **28b1340**.
Base de teste própria `plat_tstac` (nunca o schema `plat` de produção). 06/09/2026.

⚠ **A trilha `stac` estava sendo trabalhada por OUTRO agente ao mesmo tempo, no MESMO worktree**
(itens L6-02-c WFS/OGC API, L0-09-a procedência, L0-04-h exportação, L2-11-a geocodificação em
lote). Tudo o que fiz foi comitado arquivo a arquivo, por um índice temporário (`GIT_INDEX_FILE`),
para que nenhuma linha do trabalho dele entrasse no meu commit — inclusive em `app/main.py` e
`CHANGELOG.md`, onde só as MINHAS linhas foram para o commit.

## O que foi construído

| arquivo | o que é |
|---|---|
| `db/migracoes/20260906T1549_documento_mapa.sql` | esquema `mapa-v1` em `plat.tipo_item` + tipos de relação `estilo_de_mapa` e `servico_de_mapa` (idempotente) |
| `docs/esquemas/mapa-v1.json` | esquema publicado, GERADO do banco por `docs/gerar_esquemas.py` (que passou a publicar o tipo `mapa`) |
| `app/mapas/documento.py` | regras que o JSON Schema não expressa + resolução de `/completo` |
| `app/mapas/rotas.py` | `POST/GET/PUT /api/mapas`, `GET /api/mapas`, `GET /api/mapas/{id}/completo` |
| `app/catalogo/relacoes.py` | extrator do mapa passa a ler `ref`, estilo, popup e base; tipo `auto:mapa` resolvido por família em `sincronizar` |
| `app/main.py` | duas linhas: import e registro do router |
| `web/mapa.html`, `web/mapa.css`, `web/js/mapa/{mapa,documento,painel_camadas}.js`, `web/js/i18n/pt-BR.json` | painel de camadas em `/mapa?id=<uuid>`: arrasta-e-solta, Alt+seta, botões, visibilidade, salvar |
| `docs/adr/0022-documento-de-mapa.md` | contrato e alternativas descartadas (o número 0018 foi tomado por outra trilha no meio do turno) |
| `docs/PARIDADE.md` | de-para chave a chave contra a Web Map Specification |
| `tests/unit/test_documento_mapa.py` (13), `tests/api/catalogo/test_mapas.py` (25), `tests/e2e/test_mapa_documento.py` (1) | provas |
| `tests/api/catalogo/{conftest,test_relacoes,test_lixeira,test_transferencia,test_compartilhamento}.py` | ajudante `documento_mapa(...)` e as 9 chamadas que usavam a forma antiga |

Ambiente (o que o adversário precisa repetir):

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh stac
set -a; source /home/dev/plataforma/laco/var/trilha/stac.env; set +a
cd /home/dev/plataforma/wt/stac
# a migração deste item NÃO é aplicada pelo trilha_ambiente.sh (ele lê db/migracoes do repo principal):
TRILHA=stac /home/dev/plataforma/laco/trilha_reescrever.py db/migracoes/20260906T1549_documento_mapa.sql > /tmp/m.sql
chmod 644 /tmp/m.sql && sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f /tmp/m.sql
venv/bin/pytest tests/unit/test_documento_mapa.py tests/api/catalogo/test_mapas.py -q     # sem flock
```

## Cláusula do portão → prova

| cláusula (literal) | prova | resultado |
|---|---|---|
| JSON Schema em `docs/esquemas/mapa-v1.json` validado no servidor; documento inválido = 422 com o caminho do erro | `test_documento_fora_do_esquema_e_422_com_o_caminho_do_campo`, `test_crs_de_exibicao_diferente_de_3857_e_recusado`, `test_chave_desconhecida_no_documento_e_recusada`, `test_esquema_do_tipo_mapa_e_o_arquivo_publicado` (arquivo == banco) | PASSOU — 422 `dados_invalidos` com `corpo.camadas.0.id` e `corpo.camadas.0.ref` |
| `/completo` de mapa com 10 camadas ≤ 150 ms p95, 50 chamadas, medido em `tests/medidas/L2-01-a.json` | `test_completo_de_mapa_com_10_camadas_p95` com `PLAT_GRAVAR_MEDIDAS=1` | PASSOU — **p95 20,7 ms**, mediana 12,2 ms, 50 chamadas |
| camada de outro inquilino = 404 no salvar (teste cruzado) | `test_camada_de_outro_inquilino_e_404_ao_salvar`, `test_uuid_inexistente_e_o_mesmo_404...`, `test_editar_mapa_com_camada_de_outro_inquilino_e_404` | PASSOU — 404 `referencia_inexistente`, mensagem idêntica à de uuid inexistente; o documento gravado não muda |
| apagar camada com mapa dependente = 409 com a lista de mapas (usa L0-03-i) | `test_apagar_camada_usada_por_mapa_da_409_com_a_lista_de_mapas`, `test_apagar_estilo_usado_por_mapa_da_409` | PASSOU — 409 `possui_dependentes` com id e título dos 2 mapas |
| e2e: criar, ordenar, salvar, recarregar, mesma ordem, captura | `tests/e2e/test_mapa_documento.py` contra `https://127.0.0.1:8172` | PASSOU — captura `tests/e2e/capturas/L2-01-a-documento-mapa_painel_camadas.png` (não vai para o git: `.gitignore` ignora `capturas/*.png`) |
| tabela Web Map Spec → documento nosso em `docs/PARIDADE.md`, feito/parcial/fora por chave | seção nova, 3 tabelas (raiz, operationalLayers/groupLayer, baseMap) | PASSOU — chaves lidas em 06/09 em `developers.arcgis.com/web-map-specification/objects/{webmap,operationalLayers,featureLayer,groupLayer,baseMap}` |

Refutação exigida (rodei eu mesmo; o adversário deve repetir e ir além):

| ataque | resultado |
|---|---|
| camada de outro inquilino | 404, nunca 200 (`test_camada_de_outro_inquilino_e_404_ao_salvar`) |
| 5 níveis de grupo | 422 `documento_incoerente`, regra `grupo_profundo` |
| ciclo de grupo | 422, regra `grupo_ciclo`, sem laço infinito (unitário cobre o caminho) |
| 500 camadas | 422 `dados_invalidos` (teto 200 no esquema) |
| extensão fora do mundo | 422 pelo esquema (4 posições testadas); extensão invertida = 422 `documento_incoerente` |
| `/completo` conferido contra o banco | `test_completo_resolve_camadas_estilo_e_campos` lê `plat.item` direto com `plat_app` e compara título, campos, srid e geometria |
| erro 500 | nenhum em toda a bateria |

## O que ficou de fora, e por quê (fronteira honesta)

1. **URL de tiles não é promessa.** `/completo` devolve o CONTRATO (`/tiles/{token}/c_<16 hex>/{z}/{x}/{y}.pbf`
   e `/raster/{token}/<uuid>/{z}/{x}/{y}.png`) com `pronto: false` e o motivo: não há Martin nem
   TiTiler instalados (itens L2-01-b e L1-02; conferido: `/usr/local/bin/martin` não existe e não há
   unidade `plat-martin`). Camada de conexão externa sai com a URL real que o item de conexão registra.
2. **`dominios` sai sempre `{}`** com `dominios_motivo` escrito: não existe vocabulário de domínio por
   campo na camada (dependência **L0-04-c está PARCIAL**). Campo vazio com motivo, nunca valor inventado.
3. **`filtro`** é validado como objeto; a gramática CQL2-JSON é do item L2-01-h.
4. **`estilo.embutido` / `popup.embutido`** são objetos livres até L2-02-a e L2-01-d fixarem a forma.
5. **A tela não desenha as camadas do documento no canvas** (mesmo motivo do item 1) — mostra o selo
   "sem tiles" com o motivo, em cada linha.
6. **`docs/openapi.json` NÃO foi regerado.** `make openapi` regeneraria o arquivo com as rotas em voo do
   outro agente desta árvore, que ainda não estão comitadas. **Pendência do merge: rodar `make openapi`
   na árvore principal depois de juntar os dois ramos.** Nenhum teste reprova por isso (o teste compara
   "comitado ⊆ aplicação").
7. **`tests/e2e/servidor_local.py` não é meu** — apareceu no worktree durante o turno, de outra trilha, e
   fica sem commit meu. O e2e depende dele.

## Quebra declarada

`corpo.camadas` como lista de uuid soltos (a forma que existia enquanto o tipo `mapa` tinha `corpo`
livre) passa a ser 422. Nenhum código de `app/` gravava assim; 4 arquivos de teste gravavam e passaram a
usar `documento_mapa(...)` de `tests/api/catalogo/conftest.py`. Quem tiver documento antigo no banco não
quebra na leitura, só no próximo PUT.

## Riscos de merge

- `app/main.py` (2 linhas), `app/catalogo/relacoes.py` (extrator do mapa), `CHANGELOG.md`,
  `docs/PARIDADE.md`, `web/js/i18n/pt-BR.json`, `tests/api/catalogo/conftest.py` — todos com mudança
  mínima e localizada, mas são arquivos que a árvore principal também mexe.
- **ADR**: usei `0022` porque `0018` foi tomado por outra trilha no meio do turno e `0019`/`0020`/`0021`
  já existem em outras árvores. Conferir no merge.
- **Migração**: `20260906T1549_documento_mapa.sql` (carimbo, não número). Conferir `ls db/migracoes | tail -3`
  no instante do merge; ela é idempotente e só faz `UPDATE` do esquema do tipo e `INSERT ... ON CONFLICT`
  de dois tipos de relação.
- A migração **não foi aplicada ao schema `plat` de produção** (regra: worktree não toca produção). Aplicar
  no merge com `sudo -u postgres PLAT_MIGRACOES=$PWD/db/migracoes bash db/migrar.sh`.

## Estado da base de teste

`plat_tstac` **NÃO foi apagado**: o outro agente desta mesma árvore estava usando a mesma base no
momento do fim do turno (subiu servidor de e2e a partir de `/home/dev/plataforma/wt/stac`). Apagar
derrubaria o turno dele. Quando ninguém mais estiver usando:

    sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tstac CASCADE; DROP SCHEMA plat_trabalho_tstac CASCADE'

Também apliquei nessa base as duas migrações em voo do outro agente (`20260906T1540_migracao_inventario_portal`,
`20260906T1544c24_procedencia_item`), sem as quais o código compartilhado da árvore não roda.

## Falhas de teste que NÃO são deste item (medidas, não suposições)

- `tests/api/catalogo/test_documento.py`, `test_eventos_e_seguranca.py`, `test_busca.py::test_facetas_...`:
  conectam com DSN de `plat_app` de produção e falham na base da trilha (senha) — pré-existente.
- `tests/unit/test_jobs_registro.py`: `conexao.copiar_vetor` com `memoria_mb=1024` fora da faixa — vem do
  `app/jobs/tipos.py` em voo do outro agente.
- `test_camada_usada_por_mapa_nao_apaga_sem_cascata` e outros que exigem `plat-worker` vivo: o worker do
  systemd atende o schema `plat`, não a base da trilha.
