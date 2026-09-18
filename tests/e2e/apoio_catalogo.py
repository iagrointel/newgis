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

    def _kb_de(self, filtro_js: str) -> float:
        return self.page.evaluate(
            "() => Math.round(performance.getEntriesByType('resource')"
            f".filter(r => r.name.includes('/static/js/') && ({filtro_js}))"
            ".reduce((s, r) => s + (r.decodedBodySize || r.encodedBodySize || 0), 0) / 1024 * 10) / 10"
        )

    def soma_modulos_kb(self) -> float:
        """soma (kB decodificados) dos MÓDULOS ES carregados nesta navegação — código, sem o catálogo de
        tradução.

        18/09/2026 (ADR docs/adr/20260918T0240-orcamento-da-tela-separa-modulo-de-catalogo-de-traducao.md):
        a conta antiga somava tudo sob `/static/js/`, e o catálogo de tradução mora em `web/js/i18n/*.json`.
        Eram 511 kB na tela /conteudo: 314,6 de módulo e 193,9 de UM arquivo de dados que é o mesmo em toda
        tela do produto e cresce a cada item que acrescenta texto. Somados, o número deixava de dizer o que
        o orçamento governa (o código da tela) e reprovava a tela que por acaso fosse medida primeiro.
        As duas partes continuam medidas e as duas reprovam — cada uma contra o seu teto."""
        return self._kb_de("!r.name.includes('/static/js/i18n/')")

    def catalogo_traducao_kb(self) -> float:
        """kB do catálogo de tradução buscado nesta navegação (`/static/js/i18n/<idioma>.json`).

        Orçamento próprio de 220 kB (ADR acima). Passou disso, a saída é partir o catálogo por tela — não
        subir o teto."""
        return self._kb_de("r.name.includes('/static/js/i18n/')")


def gravar_medidas_catalogo(medida, tela: Tela) -> None:
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        unidade = "kB" if nome.endswith("_kb") else "ms"
        gravar(nome, valor, unidade, "playwright chromium 1280x800 contra a URL interna (tests/e2e/test_conteudo.py)")
