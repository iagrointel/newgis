"""Apoio dos e2e de L6-02-l-saude/L6-05-proveniencia-camada-externa: Tela com capturas L6-02-l_<tela>.png."""

from pathlib import Path

from tests.e2e.apoio import CAPTURAS, Tela

ITEM = "L6-02-l-saude"
ROTAS_CONEXOES = ("/api/conexoes",)


class TelaConexoes(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


def gravar_medidas_conexoes(medida, tela: Tela) -> None:
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "playwright chromium contra a URL interna (tests/e2e/test_conexoes.py)")
