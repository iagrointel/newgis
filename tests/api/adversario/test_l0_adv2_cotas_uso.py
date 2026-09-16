"""Adversário de linha L0 (rodada 2, wt/f2-adv-l02) — achado sobre `L0-07-c-cotas-uso`. Laudo completo em
`laco/handoffs/T9/linha-L0-laudo-adversario-2.md`.

Portão (LITERAL) do item: "... série diária com 30 pontos após simular 30 dias; tela 'Uso' do admin do
inquilino com gráfico e captura; superadmin altera cota e o efeito é imediato". A retaguarda existe de
verdade (job `jobs.uso_medir` grava `plat.uso_inquilino` com bytes de banco e do bucket Garage — ver
`app/jobs/periodicos.py`), mas NENHUMA rota HTTP lê essa série de volta e NENHUM arquivo em `web/` mostra
gráfico algum: a cláusula "tela 'Uso' ... com gráfico e captura" nunca foi cumprida, apesar do item estar
`entregue`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.xfail(
    strict=True,
    reason="L0-07-c: plat.uso_inquilino é escrito pelo periódico jobs.uso_medir mas NUNCA lido de volta — "
    "nenhuma rota do OpenAPI vivo menciona 'uso' e nenhum arquivo em web/ é a tela 'Uso' que o portão exige "
    "(gráfico + captura). Confirmado por leitura: `grep -rn uso_inquilino app/` só aparece na escrita "
    "(app/jobs/periodicos.py, app/cotas.py em comentário), e `find web -iname '*uso*'` não acha nada.",
)
def test_existe_rota_e_tela_de_uso_do_inquilino(conexao_plat_app):
    """Confirma ao vivo, contra a trilha: (a) o OpenAPI comitado não declara nenhuma rota com 'uso' no
    caminho; (b) nenhum arquivo web/ tem nome relacionado a uso/gráfico de cota."""
    import json

    openapi = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    rotas_de_uso = [p for p in openapi["paths"] if "uso" in p.lower()]
    assert rotas_de_uso, "esperava ao menos 1 rota que exponha a série de uso do inquilino (plat.uso_inquilino)"

    achados = subprocess.run(
        ["grep", "-rl", "-i", "uso", str(ROOT / "web")], capture_output=True, text=True
    ).stdout.splitlines()
    # arquivos que claramente seriam a tela: nome contém 'uso' (não apenas menção incidental da palavra)
    tela = [a for a in achados if "uso" in Path(a).name.lower()]
    assert tela, "esperava uma tela dedicada de 'Uso' em web/ (gráfico + captura, como o portão pede)"
