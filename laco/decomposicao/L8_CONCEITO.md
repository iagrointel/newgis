# L8 rodovias — decisões de conceito (esboço para decisão do dono)

Data: 06/09/2026. Pesquisa rápida (pedido: decidir hoje se a linha abre), sem código. Lido antes: `L4_CONCEITO.md`
(addendum 06/09, decisão D38 — rodovia NÃO é rede de utilidade no sentido do L4: não tem traçado/isolamento/subrede,
é routing + condição de pavimento + tráfego, tema INSPIRE separado — "Transport Networks", não "Utility and
Governmental Services"); `rs-coop/tracado-lt/METODOLOGIA.md` (regras de corredor/routing e portões que a casa já
opera); `CLAUDE.md` seção parceiro geo/mineração (buffers de UC/TI/quilombo, "ausência de dado nunca vira medição",
"co-locação não é fraude"). Nada abaixo é dado ingerido nesta máquina — é o que foi lido e testado por HTTP em
06/09/2026, com URL. Onde a pesquisa não deu resposta segura, o item diz isso, em vez de inventar.

## 0. O que foi pesquisado e testado por HTTP em 06/09/2026 (nenhum dado ainda ingerido)

- INSPIRE tema "Transport Networks" cobre quatro sub-temas — Road, Rail, Water e Air — com estrutura de
  nó/aresta ("link and node structure") comum a todos e referências cruzadas entre eles para permitir roteamento e
  navegação integrados — [INSPIRE, Utility and Governmental Services](https://knowledge-base.inspire.ec.europa.eu/utility-and-governmental-services_en)
  (a própria base de conhecimento separa "Transport Networks" de "Utility and Governmental Services" — dois temas,
  não um) e [INSPIRE Technical Guidelines — Transport Networks](https://inspire-mif.github.io/technical-guidelines/data/tn/)
  (HTTP 200; não foi lido o PDF de ~200 pp da especificação completa nesta rodada — só a página de entrada e o
  resumo por sub-tema; qualquer classe específica citada abaixo do padrão INSPIRE precisa de leitura do PDF antes
  de virar portão de item).
- DNIT publica o cadastro de jurisdição de vias do SNV (Lei 12.379/2011) em `servicos.dnit.gov.br/dadosabertos`,
  dataset "Jurisdição de Vias": XLS/XLSX mensal (mais recente 07/2024 no momento da consulta) + histórico CSV
  2020-2022 + dicionário de dados em PDF, licença aberta — [DNIT, Jurisdição de Vias](https://servicos.dnit.gov.br/dadosabertos/dataset/jurisdicao-de-vias).
  A malha geoespacial (SHP/GeoJSON/KML) sai pelo VGeo (visualizador) e pelo mesmo portal de dados abertos —
  [DNIT, Sistema Nacional de Viação](https://www.gov.br/dnit/pt-br/assuntos/atlas-e-mapas/pnv-e-snv). API REST
  própria está anunciada (Portaria 595/2024) com disponibilização progressiva a partir de 2026 — ainda não testada.
  ⛔ Nesta pesquisa **não se achou dataset federal aberto de obras de arte especiais (pontes/viadutos/túneis) nem
  de condição de pavimento (IRI/PCI) do DNIT** — o gerenciamento existe (sistema SGO, interno, desde 1993;
  [DNIT, revista técnica sobre avaliação patrimonial de OAE](https://revistaeninfra.dnit.gov.br/index.php/inicio/article/view/146/89)),
  mas não apareceu como conjunto de dados abertos nesta varredura. Estados publicam OAE separadamente (ex. São
  Paulo/DER-SP — [Dados Abertos SP, Obras de Arte Especiais](https://dadosabertos.sp.gov.br/dataset/obras-de-arte-especiais-oae)) — sem padrão nacional único.
- IBGE mantém a malha rodoviária como parte da Base Cartográfica Contínua (BC250, escala 1:250.000), compilando
  DNIT + DERs estaduais + bases estaduais em metadado único, padrão ISO 19115/Perfil MGB, distribuído por FTP —
  [IBGE, Infraestrutura de Transporte](https://www.ibge.gov.br/geociencias/cartas-e-mapas/redes-geograficas/15968-infra-estrutura-de-transporte.html).
  É mosaico de fontes de qualidade heterogênea, não um cadastro único — útil como malha de referência nacional,
  não como fonte de atributo de gestão de ativo.
- OSM tag `highway=*` já cobre a hierarquia funcional (motorway…track) e tem tags específicas de condição —
  `surface=*` (tipo de revestimento), `smoothness=*` (usabilidade física declarada), `tracktype=*` (grade1-grade5
  para não pavimentada), `lanes=*`, `maxspeed=*` — [OSM Wiki, Key:surface](https://wiki.openstreetmap.org/wiki/Key:surface),
  [OSM Wiki, Key:tracktype](https://wiki.openstreetmap.org/wiki/Key:tracktype), [OSM Wiki, Highways](https://wiki.openstreetmap.org/wiki/Highways).
  É tag declarada por mapeador voluntário, cobertura desigual (BR-230/BR-319 citadas como trechos historicamente
  mal mapeados) — nunca fonte de condição oficial, só proxy aberto e contínuo.
- Esri está fundindo "ArcGIS Roads and Highways" e "ArcGIS Pipeline Referencing" num produto único, "ArcGIS Linear
  Referencing", previsto para novembro de 2026 (ArcGIS Online, Pro 3.8, Enterprise 12.2) —
  [Esri, Introducing ArcGIS Linear Referencing](https://www.esri.com/arcgis-blog/products/arcgis-enterprise/announcements/introducing-arcgis-linear-referencing).
  O modelo é rota + evento por medida (dynamic segmentation), não traçado/isolamento de rede — o produto **não
  tem** utility network por baixo; serve a HPMS (Highway Performance Monitoring System, relatório federal dos
  EUA) — [Esri, ArcGIS Roads and Highways overview](https://www.esri.com/en-us/arcgis/products/arcgis-roads-highways/overview).
- Bentley tem produto equivalente, AssetWise Linear Network Management ("linear referencing services" +
  "decision support" sobre rede de transporte) e usa dado de realidade (nuvem de pontos/imagem) para detectar e
  catalogar automaticamente placa, guarda-corpo e marcação de pavimento —
  [Bentley, AssetWise Linear Network Management](https://www.bentley.com/software/assetwise-linear-network-management/).
  Confirma que "extrair ativo de imagem/nuvem de pontos" já é prática de mercado, não invenção da casa.
- Sensoriamento de condição de pavimento por imagem tem duas frentes na literatura: (1) óptico + aprendizado
  profundo contra o banco de dados de gestão de pavimento do Texas (TxDOT PMIS): >3.000 imagens de satélite
  casadas com nota oficial, acurácia acima de 90% relatada — [MDPI/arXiv, Deep Learning for Pavement Condition
  Evaluation Using Satellite Imagery](https://arxiv.org/abs/2508.01206) (resumo lido; método e arquitetura exata
  não estavam no resumo, exigem o PDF completo antes de virar portão); (2) radar de abertura sintética (SAR,
  Sentinel-1, C-band, gratuito, funciona com nuvem e à noite) estimando rugosidade —
  [ScienceDirect, Deep Learning for Estimating Pavement Roughness using SAR Data](https://www.sciencedirect.com/science/article/abs/pii/S0926580522003776);
  e um terceiro resultado, mais fraco, com imagem multiespectral + XGBoost contra IRI em 3 classes (bom/regular/
  ruim), acurácia 69% (fonte: resumo de busca, ASCE *Journal of Performance of Constructed Facilities*, não lido
  em texto completo — citar com essa reserva). Nenhum desses conjuntos é brasileiro; nenhum foi replicado nesta
  máquina.

## C1. Modelo de dado primário: referenciamento linear (rota + medida = evento), não nó/aresta como fonte

- Opções: (a) o cadastro de ativo/atributo/condição vive como EVENTO sobre uma ROTA com MEDIDA (km), no padrão
  "linear referencing" (DNIT já nomeia assim: "BR-101/SP km 234"); um grafo roteável (nó/aresta) é uma PROJEÇÃO
  derivada da mesma geometria, não a fonte; (b) copiar o modelo de rede do L4 (topologia nó/aresta com terminal,
  subrede, traçado) para rodovia; (c) só grafo roteável (OSRM), sem camada de evento.
- Custo de mudar: (b)→(a) é trocar o motor inteiro depois de construído (a rodovia não tem terminal, dispositivo
  nem subrede — forçar essa semântica é o mesmo erro que o addendum do L4 já registrou); (c)→(a) perde toda a
  gestão de ativo por km, que é o motivo de existir a linha.
- Recomendação: **(a)**, o mesmo modelo do produto de mercado (Esri funde Roads and Highways nisso; Bentley tem
  produto próprio equivalente — fontes na seção 0) e o mesmo vocabulário do dono (SNV/DNIT referenciam por
  rodovia+UF+km, não por nó de rede). O grafo roteável (para OSRM) continua existindo, mas como saída de um
  conversor, igual ao pacote C12 do L4 faz para OpenDSS — nunca como fonte de evento.
- Obriga: L8-01 (pacote rodoviário) nasce com tabela de rota+medida antes de qualquer tabela de nó/aresta.

## C2. Conector DNIT SNV: fonte de rota oficial federal; condição de pavimento e OAE ficam FORA dele (não existem abertos)

- Opções: (a) importar "Jurisdição de Vias" (XLS mensal) como referência de rota federal (BR-xxx, km inicial/
  final, UF) e tratar API REST da Portaria 595/2024 como conector futuro a testar quando publicada; (b) esperar a
  API REST antes de abrir a linha; (c) assumir que o DNIT também publica OAE/condição em algum lugar não achado
  e prometer isso ao dono.
- Custo de mudar: (b) trava a linha por tempo indefinido (a API não tem data confirmada); (c) é prometer dado que
  esta pesquisa não achou — risco de "ausência de dado virar medição" (regra 1 do motor de LT).
- Recomendação: **(a)**. Importar o XLS mensal como está, guardando a data do arquivo (frescor); registrar OAE e
  condição de pavimento como LACUNA CONHECIDA, não como pendência de engenharia — a pesquisa não achou fonte
  federal aberta para nenhum dos dois (seção 0). Se o dono quiser insistir, o próximo passo é achar o dado
  estadual (ex. DER-SP já publica OAE) trecho a trecho, nunca prometer cobertura nacional sem medir.
- Obriga: L8-02 (conector SNV) grava `frescor` e `cobertura_km` por UF; L8-10 (OAE) nasce como item de PESQUISA de
  fonte, não de ingestão.

## C3. Conector IBGE BC250: malha nacional de referência multiescala, nunca fonte de atributo de gestão

- Opções: (a) usar a BC250 (DNIT+DER+bases estaduais, ISO 19115) como malha de PREENCHIMENTO onde o SNV não cobre
  (rodovia estadual/municipal) e como conferência de completude; (b) ignorar o IBGE e usar só SNV+OSM.
- Custo de mudar: (b) perde a única fonte com metadado formal e proveniência declarada por trecho, e produz buraco
  de cobertura em rodovia não federal sem aviso.
- Recomendação: **(a)**, mesma disciplina do L4 (nunca uma fonte só). Camada de referência, licença e frescor
  registrados no acervo (L6), nunca misturada linha a linha com o SNV sem marcar a origem.
- Obriga: L8-03 grava `fonte` por trecho (SNV | BC250 | OSM) na mesma tabela.

## C4. Conector OSM `highway=*`: cobertura contínua e tags de condição como PROXY aberto, nunca "condição oficial"

- Opções: (a) importar `highway`, `surface`, `smoothness`, `tracktype`, `lanes`, `maxspeed`, `ref` como camada
  contínua nacional, rotulada desde a entrada como proxy declarado por voluntário; (b) tratar tag OSM como
  equivalente a levantamento de campo.
- Custo de mudar: (b) é o erro que a casa já bateu em vegetação (regra 53 da METODOLOGIA: "camada é PROXY quando
  mede grandeza diferente da norma") — corrigir depois de publicado é reescrever o discurso do produto.
- Recomendação: **(a)**. `surface`/`smoothness`/`tracktype` substituem a régua de condição só onde não há nada
  melhor, e sempre com a tag de "declarado, não medido" ao lado do valor — mesma arquitetura da inspeção orbital
  de vegetação do L4 (C15 do L4_CONCEITO, reaproveitada em C9 abaixo).
- Obriga: L8-04 grava `origem_tag = osm_voluntario` distinto de `origem_tag = sensoriamento` e de `origem_tag =
  levantamento_oficial` na mesma coluna de proveniência.

## C5. Grafo roteável é saída derivada (reaproveitar o padrão OSRM já usado noutra linha), não construção nova

- Opções: (a) gerar o grafo roteável a partir da mesma geometria de rota+medida, pelo mesmo padrão de conversor já
  operado pela casa (OSRM sobre extração OSM, usado em routing de corredor e em análise logística); (b) escrever
  um motor de roteamento novo.
- Custo de mudar: (b) é reconstruir o que já funciona; nenhuma vantagem identificada nesta pesquisa.
- Recomendação: **(a)**. O item de rota/matriz/isócrona da plataforma (`L2-11-c-rota-matriz-isocrona`) já é o
  contrato certo; L8 só acrescenta o passo "grafo nasce de rota+medida", nunca o contrário.
- Obriga: dependência declarada de `L2-11-c-rota-matriz-isocrona`.

## C6. Referenciamento de evento casa com a nomenclatura nacional (rodovia+UF+km), com conversor coordenada↔medida

- Opções: (a) todo evento (obra de arte, sinalização, trecho de condição, ponto de contagem de tráfego) é gravado
  como (rota, km_inicial, km_final|km_pontual) e um serviço converte medida↔coordenada e coordenada↔medida (com
  tolerância declarada, igual à regra C10 do L4 para coincidência geométrica); (b) evento gravado só como ponto/
  linha solta, sem referência de rota.
- Custo de mudar: (b) perde a comparabilidade com qualquer citação de campo (ninguém em rodovia cita coordenada,
  cita "km 234") e obriga a reprocessar tudo quando a geometria da rota for atualizada.
- Recomendação: **(a)**, é o núcleo de qualquer sistema de LRS rodoviário (Esri e Bentley fazem isso — seção 0).
- Obriga: L8-06 nasce antes de qualquer camada de evento (OAE, condição, tráfego).

## C7. Condição de pavimento por sensoriamento: camada derivada com data, sensor, régua e ressalva — nunca substitui levantamento oficial

- Opções: (a) camada `rodovia_condicao_sensoriamento` com sensor, data da cena, classe/índice, nº de cenas,
  cobertura de nuvem e a ressalva "proxy, não substitui IRI/PCI medido em campo" impressa; calibrada contra
  levantamento oficial ONDE existir (D — ver C8); (b) publicar "condição" sem dizer que veio de imagem.
- Custo de mudar: (b) é o erro já cometido e corrigido em ferrugem e vegetação (nunca dizer "detectado" sem
  controle negativo) — corrigir depois de vendido é o cenário mais caro já registrado na casa.
- Recomendação: **(a)**, arquitetura idêntica à C15 do L4 (inspeção orbital de vegetação): resultado por trecho,
  nunca por atributo do cadastro; "localiza candidato", nunca "mede IRI".
- Obriga: L8-08 só entra em produção com L8-09 (calibração) rodada, mesmo que a métrica de calibração seja fraca.

## C8. Calibração do sensor exige levantamento oficial de referência — hoje NENHUM foi identificado no Brasil nesta pesquisa

- Opções: (a) buscar ativamente um trecho brasileiro com IRI/PCI oficial publicado (DER estadual, concessionária
  de pedágio sob regulação, ANTT) para servir de controle, antes de calibrar qualquer classificador; (b) calibrar
  contra a literatura estrangeira (TxDOT) e aplicar direto no Brasil; (c) publicar sem calibração, rotulado "não
  calibrado".
- Custo de mudar: (b) transporta uma régua estrangeira sem prova de que se aplica a rodovia/pavimento/clima
  brasileiro — mesmo erro que a régua da distribuidora não se transportar entre redes, já registrado noutra
  frente da casa; (c) é aceitável como primeiro passo, nunca como entrega final.
- Recomendação: **(a) como meta, (c) como estado inicial declarado**. Sem controle nacional, a camada nasce
  marcada "não calibrada" e primeiro serve de FILTRO DE FILA (achar candidato a inspecionar), não de laudo —
  mesma disciplina que o CHM aplicou à vegetação (reduz fila, não substitui campo).
- Obriga: L8-09 registra explicitamente a ausência de controle nacional como item de pesquisa contínua, não como
  bloqueio de todo o resto da linha.

## C9. Reaproveitar o motor de custo/veto por camada do corredor de LT para estudo de corredor rodoviário

- Opções: (a) o item de corredor de custo mínimo já existente na plataforma (`L3-10-corredor-custo-minimo`) e o
  item de restrições/veto (`L3-04-restricoes`) recebem um pacote de camadas rodoviário (faixa de domínio, área
  urbana, UC, TI, cavidade, travessia de água) e passam a servir também estudo de duplicação/contorno viário,
  sem duplicar motor; (b) escrever um motor de corredor específico para rodovia.
- Custo de mudar: (b) é recriar 07/08/2026 em diante (o motor de LT já tem os 8 portões congelados e a lição de
  "rota de veto é A rota, custo é preferência" — replicar isso do zero é jogar fora meses de correção de erro).
- Recomendação: **(a)**. O motor não muda; muda o pacote de camadas e os limiares (C10 abaixo).
- Obriga: dependência declarada de `L3-10-corredor-custo-minimo` e `L3-04-restricoes`.

## C10. Buffers regulatórios de UC/TI/quilombo para rodovia: NÃO CONFIRMADOS nesta pesquisa — gate obrigatório antes de citar número

- Opções: (a) registrar que a Lei 15.190/2025 tem buckets de distância diferentes por tipologia de empreendimento
  (LT/linear: 5 km bioma Amazônia / 3 km demais, já usado no motor de LT; mineração/pontual: 8 km Amazônia / 5 km
  demais, já usado na linha de mineração) e que **esta pesquisa não determinou em qual bucket a rodovia cai** no
  Anexo da lei — exige leitura jurídica antes de qualquer número entrar em portão; (b) assumir por analogia que
  rodovia usa o bucket "linear" (mesmo de LT) sem checar; (c) não tratar buffer nenhum até a leitura acontecer.
- Custo de mudar: (b) é exatamente o erro já cometido e corrigido na linha de mineração (a casa mediu 8/5 km
  errado antes de achar o texto certo do Anexo) — repetir sem checar é reincidência conhecida; (c) atrasa a
  linha inteira por um item que é só leitura de texto.
- Recomendação: **(a) registrado como decisão aberta, (c) até a leitura acontecer** — nenhum buffer de rodovia
  entra em portão de item sem a citação do Anexo, mesma régua da mineração e da LT.
- Obriga: L8-12 nasce como item de LEITURA JURÍDICA, não de código; nenhum outro item de L8 cita km de buffer
  antes dele fechar.

## C11. Reaproveitar o motor de favorabilidade (AMC) para priorização de trecho/corredor, pesos sempre do usuário

- Opções: (a) o motor de favorabilidade 0-100 com pesos escolhidos pelo usuário (já operando como motor logístico
  noutra linha, mesmo núcleo do item `L3-01` da plataforma) recebe fatores rodoviários (condição declarada,
  proximidade de polo gerador de tráfego, sinuosidade, travessia, sobreposição ambiental) como mais um conjunto de
  fatores/critérios; (b) escrever um segundo motor de favorabilidade específico de rodovia.
- Custo de mudar: (b) duplica o que o item `L3-01-j-equivalencia-motor-logistico` já existe para provar (o motor é
  único, o pacote de fatores muda).
- Recomendação: **(a)**. Linguagem igual à das outras linhas: fator, critério, favorabilidade, peso escolhido pelo
  usuário — nunca peso medido.
- Obriga: dependência declarada de `L3-01-j-equivalencia-motor-logistico`.

## C12. Paridade declarada: contrato próprio primeiro, fachada Esri "ArcGIS Linear Referencing" depois — nunca prometer traçado/tracing em rodovia

- Opções: (a) documentar a paridade contra o modelo rota+evento (dynamic segmentation) do produto fundido da Esri
  (previsto para Q4 2026 — seção 0), sem fachada de tracing porque o produto de mercado também não tem (ele não
  monta em cima de utility network); (b) prometer para rodovia as mesmas operações de traçado/isolamento do L4.
- Custo de mudar: (b) é prometer uma capacidade que nem o produto de mercado equivalente tem — descobrir depois
  de vender é o mesmo erro que o UN do Pro exigindo geodatabase corporativa (C17 do L4).
- Recomendação: **(a)**. `docs/PARIDADE.md` ganha seção rodovia com "traçado de rede = FORA, não é o modelo do
  domínio" escrito explicitamente.
- Obriga: L8-14 registra a paridade e a ausência deliberada de tracing.

## C13. Linha própria (L8), não módulo do L4 — reaproveitando L0/L2/L3/L6, com schema de dado próprio

- Opções: (a) L8 nasce como linha de produto separada (schema `plat.rodovia_*` próprio, pacote de ativos
  "rodovia-BR" próprio) que reaproveita a fundação (L0: ingestão/jobs/acervo), a plataforma (L2: mapa, estilo,
  FeatureServer, geoprocessamento, rota/matriz/isócrona) e o motor (L3: corredor de custo mínimo, restrições,
  favorabilidade) — mesma relação que o motor logístico já tem com o motor de LT (mesmo motor, critério
  diferente, sessão diferente); (b) item novo dentro do L4 (rejeitado pelo addendum de 06/09 do próprio
  L4_CONCEITO: rodovia não tem traçado/isolamento/subrede — forçar o modelo teria custo alto de reverter);
  (c) produto totalmente isolado, sem reaproveitar nada da plataforma.
- Custo de mudar: (b) já foi descartado com motivo escrito (D38); (c) reconstrói ingestão, mapa e motor do zero
  por um domínio que não precisa de nada novo em nenhum dos três.
- Recomendação: **(a)**. Rodovia é tema INSPIRE separado de utilidade (Transport Networks ≠ Utility and
  Governmental Services, seção 0) e o próprio mercado trata como produto (ou extensão) separado do utility
  network (Esri: Roads and Highways nunca foi parte do Utility Network; Bentley: AssetWise Linear Network
  Management é produto à parte do gêmeo digital de rede). Reaproveitar plataforma comum é o que já funciona na
  relação motor de LT × motor logístico.
- Obriga: registrar `L8 rodovias` como linha no `estado.json` (mesmo padrão de L3L6, L4, L5, L7); nenhuma
  dependência interna do L4 além das compartilhadas (L0/L2/L3/L6).

## O que fica FORA desta rodada (declarado)

- Tráfego em tempo real, pedágio e pesagem — nenhuma fonte nacional aberta e contínua identificada nesta pesquisa
  rápida; não vira item de construção, só nota de pesquisa futura.
- Sinalização vertical detalhada (placas individuais) — sem fonte estruturada encontrada; Bentley/Esri fazem isso
  via captura de realidade paga, fora do escopo desta rodada.
- Qualquer número de buffer de UC/TI/quilombo para rodovia antes da leitura jurídica do Anexo da Lei 15.190/2025
  (C10) — sem exceção.
- Qualquer promessa de "condição de pavimento medida" por sensoriamento sem a ressalva "proxy, não substitui
  levantamento oficial" ao lado (C7/C8).
- OAE (pontes/viadutos/túneis) como camada de gestão — permanece item de PESQUISA de fonte, não de ingestão,
  até achar publicação federal aberta ou decidir consolidar por estado.

## Resumo da recomendação ao dono

Abrir **L8 rodovias como linha própria**, reaproveitando fundação/plataforma/motor já existentes (não código
novo de baixo nível): modelo de dado é referenciamento linear (rota+km), não nó/aresta; conectores DNIT SNV + IBGE
BC250 + OSM cobrem geometria e classificação funcional, mas NENHUM cobre condição de pavimento ou obras de arte
com abertura nacional — aí entra sensoriamento como proxy de fila, nunca como laudo, e sem controle brasileiro de
calibração ainda identificado; o motor de corredor/veto e o motor de favorabilidade da casa se reaproveitam quase
sem mudança, só trocando o pacote de camadas; e o único bloqueio de verdade antes de prometer buffer regulatório é
uma leitura jurídica de meia página que ainda não foi feita.
