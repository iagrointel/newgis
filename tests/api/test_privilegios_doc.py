"""docs/PRIVILEGIOS.md é gerado do BANCO, não escrito à mão (item L0-07-b-papeis-privilegios, portão de pronto).
Roda o gerador em memória (`docs/gerar_privilegios.py::gerar_markdown`) contra o mesmo `PLAT_DSN` da suíte e
compara com o arquivo comitado — diverge se alguém editar `docs/PRIVILEGIOS.md` à mão, ou aplicar uma migração
que mexe em `plat.privilegio`/`plat.perfil_privilegio` sem rodar `make privilegios` de novo."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs"))

import gerar_privilegios  # noqa: E402 — módulo em docs/, fora do pacote app


def test_privilegios_md_bate_com_o_banco_agora(env):
    gerado = gerar_privilegios.gerar_markdown()
    comitado = gerar_privilegios.DESTINO.read_text(encoding="utf-8")
    assert gerado == comitado, "docs/PRIVILEGIOS.md desatualizado; rode `make privilegios` e comite o resultado"
