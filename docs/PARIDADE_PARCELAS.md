# Paridade da malha de parcelas com o parcel fabric do ArcGIS Pro (item L4-parcelas-01-modelo-de-parcelas)

Documento de paridade do modelo de parcelas (`app/parcelas/`, migração
`20260908T2140_parcelas.sql`). Compara as seis tabelas por inquilino (`parcela_registro`,
`parcela_ponto`, `parcela_linha`, `parcela_linha_parcela`, `parcela`, `parcela_conexao`) e as duas
visões (`v_parcela_atual`, `v_parcela_historico`) com o modelo de dados do parcel fabric do ArcGIS
Pro 3.4.

Fontes (consultadas em 08/09/2026; as URLs sob `help/data/parcel-fabric/` estão FORA DO AR nesta
data — 404 —, então os fatos vêm das páginas vivas sob `help/data/parcel-editing/`):

- O que é o parcel fabric — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/whatisparcelfabric.htm`
- Esquema do parcel fabric (classes de feição, campos, domínios, editor tracking) — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/aboutparcelfabricschema.htm`
- Criar registros — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/createparcelfabricrecords.htm`
- Ver a linhagem (lineage) — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/viewparcellineage.htm`
- Parcelas estrato (strata parcels) — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/createstrataparcels.htm`

Regra do documento: paridade ≠ identidade. Onde o modelo diverge de propósito, a divergência está
marcada **[diverge — decidido]** com o motivo; onde falta por escopo do item, marca **[falta]** com
quem cobre. Nada aqui afirma comportamento do produto Esri além do que as páginas acima dizem.

Regra da casa que atravessa tudo: parcela ≠ gleba ≠ lote ≠ matrícula. O `codigo` do registro e da
parcela é texto do inquilino; nenhuma matrícula real e nenhum nome entra no modelo. SIGEF e CAR são
camada de referência, nunca parcela oficial.

## 1. O modelo em uma tabela

| conceito Esri (parcel fabric) | o que a documentação diz | aqui | estado |
|---|---|---|---|
| Records | classe de feição com **Name** (único), **Record Type**, **Recorded Date**, **GlobalID**, **Created Parcel Count**, **Retired Parcel Count** | `plat.parcela_registro`: `codigo` único por inquilino, `tipo` com vocabulário fechado (matricula, escritura, loteamento, desmembramento, remembramento, aprovacao, outro), `data_registro` | feito (sem contador gravado — computa à hora; §3) |
| Created By Record / Retired By Record | campos Guid no polígono, na linha, no ponto e na connection line; a parcela retirada vira **historic parcel** | `criada_por_registro` / `retirada_por_registro` em `parcela`, `parcela_linha`, `parcela_ponto`, `parcela_conexao`; retirada = `ativa = false` + `retirada_em` | feito |
| current × historic | a visão do "atual" contra o acervo histórico com o registro que retirou | `v_parcela_atual` (ativa) e `v_parcela_historico` (com `retirada_por_codigo`, `retirada_por_tipo`, `retirada_em`), ambas `security_invoker` — respondem com a RLS de quem consulta | feito |
| parcel type | classe de polígono + classe de linha SEPARADAS definidas pela organização (ex.: ownership, subdivision) | uma tabela `parcela` com coluna `tipo` e vocabulário fechado (lote, gleba, quadra, servidao, estrato) | feito **[diverge — decidido, §6]** |
| COGO nas linhas | **Direction**, **Distance**, **Radius**, **Arc Length**, **COGO Type**, Direction Accuracy, Distance Accuracy | `rumo_graus`, `distancia_m`, `raio_m` (com sinal), `arco_m`, `tipo_cogo` ('reta'/'arco'), `precisao_rumo_s`, `precisao_dist_cm` | feito (convenções divergem — §4) |
| Stated Area / Calculated Area | área declarada pelo registro contra a área calculada da geometria | `area_declarada_m2` declarado pelo chamador; `area_calculada_m2` SEMPRE do banco (`ST_Area`), nunca do chamador | feito |
| Misclose Ratio / Misclose Distance | erro de fechamento da malha de medidas | `erro_fechamento_m` (distância) e `erro_fechamento_razao` (perímetro ÷ erro; nulo quando fecha exato) | feito |
| Points | Name, **Fixed Shape**, **XY Accuracy**, Created/Retired By Record | `parcela_ponto`: `nome`, `fixo`, `precisao_xy_m`, `criada_por_registro`/`retirada_por_registro` | feito (ponto NÃO se retira por retirada de parcela — §5) |
| Connection Lines | "measurements between points that are not parcel boundaries", com COGO e Created/Retired By Record | `parcela_conexao` com rumo, distância, descrição e registro | feito (sem COGO de arco na conexão — §4) |
| Validation status (coluna) | campo na feição atualizado pela avaliação de regras | não é coluna: validação é consulta viva de sobreposição (`app/parcelas/validacao.py`), item por par com área de interseção | feito **[diverge — decidido, §7]** |
| Is Seed | domínio PF_YesNo marcando semente (parcela só com linhas de contorno pendentes) | não existe | fora (semeadura por geometria pronta é o import; §8) |
| branch versioning | versionamento de ramo do parcel fabric em feature service | não existe aqui | falta (linha L2-13) |
| ajuste por mínimos quadrados | três classes de Adjustment no esquema | não existe | fora do portão |

## 2. Registro como ato (Records)

No parcel fabric o record é o documento legal (planta, escritura, aprovação) que cria e retira
feições; a documentação diz que o Name do record deve ser único. Aqui `plat.parcela_registro` é o
mesmo ato: `criar_registro` exige `codigo` de texto não vazio e único por inquilino, `tipo` no
vocabulário fechado e `origem` manual/importado/sintetico. O `Recorded Date` é `data_registro`. Os
contadores **Created Parcel Count / Retired Parcel Count** não são gravados: a contagem é consulta
(`ficha` e visões), e contador gravado em banco envelhece mal quando a rodada de import é grande.
O `Record Type` da Esri é um Long com domínio; aqui `tipo` é texto com `CHECK` — ver §8.

## 3. Linhagem nos dois sentidos (lineage)

A página de lineage da Esri desenha as parcelas históricas ACIMA do registro que as retirou e as
parcelas atuais ABAIXO do registro que as criou, e mostra só as parcelas diretamente afetadas pelo
registro escolhido. A `ficha(cur, tenant_id, parcela_id)` devolve o mesmo desenho em duas listas:

- `predecessoras`: parcelas retiradas PELO registro que criou esta (o "para trás");
- `sucessoras`: parcelas criadas PELO registro que retirou esta (o "para frente").

A retirada é a refutação do item e não apaga nada: `retirar_parcela` marca `ativa = false` +
`retirada_por_registro` + `retirada_em`; a parcela sai de `v_parcela_atual` e entra em
`v_parcela_historico` com o registro. Linha que só servia à parcela retirada é retirada junto;
linha PARTILHADA com parcela ativa continua ativa (`parcela_linha_parcela` é n:n — é aqui que a
divisa comum de dois lotes vive uma única vez). Segunda retirada na mesma parcela é recusada
(422). Testes: `test_retirada_sai_do_atual_e_fica_no_historico`,
`test_linha_partilhada_sobrevive_a_retirada_de_um_dos_lados`,
`test_ficha_mostra_linhagem_nos_dois_sentidos`.

## 4. COGO nas linhas

A classe de linha do parcel fabric é "COGO-enabled" com Direction, Distance, Radius, Arc Length,
COGO Type e campos de precisão (Direction Accuracy padrão de 30 segundos, Distance Accuracy padrão
de 0,15 m). Convenções aqui:

- `rumo_graus` é AZIMUTE em graus decimais, 0 = norte (+Y), sentido 0–360. A Esri documenta
  Direction em graus-minutos-segundos com quadrantes **[diverge — decidido: grau decimal de
  máquina, a conversão de planta fica para a camada de entrada]**.
- `raio_m` COM SINAL: positivo curva à direita (horário), negativo à esquerda — o sinal é o que
  distingue a direção da curva sem campo extra de rotação. A restrição do banco é `raio_m <> 0`
  (arco de raio zero não existe; `CHECK (tipo_cogo = 'arco') = (raio IS NOT NULL)`).
- `arco_m` é o comprimento de arco declarado; a GEOMETRIA gravada é a CORDA entre os dois pontos
  **[diverge — decidido: a malha fecha com corda; o arco de verdade é desenho, fase posterior;
  o raio e o comprimento ficam declarados na linha e o ponto de chegada do trajeto COGO é
  calculado analiticamente no centro, não pela corda]**.
- `precisao_rumo_s` (segundos de arco) e `precisao_dist_cm` (centímetros) são os campos de
  accuracy, SEM padrão inventado — quem mediu declara; NULL é ausência declarada.
- `tipo_cogo` fecha o par da Esri COGO Type no vocabulário 'reta'/'arco'.

O trajeto (`app/parcelas/cogo.py`) caminha do ponto inicial por (rumo, distância) ou (rumo, arco,
raio com sinal), cria um ponto por vértice e uma linha por lado, e devolve o erro de fechamento:
`erro_fechamento_m` é a distância do último ponto ao primeiro e `erro_fechamento_razao` é
perímetro ÷ erro (nulo quando fecha exato) — o par Misclose Distance / Misclose Ratio. Teto de
200 segmentos por trajeto (`PARCELA_TRAJETO_MAX`).

## 5. Pontos e connection lines

Ponto é vértice com nome, precisão declarada e sinal de controle: `precisao_xy_m` (XY Accuracy),
`fixo` (Fixed Shape, domínio PF_YesNo lá; boolean aqui), `origem` medida/escaneada/derivada. A
documentação Esri diz que o ponto "torna-se histórico se todas as parcelas adjacentes forem
históricas" — aqui o ponto NÃO é retirado quando a parcela sai **[diverge — decidido: ponto é
acervo cadastral do inquilino, não da parcela; a retirada é da parcela e das linhas exclusivas;
`test_retirada…` confere que os 4 pontos ficam]**.

Connection Lines da Esri são "measurements between points that are not parcel boundaries" com
COGO e registro. `parcela_conexao` cobre o mesmo papel com rumo, distância, descrição e registro
de criação/retirada, sem arco **[diverge — decidido: medida direta entre pontos; arco de conexão
não tem caso de uso na casa hoje]**.

## 6. parcel type

Na Esri, parcel type é um PAR de classes (polígono + linha) criado pela organização por tipo de
parcela (ownership, subdivision, …); o esquema do fabric cresce um par de classes por tipo. Aqui é
uma tabela `parcela` com `tipo` fechado em lote, gleba, quadra, servidao, estrato, e a classe de
linha é única e compartilhada entre tipos (`parcela_linha_parcela`) **[diverge — decidido: RLS e
índices em UMA tabela valem para todo tipo novo sem migração de DDL por inquilino; criar classe
por tipo em banco por inquilino multiplicaria DDL]. O vocabulário é CHECK no banco e tupla em
`app/parcelas/modelo.py` (TIPOS, TIPOS_REGISTRO); fora do vocabulário é 422, nunca silêncio.
A parcela estrato da Esri (strata parcels, ex.: unidades de condomínio) é o tipo `estrato`.

## 7. Validação

A coluna Validation status do fabric é escrita pela avaliação de regras (ferramenta Evaluate
Rules) e as violações viram feições de erro. Aqui não há coluna nem feição de erro: a validação é
consulta viva (`validacao.sobreposicoes`), par de parcelas ATIVAS do MESMO TIPO com interseção
acima da tolerância (1 cm² — lascas de malha flutuante não são sobreposição), ordenada por área,
com total contado e teto de lista (`PARCELA_VALIDACAO_PARES_MAX`) **[diverge — decidido: a sobreposição
é pergunta sobre o dado de agora, não estado gravado que envelhece; o motor de regras de atributo
da rede (item L4-29) já cobre o perfil validação onde ele pertence]**. Parcela histórica nunca
aponta: só o "atual" se valida. Testes: `test_sobreposicao_mesmo_tipo_aponta` (par de lote 200 m²,
par de gleba 400 m², cruzamento lote × gleba NÃO aponta, retirada tira o par) e
`test_sobreposicao_de_tipo_diferente_nao_aponta`.

## 8. Domínios e editor tracking

Os domínios PF_* do fabric (PF_COGOType, PF_YesNo, PF_AreaUnits, PF_COGOAccuracy,
PF_LabelPosition, PF_AdjustmentConstraint) são, aqui, restrições CHECK na coluna e tuplas no
módulo — vocabulário fechado com recusa nomeada, sem tabela de domínio por inquilino. Editor
tracking "habilitado em todas as classes" é `criado_em`/`atualizado_em` em toda tabela.

## 9. Importação de malha pronta (o caminho de entrada da casa)

O portão pede importar os lotes derivados do SIG de teste interno (dado aberto, schema `sigcorp`,
SÓ LEITURA) como parcelas do tipo 'lote'. `app/parcelas/importar.py` + `scripts/importar_lotes_sig.py`:

- um registro SINTÉTICO por empreendimento de origem (tipo 'loteamento', origem 'sintetico',
  código `LS-<empreendimento>` — número, nunca nome), marca em `parcela.atributos`
  (`origem = sig_lote_derivado`, `empreendimento_origem`);
- vértice deduplicado por coordenada (arredondada a 1e-6 m) e linha deduplicada pelo par de
  pontos — é o que faz a divisa comum nascer UMA vez com dois usos;
- `precisao_xy_m` fica NULA de propósito: malha derivada não declara precisão, e inventar número
  é pior que nulo;
- anel com vértice consecutivo repetido é limpo na entrada (malha derivada traz vértice
  duplicado; sem isso o par de/ponto=ponto viola a restrição da linha); buraco e não-polígono são
  recusados (422);
- o import NÃO é idempotente de propósito: rodar duas vezes cria dois registros — segundo
  registro é segundo documento, não a mesma carga. Teto de rodada `PARCELA_IMPORT_LOTES_MAX`.

## 10. Estado

Feito: registro como ato com vocabulário fechado; linhagem nos dois sentidos via `ficha`; retirada
sem apagar (parcela histórica + linha exclusiva sai, partilhada fica); COGO com rumo/distância/
raio com sinal/arco e precisão declarada; fechamento (erro + razão); pontos com precisão e ponto
fixo; conexão; import real medido (`tests/medidas/L4-parcelas-01-modelo-de-parcelas.json`);
RLS por inquilino nas seis tabelas e nas duas visões; tetos em `app/limites.py` documentados.

Falta (com quem está): versionamento de ramo do fabric (branch versioning) — linha L2-13; rota de
API REST para o modelo — itens seguintes da linha; desenho de arco como arco (a corda fecha a
malha) — fase de desenho.

Fora do portão: ajuste por mínimos quadrados (classes de Adjustment); Is Seed; feição de erro
persistente de validação.

## 11. Fachada REST `ParcelFabricServer` (fluxos do item 02)

A fachada da casa é `POST /api/parcelas/fabrica/<operação>` (escopo de token `parcelas:usar`),
mapeada na documentação de desenvolvedores do ParcelFabricServer (feature service, consultada em
08/09/2026). Forma de resposta da doc aceita: `moment`, `exceededTransferLimit`, `success` e
`serviceEdits` (id da camada + `editedFeatures.adds/updates` resumidos em `id`, `codigo`,
`areaCalculadaM2`). Erro é HTTP 4xx do padrão da casa com `erro`/`mensagem` — nunca
`success: false` com 200. O `record` da doc é o registro da casa e é OBRIGATÓRIO em toda
operação que nasce ou mata feição (regra do item 01); onde a doc o faz opcional, a divergência é
declarada. O "apaga" da doc é RETIRADA na casa (`ativa=false` + `retirada_por_registro` +
`retirada_em`): nada é DELETE.

| Operação da doc | Rota da casa | Parâmetros aceitos e mapeados | Divergência declarada |
|---|---|---|---|
| build | `/build` | `record` (obrigatório na casa), `buildExtent` (envelope), `tipo` extra da casa para `parcel type` | `gdbVersion`, `sessionId`, `async`, `f`, `spatialReference` aceitos sem efeito (versão única por inquilino, síncrono, SRID 31982 fixo); `record` opcional na doc, obrigatório na casa |
| divide | `/divide` | `divideParcelGuid`, `divideParcelType`, `record`, `divideOption` (`ProportionalArea` = N partes proporcionais; `EqualArea` = área igual por parte, 0 = N partes iguais; `EqualWidth` = faixas de largura fixa), `divideNumberOfParts`, `dividePartAreaOrWidth`, `divideLineBearing` (azimute 0-360), `divideLeftSide`, `divideDistributeRemainder` | extra da casa: `linha` com 2 pontos corta direto (a doc aceita polilinha; a casa só corte reto). Corte que não cruza: 422 `linha_nao_cruza` (recusa, nunca divisão em silêncio). Sobra vira a ÚLTIMA parte (`divideDistributeRemainder=false` da doc) |
| merge | `/merge` | `parentParcels` [{id, layerId}], `record`, `targetParcelType`, `defaultAreaUnit` (aceito, sem efeito — a casa grava m²) | `mergeInto` é recusado 422: a união sempre cria parcela nova. Linhas externas continuam ativas e passam à unida; a divisa interna é RETIRADA (o "apaga a interna" da doc) |
| clip | `/clip` | `parentParcels`, `record`, `clippingParcels` OU `clippingGeometry` (GeoJSON Polygon), `clipOption` (`PreserveArea`: interseção vira parcela e o pai fica com o resto, sem resto o pai é retirado; `DiscardArea`: o pai fica com o resto e a interseção é descartada; `PreserveBothAreasSplit`: o pai é retirado e nascem interseção e resto), `codigo` extra da casa | a casa aceita 1 `parentParcel` por chamada (a doc aceita array); área sempre m² |
| createSeeds | `/createSeeds` | `record` (obrigatório na casa e na doc), `extent` | a semente da casa vive em `plat.parcela_semente` (tabela própria, mesma semântica Is Seed do item 01), não em linha de classe especial |
| reconstructFromSeeds | `/reconstructFromSeeds` | `extent` (obrigatório na doc e na casa), resposta com `reconstructedParcelCount` | `record` não existe na doc e é obrigatório na casa (a parcela nasce por registro); `targetParcelType` não existe na casa (a semente reconstrói como `lote`) |
| assignToRecord (nome do portão) = **assignFeaturesToRecord** (nome real da doc) | `/assignFeaturesToRecord` | `parcelFeatures` [{id, layerId}], `record`, `writeAttribute` (`CreatedByRecord` reatribui a criação; `RetiredByRecord` RETIRA) | `layerId` da doc vira camada da casa: `parcela`, `linha`, `ponto` ou `conexao` (vocabulário fechado). Retirada pelo MESMO registro que criou: 422 legível (a restrição da tabela proíbe). Ponto não tem retirada por registro (item 01, decisão declarada): `RetiredByRecord` deixa o ponto inativo |

Fluxos de edição da hipótese que a fachada cobre: dividir por área igual/proporção/largura ou
por linha de corte, unir, recortar, construir parcelas a partir de linhas (build), copiar linhas
de CAD (import DXF, §12), duplicar (cópia nova por registro, linhas continuam partilhadas) e
mudar tipo (EDIÇÃO DE ATRIBUTO na casa: a feição continua a mesma, sem nascer nem morrer; na
referência a feição MIGRA de classe de feição — divergência declarada). A varredura do corte por
rumo usa meio-plano com busca binária (área acumulada monótona no deslocamento, raiz única,
64 passos de bisseção — erro de corte muito abaixo do ±0,01 m² do portão).

## 12. Copiar linhas de CAD (DXF)

Escopo do leitor da casa (`app/parcelas/dxf.py`): DXF **ASCII** com entidades `LINE` e
`LWPOLYLINE` (a fechada, flag 70 = 1, é quebrada em segmentos — o modelo da casa só tem linha
reta de dois pontos, paridade §3). DXF **binário** e **DWG** ficam FORA: conversão é fase
externa (o handoff L0-04 mediu que os conversores de linha de comando geram arquivo que nem o
GDAL nem o ezdxf reabrem — a casa não depõe sobre binário que não lê). A camada (código 8) vai
na descrição do registro sintético; `parcela_linha` não tem campo de atributo livre e inventar
coluna por formato é o caminho para tabela de importador. Coordenada: DXF de planta não tem CRS
declarado; o import aceita as coordenadas do arquivo COMO ESTÃO (planta importa em coordenada
local sobre a malha 31982) — quem precisa de georreferência reposiciona com os pontos fixos.
Rumo e distância são CALCULADOS da geometria e a precisão fica NULA (origem `derivada`:
ausência declarada, não inferência). O dado de teste é a planta de teste da casa (corpus aberto
de projeto, fixture `tests/api/parcelas/dados/planta_baixa_A01.dxf`, 557 segmentos, camada LOT
fechando o terreno); nenhuma planta de cliente passa por aqui.

Estado do item 02: fluxos medidos em `tests/medidas/L4-parcelas-02-fluxos-cogo.json` (segmentos
do DXF real, faces que o build fecha, área do lote da camada LOT). Captura de tela dos fluxos
com pré-visualização: SEM CAPTURA — o google-chrome headless desta máquina quebra (dumped core,
defeito de máquina já registrado na casa); a suíte prova os fluxos por API e por banco, e a
interação de arrastar-e-soltar com pré-visualização fica na hipótese do item, para a trilha de
interface (UX).

## 13. Ajuste por mínimos quadrados e qualidade da malha (item 03)

Fontes (consultadas em 09/09/2026):

- Analyze by least squares adjustment (REST, parâmetros e valores de `analysisType`) — `developers.arcgis.com/rest/services-reference/enterprise/analyzebylsa-parcel-fabric-service/`
- Apply least squares adjustment (REST, `movementTolerance`, `updateAttributes`) — `developers.arcgis.com/rest/services-reference/enterprise/applylsa-parcel-fabric-service/`
- Least-squares adjustments and the parcel fabric (Pro) — `pro.arcgis.com/en/pro-app/3.5/help/data/parcel-editing/least-squares-parcel-fabric.htm`
- Run a parcel least-squares adjustment (Pro; o analisar escreve em classes de ajuste e a malha original não muda; sigma perto de 1 é ajuste bem estimado; a priori padrão 30 s / 0,15 m) — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/runleastsquaresadjustment.htm`
- Measurements and accuracy (Pro; Direction/Distance/XY Accuracy como pesos, sem valor = ponto flutuante) — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/aboutmeasurementaccuracy.htm`
- Parcel fabric attribute rules (Pro; AREAS MUST MATCH WITHIN, MISCLOSE RATIO/DISTANCE) — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/parcelfabricattributerules.htm`
- Find gaps and overlaps (Pro, comando Highlight da aba Quality) — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/findgapsoverlaps.htm`
- Parcel fabric data quality layers ("do not alter the original data") — `pro.arcgis.com/en/pro-app/3.4/help/data/parcel-editing/parcelfabricdataqualitylayers.htm`

### 13.1 analyzeByLSA / applyLSA

Rota da casa: `POST /api/parcelas/fabrica/analyzeByLSA` e `POST /api/parcelas/fabrica/applyLSA`
(escopo `parcelas:usar`, registro triplo). Resposta na forma da doc: `moment`, `success`,
`exceededTransferLimit`; o analyze devolve `analysisType`, `resumo` e a lista integral de
`pontos` e `linhas`; o apply devolve `serviceEdits` (camada "Ponto", `updates` com `id`, `x`,
`y`, `deslocamentoM`) e o bloco `ajuste` com a versão gravada. Erro é 4xx do padrão da casa.

| Parâmetro da doc | analyze | apply | Na casa |
|---|---|---|---|
| `parcelFeatures` [{id, layerId}] | sim | — | aceito (o apply da casa re-resolve as parcelas pedidas — divergência abaixo); `layerId` fixo `parcela` |
| `analysisType` (`CONSISTENCY_CHECK` \| `WEIGHTED_LEAST_SQUARES`) | sim | — | aceito; **[diverge — declarado]**: os dois resolvem a MESMA rede ponderada com controles fixos; a rede livre da doc (sem controle) não está implementada e rede sem controle é recusada (`rede_sem_redundancia`) |
| `convergenceTolerance` (padrão 0,05 m) | sim | — | aceito; a casa para quando o MAIOR passo fica abaixo da tolerância (semântica da doc: "maximum coordinate shift expected after iterating"); com a tolerância padrão isso é UM passo e sigma_zero ~1,5 sigma — declarado no teste, que roda também com tolerância fina |
| `movementTolerance` (padrão 0,05 m) | — | sim | aceito; regra da doc aplicada à risca: ponto atualizado só quando o deslocamento é ESTRITAMENTE maior que a tolerância |
| `updateAttributes` | — | sim | aceito; na doc copia XY Uncertainty/error ellipse para os pontos — na casa grava `precisao_xy_m` a posteriori |
| `gdbVersion`, `sessionId`, `async`, `f` | aceitos sem efeito | aceitos sem efeito | versão única por inquilino, síncrono, JSON (mesma posição do §11) |
| `semLinhas` | extra da casa | extra da casa | exclui a medida SÓ da rodada (nunca apaga); volta no relatório como `linhas_excluidas` |

Divergências declaradas do apply: na doc ele aplica resultados ARMAZENADOS (classes AdjustmentPoints
/ AdjustmentLines) e não recebe parcelas; na casa não há classes de ajuste — o apply re-resolve,
escreve e grava a versão numa transação só, e `plat.parcela_ajuste` guarda o relatório integral
(append-only). Na doc o ponto que se move mais que a tolerância "is updated to the location of the
adjustment point"; na casa é a mesma regra, com a geometria de linha recomposta dos dois pontos e a
face da parcela pelo polygonize das linhas dela (anel aberto não tem face e fica declarado em
`sem_face`).

Método da casa: Gauss-Newton ponderado sobre rumos (arcsegundos) e distâncias (metros), pesos por
categoria (`medido` 2 cm/10"; `escritura` 10 cm/60"; `derivado` 50 cm/300"; ponto `controle`
0,005 m / `apoio` 0,05 m), superáveis por coluna explícita de precisão (o par da doc são
Direction/Distance/XY Accuracy, com a priori padrão de 30 s / 0,15 m — a casa usa tetos mais
rígidos por categoria, declarados, não os padrões da doc). Leitura do `sigma_zero` como na doc:
perto de 1 é ajuste bem estimado (os a priori retratam o erro real); na malha de teste as medidas
são EXATAS, então o sigma zero desce a ~0 com tolerância fina — e é isso que o teste prova. O
portão é a solução analítica: malha 4x5 (98 observações, 54 incógnitas, 44 redundâncias) cujas
coordenadas verdadeiras o ajuste tem de reproduzir a 1 mm — e a refutação (1 m em 100) tem de
virar a SUSPEITA nº 1 e, excluída, reconvergir limpa. ADR
`docs/adr/20260909T0142-ajuste-lsa-parcelas.md` registra os três bugs que essa prova pegou antes
de passar.

### 13.2 Qualidade — lacunas, sobreposições e regras de atributo

Rota da casa: `POST /api/parcelas/qualidade` (mesmo escopo; `tipo` opcional no vocabulário fechado,
`toleranciaM2` > 0). É o par do Find Gaps and Overlaps (o Highlight da aba Quality e a ferramenta
da Parcel toolbox, que guarda lacuna/sobreposição como polígono): a casa devolve RELATÓRIO VIVO —
sobreposições por par do MESMO tipo com área de interseção, lacunas por face do polygonize que
nenhuma parcela DO MESMO REGISTRO cobre, e as regras de atributo (área calculada x declarada fora
da tolerância; fechamento acima de 0,10 m). **[diverge — decidido]**: a LACUNA é calculada DENTRO
de cada registro — polygonize E cobertura — (cada registro é um levantamento; espaço entre dois
registros não é lacuna de malha nenhuma, e a lacuna de um não desaparece porque a malha de outro
cobre a área por cima: esse transpasse entre malhas é o que a seção de sobreposições aponta —
medido no corpus: cobertura global dizia 234 lacunas, por registro 250, 16 faces cobertas por
importações duplicadas; e o `ST_Polygonize` com geometria solta resolve para a forma AGREGADA,
que misturava as bordas dos registros numa polygonize só — a forma por linha é
`ST_Polygonize(ARRAY[g])`) — a ferramenta da doc opera sobre a seleção do usuário, a casa sobre a
malha do registro, e o polygonize do corpus inteiro de uma vez é inviável (medido: 20 min de GEOS
e estouro de memória; por registro a maior malha do corpus é de 968 lotes e o mesmo cálculo é
trivial). As camadas de qualidade do Pro "do not alter the original data" — a casa idem: a regra
aponta, não altera dado. Conferência independente no teste com predicados DIFERENTES dos da
implementação (ST_Overlaps no par; ST_Difference contra a união do registro na face), sobre a
malha determinística E sobre o corpo real de lotes de exemplo.
