# ADR 0017 — Extratores de fator bruto: raster (estatística zonal) e vetor

Data: 07/09/2026. Item L3-01-c-extracao-fator, decisão de conceito A4/A9 (`laco/decomposicao/L3L6_CONCEITO.md`).
Depende de L3-01-b-unidades (`parcial`, aguardando merge combinado com a outra sessão) e do módulo `app/amc/crs.py`
(A7: CRS de trabalho UTM SIRGAS 2000 da zona do centróide). Este item entrega SÓ a extração — a transformação em
favorabilidade é L3-01-d, a combinação é L3-01-e.

## Contexto

O motor logístico (`cbre/pipeline/85_fatores.sql`) já prova que extração cara/materializada + combinação barata/
interativa funciona (decisão A2). Faltava, em Python puro e sem depender do banco para o cálculo em si, a função que
lê um raster ou uma camada vetorial e devolve o valor bruto por unidade, com o peso de área na borda que separa o
motor certo do aproximado (regra do portão do item).

## Decisão

**1. Dois módulos, sem estado, sem I/O de banco: `app/amc/zonal.py` (raster) e `app/amc/vetorial.py` (vetor).**
Recebem a lista de unidades já em GeoJSON 4326 e devolvem `{unidade_id: {"valor": float|None, "cobertura": float,
"avisos": [...]}}`. Quem chama (o job de extração, fora do escopo deste item) resolve onde a camada e as unidades
vêm de — arquivo, `/vsicurl`, ou consulta ao banco.

**2. Peso de área na borda, nunca centróide.** `zonal.pesos()` rasteriza a unidade duas vezes menos do que a
primeira versão: uma só chamada a `rasterio.features.rasterize` com dois valores de burn (1 = célula tocada,
2 = célula tocada pela BORDA da unidade) — a borda está sempre contida no conjunto de tocadas, então o valor 2
identifica sem ambiguidade as células que precisam da fração exata por interseção shapely. Célula interior = peso
1,0; célula de borda = `área(interseção) / área(célula)`, exato, não amostrado. Motivo da fusão das duas chamadas:
medido que cada chamada a `rasterize` custa ~0,53 ms de overhead de ambiente GDAL por unidade, e a fusão foi o que
tirou o teste de desempenho de ~11 min para ~9 min nas 73 mil unidades × 12 fatores (ver "Desempenho" abaixo).

**3. Ausência de dado nunca é zero.** Raster sem CRS ou banda inexistente aborta a extração inteira
(`ErroExtracao`) antes de processar qualquer unidade. Camada vetorial com zero feições faz o mesmo
(`ErroExtracao('camada_vazia', ...)`). Dentro de uma extração válida, unidade sem NENHUMA célula com dado válido
(raster) sai com `valor=None, cobertura=0.0`; unidade que só toca dado parcialmente sai com `0 < cobertura < 1` e
`valor` calculado só sobre as células válidas. Para vetor, "sem feição sobreposta" é resposta real (fração/área/
contagem = 0, cobertura = 1,0) — diferente de "camada ausente", que aborta.

**4. Tipos fechados, sem expressão livre** (decisão A4): sete extratores de raster (`raster_media`, `_minimo`,
`_maximo`, `_mediana`, `_percentil`, `_moda`, `_fracao_classe`) e nove de vetor (`vetor_fracao_area`, `_area`,
`_contagem`, `_atributo_ponderado_area`, `_comprimento_dentro`, `_distancia_mais_proxima`, `_contagem_raio`,
`_densidade_kernel`, `_atributo_mais_proximo`). Percentil ponderado usa a definição "inferior" (primeiro valor cujo
peso acumulado alcança p/100 da soma), a mesma que os testes recomputam.

**5. Vetor: reprojeção única para `srid_trabalho`, com `shapely.make_valid` antes de qualquer operação booleana**
(regra de método da casa: "ST_MakeValid antes de operação em massa"). Geometria inválida (auto-interseção) é reparada, não
rejeitada e não ignorada — o reparo fica registrado em `avisos` por unidade. Área, comprimento e fração usam
`geopandas.overlay`/`sjoin`/`sjoin_nearest` no CRS projetado (não graus, não Web Mercator), vetorizado por camada
inteira em vez de laço unidade a unidade — é o que torna o vetor rápido o bastante para 73 mil unidades (o raster,
que precisa de interseção exata por célula, não tem esse atalho e é o gargalo medido abaixo).

**6. Densidade kernel usa `sklearn.neighbors.KernelDensity` (gaussiano, `bandwidth = largura_m` declarada pelo
modelo)**, avaliada no ponto representativo da unidade, multiplicada pelo número de pontos da camada para devolver
intensidade (pontos por unidade de área), não densidade normalizada a 1. Distância ao mais próximo usa
`GeoDataFrame.sjoin_nearest`, que mede a distância entre as GEOMETRIAS (não entre centróides) no CRS projetado.

## Desempenho — o que ficou PARCIAL, com número

Referência do item: motor logístico faz 12-19 fatores em 73 mil células em 1-2 min, **em SQL**. Este extrator é
Python puro, por unidade, sem lote no raster (o vetor é vetorizado; o raster não). Medido em REPL antes da fusão das
duas chamadas a `rasterize`: ~0,77 ms/unidade (máquina com carga 4,3-6,4 no momento, `free -g` disponível ~10 GB).
Depois da fusão: ~0,62 ms/unidade. Extrapolado para 12 fatores × 72.900 unidades: **≈ 540 s (9 min)**, contra a
referência de 1-2 min. O teste formal (`tests/unit/test_amc_zonal.py::test_extracao_de_12_fatores_sobre_73_mil_
celulas_tempo`) roda a extração completa das 72.900 unidades × 12 vezes e grava o número real em
`tests/medidas/L3-01-c-extracao-fator.json`, com a carga da máquina ao lado — mas só quando `os.getloadavg()[0] <=
8` (regra do turno); com a máquina compartilhada acima de carga 8 na maior parte de 07/09 (outra sessão rodando
agentes em paralelo), a medida formal **não foi possível hoje** e o item registra essa cláusula como PARCIAL, com o
número extrapolado acima como evidência informal, não como prova.

Caminho de otimização registrado para quem pegar o próximo passo (fora do escopo deste item): materializar a
extração raster em lote — rasterizar a grade de unidades inteira UMA vez (um raster de "id de unidade" do tamanho
do raster de entrada) e agregar com `numpy`/`scipy.ndimage` por rótulo, em vez de reabrir a janela e rasterizar por
unidade. É o que o `exactextract` faz e que não está instalado nesta máquina (`L3L6_CONCEITO.md`, "ausentes").

## Obriga

L3-01-d (transformações) recebe o `valor` bruto e a `cobertura` por fator, nunca o `NULL` silenciosamente convertido
em nota. L3-01-f (explicação) usa `avisos` para dizer que uma geometria foi reparada. L0-05 (fila) é quem decide
paralelizar por fator/raster respeitando "1 job pesado de máquina por vez"; este item não paraleliza sozinho.
