"""Varredura estática do item L3-14-cobertura-dado-ausente.

Regra dura do motor AMC: ausência de dado é informação, nunca vira medição. Este teste varre o
código do motor (`app/amc/`, onde a matriz unidade×fator é construída, transformada e combinada)
atrás de qualquer forma de "ausente vira zero" — em SQL (``COALESCE(coluna, 0)``/``coalesce``) e nos
equivalentes em Python/numpy sobre uma coluna de fator ou de favorabilidade (``fillna(0)``,
``nan_to_num`` sem cuidado, ``or 0`` como substituto de valor ausente).

Falso positivo esperado e por quê cada exceção é segura: nenhuma hoje (lista abaixo fica vazia de
propósito — qualquer entrada nova exige justificar por que aquele COALESCE(...,0) NÃO é sobre uma
coluna de fator/favorabilidade, com o número da linha).
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

# Exceções declaradas: (arquivo relativo a app/amc/, trecho da linha, motivo). Vazia por enquanto —
# nenhum caso legítimo de COALESCE(...,0) apareceu dentro do motor AMC.
EXCECOES: set[tuple[str, str]] = set()


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
