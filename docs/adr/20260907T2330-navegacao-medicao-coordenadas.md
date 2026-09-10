# ADR 20260907T2330 — navegação, medição geodésica e coordenadas do visualizador

Item L2-01-f-navegacao-medicao-coordenadas. Segue C11 do L2_CONCEITO (geodésico sempre, exibição em 3857,
entrega em qualquer EPSG, CRS brasileiros em destaque) e reusa os controles nativos do MapLibre em vez de
reescrever o que ele já faz certo.

## Decisões

1. **Medição no elipsoide, não na esfera.** O portão exige erro ≤ 0,1 % contra `ST_Length/ST_Area(geography)`
   do PostGIS, que calcula no esferoide; a esfera do L2-01 errava 0,3 a 0,5 % (medido no teste: `areaEsferica`
   fica ao lado como reserva). Distância = inversa de Vincenty (GRS80, converge em mm); área = arestas
   densificadas ao longo da GEODÉSICA (direta de Vincenty, passos ≤ 1 km) projetadas numa azimutal equivalente
   local do proj4 e somadas pela fórmula do laço. A densificação por reta em lon/lat foi tentada e reprovada
   pelo teste (3 % num polígono de 300 mil km²): o PostGIS mede a geodésica, não a reta geográfica.
2. **proj4js 2.22.0 vendorizado (MIT)**, mesma cópia no navegador e no node dos testes; as definições PROJ da
   lista curada (`web/js/mapa/crs.js`) são as de `spatial_ref_sys` desta instalação, conferidas texto a texto.
   Coordenada em UTM 22S confere com `ST_Transform` em ≤ 1 cm. Nenhuma rota nova: o registro de CRS como serviço
   é o L2-17 (na fila); quando entrar, `crs.js` pode passar a ler dele sem mudar quem o chama.
3. **Barra de escala e zoom/rotação/norte são os controles do MapLibre.** A barra mede a distância geodésica na
   latitude do centro da tela (o teste compara o rótulo com `ST_Length` da mesma largura: erro < 1 %).
4. **"Ir para" sem adivinhação:** decimal (vírgula, sinal tipográfico), GMS (′ ″ ou ' "), e projetado só com
   EPSG explícito da lista curada (`333.000 7.394.000 EPSG:31983`); zona UTM nunca é inferida. Texto com cara de
   coordenada mas malformado recebe a mensagem de formato e não vai ao geocodificador.
5. **Favoritos em localStorage por mapa** (mesma decisão da ordem das camadas em `camadas.js`). Gravar no
   documento do item de mapa (L2-01-a) espera o esquema mapa-v1 ganhar o campo `favoritos` — o ramo daquele item
   está na fila; declarado como parcial em PARIDADE.md.
6. **Histórico de extensão** por pilha de estados (centro, zoom, rotação, inclinação) em `moveend`, com guarda
   para o próprio `jumpTo` não registrar; **minha localização** e **tela cheia** são os controles nativos
   (GeolocateControl com círculo de precisão; FullscreenControl). Atalhos de teclado documentados na própria
   tela (`?` abre a lista) e ignorados dentro de campos de texto.

## Fora deste item
Registro de CRS como serviço e grades de transformação (L2-17); favoritos no documento do mapa (L2-01-a);
medição com unidades não métricas.
