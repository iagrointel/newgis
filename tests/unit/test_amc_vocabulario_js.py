"""O navegador e o servidor têm de chamar a mesma coisa pelo mesmo nome (item L3-01-g-tela-motor).

A tela do motor lê o documento do modelo (`combinador.tipo` = `soma_ponderada_normalizada`, `dado_ausente` =
`excluir_fator`) e chama `combinar()` do JavaScript, que usa outro vocabulário (`soma_ponderada`, `excluir`).
A tradução existe duas vezes — em `app/amc/explicacao.py` e em `web/js/amc/combinacao.js` — porque as duas
implementações da conta são deliberadamente independentes. Duas cópias que se desencontram fariam a tela
mostrar uma nota e a explicação do servidor mostrar outra, sem erro nenhum aparecer. Este teste é o que
cobra que elas continuem iguais, e que cubram todos os valores que o próprio esquema do modelo admite."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.amc.esquema import esquema
from app.amc.explicacao import MAPA_COMBINADOR, MAPA_POLITICA

ROOT = Path(__file__).resolve().parents[2]
MODULO_JS = ROOT / "web" / "js" / "amc" / "combinacao.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node ausente nesta máquina")


def _do_js() -> dict:
    programa = (
        "import { MAPA_COMBINADOR, MAPA_POLITICA, COMBINADORES, POLITICAS_AUSENTE } "
        f"from {json.dumps(MODULO_JS.as_posix())};"
        "process.stdout.write(JSON.stringify({combinador: MAPA_COMBINADOR, politica: MAPA_POLITICA,"
        " combinadores: Object.keys(COMBINADORES), politicas: Object.keys(POLITICAS_AUSENTE)}));"
    )
    p = subprocess.run(["node", "--input-type=module", "-e", programa], capture_output=True, text=True,
                       timeout=120, check=False)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_traducao_do_combinador_e_a_mesma_nos_dois_lados():
    assert _do_js()["combinador"] == MAPA_COMBINADOR


def test_traducao_da_politica_de_dado_ausente_e_a_mesma_nos_dois_lados():
    assert _do_js()["politica"] == MAPA_POLITICA


def test_todo_combinador_do_esquema_tem_traducao_e_destino():
    """Combinador novo no esquema sem tradução faria a tela cair no padrão em silêncio — a pior falha desta
    tela é recolorir o mapa com uma conta que não é a que o modelo declara."""
    props = esquema()["properties"]
    do_esquema = set(props["combinador"]["properties"]["tipo"]["enum"])
    js = _do_js()
    assert do_esquema <= set(MAPA_COMBINADOR), do_esquema - set(MAPA_COMBINADOR)
    assert set(MAPA_COMBINADOR.values()) <= set(js["combinadores"]), \
        set(MAPA_COMBINADOR.values()) - set(js["combinadores"])


def test_toda_politica_de_dado_ausente_do_esquema_tem_traducao_e_destino():
    do_esquema = set(esquema()["properties"]["dado_ausente"]["enum"])
    js = _do_js()
    assert do_esquema <= set(MAPA_POLITICA), do_esquema - set(MAPA_POLITICA)
    assert set(MAPA_POLITICA.values()) <= set(js["politicas"]), \
        set(MAPA_POLITICA.values()) - set(js["politicas"])


def test_a_tela_do_motor_nao_repete_a_traducao_por_conta_propria():
    """A tela importa os dois dicionários de combinacao.js; se voltar a escrever o seu, esta prova perde valor."""
    fonte = (ROOT / "web" / "js" / "amc" / "motor_pagina.js").read_text(encoding="utf-8")
    assert "MAPA_COMBINADOR" in fonte and "from './combinacao.js'" in fonte
    assert not re.search(r"^\s*(const|let|var)\s+MAPA_(COMBINADOR|POLITICA)\b", fonte, re.M)
