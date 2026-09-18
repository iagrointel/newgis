# Alinhamento do pacote de ativos ao INSPIRE Generic Network Model (item L4-01-h)

Item pai: L4-01-a-pacote-de-ativos (esquema `plat.rede_*`, `app/rede_utilidades/esquema.py`). Este
documento mapeia esse pacote para o modelo genérico de rede de utilidades do INSPIRE — o "Generic
Network Model" (GNM), definido em três XSD oficiais, vendorizados offline em `gnm_xsd/` (cópia
verificada, catálogo de resolução em `gnm_xsd/catalogo.xml`):

| namespace | arquivo | o que define |
|---|---|---|
| `net` (`http://inspire.ec.europa.eu/schemas/net/4.0`) | `Network.xsd` | `Node`, `Link`, `LinkSet`, `NetworkElement` — o grafo genérico, comum a qualquer rede (não só utilidade) |
| `us-net-common` (`.../us-net-common/4.0`) | `UtilityNetworksCommon.xsd` | especialização para redes de UTILIDADE: `UtilityNode`, `UtilityNodeContainer`, `UtilityLink`, `UtilityLinkSet`, `Appurtenance`, `Cable`, `Pipe`, `Duct`, `Pole`, `Tower`, `Manhole`, `Cabinet` |
| `us-net-el` (`.../us-net-el/4.0`) | `ElectricityNetwork.xsd` | especialização elétrica: `ElectricityCable` (subtipo de `Cable`, com `nominalVoltage`/`operatingVoltage`) |

Não existe um `us-net-water` nem `us-net-gas` publicado pelo INSPIRE — água e gás usam as classes
genéricas de `us-net-common` (`Pipe`, `Appurtenance`) sem extensão própria. Isso é uma lacuna do
padrão, não do nosso mapeamento, e está registrada como tal.

## Decisão de implementação: `UtilityLink`, não `Cable`/`Pipe`/`ElectricityCable`

`Cable`, `Pipe`, `Duct` e `ElectricityCable` têm `substitutionGroup="us-net-common:UtilityLinkSet"`,
não `net:Link` — pertencem à cadeia de tipo `LinkSet` (uma coleção ORDENADA de `Link`s reais, sem
`centrelineGeometry`/`fictitious`/`startNode`/`endNode` próprios). Modelar um elo do pacote de ativos
como `LinkSet` exigiria criar, para cada elo, um `Link` genérico interno referenciado pelo `LinkSet` —
duas features por elo em vez de uma, sem ganho para o alinhamento pedido no portão. `UtilityLink`
(`us-net-common:UtilityLink`, `substitutionGroup="net:Link"`) É concreto, tem `centrelineGeometry` e
conectividade (`startNode`/`endNode`) diretas, e é o elemento que o próprio arquiteto de referência da
INSPIRE usa quando não há necessidade de path composto. O exportador (`app/rede_utilidades/
inspire_gnm.py`) usa `UtilityLink` para elétrica e água; `ElectricityCable`/`Pipe` como `LinkSet` fica
como extensão de trabalho futuro, registrada aqui, não escondida.

## Mapeamento campo a campo

Fonte única (código e texto): `MAPEAMENTO_GNM` em `app/rede_utilidades/inspire_gnm.py`.

### Geral (qualquer disciplina)

| pacote de ativos | GNM | nota |
|---|---|---|
| `pacote` (objeto inteiro) | `base:SpatialDataSet` | wrapper único; `pacote.codigo` -> `identifier/localId`; `pacote.nome` NÃO tem campo GNM (perde-se); `pacote.versao` -> não usado (haveria `identifier/versionId`, deixado de fora nesta versão do exportador) |
| `grupo` (ex. `chave_de_media_tensao`) | sem classe própria | vira o valor de `specificAppurtenanceType` do nó, como URI da própria ontologia do pacote (`https://iagrointel.invalido/esquemas/plat.rede.pacote/1#<disciplina>/<grupo>`) — nunca um código do INSPIRE, que não tem vocabulário fechado publicado para isso |
| `tipo` | referência genérica (`appurtenanceType`) | o código numérico do pacote não aparece no GML: o GNM não tem campo de código inteiro livre nessa posição |
| `atributo` (POT_NOM, PER_FER, DIC, FIC, …) | **sem correspondência** | o GNM modela TOPOLOGIA e STATUS regulatório, não os atributos operacionais do ativo (potência, corrente, diâmetro); nenhum atributo do pacote aparece no GML de saída — essa é a limitação central deste alinhamento, e não é um bug: o GNM não foi desenhado para isso |

### Elétrica (`eletrica-br.json`)

| pacote | GNM | elemento |
|---|---|---|
| nó (grupo com `geometria: "ponto"`) | `us-net-common:Appurtenance` | `net:geometry` (`gml:PointPropertyType`) |
| elo (grupo com `geometria: "linha"`, ex. `alimentador`) | `us-net-common:UtilityLink` | `net:centrelineGeometry` (`gml:CurvePropertyType`) |
| `appurtenanceType` (obrigatório no XSD) | fixo `urn:iagrointel:gnm:eletrica:no` | o INSPIRE define o codelist `ElectricityAppurtenanceTypeValue` como abstrato/vazio para extensão por implementador — não há vocabulário oficial publicado, então usamos URI própria |
| `nominalVoltage`/`operatingVoltage` (só existiriam em `ElectricityCable`) | **fora do GML** | decorrência de usar `UtilityLink` em vez de `ElectricityCable` (ver decisão acima); não há atributo de tensão nominal padronizado nos grupos hoje no pacote de qualquer forma |

### Água (`agua-epanet.json`)

| pacote | GNM | elemento |
|---|---|---|
| nó (`junction`, `tank`, `reservoir`) | `us-net-common:Appurtenance` | `net:geometry` |
| elo (`pipe`) | `us-net-common:UtilityLink` | `net:centrelineGeometry` |
| `pipeDiameter` (só existiria em `Pipe`) | **fora do GML** | mesma decorrência acima |

### Gás (`gas-br.json`)

| pacote | GNM | elemento |
|---|---|---|
| nó (`city_gate`, `estacao_de_medicao`, `juncao_de_gas`, `ponto_de_entrega`, `regulador`, `valvula_de_gas`) | `us-net-common:Appurtenance` | `net:geometry` |
| elo (`tubulacao_de_gas`) | `us-net-common:UtilityLink` | `net:centrelineGeometry` |
| `appurtenanceType` (obrigatório no XSD) | fixo `urn:iagrointel:gnm:gas:no` | mesma lacuna de codelist da elétrica: o INSPIRE não publica vocabulário de aparelhos para gás (não existe `us-net-og` utilizável) |
| `pipeDiameter` (só existiria em `Pipe`) | **fora do GML** | o pacote gas-br não modela diâmetro nominal com unidade normalizada |

## O que o exportador PROVA (portão de pronto)

1. Documento de mapeamento campo a campo — este arquivo + `MAPEAMENTO_GNM` (dado, não prosa solta).
2. Exportador (`app/rede_utilidades/inspire_gnm.py::exportar_gml`) que gera GML para 1 rede de teste
   por disciplina (elétrica: 3 nós / 2 elos com códigos reais do pacote `eletrica-br.json`; água: 2
   nós / 1 elo; gás: 3 nós / 2 elos com grupos reais do pacote `gas-br.json` — `city_gate`,
   `regulador`, `ponto_de_entrega`, `tubulacao_de_gas`), coordenadas dentro do Brasil, sem CAR nem
   dado de cliente.
3. Validação contra o XSD OFICIAL do INSPIRE (não uma cópia relaxada): `tests/unit/test_inspire_gnm.py`
   valida o GML gerado com `lxml.etree.XMLSchema` — a mesma engine libxml2 do `xmllint --schema`
   (lxml é binding da libxml2; o binário xmllint não está instalado neste servidor e a trilha proíbe
   alterar o sistema) — com resolução 100% OFFLINE via `gnm_xsd/catalogo.xml` (nenhuma chamada de
   rede durante o teste), e um teste negativo confere que GML adulterado é recusado pelo mesmo XSD.

Comando de reprodução manual (em máquina com xmllint instalado — o teste de CI usa lxml, mesma engine):

```
XML_CATALOG_FILES=app/rede_utilidades/gnm_xsd/catalogo.xml \
  xmllint --noout --schema app/rede_utilidades/gnm_xsd/inspire.ec.europa.eu/schemas/us-net-el/4.0/ElectricityNetwork.xsd \
  <(python3 -c "from app.rede_utilidades.inspire_gnm import exportar_gml, rede_teste_eletrica_br; import sys; sys.stdout.buffer.write(exportar_gml(rede_teste_eletrica_br()))")
```

## O que NÃO está feito (fronteira honesta)

- **Esgoto**: o portão de pronto nomeia elétrica, água e gás — os três têm mapeamento + rede de
  teste + validação XSD. Esgoto (`esgoto-teksi.json`) não é nomeado pelo portão e ficou de fora;
  o caminho é o mesmo de água/gás (Pipe/Appurtenance), sem surpresa esperada.
- **Atributos operacionais** (tensão, diâmetro, potência, corrente) não aparecem no GML — ver acima;
  reintroduzi-los exigiria usar `Cable`/`Pipe` (LinkSet) em vez de `UtilityLink`, ou estender o GNM
  com um `applicationSchema` próprio, o que o INSPIRE permite mas o portão não pediu.
- **teamengine** (validador oficial do INSPIRE usado em produção pela UE) não foi rodado — não há
  instância local nem acesso de rede autorizado nesta trilha; a prova usada é `xmllint` contra o XSD
  W3C XML Schema oficial (é a mesma peça que o teamengine consome internamente para a checagem
  estrutural; falta a camada de regras de negócio ATC/OGC que o teamengine testa por cima do XSD).
- **`versionId`/`inspireId`** (identificadores externos oficiais do INSPIRE) não são emitidos — o
  pacote de ativos não tem um namespace de identificador externo registrado (isso exigiria registro
  no "INSPIRE External Object Identifier Namespaces Register", fora do escopo de uma trilha de teste).
