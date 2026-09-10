"""Doctests do SDK contra a instalação de demo (cláusula do portão: "doctest de todos os exemplos
passa contra a instalação de demo"). A variável `pla` (e os nomes de classe usados nos exemplos) é
injetada em todos os módulos; o servidor e o worker são os subprocessos da suíte (conftest)."""

import doctest

import plat
from plat import Plataforma


def test_doctests_do_sdk_contra_a_demo(pla):
    globs = {
        "pla": pla,
        "Plataforma": Plataforma,
        "plat": plat,
        "ErroPlataforma": plat.ErroPlataforma,
        "ErroPermissao": plat.ErroPermissao,
        "NaoEncontrado": plat.NaoEncontrado,
        "Pagina": plat.Pagina,
    }
    testes = 0
    for modulo in (plat, plat.cliente, plat.erros, plat.catalogo, plat.acervo, plat.jobs, plat.ferramentas):
        resultado = doctest.testmod(modulo, extraglobs=globs, verbose=False, optionflags=doctest.ELLIPSIS)
        assert not resultado.failed, f"doctest de {modulo.__name__}: {resultado.failed} falha(s)"
        testes += resultado.attempted
    assert testes >= 10, f"esperava os exemplos de todos os módulos, achei {testes} testes de doctest"
