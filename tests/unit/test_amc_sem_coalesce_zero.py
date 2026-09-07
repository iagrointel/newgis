"""Varredura estática do item L3-14-cobertura-dado-ausente.

Regra dura do motor AMC: ausência de dado é informação, nunca vira medição. Este teste varre o
código do motor (`app/amc/`, onde a matriz unidade×fator é construída, transformada e combinada)
atrás de qualquer forma de "ausente vira zero" — em SQL (``COALESCE(coluna, 0)``/``coalesce``) e nos
equivalentes em Python/numpy sobre uma coluna de fator ou de favorabilidade (``fillna(0)``,
``nan_to_num`` sem cuidado, ``or 0`` como substituto de valor ausente).

Falso positivo esperado e por quê cada exceção é segura (achados ao rodar a suíte completa pela
primeira vez com o item L3-07-agregacao, não introduzidos por ele — `unidades.py` já tinha os dois
primeiros): as três linhas abaixo somam uma CONTAGEM/ÁREA sobre um CONJUNTO de linhas (unidades ou
células), não o valor de um FATOR ou de uma FAVORABILIDADE. Quando o conjunto é vazio, `sum()` dá
`NULL` e o `COALESCE(..., 0)` está certo: "zero linhas somam zero", não "fator ausente virou zero".
A regra do item é sobre a métrica que descreve UMA unidade (a coluna teria de ficar `NULL`, nunca 0,
quando falta dado); aqui é sobre quantas unidades/células existem ou quanta área elas somam — 0 é a
resposta verdadeira, não um substituto de ausência.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ_AMC = Path(__file__).resolve().parents[2] / "app" / "amc"

# Padrões que, aplicados a uma coluna de fator/favorabilidade, transformariam ausência em zero.
# Casam tanto SQL (COALESCE) quanto o equivalente em pandas/numpy.
PADRAO_COALESCE_ZERO = re.compile(r"coalesce\s*\(\s*[^,]+,\s*0(?:\.0)?\s*\)", re.IGNORECASE)
PADRAO_FILLNA_ZERO = re.compile(r"\.fillna\s*\(\s*0(?:\.0)?\s*\)")
PADRAO_OR_ZERO_ATRIBUICAO = re.compile(r"=\s*[\w\.\[\]]+\s+or\s+0\b")

# Exceções declaradas: (arquivo relativo a app/amc/, trecho da linha) — ver a justificativa no
# docstring do módulo. Todas somam CONTAGEM/ÁREA sobre um conjunto (nunca o valor de um fator).
EXCECOES: set[tuple[str, str]] = {
    ("unidades.py",
     'cur.execute("SELECT count(*) AS n, coalesce(sum(area_m2), 0) AS a FROM plat.amc_unidade '
     'WHERE conjunto_id = %s",'),
    ("unidades.py", '"  SELECT count(*) AS n, coalesce(sum(area_m2), 0) AS a, "'),
    ("agregacao.py",
     "ELSE coalesce(t.area_vetada_m2, 0) / t.area_total_m2 END AS fracao_vetada,"),
}


def _arquivos_amc() -> list[Path]:
    return sorted(p for p in RAIZ_AMC.glob("*.py") if p.name != "__init__.py")


def _achados(padrao: re.Pattern) -> list[tuple[str, int, str]]:
    achados = []
    for arquivo in _arquivos_amc():
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), start=1):
            if padrao.search(linha):
                chave = (arquivo.name, linha.strip())
                if chave in EXCECOES:
                    continue
                achados.append((arquivo.name, numero, linha.strip()))
    return achados


def test_sem_coalesce_de_coluna_de_fator_para_zero():
    achados = _achados(PADRAO_COALESCE_ZERO)
    assert achados == [], (
        "COALESCE(coluna, 0) achado no motor AMC — ausência de dado nunca pode virar zero "
        f"numérico (declare exceção em EXCECOES se for engano do regex): {achados}"
    )


def test_sem_fillna_zero_em_coluna_de_fator():
    achados = _achados(PADRAO_FILLNA_ZERO)
    assert achados == [], f".fillna(0) achado no motor AMC: {achados}"


def test_sem_or_zero_como_substituto_de_ausencia():
    achados = _achados(PADRAO_OR_ZERO_ATRIBUICAO)
    assert achados == [], f"'x or 0' achado no motor AMC (mascara None como zero): {achados}"


def test_lista_de_arquivos_varridos_nao_esta_vazia():
    """Guarda contra a varredura silenciosamente varrer zero arquivo (diretório errado, etc.)."""
    arquivos = _arquivos_amc()
    assert len(arquivos) >= 5
    nomes = {a.name for a in arquivos}
    assert {"cobertura.py", "combinacao.py", "relatorio.py", "zonal.py", "vetorial.py"} <= nomes
