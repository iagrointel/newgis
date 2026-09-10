# ADR — motor multicritério e rotas de rede no visualizador (UX-08)

Data: setembro de 2026. Estado: aceito. Trilha de interface.

## Contexto
O item UX-08 pede as telas da rede de utilidades (importar BDGD/EPANET, topologia, traçado montante/jusante) e do
motor multicritério, integradas ao visualizador. No tronco de hoje só existe metade disso: o motor de grades
aninhadas (L3-19, `/api/multiescala`, 13 rotas sem tela — UX-21) e as três rotas de rede viária sobre OSRM
(`/api/rota`, `/api/isocrona`, `/api/matriz`, sem tela — UX-19). O traçado de rede de utilidades não tem uma rota
sequer no tronco: vive em sete ramos L4 da fila de junção, cada um com 13 a 22 mil linhas de backend e migrações.

## Decisão
1. **Escopo declarado, não escopo escondido.** Este item entrega o que o tronco sustenta — painéis "Motor" e
   "Rotas" no chrome único do mapa — e registra no handoff, com os nomes dos ramos, que o traçado de rede de
   utilidades fica para quando a fila os juntar. Juntar sete ramos de backend na trilha de interface seria refazer
   o trabalho da fila com risco de conflito entre eles.
2. **Motor como painel do mapa, não tela à parte.** A área de estudo nasce da VISTA ATUAL (o retângulo visível
   vira o polígono do conjunto); os fatores carregam a escala nativa DECLARADA e recebem PESO por controle
   deslizante (o painel repete `AVISO_PESOS`: pesos escolhidos pelo usuário, não medidos); macro e micro são as
   duas chamadas que a API já tinha; o relatório por fator que o servidor devolve vira texto — e quando
   `escala_grosseira` é verdadeiro o painel explica que a nota da célula vem do bloco da fonte, não de dado próprio.
3. **Uma rota de leitura nova, por lacuna real**: `GET /api/multiescala/execucoes/{id}/celulas` devolve as células
   com nota/cobertura/aprovada como FeatureCollection (teto `ESCALA_CELULAS_GEOJSON_MAX`, com `total` e
   `truncado` declarados). Sem ela o resultado do motor não chega ao mapa; nenhuma outra rota foi criada. O
   conjunto passa a devolver `area` (GeoJSON) para o painel desenhar o polígono.
4. **Rotas com dois caminhos de entrada, sempre**: marcar no mapa (captura do próximo clique) ou digitar
   "longitude, latitude". Resultado no mapa (linha, polígono, marcadores) e no painel (distância, duração,
   instruções, tabela da matriz), com a proveniência que a API devolve. Erros nomeados: `isocrona_vazia`,
   `matriz_grande_demais`, serviço fora do ar.
5. **Cores lidas dos tokens** (`getComputedStyle(...).getPropertyValue('--acento')`): o MapLibre não lê CSS, e um
   literal solto no JS seria a única cor da tela fora do sistema de design.
6. Atalhos `r` (Rotas) e `o` (Motor) seguem a convenção do chrome (UX-04); os painéis entram em `PAINEIS` e no
   diálogo de atalhos sem CSS próprio além do que a gaveta já dá.

## Consequências
- A refutação literal do item ("traçado sem controlador mostra aviso") não é verificável no tronco; o e2e prova a
  análoga possível: rodar sem área ou sem fator, e calcular rota sem pontos, mostram o motivo no painel.
- O e2e do Motor reproduz a geometria do teste de API do L3-19 (1,9 km × 1,9 km em -46,60/-23,50) para que as
  contagens (4 células macro, 32 micro) sejam determinísticas.
- A isócrona depende do OSRM do recorte de Guarulhos (`PLAT_OSRM_URL`, :5010): fora dele o painel mostra o erro
  nomeado, o que também está provado por interceptação.

## Alternativas recusadas
- Tela `/motor` separada com mapa próprio: duplicaria o visualizador; o item pede o mesmo chrome.
- Desenhar a área de estudo com o painel Desenho: o fluxo mínimo (vista atual → área) cobre o caso comum e não
  cria dependência entre painéis; desenhar um polígono qualquer é evolução natural quando a paleta de desenho
  expuser o polígono ativo.
