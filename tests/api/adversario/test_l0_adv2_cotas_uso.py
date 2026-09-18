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

ROOT = Path(__file__).resolve().parents[3]


# REMEDIADO (wt/l02, 18/09/2026): plat.uso_inquilino passou a ter caminho de VOLTA. GET /api/uso devolve a
# serie diaria do inquilino da sessao com as cotas em vigor e os contadores vivos ("agora") ao lado, e a tela
# /admin/uso desenha consumo contra cota e a linha do armazenamento por dia (SVG proprio: a CSP nao deixa
# carregar biblioteca de fora). Testes em tests/api/test_uso.py; medidas em tests/medidas/L0-07-c-cotas-uso.json.
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
