"""Catraca: chamada da tela para rota que a API não publica não pode crescer (achado de 17/09/2026).

O DEFEITO que motivou: `web/js/app/fontes.js` chamava a família `ogc-collections-items`, um caminho que
esta instalação nunca publicou — o serviço OGC de feições mora sob `/ogc/features` e exige a coleção.
Resultado medido em produção: 404 em toda camada vetorial usada como fonte, e a tela abria com zero
feições sem dizer por quê. O defeito só apareceu quando passou a haver navegador para exercitar a tela.

`docs/gerar_cobertura_ui.py` já sabia disso: a seção "URLs chamadas pela tela sem rota correspondente
na API" lista cada chamada morta com arquivo e linha. Mas era RELATÓRIO, não portão — ninguém reprovava,
e por isso as chamadas ficaram. Este teste transforma o relatório em catraca: o número pode cair, nunca
subir. Quem consertar uma, baixa a constante; quem escrever uma nova, reprova aqui.

⛔ Não suba MORTAS_MAXIMO para fazer o teste passar. Se o número subiu, uma tela passou a chamar coisa
que não existe — o conserto é a chamada, não a constante.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RELATORIO = RAIZ / "docs" / "COBERTURA_UI.md"
TITULO = "## URLs chamadas pela tela sem rota correspondente na API"

# 17/09/2026: 38 na medida da manhã; 15 depois da união descer para o tronco e do conserto de fontes.js.
# 18/09/2026: 11 depois que as fusões da noite consertaram 4 chamadas (o tronco ganhou as rotas ou as telas
# deixaram de chamá-las).
MORTAS_MAXIMO = 11


def _mortas() -> list[str]:
    texto = RELATORIO.read_text(encoding="utf-8")
    i = texto.find(TITULO)
    assert i >= 0, f"{RELATORIO.name} sem a seção '{TITULO}'; regenere com docs/gerar_cobertura_ui.py"
    bloco = texto[i:].split("\n## ")[0]
    return [linha for linha in bloco.splitlines() if linha.startswith("- `")]


def test_relatorio_existe_e_tem_a_secao():
    # controle: sem isto, o teste viraria decoração se a seção mudasse de nome.
    assert RELATORIO.is_file()
    _mortas()


def test_chamada_morta_da_tela_nao_pode_crescer():
    mortas = _mortas()
    assert len(mortas) <= MORTAS_MAXIMO, (
        f"{len(mortas)} chamadas da tela para rota inexistente, acima da catraca de {MORTAS_MAXIMO}.\n"
        "Uma tela passou a chamar coisa que a API não publica — conserte a chamada, não a constante.\n"
        + "\n".join(mortas)
    )


def test_a_catraca_nao_esta_frouxa():
    # se o número real cair, a catraca tem de acompanhar, senão ela para de proteger.
    mortas = _mortas()
    assert len(mortas) >= MORTAS_MAXIMO - 3, (
        f"só {len(mortas)} mortas contra catraca de {MORTAS_MAXIMO}: baixe MORTAS_MAXIMO para {len(mortas)} "
        "e registre no commit qual chamada foi consertada."
    )


def test_a_fonte_de_feicoes_do_mapa_nao_chama_rota_inexistente():
    """O caso concreto que motivou a catraca, preso por nome."""
    fontes = (RAIZ / "web" / "js" / "app" / "fontes.js").read_text(encoding="utf-8")
    chamadas = re.findall(r"buscar\(`([^`]+)`", fontes)
    assert chamadas, "fontes.js deixou de ter chamadas reconhecíveis; o teste precisa ser reescrito"
    for c in chamadas:
        assert "/ogc/collections/" not in c, f"fontes.js voltou a chamar rota inexistente: {c}"
