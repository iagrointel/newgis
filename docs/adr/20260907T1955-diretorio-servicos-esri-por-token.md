# Diretório de serviços Esri escopado por token no caminho (item L2-04-b)

Estado: aceito. Data: setembro de 2026.

## Problema

A plataforma já servia um FeatureServer por camada (`/rest/services/{item}/FeatureServer`, itens
L2-04-c e L2-04-servicos-esri-ogc). Faltava o passo anterior: um cliente que ainda não sabe o UUID da
camada não tem por onde começar. ArcGIS Pro, o conector "ArcGIS REST Server" do QGIS e o `arcgis` do
Python pedem uma RAIZ de serviços e descem sozinhos a partir dela — pastas, serviços, camadas,
campos. Sem essa raiz, quem opera precisa colar uma URL diferente por camada.

## Decisão

O diretório fica em `/svc/{token}/rest/...`, com o token de serviço no CAMINHO.

1. **Token no caminho, não em cabeçalho.** A raiz é entregue por quem opera, copiando uma URL. Uma
   URL com o token dentro navega inteira; um cabeçalho `Authorization` não sobrevive a copiar e
   colar, e o próprio protocolo Esri já pressupõe `?token=` na URL. A consequência está declarada:
   quem tem a URL tem o acesso do token. Por isso `generateToken` emite token de LEITURA com teto de
   24 h, e a rotação/revogação é a mesma do resto da plataforma (`plat.token_servico`).
2. **A segregação é a RLS, não um filtro de aplicação.** Todo recurso do diretório abre
   `db.db(auth.contexto())` com o inquilino do token; o catálogo lista o que a RLS deixa ler, e a
   camada de outro inquilino responde 404 pelo mesmo caminho que a própria responde 200.
3. **O FeatureServer não foi reescrito.** `rotas_servico.descritor_do_servico`, `descritor_da_camada`
   e `_camada_por_id` passaram a ser funções públicas do módulo, e o diretório as chama. Uma segunda
   cópia do descritor envelheceria em separado — é o defeito clássico desta família de rotas.
4. **`f` e `callback` num lugar só.** `app/consulta/formato_esri.py` decide json/pjson/html/JSONP para
   todo recurso. `f=html` responde uma página simples: o que não pode acontecer é 500 num formato que
   o protocolo prevê. O nome da função de JSONP é validado contra identificador simples e recusado
   com 400 quando não é — ele é escrito dentro de um documento JavaScript.
5. **CORS aberto só em `/svc`, `/ogc` e `/tiles`.** Nesses caminhos a credencial é o token da URL, e
   uma origem qualquer que o tenha já leria por `curl`. Em `/api` a credencial é o cookie de sessão:
   CORS aberto ali seria falsificação de requisição entre sítios com resposta legível. O middleware
   nunca emite `Access-Control-Allow-Credentials`.
6. **`drawingInfo` vem do estilo declarado, ou é cinza assumido.** `app/consulta/renderizador.py`
   converte cor constante em `simple`, `["match", …]` em `uniqueValue` e `["step", …]` em
   `classBreaks`, e `layout.text-field` em `labelingInfo`. Qualquer outra expressão (interpolação,
   cor por zoom) NÃO é convertida: sai `simple` cinza com o motivo no campo `_conversao`. Um renderer
   aproximado pintaria o mapa do cliente com uma classificação que não é a dele.
7. **O estilo se liga à camada pela relação `estilo_de_camada`.** Ela já existe em
   `plat.relacao_tipo` e é declarada por `PUT /api/itens/{estilo}/relacoes` — o descritor a LÊ, e
   nada foi acrescentado ao catálogo por causa disto. Uma primeira versão pôs um extrator de
   relações para o tipo `estilo` (`corpo.camada_id`) e foi desfeita: tipo com extrator tem as
   relações derivadas de `dados`, e o `PUT /relacoes` deixa de ser aceito — o que quebrou
   `tests/api/catalogo/test_relacoes.py`. Ler a relação que já existe é menos código e não muda
   contrato de outra linha.

## O que ficou declarado como ausente, não simulado

`fields[].domain` sai `null`, `types`/`subtypes` saem vazios e `relationships` sai vazia porque as
linhas L2-10-a e L2-10-b não estão nesta base. `capabilities` anuncia só `Query` e `syncEnabled` é
`false` porque a edição transacional (L2-03-a) também não está. Anunciar capacidade sem mecanismo é o
mesmo defeito de um botão que não faz nada — o cliente Esri tentaria usar e falharia no meio.

## Consequências

`currentVersion` subiu de 11.3 para 11.4, que é o que a operação `query` já entrega (`fullText`,
`returnEnvelope`, `esriFieldTypeDateOnly`/`TimeOnly`/`BigInteger`). O corpo do formulário de
`generateToken` é lido com `urllib.parse.parse_qsl` e não com `request.form()`, que exigiria a
dependência `python-multipart` só para reler duas chaves.
