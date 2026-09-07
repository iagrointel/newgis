# ADR 20260907T2200 — catálogo de conectores públicos prontos (item L6-02-m-catalogo-endpoints-brasil)

Estado: aceita (07/09/2026). Linha L6, decisão B12 do L3L6_CONCEITO ("catálogo de endpoints prontos vem do
registro vivo, não de lista digitada; retestado por semana; entrada morta some").

## Contexto

O registro do acervo (`acervo.endpoint`, exposto por `plat.acervo_endpoint`, migração 040) tem 342 endereços
confirmados e vivos, mas quase todos são páginas e catálogos, não serviços: filtrando por padrão de URL sobram
46 linhas, ~20 endereços-base únicos, e só 10 passam a regra D17 (fonte com licença escrita). A hipótese pede um
catálogo de "um clique" com dezenas de serviços OGC/ArcGIS REST/STAC.

## Decisões

1. **Tabela global `plat.endpoint_publico`, escrita só por função.** Uma linha por (tipo, url base); `plat_app`
   só lê; `endpoint_publico_semear(jsonb)` e `endpoint_publico_registrar(...)` (SECURITY DEFINER, mesmo padrão de
   `conexao_saude_registrar`) são a única escrita, chamadas pelo job `endpoints_publicos.retestar`. Nenhum
   inquilino edita o catálogo; a conexão que nasce dele é do inquilino, como qualquer `plat.conexao`.
2. **Três origens, o mesmo teste.** `registro` (derivado de `plat.acervo_endpoint` com `tipos_da_url`: GeoServer
   `/ows` vira WMS e WFS, `rest/services` vira `esri_rest` até o serviço), `curadoria` (semente JSON no
   repositório: serviços públicos federais, estaduais e municipais) e `fila_keyless` (catálogos STAC e serviços
   globais sem chave, os da fila do mapa aberto da casa). A semente é lista digitada, sim — mas nunca aparece sem
   passar pelo mesmo reteste semanal, e a poda de 07/09 tirou 29 endereços adivinhados que não existiam.
3. **"Vivo" é assinatura do corpo, não HTTP 200.** `testar` pede o documento do protocolo (GetCapabilities,
   `?f=json`, raiz STAC/OGC API) e confere: raiz `*Capabilities` (nunca `ExceptionReport`, nunca `<html`), JSON
   ArcGIS sem `error`, `stac_version`, `links`. Refutação do item ("200 que devolve HTML de erro conta como morto")
   é o caso `html_no_lugar_do_servico`; um FeatureServer que responde 200 com `{"error": "Token Required"}` é
   `arcgis_error`. Capabilities acima de 4 MiB conta como vivo (o serviço respondeu XML; a INDE passa de 1 MiB).
4. **Morto sai da lista no mesmo teste, sem apagar.** A API lista `vivo = true`; `vivo = false` é a seção "fora do
   ar" (com motivo e data); `adicionar` em entrada morta devolve 409. Volta sozinha quando o reteste passar
   (`primeiro_ok_em` e `falhas_seguidas` guardam a história).
5. **Licença nunca inferida.** `licenca` segue o vocabulário B3; `nao-declarada` quando o órgão não publica termo
   em página própria — a ficha de procedência da conexão criada carrega isso como ressalva, e o `publicar`
   completa com o que o serviço vivo declarar.

## Consequências

- Medido em 07/09/2026 (`tests/medidas/L6-02-m-catalogo-endpoints-brasil.json`): 100 candidatos, 78 verdes
  (WMS 20, WFS 16, WMTS 6, ArcGIS REST 20, STAC 12, OGC API 4; 3 do registro, 51 curados, 24 sem chave).
- e2e: 10 conectores adicionados pela tela `/conexoes` (seção "conectores públicos prontos") num servidor da trilha
  atrás de uma frente que serve `/static/` e reescreve `Origin` para a URL pública (o papel do nginx em produção;
  a checagem de origem da sessão exige `https://` e a URL pública configurada).
- Não coberto: GeoWebCache WMTS de vários GeoServers responde 400 ao GetCapabilities KVP (fica fora do ar até se
  medir o caminho REST); conectores `http`/COG por URL não entram (tipo sem teste de assinatura definido).
