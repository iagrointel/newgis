# L0-09-metadado-catalogo — turno 3 (sessão única: arquiteto+backend, com pesquisa/teste do próprio autor)

**Objetivo desta passagem** (escopo dado pelo gerente, mais estreito que a hipótese cheia do item no
backlog): exportação de metadado ISO 19139/19115-3 por item (`GET /api/itens/{id}/metadado.xml`), validada
contra o XSD oficial; catálogo CSW básico OU OGC API Records (escolher um, justificar) para descoberta
externa por protocolo padrão, autenticado por token de serviço do L0-02 — nunca aberto.

## Portão do item no backlog (para referência; cobre só uma fatia dele)

> **portão de pronto** (do item inteiro, maior que esta passagem): editor de metadado com exportação ISO
> válida (valida contra XSD); CSW GetRecords e OGC API Records respondem e passam no validador; dependências
> mostram "usado por"; e2e; paridade escrita
> **refutação do item**: adversário apaga item com proteção ligada e item usado por mapa: deve recusar

O que falta do portão do item **já existe de outro item** (L0-03-catalogo, dependência declarada): proteção
contra exclusão (`protegido`), "usado por" (`item_relacao`/`usado_por`), histórico de versões
(`item_versao`), transferência de dono — todos na ADR 0004, seções 4/5/9/10, testados por outro turno. A
refutação do backlog ("apaga item protegido/usado deve recusar") portanto já está coberta ali, não aqui.
**Esta passagem só cobre a metade nova**: exportação ISO + catálogo externo por protocolo padrão.

## O que fiz

### 1. Escolha de protocolo: OGC API Records, não CSW (justificativa)

Decidido por `app/catalogo/rotas_ogc.py` (docstring do módulo) e `docs/PARIDADE.md`: (1) toda a API deste
repositório já é JSON/REST com o mesmo contrato de auth (sessão ou `Authorization: Bearer` com escopo); OGC
API Records é do mesmo estilo, CSW é XML/SOAP-like com gramática de filtro própria (Filter Encoding/CQL) que
exigiria um parser novo; (2) RAM desta máquina medida no limite (23 GB, ~2 GB livres) e nenhuma biblioteca
CSW está instalada (`owslib` ausente — confirmado, `pip show owslib` = not found); instalar um serviço CSW
correto (pycsw) não cabia no orçamento do turno; (3) OGC API Records é a linha ativa do OGC (Records 1.0,
20-004r1) enquanto CSW 2.0.2 é legado. Custo de mudar registrado como médio (um roteador novo reaproveitando
`listar_ids`/`carregar_varios`, que já fazem o trabalho pesado).

### 2. Exportação ISO 19139 (`app/catalogo/metadado.py`, sem migração)

Perfil escolhido: **ISO 19139/GMD**, não 19115-3 — é o que o Perfil MGB 2.0/GeoNetwork da INDE realmente
consomem (D17 do `L0_CONCEITO.md`; confirmado por pesquisa: Portal for ArcGIS 11.2 suporta os dois como
estilos separados, `enterprise.arcgis.com/en/portal/11.2/use/metadata.htm`, testado por HTTP 06/09/2026).
`montar_md_metadata()` monta a árvore `gmd:MD_Metadata` inteira à mão com `lxml.etree` (namespaces gmd/gco),
mapeando: `fileIdentifier`=id, `language`="por", `hierarchyLevel`="dataset", `contact`=inquilino
(`auth.tenant_nome`, role `pointOfContact`), `dateStamp`=modificado_em, `referenceSystemInfo`=EPSG:4326,
`identificationInfo/MD_DataIdentification` com `citation` (título+datas de criação/revisão+identifier=uuid),
`abstract` (resumo ou descrição, nunca vazio), `credit`=creditos, `status` mapeado (`autoritativo`→
`completed`, `obsoleto`→`obsolete`), `pointOfContact`=dono do item (role `owner`), `graphicOverview` se há
miniatura, `descriptiveKeywords`=tags, `resourceConstraints/MD_LegalConstraints/useLimitation`=termos_de_uso,
`language`, `extent`/`EX_GeographicBoundingBox` se há bbox; `distributionInfo` com dois `onLine` (item JSON e
o próprio metadado.xml); `dataQualityInfo/lineage` **só** quando `dados.procedencia` existe (D17: "procedência
errada é pior que nenhuma" — sem bloco de procedência, sem lineage genérico inventado). `topicCategory`
deliberadamente OMITIDO: a lista fechada de 19 valores ISO não tem tradução única e correta a partir de
`tipo`/`familia` sem inventar (documentado no docstring do módulo).

### 3. XSD oficial cacheado offline (`docs/xsd/baixar_iso19139.py` + `docs/xsd/cache/`)

Baixei a árvore XSD real de `schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd` (o perfil que GeoNetwork usa
para `schema=iso19139`) — BFS seguindo `schemaLocation`, 57 arquivos (gmd, gco, gsr, gss, gts + a GML 3.2.1
que eles puxam + xlink/xml do W3C), 611.925 bytes. O script reescreve **todo** `schemaLocation` absoluto
(http/https, схemas.opengis.net e www.w3.org) para caminho relativo dentro do próprio cache, antes de gravar
— por isso a validação nunca mais toca rede depois de rodado uma vez (prova no teste: `lxml.XMLSchema`
carrega com `socket.socket` bloqueado de propósito). Cache comitado no repositório (796 KB) — não é gerado no
deploy; `install.sh` ganhou o passo "f2" que roda o script de novo (idempotente, sem rede quando já presente)
como cinto-e-suspensório. `docs/xsd/cache/MANIFESTO.json` registra url de origem + sha256 + bytes de cada
arquivo.

Estudei o XSD real (não assumi a forma) antes de escrever o gerador: li `metadataEntity.xsd`
(`MD_Metadata_Type`: `contact`/`dateStamp`/`identificationInfo` obrigatórios, resto opcional, ORDEM fixa da
sequência), `identification.xsd` (`AbstractMD_Identification_Type`+`MD_DataIdentification_Type`: `citation`/
`abstract`/`language` obrigatórios), `citation.xsd`, `extent.xsd`, `referenceSystem.xsd`, `constraints.xsd`,
`distribution.xsd`, `dataQuality.xsd`, `gcoBase.xsd` (`CodeListValue_Type`: `codeList`/`codeListValue`
`xs:anyURI`, obrigatórios) — o gerador segue a ORDEM exata da sequência XSD (violar ordem é erro de schema
mesmo com todo campo presente).

### 4. Rota `GET /api/itens/{id}/metadado.xml` (`app/catalogo/rotas_itens.py`)

Inserida logo depois de `ver()`. Reaproveita `item_ou_404`+`auth.contexto()` — **a RLS de `plat.item` decide
tenant, não um filtro escrito na rota** (mesmo padrão de toda outra leitura do catálogo); `escopo_token=
"catalogo:ler"` (sessão OU token de serviço). Gera o XML, VALIDA contra o XSD ANTES de responder (nunca
confia em si mesma); `ErroXSDAusente`→`503` (cache não provisionado nesta máquina); `ErroMetadadoInvalido`→
`500` (erro de build do gerador — nunca deveria acontecer para item bem formado, mas se acontecer é bug
nosso, não pedido malformado do cliente).

### 5. `/ogc/records` (`app/catalogo/rotas_ogc.py`, novo módulo, registrado em `app/main.py`)

Prefixo `/ogc/` já era reservado na arquitetura (`app/limite_corpo.py`/`app/auth/middleware.py` já tratavam
`/ogc/` como prefixo de API desde antes deste item — confirmado lendo o código, não suposto). Rotas: pouso
(`/ogc/records`), `/conformance` (cita só Core+JSON — não Filter/Sorting/Queryables, porque não implementei
CQL2/ordenação), `/collections` (1 coleção: `catalogo`, o catálogo inteiro do inquilino), `/collections/
catalogo/items` (GeoJSON FeatureCollection; filtros `q`/`bbox`/`tipo`/`tags`, paginação `limit`/`offset`/
`cursor`, reaproveitando `listar_ids`+`carregar_varios` de `rotas_itens.py` **sem reescrever a busca**),
`/collections/catalogo/items/{id}`. Cada registro tem `links` para o item JSON e para o `metadado.xml`. TODAS
as rotas exigem `catalogo:ler` (sessão ou token) — nunca abertas, nem a página de pouso (decisão literal do
portão "nunca aberto").

## Evidência (comando + saída literal)

```
$ ./venv/bin/python docs/xsd/baixar_iso19139.py
...
MANIFESTO.json: 57 arquivos

$ ./venv/bin/python -c "
import socket, lxml.etree as ET
def bloqueado(*a,**k): raise RuntimeError('rede!')
socket.socket = bloqueado
ET.XMLSchema(ET.parse('docs/xsd/cache/schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd'))
print('schema carregado OK, offline')
"
schema carregado OK, offline

$ flock /home/dev/plataforma/laco/.pytest.lock -c "... venv/bin/pytest tests/api/catalogo/test_metadado_ogc.py -v"
tests/api/catalogo/test_metadado_ogc.py::test_metadado_xml_valida_contra_xsd_oficial PASSED
tests/api/catalogo/test_metadado_xml_item_minimo_tambem_valida PASSED
tests/api/catalogo/test_metadado_xml_404_item_inexistente_e_de_outro_inquilino PASSED
tests/api/catalogo/test_metadado_xml_por_token_de_servico_catalogo_ler PASSED
tests/api/catalogo/test_ogc_records_nunca_aberto PASSED
tests/api/catalogo/test_ogc_records_pouso_e_conformidade PASSED
tests/api/catalogo/test_ogc_records_colecao_catalogo PASSED
tests/api/catalogo/test_ogc_records_items_isolamento_por_inquilino PASSED
tests/api/catalogo/test_ogc_records_item_tem_link_para_metadado_xml PASSED
tests/api/catalogo/test_medidas_l0_09 PASSED
========================= 10 passed in ~3s =========================

$ ./venv/bin/ruff check app/catalogo/metadado.py app/catalogo/rotas_ogc.py docs/xsd/baixar_iso19139.py tests/api/catalogo/test_metadado_ogc.py
All checks passed!
```

Medidas (`tests/medidas/L0-09-metadado-catalogo.json`): mediana de 5x `GET .../metadado.xml` (gera + valida)
= **10,4 ms**; cache do XSD = 57 arquivos / 611.925 bytes.

## Refutação própria (a prova mais importante do item)

`test_metadado_xml_404_item_inexistente_e_de_outro_inquilino`: sessão do inquilino A pedindo o metadado.xml
de item do inquilino B → `404` (não `403`, mesmo padrão de todo o catálogo). `test_metadado_xml_por_token_de_
servico_catalogo_ler`: token `catalogo:ler` do inquilino A → `200` no item de A, `404` no item de B, mesmo
sabendo o uuid certo. `test_ogc_records_items_isolamento_por_inquilino`: `GET /ogc/records/collections/
catalogo/items` com token de A nunca inclui o id do item de B na lista, e `/items/{id}` do item de B → `404`;
sessão de B nunca vê o item de A na mesma busca. `test_ogc_records_nunca_aberto`: as 4 rotas OGC (inclusive o
pouso) recusam sem `Authorization`/cookie com `401`.

## Riscos

- Adversário INDEPENDENTE do turno não rodou contra este item (o gerente desta sessão fez arquitetura+
  backend+teste próprio; `docs/PARIDADE.md` registra isso explicitamente, não escondido).
- Nenhuma migração foi necessária (não toquei `db/migracoes/`), o que também significa que não há como
  colidir número de migração com as outras trilhas do turno (que usaram 027-029 concorrentemente).

## Pendências (nomeadas, não escondidas)

1. **ISO 19115-3** (perfil `mdb`/2.0): só 19139 nesta passagem — justificado (é o que INDE/GeoNetwork
   realmente consomem hoje). Custo de acrescentar: um segundo gerador + um segundo XSD cacheado (a mesma
   técnica de `baixar_iso19139.py` serve, mudando a URL semente).
2. **CSW**: fora desta passagem (seção 1 acima). Custo médio.
3. **Varredura cruzada A→B automática** (`docs/openapi.json`/`tests/api/cruzado_casos.py`): as duas rotas
   novas NÃO foram acrescentadas a esses dois arquivos porque, no momento da construção, DUAS outras trilhas
   do mesmo turno (`L0-04-ingestao`, `L5-05-documento-versoes`) estavam regravando exatamente esses arquivos
   ao vivo (concorrência real, confirmada por `git status`/`git diff` — `app/main.py` e `app/catalogo/
   rotas_itens.py` também mudaram por baixo enquanto eu trabalhava, por essas duas trilhas). Rodar `make
   openapi` no meio disso capturaria rotas parciais de trilhas alheias num commit atribuído a este item.
   Fica para quem fizer a integração final do turno somar TODAS as rotas novas de uma vez. **A isolação por
   inquilino das minhas duas rotas já está PROVADA** pelos testes próprios (não depende dessa varredura
   genérica para ser verdade, só para ser automática).
4. Editor de metadado na TELA (frontend): não existe; `dados.procedencia` e os campos que a exportação usa
   são escritos hoje por API/JSON direto no item, não por formulário.
5. Adversário independente do item ainda não rodou (ver Riscos).

## Concorrência real durante a construção (não escondida)

O repositório teve MUITA atividade simultânea de outras trilhas durante esta sessão: `app/main.py` e
`app/catalogo/rotas_itens.py` foram editados por baixo enquanto eu trabalhava (o item L5-05-documento-
versoes acrescentou `documento.validar_grafo`/`migrar_para_leitura`/rotas `/api/esquemas` no MESMO arquivo
`rotas_itens.py`; o L0-04-ingestao acrescentou `rotas_ingestao` em `main.py`); `MANUAL.md`, `ARQUITETURA.md`,
`CHANGELOG.md` e `docs/PARIDADE.md` também ganharam seções de outras trilhas nos mesmos minutos. Em vez de
`git add` cru (que teria arrastado trabalho alheio incompleto para dentro do meu commit, ou pior, um commit
com código de outro item ainda sem teste/veredito), usei em cada arquivo compartilhado a técnica: (1)
reconstruir "HEAD + só a minha edição" num arquivo à parte; (2) conferir com `diff` que o resultado é
IDÊNTICO a HEAD exceto pelo meu trecho; (3) `git hash-object -w` + `git update-index --cacheinfo` para
colocar exatamente esse blob no índice, sem tocar a árvore de trabalho (que continuou com o trabalho de todo
mundo, para as outras trilhas continuarem). Also encontrei staged no índice compartilhado uma mudança de
OUTRA trilha em `docs/PARIDADE.md` que eu não tinha adicionado (evidência de que outra sessão também usa
`git add` diretamente no mesmo índice) — reconstruí a partir de HEAD para não a arrastar. Conferido
`git status`/`git log` logo após o commit: todo o trabalho alheio (commitado ou não) segue intacto.

## Para o próximo papel (cronista/gerente)

`app/catalogo/metadado.py`, `app/catalogo/rotas_ogc.py`, `docs/xsd/baixar_iso19139.py` + `docs/xsd/cache/`
· `docs/PARIDADE.md` (seção "Metadado ISO e catálogo externo") · `ARQUITETURA.md` (bullet no L0-09) ·
`MANUAL.md` seção 16 · `CHANGELOG.md` (entrada deste turno) · `tests/medidas/L0-09-metadado-catalogo.json`.
**Commitado: `c4f1c20`** ("Metadado ISO 19139 por item e catálogo externo OGC API Records"), 70 arquivos, só
os deste item (conferido `git status`/`git diff --cached` várias vezes antes do commit — nada de outras
trilhas foi arrastado; confirmado de novo depois do commit que o trabalho alheio continua intacto).

Estado do item no backlog: **parcial** — a fatia "exportação ISO + catálogo externo autenticado" está feita
e testada; o portão COMPLETO do item (editor na tela, CSW, ISO 19115-3, varredura cruzada automática) segue
aberto, com cada pendência nomeada acima. Sugestão para o próximo turno deste item: (a) somar as rotas novas
a `docs/openapi.json`/`cruzado_casos.py` numa integração que já capture as outras trilhas também; (b)
adversário independente; (c) decidir se ISO 19115-3/CSW entram nesta linha ou ficam definitivamente fora.
