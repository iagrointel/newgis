"""Portão do item L2-01-k-desenho-anotacoes, metade da TELA: os módulos de desenho e de anotação
precisam estar LIGADOS à página do mapa, não apenas existir no repositório.

Por que um teste estático e não só o e2e: `tests/e2e/test_mapa_desenho.py` (e os vizinhos
`test_l201k_desenho.py` e `test_ux23_selecao_anotacoes_pacote.py`) só conseguem dizer "a tela não
expõe window.plat.mapa" depois de subir navegador, servidor e banco — e, sem navegador na máquina,
saltam e não dizem nada. Aqui a mesma cláusula é medida em milissegundos, lendo o que a página
importa: `web/mapa.html` -> `web/js/mapa/mapa.js` -> imports, transitivamente.

O par positivo é obrigatório e está junto: a mesma travessia TEM de alcançar `estilo.js`, que a tela
comprovadamente usa. Sem esse par, uma travessia quebrada (regex errada, caminho errado) devolveria
"nada alcançado" e o teste da lacuna passaria por engano.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
PAGINA = WEB / "mapa.html"
# `import ... from './x.js'`, `import './x.js'` e `import(`./x.js`) dinâmico
_IMPORT = re.compile(r"""(?:from|import)\s*\(?\s*['"`]([^'"`]+\.js)['"`]""")
_SCRIPT_MODULO = re.compile(r"""<script[^>]*type=["']module["'][^>]*src=["']([^"']+)["']""")


def _alcancaveis() -> set[Path]:
    """Fecho transitivo dos módulos que a PÁGINA carrega, começando pelos <script type="module">."""
    fila = []
    for src in _SCRIPT_MODULO.findall(PAGINA.read_text(encoding="utf-8")):
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


@pytest.mark.xfail(
    strict=True,
    reason="MEDIDO 18/09 em master: web/js/mapa/desenho.js e web/js/mapa/anotacoes.js existem mas "
           "NINGUÉM os importa — web/mapa.html carrega só web/js/mapa/mapa.js, que não os alcança. "
           "A cláusula do portão 'desenho salvo e reaberto pela tela' e 'anotação aparece para outro "
           "usuário do grupo' não tem por onde ser medida na tela. Estrito de propósito: no dia em que "
           "a página importar os dois, este teste XPASSA, vira falha e a marca sai.",
)
def test_modulos_de_desenho_e_anotacao_estao_ligados_a_pagina_do_mapa(alcancaveis):
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
    # (L2-03-edicao) espera `#edicao-camada` na tela /mapa, e o botão de exportar do mapa (L2-01-l)
    # espera exportar.js — os dois módulos estão na mesma lista de órfãos.
    for item, modulo in (("L2-03-edicao", "edicao.js"), ("L2-01-l-exportacao-do-mapa", "exportar.js")):
        medida(item)(
            f"{modulo.removesuffix('.js')}_ligado_a_pagina_do_mapa", modulo in alcancados,
            "módulo alcançado a partir de web/mapa.html (False = e2e da tela impossível hoje)", cmd)

    assert "desenho.js" in orfaos and "anotacoes.js" in orfaos, orfaos
    assert "edicao.js" in orfaos and "exportar.js" in orfaos, orfaos
