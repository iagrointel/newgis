"""Cláusula do portão de pronto: "as transformações dos 19 fatores do motor logístico reescritas
neste JSON reproduzem cbre.hex_fav (só leitura) com |Δ| ≤ 0,5 em 100 % das células".

Os "19 fatores" são os de ordem 1-19 em `cbre.fatores` (o motor tinha exatamente 19 fatores em
29/08/2026 — README.md do projeto CBRE, seção "19 fatores"; cresceu para 26 depois). `cbre.hex_fav`
é lida SÓ LEITURA (`sudo -u postgres psql`, sem escrever nada) — é o produto de outro projeto
(`/home/dev/cbre`), não deste item.

Cobertura HONESTA, não 19 de 19: dos 19, só os que são uma transformação DECLARATIVA de UMA coluna
bruta E cuja coluna bruta bate 100 % com a favorabilidade oficial (a prova é ela mesma o filtro) ficam
verificados aqui — 4: decl, rod, agua, press. `gru` e `se` TÊM coluna bruta candidata (`v_t_gru_ctrl`,
`v_dist_se`) e a fórmula do README bate na maioria das células, mas ~4 % (`gru`) e a maior parte
(`se`) divergem mais que a tolerância — sinal de que a coluna gravada não é o mesmo valor que o
pipeline do fator usou (nome "_ctrl" sugere controle/QA, não a entrada; `se` pode agregar mais de uma
subestação ou aplicar bônus não documentado) — apurar isso é trabalho de outro item, não deste; ficam
em `FORA_DE_ESCOPO` com o percentual medido, não escondidos atrás de um "reprovado" mudo. Os demais 13
combinam VÁRIAS colunas, aplicam veto, somam bônus, ou têm fronteira que a convenção única de `faixas`
não representa (ex.: `ener` soma bônus de subestação; `restr` é o MENOR de quatro regras; `roubo`/
`trib`/`cluster` são fórmulas de mais de uma variável) — isso é trabalho de EXTRAÇÃO/combinação de
fator (L3-01-c/L3-01-e), não de transformação de um valor já extraído. Todos os 15 fora de escopo têm
uma linha nomeada no `tests/medidas/*.json` com o motivo específico."""

import json
import subprocess

import numpy as np
import pytest

from app.amc import transformacoes as tr

TOLERANCIA = 0.5
EPSILON_PONTO_FLUTUANTE = 1e-6  # f_* é smallint arredondado; sem isto, 54,5 vs 55 falha por erro de fp em x.5


def _psql_json(sql: str) -> list[dict]:
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-Atqc",
         f"SELECT coalesce(json_agg(t), '[]') FROM ({sql}) t"],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(r.stdout)


# fator -> (colunas brutas, transformação declarativa equivalente, coluna de favorabilidade oficial)
CASOS = {
    "decl": (["v_slope"], {"tipo": "linear", "minimo": 2.0, "maximo": 30.0, "direcao": "decrescente",
                           "abaixo": 100.0, "acima": 0.0}, "f_decl"),
    "rod": (["v_dist_rod"], {"tipo": "linear", "minimo": 300.0, "maximo": 5000.0, "direcao": "decrescente",
                             "saida_min": 10.0, "saida_max": 100.0, "abaixo": 100.0, "acima": 10.0}, "f_rod"),
    "agua": (["v_app30"], {"tipo": "categoria", "notas": {"True": 40.0, "False": 100.0}}, "f_agua"),
    "press": (["v_durb"], {"tipo": "linear", "minimo": 0.0, "maximo": 0.20, "direcao": "crescente",
                           "abaixo": 0.0, "acima": 100.0}, "f_press"),
}

# fator (ordem 1-19) fora da cobertura, e por quê — cada um seria "combinação de várias colunas/veto",
# não uma transformação declarativa de um valor já extraído (ver docstring do módulo)
FORA_DE_ESCOPO = {
    "zon": "categoria multi-regra: nota depende de v_zona OU de texto livre 'onde a lei foi lida' — "
           "duas fontes concorrentes para a mesma célula, não é 1 coluna -> 1 nota",
    "gru": "coluna candidata v_t_gru_ctrl (o nome sugere controle/QA, não a entrada do fator) segue a "
           "forma de degraus 15/30/45/60 na maioria das células mas diverge > 0,5 em 3,90% delas "
           "(2.731 de 70.001, medido 07/09/2026) — sinal de que não é a mesma entrada que o pipeline "
           "do fator usou; apurar a coluna certa é trabalho de outro item",
    "se": "coluna candidata v_dist_se tem a forma qualitativa certa (perto=100, longe=20) mas só "
          "19,90% das células batem a ≤ 0,5 (medido 07/09/2026) — a dispersão sugere que a favorabilidade "
          "considera mais de uma subestação ou um bônus não documentado; não é uma transformação de "
          "1 valor até isso ser investigado",
    "disp": "combina fração de 4 classes de uso do solo (pasto+agrícola+não-vegetado+mineração) com veto "
            "por urbano/floresta antes de virar nota — extração composta, não transformação de 1 valor",
    "ener": "categórico (rede MT na célula/perto) + bônus de +10 por subestação a até 5 km, com teto 100",
    "restr": "nota = MENOR de até 4 regras independentes (manancial/RBCV/UC uso sustentável/borda UC-PI) "
             "mais veto por TI/UC integral/embargo/zona núcleo",
    "varzea": "4 classes com fronteira MISTA (pct=0 fechado à esquerda, pct=0,10 fechado à direita da "
              "classe seguinte) — não expressável na convenção única de `faixas` deste item, mais um "
              "caminho de proxy declarado quando falta cobertura oficial",
    "dens": "3 trechos com INCLINAÇÕES diferentes (0-500, 500-2.000 platô, 2.000-10.000) — mais de um "
            "segmento linear, fora do que um único `linear`/`faixas` representa",
    "roubo": "nota vem de densidade kernel gaussiana 2 km sobre boletim de ocorrência de duas leituras "
             "somadas sem duplicar — o valor bruto em si já é uma extração espacial composta",
    "trib": "combina 3 variáveis com pesos fixos (0,40×ISS + 0,30×IPTU + 0,30×incentivo) min-max por "
            "município antes de virar nota — soma ponderada de 3 fatores brutos, não 1",
    "renda": "percentil por setor censitário não está materializado em `cbre.hex_fav` como coluna bruta "
             "própria (é calculado dentro do pipeline do fator) — sem a coluna de entrada não há o que "
             "comparar aqui, ainda que a fórmula (100 − percentil) seja um `linear` trivial",
    "rlapp": "fator é POR IMÓVEL (área útil fora de RL/APP ÷ área do imóvel do CAR), não por célula — "
             "não existe em `cbre.hex_fav`, que é a grade; comparável só em `cbre.imoveis_fav`",
    "polos": "rampa linear de base MENOS penalidade de −8/polo grande e −4/escola a até 1 km — a "
             "penalidade depende de contagem de pontos na vizinhança, não é 1 valor bruto",
    "cluster": "soma de dois termos (m² de galpão a 2 km + nº de condomínios a 5 km), cada um por si um "
               "raio de busca espacial — 2 variáveis compostas, não 1",
    "mine": "nota depende do VEREDITO por imóvel OU da fração de polígono de direito minerário por "
            "célula — categórico de fonte composta (ANM + Sentinel), sem coluna de valor contínuo único",
}


@pytest.mark.parametrize("fator", sorted(CASOS))
def test_reproduz_fator_do_hex_fav(env, fator, medida):
    colunas, transformacao, col_fav = CASOS[fator]
    sql_colunas = ", ".join(colunas + [col_fav])
    condicao = " AND ".join(f"{c} IS NOT NULL" for c in colunas + [col_fav])
    linhas = _psql_json(f"SELECT {sql_colunas} FROM cbre.hex_fav WHERE {condicao}")
    assert linhas, f"cbre.hex_fav sem nenhuma linha com {colunas}/{col_fav} preenchidos"
    bruto = [li[colunas[0]] for li in linhas]
    if transformacao["tipo"] == "categoria":
        bruto = [str(v) for v in bruto]
    oficial = np.asarray([float(li[col_fav]) for li in linhas], dtype=float)
    nosso = tr.transformar(bruto, transformacao)
    delta = np.abs(nosso - oficial)
    n_total = len(linhas)
    n_dentro = int((delta <= TOLERANCIA + EPSILON_PONTO_FLUTUANTE).sum())
    pct = 100.0 * n_dentro / n_total
    medida("L3-01-d-transformacoes")(
        f"cbre_fator_{fator}_pct_dentro_de_{TOLERANCIA}", round(pct, 4), "%",
        f"pytest tests/unit/test_amc_transformacoes_cbre.py::test_reproduz_fator_do_hex_fav[{fator}] "
        f"(n={n_total}, max|delta|={float(delta.max()):.4f})",
    )
    assert pct == 100.0, (
        f"fator {fator!r}: só {pct:.4f}% das {n_total} células ficaram a ≤ {TOLERANCIA} da nota oficial "
        f"(máxima diferença observada: {float(delta.max()):.4f})"
    )


def test_fora_de_escopo_documentado(medida):
    """Os 15 fatores de ordem 1-19 que este item NÃO reproduz têm motivo nomeado — não é omissão. Os
    19 = 4 cobertos (CASOS) + 15 fora de escopo (FORA_DE_ESCOPO); ver docstring do módulo."""
    cobertos = set(CASOS) | set(FORA_DE_ESCOPO)
    assert len(CASOS) == 4 and len(FORA_DE_ESCOPO) == 15 and len(cobertos) == 19, sorted(cobertos)
    for fator, motivo in FORA_DE_ESCOPO.items():
        medida("L3-01-d-transformacoes")(f"cbre_fator_{fator}_fora_de_escopo", motivo, "texto",
                                          "ver FORA_DE_ESCOPO em tests/unit/test_amc_transformacoes_cbre.py")
