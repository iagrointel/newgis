"""Apoio do e2e da tela /admin/auditoria (item L7-20): capturas com o prefixo do item."""

from pathlib import Path

from tests.e2e.apoio import CAPTURAS, Tela

ITEM = "L7-20-trilha-auditoria"


class TelaAuditoria(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


def gravar_medidas_auditoria(medida, tela: Tela) -> None:
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "playwright chromium contra o uvicorn da trilha (tests/e2e/test_auditoria.py)")
