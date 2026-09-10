"""Os 10 exemplos de sdk/python/exemplos/ SÃO os testes que a cláusula 1 do portão pede: "os 10
exemplos passam no make check". Cada exemplo expõe `main(url, inquilino, login, senha)`; este
arquivo só os chama contra a API real da trilha (fixture `url_api`, um uvicorn de verdade)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

EXEMPLOS_DIR = Path(__file__).resolve().parents[2] / "sdk" / "python" / "exemplos"
NOMES = [
    "01_login",
    "02_listar_itens",
    "03_criar_camada",
    "04_atualizar_e_apagar",
    "05_pastas_e_mover",
    "06_paginacao_com_muitos_itens",
    "07_tokens_de_servico",
    "08_jobs",
    "09_compartilhamento",
    "10_erros_e_escopo",
]


def _carregar(nome: str):
    caminho = EXEMPLOS_DIR / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(f"sdk_exemplo_{nome}", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_exatamente_dez_exemplos():
    arquivos = sorted(p.stem for p in EXEMPLOS_DIR.glob("*.py") if not p.stem.startswith("_"))
    assert arquivos == NOMES, f"portão pede 10 exemplos; achado: {arquivos}"


@pytest.mark.parametrize("nome", NOMES)
def test_exemplo(nome, url_api, credenciais_demo, worker_da_fila):
    inquilino, login, senha = credenciais_demo
    if EXEMPLOS_DIR not in map(Path, sys.path):
        sys.path.insert(0, str(EXEMPLOS_DIR))
    modulo = _carregar(nome)
    modulo.main(url_api, inquilino, login, senha)
