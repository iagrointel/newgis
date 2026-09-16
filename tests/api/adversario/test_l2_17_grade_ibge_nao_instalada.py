"""Adversário L2 (linha, parte 3) — item `L2-17-crs-transformacoes`.

Portão (literal): "grade .gsb instalada pelo install.sh com sha256 conferido". O script que faz essa
conferência existe (`grades_ibge/instalar.sh`, confere `SHA256SUMS` das 3 grades NTv2 do IBGE) e o
PRÓPRIO CABEÇALHO dele afirma "Chamado pelo install.sh (seção 'h5')" — mas isso é falso: `install.sh`
nunca menciona `grades_ibge` nem `instalar.sh` em lugar nenhum, e a seção "h5" real do instalador é
outra coisa inteiramente (a imagem docker do notebook por inquilino, item L2-16-b — conferido nesta
rodada, `grep -n '== h5' install.sh`). Rodar `install.sh` do zero numa máquina nova NUNCA confere a
integridade das grades — a única forma de rodar essa conferência é chamar `grades_ibge/instalar.sh`
manualmente, por fora do instalador, o que ninguém no portão pede para fazer.

Isto não muda o resultado NUMÉRICO das transformações datum a datum (as grades já estão no repositório
e `app/crs/grades.py` as lê por caminho absoluto, sem depender do instalador para achá-las) — mas quebra
a garantia de PROVENIÊNCIA/INTEGRIDADE que o portão pede: uma grade `.gsb` corrompida ou trocada por
engano nunca seria pega antes de entrar em produção, porque o passo que pegaria isso não roda.

Reprodução (sem rede, sem banco — só o texto dos dois scripts):

    set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh \
        tests/api/adversario/test_l2_17_grade_ibge_nao_instalada.py -q -rxX
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-17: install.sh nunca chama grades_ibge/instalar.sh (a conferência de sha256 das grades "
        "NTv2 do IBGE), apesar do cabeçalho do script e da hipótese do item afirmarem que o install.sh "
        "faz isso; a seção 'h5' real do instalador é a imagem docker do notebook (L2-16-b), não as grades"
    ),
)
def test_l2_17_install_sh_chama_conferencia_das_grades_ibge():
    texto_install = (ROOT / "install.sh").read_text()
    assert "grades_ibge" in texto_install, (
        "install.sh deveria chamar grades_ibge/instalar.sh (conferência de sha256 das grades NTv2 do "
        "IBGE, exigida pelo portão de L2-17) em alguma seção; hoje não chama"
    )
