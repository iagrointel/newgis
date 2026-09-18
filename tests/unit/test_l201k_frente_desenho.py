"""Portão do item L2-01-k-desenho-anotacoes, metade da TELA: os módulos de desenho e de anotação
precisam estar LIGADOS à página do mapa, não apenas existir no repositório.

Por que um teste estático e não só o e2e: `tests/e2e/test_l201k_desenho.py` só consegue dizer "a tela
não expõe window.plat.mapa" depois de subir navegador, servidor e banco — e, sem navegador na máquina,
salta e não diz nada. Aqui a mesma cláusula é medida em milissegundos, lendo o que a página importa:
`web/mapa.html` -> `web/js/mapa/mapa.js` -> imports, transitivamente.

Histórico: em 18/09 os módulos existiam mas NINGUÉM os importava (a junção do tronco tinha revertido
mapa.js/mapa.html para a versão sem painéis). A ligação foi refeita na mesma data; este teste, que era
xfail estrito medindo a lacuna, passou a valer como guarda contra nova regressão.

O par positivo é obrigatório e está junto: a mesma travessia TEM de alcançar `estilo.js`, que a tela
comprovadamente usa. Sem esse par, uma travessia quebrada (regex errada, caminho errado) devolveria
"nada alcançado" e o teste passaria por engano.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
PAGINA = WEB / "mapa.html"
# a casca nova do mapa (L2-01-a-casca-sig): /mapa continua no ar, mas a tela cheia de trabalho é /sig —
# a "página do mapa" de fato, para os itens cujo e2e precisa de camada ligada e painel (L2-01-l, L2-03)
PAGINA_SIG = WEB / "sig.html"
# `import ... from './x.js'`, `import './x.js'` e `import(`./x.js`) dinâmico
_IMPORT = re.compile(r"""(?:from|import)\s*\(?\s*['"`]([^'"`]+\.js)['"`]""")
_SCRIPT_MODULO = re.compile(r"""<script[^>]*type=["']module["'][^>]*src=["']([^"']+)["']""")


def _alcancaveis(pagina: Path = PAGINA) -> set[Path]:
    """Fecho transitivo dos módulos que a PÁGINA carrega, começando pelos <script type="module">."""
    fila = []
    for src in _SCRIPT_MODULO.findall(pagina.read_text(encoding="utf-8")):
        caminho = WEB / src.removeprefix("/static/").lstrip("/")
        if caminho.exists():
            fila.append(caminho.resolve())
    vistos: set[Path] = set()
    while fila:
        atual = fila.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        for alvo in _IMPORT.findall(atual.read_text(encoding="utf-8")):
            if alvo.startswith(("http://", "https://")):
                continue
            base = WEB if alvo.startswith("/") else atual.parent
            caminho = (base / alvo.removeprefix("/static/").lstrip("/")).resolve()
            if caminho.exists():
                fila.append(caminho)
    return vistos


@pytest.fixture(scope="module")
def alcancaveis() -> set[Path]:
    return _alcancaveis()


def test_a_travessia_enxerga_o_que_a_tela_usa_de_fato(alcancaveis):
    """PAR POSITIVO da lacuna medida abaixo: a página carrega mapa.js, e por ele se chega a estilo.js.
    Se este teste falhar, o que o teste seguinte mede não é a ligação da tela — é a travessia."""
    nomes = {p.name for p in alcancaveis}
    assert "mapa.js" in nomes, sorted(nomes)
    assert "estilo.js" in nomes, sorted(nomes)
    assert len(alcancaveis) > 5, sorted(nomes)


def test_modulos_de_desenho_e_anotacao_estao_ligados_a_pagina_do_mapa(alcancaveis):
    """A cláusula do portão 'desenho salvo e reaberto pela tela' e 'anotação aparece para outro usuário
    do grupo' só tem por onde ser medida na tela se a página importar os dois módulos."""
    nomes = {p.name for p in alcancaveis}
    assert {"desenho.js", "anotacoes.js"} <= nomes, sorted(nomes)


def test_medida_da_ligacao_da_tela_de_desenho(alcancaveis, medida):
    """Grava em tests/medidas/L2-01-k-desenho-anotacoes.json o tamanho da lacuna: quantos módulos a
    página alcança e quais dos módulos do mapa ficam órfãos (existem em web/js/mapa e ninguém importa)."""
    alcancados = {p.name for p in alcancaveis}
    no_disco = {p.name for p in (WEB / "js" / "mapa").glob("*.js")}
    orfaos = sorted(no_disco - alcancados)

    gravar = medida("L2-01-k-desenho-anotacoes")
    cmd = "pytest tests/unit/test_l201k_frente_desenho.py::test_medida_da_ligacao_da_tela_de_desenho"
    gravar("modulos_alcancados_pela_pagina_do_mapa", len(alcancaveis), "arquivos .js", cmd)
    gravar("modulos_de_mapa_orfaos", orfaos, "arquivos em web/js/mapa sem ninguém que os importe", cmd)
    gravar("desenho_e_anotacao_ligados_a_tela", sorted({"desenho.js", "anotacoes.js"} & alcancados) or False,
           "módulos do item alcançados pela página (False = nenhum)", cmd)

    # a MESMA medida vale para os itens vizinhos que dependem da mesma página: o e2e de edição
    # (L2-03-edicao) espera `#edicao-camada` na tela do mapa, e o botão de exportar do mapa (L2-01-l)
    # espera exportar.js. Desde a casca /sig a "tela do mapa" são as DUAS páginas: o módulo conta como
    # ligado se QUALQUER uma das duas o alcança (a /mapa antiga segue no ar até a casca ser aprovada).
    alcancados_tela = alcancados | {p.name for p in _alcancaveis(PAGINA_SIG)}
    for item, modulo in (("L2-03-edicao", "edicao.js"), ("L2-01-l-exportacao-do-mapa", "exportar.js")):
        medida(item)(
            f"{modulo.removesuffix('.js')}_ligado_a_pagina_do_mapa", modulo in alcancados_tela,
            "módulo alcançado a partir da tela do mapa (web/mapa.html ou web/sig.html; "
            "False = e2e da tela impossível hoje)", cmd)

    assert "desenho.js" not in orfaos and "anotacoes.js" not in orfaos, orfaos
    # os itens vizinhos continuam com a lacuna deles medida aqui (não é deste item fechá-la)
    assert "edicao.js" in orfaos and "exportar.js" in orfaos, orfaos
