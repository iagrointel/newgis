"""Apoio do e2e de L0-04-a-upload-arquivo: Tela com capturas L0-04-a-upload-arquivo_<tela>.png."""

from pathlib import Path

from tests.e2e.apoio import CAPTURAS, Tela

ITEM = "L0-04-a-upload-arquivo"
ROTAS_UPLOADS = ("/api/uploads", "/api/uploads/{id}", "/api/uploads/{id}/partes/{n}", "/api/uploads/{id}/concluir")


class TelaUploads(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


def gravar_medidas_uploads(medida, tela: Tela) -> None:
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "playwright chromium contra a URL interna (tests/e2e/test_uploads.py)")
