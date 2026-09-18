"""Trava da guarda de rodada inteiramente pulada (tests/conftest.py, 18/09/2026).

A guarda existe porque `pytest.skip("... nesta base")` transforma base incompleta em rodada verde:
`tests/api/test_acervo_frescor.py` tem SEIS pulos desse feitio e, numa trilha sem o schema `acervo`,
os seis pulam e o arquivo sai com código 0 — o item parece medido sem que nada tenha sido medido.
A medição do acervo cegou assim duas vezes.

Como toda trava desta casa, ela tem par positivo: prova-se que a guarda REPROVA a rodada 100 % pulada
E que fica calada quando ao menos um caso aprovou. Sem o par, a trava poderia estar sempre acesa (ou
sempre apagada) e ninguém veria."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

SO_PULA = "import pytest\ndef test_a():\n    pytest.skip('nao existe nesta base')\n"
UM_PASSA = "import pytest\ndef test_ok():\n    assert True\ndef test_p():\n    pytest.skip('nao existe nesta base')\n"


def _roda(tmp_path: Path, corpo: str, extra_env: dict[str, str] | None = None):
    alvo = tmp_path / "test_alvo.py"
    alvo.write_text(corpo, encoding="utf-8")
    # `-p no:cacheprovider` e o conftest da raiz entram por --rootdir/--confcutdir na própria árvore
    env = dict(os.environ, PLAT_TESTE_EM_CGROUP="1", **(extra_env or {}))
    env.pop("PLAT_TESTE_TUDO_PULADO_OK", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(alvo), "-q", "-p", "no:cacheprovider",
         "-p", "tests.conftest"],
        cwd=RAIZ, env=env, capture_output=True, text=True, timeout=300,
    )


def test_rodada_inteiramente_pulada_reprova(tmp_path):
    r = _roda(tmp_path, SO_PULA)
    assert r.returncode != 0, r.stdout[-3000:]
    assert "guarda de rodada pulada" in r.stdout, r.stdout[-3000:]


def test_rodada_com_um_aprovado_nao_reprova(tmp_path):
    """Par positivo: a guarda não pode acender só por existir pulo."""
    r = _roda(tmp_path, UM_PASSA)
    assert r.returncode == 0, r.stdout[-3000:]
    assert "guarda de rodada pulada" not in r.stdout, r.stdout[-3000:]


def test_saida_consciente_desliga_a_guarda(tmp_path):
    r = _roda(tmp_path, SO_PULA, {"PLAT_TESTE_TUDO_PULADO_OK": "1"})
    assert r.returncode == 0, r.stdout[-3000:]
