"""Tela Tarefas mostra a posição na fila (item L0-05-e-justica-entre-inquilinos).

A coluna "progresso" da lista de tarefas é escrita por `textoProgresso` em `web/js/jobs/formato.js`, função
pura (sem DOM, sem rede). Aqui ela é executada no mesmo motor do navegador (node, módulo ES) com os quatro
casos que importam: pendente com posição, pendente sem posição (a API devolve null enquanto não há fila do
inquilino), pendente agendado para o futuro, e um estado não pendente — onde posição nenhuma pode aparecer.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORMATO = ROOT / "web" / "js" / "jobs" / "formato.js"

PROGRAMA = """
import { textoProgresso } from '%s';
const casos = JSON.parse(process.argv[1]);
process.stdout.write(JSON.stringify(casos.map(textoProgresso)));
""" % FORMATO


def _rodar(casos: list[dict]) -> list[str]:
    r = subprocess.run(["node", "--input-type=module", "-e", PROGRAMA, "--", json.dumps(casos)],
                       capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado nesta máquina")
def test_texto_da_coluna_progresso_traz_a_posicao_na_fila():
    futuro = "2099-01-01T12:00:00Z"
    pendente_com, pendente_sem, agendado, rodando = _rodar([
        {"estado": "pendente", "posicao_fila": 3},
        {"estado": "pendente", "posicao_fila": None},
        {"estado": "pendente", "posicao_fila": 2, "agendado_para": futuro},
        {"estado": "rodando", "progresso": 40, "posicao_fila": None},
    ])
    assert pendente_com == "na fila · posição 3 na fila"
    assert pendente_sem == "na fila"
    assert agendado.startswith("na fila até ") and agendado.endswith("· posição 2 na fila")
    assert "posição" not in rodando
