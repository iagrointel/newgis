# ADR 20260907T2115 — descoberta por catálogo CSW 2.0.2 (item L6-06-descoberta-csw)

Estado: aceita (07/09/2026). Linha L6, decisão B6 (conexão em dois modos) e B11 (ficha única) do L3L6_CONCEITO.

## Contexto

A INDE e geoportais de órgãos publicam catálogos CSW 2.0.2 (GeoNetwork, pycsw) com registros ISO 19139 que
declaram, em `CI_OnlineResource`, os serviços WMS/WFS/WMTS do dado. Hoje a conexão externa nasce de URL colada
à mão (`POST /api/conexoes`) e a ficha de procedência só sabe o que o `GetCapabilities` do serviço diz. O
registro do catálogo sabe mais (organização, data do dado, restrições, linhagem, extensão).

## Decisões

1. **O catálogo não vira `plat.conexao`.** A busca recebe a URL do CSW a cada pedido (`POST /api/csw/buscar`)
   e a criação recebe URL + identificador (`POST /api/csw/conexoes`). Um tipo `csw` em `CONEXAO_TIPOS` não foi
   acrescentado: não há saúde a monitorar nem camada a servir de um catálogo, e a decisão B12 (endpoints
   prontos vêm do registro vivo, não de lista digitada) cobre o "um clique" quando o catálogo de endpoints
   existir. Custo de mudar depois: baixo (as rotas ficam; um tipo `csw` seria só um atalho para a URL).
2. **Pedido por GET KVP, nunca POST de XML.** `GetRecords` com `CONSTRAINTLANGUAGE=CQL_TEXT`
   (`AnyText like '%texto%' AND BBOX(ows:BoundingBox,o,s,l,n)`) e `outputSchema=http://www.isotc211.org/2005/gmd`;
   `GetRecordById` com `elementSetName=full`. Motivo: é o único caminho que passa por `buscar_seguro` (SSRF,
   bytes, tempo, redirecionamento revalidado) sem cliente HTTP à parte; medido na INDE em 07/09/2026
   (HTTP 200, 10.134 registros para "hidrografia", 394 com bbox de São Paulo, 52 para "tuberculose").
3. **Serviço = protocolo `OGC:WMS|WFS|WMTS` E endereço http(s).** Protocolo declarado com `linkage` vazio
   (caso real: cartas topográficas do IBGE na INDE) NÃO é serviço: vira aviso, e um registro só com esses
   devolve 422 `sem_servico_ligado` sem criar nada (refutação do item). Sem protocolo, só `service=WMS|WFS|WMTS`
   explícito na URL conta. A URL da conexão é o endereço BASE (sem querystring); a camada (`gmd:name` ou
   `layers=`/`typeName=`) e a URL declarada ficam em `config`.
4. **Ficha do ISO em `config.procedencia` da conexão; o serviço vivo vence ao publicar.** `proveniencia.descobrir`
   preenche do ISO só o campo que o `GetCapabilities` não declarou e escreve no `metodo` de onde veio cada parte.
   Licença = texto de `otherConstraints`/`useLimitation`; `MD_RestrictionCode` fica em `restricoes` e nunca é
   lido como licença (decisão B3: licença nunca inferida).
5. **Idempotente por (tipo, url, camada).** Segundo clique reaproveita a conexão existente (`criada: false`);
   nome = título do registro + `(WMS)`, com a camada no nome quando o título colide.

## Consequências

- Privilégio: buscar exige `conteudo.criar`; criar exige `conteudo.registrar_fonte` (o mesmo de `POST /api/conexoes`).
- Tela `/conexoes`: seção "descobrir por catálogo" com INDE como endereço inicial (verificado em 07/09/2026).
- Não coberto: catálogos estaduais (5 endereços adivinhados não resolveram em 07/09 — nenhum foi verificado),
  `GetRecords` por POST/Filter XML, CSW 3.0 / OGC API - Records (o `rotas_ogc.py` da casa é o lado servidor).
