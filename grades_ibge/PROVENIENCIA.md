# Proveniência — grades de transformação de datum do IBGE (item `L2-17-crs-transformacoes`)

Três grades **NTv2** (formato `.gsb`) do **ProGriD**, o programa oficial do IBGE de transformação entre
sistemas de referência geodésicos brasileiros. São **dado aberto**: publicadas pelo IBGE (serviço público
federal) sem restrição de uso declarada, e distribuídas também pelo projeto `OSGeo/PROJ-data` (que as
reempacota em GeoTIFF, sob a mesma licença, e as serve por `https://cdn.proj.org/br_ibge_<nome>.tif` — ver
`br_ibge/br_ibge_README.txt` naquele repositório). Este item usa os `.gsb` originais do IBGE diretamente,
**vendorizados no repositório** (mesmo padrão de `osrm/*.osrm` e `web/vendor/*`: sem CDN em produção, ADR
0001 seção 11.4), para o serviço funcionar sem depender de rede externa em tempo de execução.

## Arquivos

| arquivo | grade | cobre | sha256 |
|---|---|---|---|
| `SAD69_003.GSB` | SAD69 (rede clássica) → SIRGAS2000 | Brasil, onshore e offshore (Rocas, Fernando de Noronha, Trindade, Martim Vaz, São Pedro e São Paulo) | `8227c9aff388a24085424f56e7664827b74a18d9b8fed7533346a22d0d0548e5` |
| `CA61_003.GSB` | Córrego Alegre 1961 → SIRGAS2000 | Brasil onshore, entre 18°S e 27°30'S (e a leste de 54°W entre 15°S e 18°S) | `820fd2476a7f85d4cc8a4a0d907477fcefd848ad925ffc79ee4478dc21beb52c` |
| `CA7072_003.GSB` | Córrego Alegre 1970/1972 → SIRGAS2000 | Brasil onshore, a oeste de 54°W e ao sul de 18°S; também ao sul de 15°S entre 54°W e 42°W; também a leste de 42°W | `ab89150df187bccb12b44a364adc256e0159d562cf60539e6629940e1c115808` |

Cobertura e exatidão declarada (classe EPSG, lida do registro oficial via `pyproj.transformer.TransformerGroup`,
PROJ 9.4.0/pyproj 3.7.2 desta máquina — comando de reexecução abaixo) — usada por `app/crs/grades.py` para
decidir a grade por área e para o texto que a resposta da API declara:

- **SAD69 → SIRGAS2000**: `bounds=(-74.01, -35.71, -25.28, 7.04)`, classe de exatidão EPSG **5,0 m** para a
  operação "pipeline" sempre disponível (parâmetros de 7/3 do R.PR 01/2005, sem grade — usada como
  alternativa quando o ponto cai fora da grade); a operação "SAD69 to SIRGAS 2000 (2)" (a que usa
  `br_ibge_SAD69_003.tif`, o MESMO conteúdo do nosso `.gsb`) tem `bounds=(-60.58, -33.78, -34.74, 4.43)` e
  classe **1,0 m**. Medido nesta rodada (10 pontos oficiais do ProGriD Online, ver
  `tests/dados/pontos_ibge_sad69_sirgas2000.json`): o pipeline local com o `.gsb` bate com o resultado oficial
  do IBGE a **≤ 0,07 mm** (bem abaixo da classe declarada — a classe é uma cota conservadora de exatidão da
  malha em relação à rede geodésica real, não do cálculo em si); sem transformação nenhuma (tratar as mesmas
  coordenadas como se já fossem SIRGAS2000) o erro medido nos 10 pontos foi de **62 a 72 m**.
- **Córrego Alegre 1961 → SIRGAS2000**: `bounds=(-58.16, -27.5, -38.82, -14.99)`, classe **2,0 m**.
- **Córrego Alegre 1970/72 → SIRGAS2000**: `bounds=(-58.16, -33.78, -34.74, -2.68)`, classe **2,0 m**.

Comando de reexecução da tabela de área/exatidão (sem precisar de rede — só consulta o `proj.db` local):

```bash
python3 - <<'PY'
from pyproj.transformer import TransformerGroup
for origem, nome in ((4618, "SAD69"), (5524, "Corrego Alegre 1961"), (4225, "Corrego Alegre 1970-72")):
    print("===", nome, "-> SIRGAS2000 (4674)")
    tg = TransformerGroup(origem, 4674, always_xy=True)
    for op in tg.transformers + tg.unavailable_operations:
        print(op.name, op.accuracy, op.area_of_use)
PY
```

## Como foram obtidos

Os quatro `.gsb` (os três acima + `SAD96_003.GSB`, baixado mas **não usado** neste item — a materialização
SAD69/96 clássica não está no escopo do portão de pronto, que pede só "SAD69 e Córrego Alegre") já estavam
em `/tmp/grades_ibge/` nesta máquina (baixados numa sessão anterior da casa, junto com os relatórios de
ajustamento do IBGE `rel_sad69.pdf`/`rel_sirgas2000.pdf` e um conjunto de 24 pontos de referência
`PID_*` — ver "O que NÃO foi usado" abaixo). Copiados para este diretório sem alteração; os sha256 acima
foram recalculados aqui, não herdados.

## Como foram VALIDADOS contra uma fonte oficial independente (a parte que importa)

Ter o arquivo `.gsb` correto não prova que o *pipeline* que o usa (`+proj=pipeline +step +proj=hgridshift
+grids=<arquivo>`, sem CRS declarado nas pontas) está montado certo — eixo trocado, unidade errada ou sinal
invertido dão número plausível e errado. A prova usada foi comparar contra o **serviço oficial ao vivo do
IBGE**, `https://servicodados.ibge.gov.br/api/v1/progrid` (API pública, descoberta por busca — não
documentada no material estático baixado antes), que devolve `"tipo_conversao":"grid"` quando usa a mesma
malha NTv2. Para 10 coordenadas SAD69 arbitrárias dentro da cobertura (capitais/cidades espalhadas pelo
país), o pipeline local bateu com a resposta oficial a ≤ 0,07 mm (`tests/unit/test_crs_grade_ibge.py`,
fixture `tests/dados/pontos_ibge_sad69_sirgas2000.json`).

## O que NÃO foi usado (e por quê)

Os arquivos `rel_sad69.pdf`, `rel_sirgas2000.pdf` e os `PID_*.txt/csv` (24 pontos, coordenadas decimais,
UTM, XYZ geocêntrico) baixados na mesma sessão anterior **não têm o par SAD69↔SIRGAS2000 do mesmo vértice
físico em formato extraível por texto** (`pdftotext` não achou tabela numérica nos PDFs — texto corrido só,
sem os quadros de resíduos; os `PID_*` são um único conjunto de coordenadas, aparentemente já em
SIRGAS2000/GRS80 pelas coordenadas XYZ geocêntricas, sem a contraparte em SAD69). Usá-los exigiria inverter
a grade numericamente (Newton local) para sintetizar o lado SAD69 — o que tornaria o "ponto oficial" um
ponto CALCULADO por nós mesmos a partir da nossa própria grade, um teste circular (a regra da casa:
"procedência errada é pior que procedência nenhuma"). O serviço `servicodados.ibge.gov.br/api/v1/progrid`
resolve isso sem ambiguidade: é o cálculo oficial, ao vivo, do órgão dono da grade.
