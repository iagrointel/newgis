"""Trava: medida so vai ao disco se o teste APROVAR (tests/conftest.py, 18/09/2026).

A fixture `medida` gravava `tests/medidas/<item>.json` no MEIO do teste. Se uma asercao posterior
reprovasse, o numero ja estava no disco — e uma medida de rodada reprovada e indistinguivel de uma
medida boa quando alguem for ler o arquivo depois. Quatro arquivos de teste faziam isso sem querer.

Agora a escrita fica em espera e o despejo anda junto com o veredito do caso. Par positivo
obrigatorio: prova-se que APROVADO grava E que REPROVADO nao grava. So a segunda metade seria
satisfeita por uma fixture quebrada que nunca grava nada."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

CORPO = '''
def test_que_aprova(medida):
    medida("zz-guarda-medida-aprova")("n", 1, "un", "cmd")
    assert True

def test_que_reprova(medida):
    medida("zz-guarda-medida-reprova")("n", 2, "un", "cmd")
    assert False, "reprova de proposito"
'''


def _roda(tmp_path: Path):
    alvo = tmp_path / "test_alvo.py"
    alvo.write_text(CORPO, encoding="utf-8")
    env = dict(os.environ, PLAT_TESTE_EM_CGROUP="1", PLAT_GRAVAR_MEDIDAS="1")
    env.pop("PLAT_TESTE_TUDO_PULADO_OK", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(alvo), "-q", "-p", "no:cacheprovider", "-p", "tests.conftest"],
        cwd=RAIZ, env=env, capture_output=True, text=True, timeout=300,
    )


def test_aprovado_grava_e_reprovado_nao_grava(tmp_path):
    aprova = RAIZ / "tests" / "medidas" / "zz-guarda-medida-aprova.json"
    reprova = RAIZ / "tests" / "medidas" / "zz-guarda-medida-reprova.json"
    for f in (aprova, reprova):
        f.unlink(missing_ok=True)
    try:
        r = _roda(tmp_path)
        assert aprova.exists(), ("a metade positiva falhou: caso APROVADO nao gravou medida", r.stdout[-2000:])
        assert json.loads(aprova.read_text(encoding="utf-8"))["medidas"]["n"]["valor"] == 1
        assert not reprova.exists(), ("caso REPROVADO deixou medida no disco", r.stdout[-2000:])
    finally:
        for f in (aprova, reprova):
            f.unlink(missing_ok=True)
