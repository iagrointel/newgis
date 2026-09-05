"""Apoio dos e2e do L0-03-catalogo: Tela com capturas L0-03_<tela>.png e medidas do item, primeira pintura pela
Performance API do navegador, soma dos módulos ES carregados pela tela e chamadas à API pelo mesmo cookie."""

from pathlib import Path

from tests.e2e.apoio import CAPTURAS, Tela

ITEM = "L0-03-catalogo"
ROTAS_CATALOGO = ("/api/itens", "/api/tipos-item", "/api/pastas", "/api/lixeira")


class TelaCatalogo(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"L0-03_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho

    def primeira_pintura_ms(self) -> float | None:
        """first-contentful-paint da navegação corrente (Performance API); None se o navegador não expôs."""
        v = self.page.evaluate(
            "() => { const p = performance.getEntriesByType('paint').find(e => e.name === 'first-contentful-paint');"
            " return p ? Math.round(p.startTime * 10) / 10 : null; }"
        )
        return v

    def soma_modulos_kb(self) -> float:
        """soma (kB decodificados) dos módulos ES de /static/js/ carregados nesta navegação."""
        return self.page.evaluate(
            "() => Math.round(performance.getEntriesByType('resource')"
            ".filter(r => r.name.includes('/static/js/'))"
            ".reduce((s, r) => s + (r.decodedBodySize || r.encodedBodySize || 0), 0) / 1024 * 10) / 10"
        )


def gravar_medidas_catalogo(medida, tela: Tela) -> None:
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        unidade = "kB" if nome.endswith("_kb") else "ms"
        gravar(nome, valor, unidade, "playwright chromium 1280x800 contra a URL interna (tests/e2e/test_conteudo.py)")
