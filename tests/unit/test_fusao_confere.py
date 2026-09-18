"""Trava do detector de fusão que apaga trabalho (scripts/fusao_confere.py, 18/09/2026).

Em UMA noite, oito entregas foram recuperadas nesta casa e nenhuma era trabalho novo: era trabalho que
existia em master e que uma fusão apagou. O item ficava marcado "refutado: artefato ausente em master"
e parecia coisa por construir. `git merge` não avisa, porque o caso perigoso NÃO conflita — um lado
simplesmente vence, calado.

Par positivo obrigatório, num repositório de brinquedo criado aqui mesmo:
  - ACUSA quando master acrescentou algo depois que o ramo nasceu e o ramo não tem aquilo;
  - CALA quando o ramo nasceu do master atual e só acrescenta.
Só a primeira metade seria satisfeita por um script que acusa sempre."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "fusao_confere.py"


def _git(repo: Path, *args: str):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "app.py").write_text("linha_base = 1\n", encoding="utf-8")
    _git(r, "add", "app.py")
    _git(r, "commit", "-qm", "base")
    return r


def _roda(repo: Path, ramo: str):
    return subprocess.run([sys.executable, str(SCRIPT), ramo], cwd=repo,
                          capture_output=True, text=True, timeout=120)


def test_acusa_quando_a_fusao_apagaria_o_que_master_ganhou(tmp_path):
    r = _repo(tmp_path)
    _git(r, "checkout", "-q", "-b", "ramo")          # ramo nasce da base
    (r / "app.py").write_text("linha_base = 1\nDO_RAMO = 2\n", encoding="utf-8")
    _git(r, "commit", "-qam", "ramo mexe no arquivo")
    _git(r, "checkout", "-q", "master")
    # master ganha uma linha DEPOIS que o ramo nasceu, e o ramo nao a tem
    (r / "app.py").write_text("linha_base = 1\nDE_MASTER_ENTREGUE = 99\n", encoding="utf-8")
    _git(r, "commit", "-qam", "master entrega algo novo")

    out = _roda(r, "ramo")
    assert out.returncode == 1, (out.returncode, out.stdout, out.stderr)
    assert "DE_MASTER_ENTREGUE = 99" in out.stdout, out.stdout
    assert "app.py" in out.stdout, out.stdout


def test_cala_quando_nada_de_master_se_perde(tmp_path):
    """Par positivo: ramo em dia com master, só acrescentando — o detector não pode acusar."""
    r = _repo(tmp_path)
    (r / "app.py").write_text("linha_base = 1\nDE_MASTER = 7\n", encoding="utf-8")
    _git(r, "commit", "-qam", "master entrega algo")
    _git(r, "checkout", "-q", "-b", "ramo")          # ramo nasce DEPOIS, ja com a entrega
    (r / "app.py").write_text("linha_base = 1\nDE_MASTER = 7\nDO_RAMO = 3\n", encoding="utf-8")
    _git(r, "commit", "-qam", "ramo acrescenta")
    _git(r, "checkout", "-q", "master")

    out = _roda(r, "ramo")
    assert out.returncode == 0, (out.returncode, out.stdout, out.stderr)
    assert "nada que master tinha se perde" in out.stdout, out.stdout
