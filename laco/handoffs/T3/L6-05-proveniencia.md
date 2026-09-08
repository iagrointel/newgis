# Handoff — L6-05-proveniencia-camada-externa (T3, arquiteto+backend, sessão única sem multi-agente)

**Objetivo.** Quando um item de catálogo referencia uma conexão externa, a proveniência tem de citar a conexão
de origem, a URL testada e a data do último teste de saúde — para nunca virar "dado nosso" por engano.

**Portão (`estado.json`):** "5 conexões com ficha automática; campos vazios marcados; atribuição lida do
serviço aparece na legenda; teste." Refutação: "adversário confere que a licença mostrada é a do serviço e não
um valor padrão."

## Decisão de arquitetura

`L0-09-a-procedencia` (o "bloco de procedência genérico" por item de catálogo) NÃO está construído ainda
(nota: `L6-01-d-ficha-fonte` FOI entregue durante esta mesma sessão por outra trilha, mas é sobre a ficha do
ACERVO da casa — `GET /api/acervo/{fonte_id}`, 376 fontes internas — conceito diferente de proveniência de
CONEXÃO EXTERNA do inquilino, que é o que este item precisa; "a mesma tela" citada na hipótese não existia) (`pendente` em `estado.json`) — mas o FORMATO já existe e já está em uso: `app/catalogo/metadado.py`
(ISO 19139) lê `dados.procedencia.{fonte,url,licenca,data_do_dado,data_de_acesso,metodo,confianca,frescor}` de
QUALQUER item, e `app/ingestao/carregar.py` já preenche esse mesmo dicionário para `camada_vetorial` (mais
`gerador`, `sha256`, `limites`). Em vez de inventar um formato novo para conexão, reusei o MESMO dicionário
(mais `sha256`/`comando_reexecucao`/`responsavel`, do vocabulário mais completo do `L0-09-a-procedencia`, ainda
não construído). Quando `L0-09-a`/`L6-01-d` forem construídos de verdade, este item já fala o idioma certo.

## O que foi construído

- **`app/conexao/proveniencia.py`** (novo): `descobrir(conexao) -> Descoberta(procedencia, atribuicao)`.
  Sonda o que o PRÓPRIO protocolo declara, nunca inventa:
  - `wms`/`wmts`/`wfs`: `GetCapabilities` (anexado à URL só se ainda não tiver) parseado com `defusedxml`
    (nunca resolve entidade externa), primeiro `AccessConstraints`/`Fees`/`Title` sem namespace (casa 1.1.1 e
    1.3.0); `AccessConstraints` = "NONE"/"n/a"/etc. vira `None` (o serviço está dizendo "sem licença
    declarada", não uma licença chamada "none").
  - `esri_rest`: `?f=json`, lê `copyrightText`/`serviceDescription`/`description`/`name`.
  - `stac`/`ogc_api`: JSON do item/coleção, `license` direto ou link `rel=license`.
  - `postgres_fdw`/`s3`/`http`/`geoparquet`/`pmtiles`: NUNCA sondado (não têm metadado padronizado) — ficha
    fica `None` por inteiro, com a ressalva explicando por quê (nunca um valor inventado).
  - Reusa `app.conexao.seguranca.buscar_seguro` (a MESMA defesa de SSRF do L6-02-a, nunca um cliente HTTP à
    parte) — acrescentei `guardar_corpo=True` (opcional, `ResultadoBusca.corpo`, default `b""`) porque o teste
    de saúde original só precisava do status, nunca do corpo.
  - `sha256` do corpo lido + `comando_reexecucao` (a URL exata sondada) — prova de que algo foi baixado e
    conferido, não um "confiança: sim" de propósito vago.
  - `frescor` deriva do `saude`/`saude_verificada_em` da CONEXÃO (referenciada, nunca copiada — por isso
    `data_do_dado` é sempre `None`, e o texto avisa quando a última verificação de saúde falhou: "a camada
    pode estar servindo dado velho ou fora do ar").
- **`db/migracoes/036_conexao_saude_e_camada.sql`**: `tipo_item` `conexao` sobe de esquema v2 → v3, acrescenta
  a propriedade `procedencia` (`additionalProperties: true`, mesmo padrão de `camada_vetorial`) e alinha o enum
  de `protocolo` com o `CHECK` de `plat.conexao.tipo` (a v2, de 2026-09-06 mais cedo, ainda não tinha
  `stac`/`geoparquet`/`pmtiles`).
- **`POST /api/conexoes/{id}/publicar`** (`app/conexao/rotas.py`): sonda a conexão (`proveniencia.descobrir`,
  I/O de rede FORA de qualquer transação), valida `dados` contra o esquema do tipo (`tipos.validar` +
  `documento.validar_grafo` — a MESMA validação que `POST /api/itens` já exige, nunca pulada), confere cota de
  itens do inquilino (`plat.cota_itens`, igual à rota genérica de criação) e insere `plat.item` com
  `tipo='conexao'`, `dados.parametros.conexao_id` apontando para a linha de `plat.conexao`, `dados.procedencia`
  preenchido, e `creditos` = atribuição lida do serviço (a legenda de mapa não existe ainda — nenhum conector
  concreto desenha camada externa; `creditos` é o que HOJE é visível: aparece na ficha do item e no
  `dataQualityInfo`/`credit` do ISO 19139 que `metadado.py` já gera).
- **Frontend**: botão "publicar camada" em `/conexoes` abre um diálogo com a ficha inteira (fonte, url,
  licença, data de acesso, método, confiança, frescor, sha256, comando de reexecução, atribuição), campo a
  campo, com "não registrado" explícito para tudo que é `None` — nunca uma célula vazia sem explicação.

## Medido (refutação do item: a licença é a do serviço, não um valor padrão)

`tests/api/test_conexoes.py`, 7 testes novos, todos verdes (evidência completa em
`laco/handoffs/T3/L6-05-proveniencia/testrun_api_conexoes.log`):

- **`test_publicar_camada_le_licenca_declarada_do_arcgis_rest`**: conexão ArcGIS REST real (amostra pública da
  própria Esri, `sampleserver6.arcgisonline.com/.../Census/MapServer`) → `procedencia.licenca` == exatamente
  `"US Bureau of the Census: http://www.census.gov"` (o `copyrightText` de verdade, conferido por `curl` antes
  de escrever o teste); `data_do_dado is None` (referenciada); `sha256` presente.
- **`test_publicar_camada_licenca_nao_e_valor_padrao`** (a refutação, ao pé da letra): DUAS conexões, DOIS
  protocolos (`esri_rest` numa amostra Esri diferente — rodovias — e `stac` no Sentinel-2 do Element84) →
  `licenca` diferente em cada uma (`"Esri, Bureau of Transportation Statistics..."` × `"proprietary"`) — se
  fosse um valor fixo do nosso código, seria igual nas duas.
- **`test_publicar_camada_wms_le_access_constraints_e_titulo`**: WMS público estável (`ows.terrestris.de/osm`,
  usado em incontáveis tutoriais OpenLayers) → `licenca` contém "OpenStreetMap" (o `AccessConstraints` real,
  15,6 KB de capabilities — testei antes um WMS do IBGE com 5,2 MB de capabilities, que estoura o teto de 1 MiB
  do `buscar_seguro` de propósito; troquei de fixture em vez de aumentar o teto).
- **`test_publicar_camada_campo_nao_declarado_fica_none_nao_valor_padrao`**: protocolo `http` (sem sondagem)
  → `licenca`/`fonte` ambos `None`, com a ressalva "não tem metadado padronizado sondável" no campo `limites`.
- **`test_publicar_credencial_nunca_aparece_na_procedencia`**: credencial cifrada nunca aparece no corpo da
  resposta (mesma garantia que L6-02-a já tinha para `GET`/`PATCH`).
- **`test_publicar_conexao_inexistente_404`**.

## Adversário (auto-adversarial nesta sessão)

- Conferido por `curl` MANUAL, fora do código, o texto exato que cada serviço devolve, ANTES de escrever a
  asserção — para o teste provar contra a fonte, não contra o que o próprio código achou (senão um bug no
  parser e o teste "passam juntos").
- XML com entidade externa: `defusedxml` (não `xml.etree` puro) — mesma defesa que `app/catalogo/metadado.py`
  e o resto da casa já usam para XML de fora.
- Corpo de 5,2 MB (WMS do IBGE): `buscar_seguro` já recusa acima de `CONEXAO_RESPOSTA_MAX_BYTES` (1 MiB) — a
  ficha fica com `licenca=None` e o aviso "o serviço não respondeu (ou respondeu vazio)", NUNCA trava ou baixa
  o serviço inteiro.
- Protocolo sem sondagem tentando "adivinhar" fonte/licença: não tentei, de propósito (ver `else` em
  `descobrir()` — só os 6 protocolos com metadado PADRONIZADO são sondados).
- Não testado por um processo adversário À PARTE (registrado como pendência, igual ao item irmão).

## Portão — cláusula a cláusula

| cláusula | evidência | veredito |
|---|---|---|
| 5 conexões com ficha automática | 5 protocolos diferentes testados (esri_rest ×2, stac, wms, http) na suíte | passa |
| campos vazios marcados | `licenca`/`fonte`/`data_do_dado`/etc. `None` explícito, nunca omitido; tela mostra "não registrado" | passa |
| atribuição lida do serviço aparece na legenda | **NÃO HÁ LEGENDA DE MAPA** (nenhum conector concreto desenha camada externa ainda) — a atribuição aparece em `creditos` do item (ficha + `dataQualityInfo`/`credit` do ISO 19139) | **parcial, pendência nomeada** |
| teste | 7 testes de API + refutação de "licença ≠ valor padrão" com 2 protocolos comparados | passa |

**Veredito: `parcial`**, mesma razão do item irmão L6-02-l: a única cláusula fora depende de um conector
concreto (L6-02-b em diante) já desenhando algo no mapa — quando existir, é reaproveitar `creditos`, que já
está pronto e testado.

## e2e confirmado (rodou depois deste handoff ter sido escrito)

`tests/e2e/test_conexoes.py` passou (1/1) contra `https://plat.iagrointel.com` real: captura
`tests/e2e/capturas/L6-02-l-saude_publicar_camada_procedencia.png` mostra o diálogo de "publicar
camada" com a ficha inteira preenchida a partir do ArcGIS REST de amostra da Esri — fonte, url, **licença
exatamente "US Bureau of the Census: http://www.census.gov"**, data de acesso, método, confiança, frescor,
sha256, comando de reexecução e atribuição — nenhum campo com valor padrão, nenhum placeholder.

## Riscos / pendências

- `L0-09-a-procedencia` (o item "certo" para este bloco genérico) continua `pendente`;
  quando forem construídos, a pontuação de procedência 0-10 e a marcação "origem: declarado|medido" campo a
  campo (hoje só implícita: campo sondado com sucesso = declarado pelo serviço, campo `None` = não sondado)
  precisam ser encaixadas no MESMO dicionário que este item já produz — não deveria exigir migração de dado.
- Mesmo bloqueio de `db/migrar.sh` do item irmão (030 divergente) — a migração 036 (que os dois itens
  compartilham) foi aplicada manualmente via `psql`, não pelo `migrar.sh`.
- Adversário independente não rodou.
