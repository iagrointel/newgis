"""Conserto do item L0-14-identidade-visual sobre a refutação do adversário G4: "das 19 telas HTML do
produto só 5 carregam os tokens". A varredura cobre TODA tela HTML de `web/` (hoje são mais que as 19 que
G4 mediu — a árvore cresceu depois da refutação), e afirma que `/static/estilo/tokens.css` está presente
e carrega ANTES de qualquer outra folha de estilo da própria tela (ordem importa: tokens define as
variáveis que as outras folhas consomem).

Exceção: as duas páginas de RENDER SERVIDOR (item L2-12) não são tela — são o viewport de um navegador
headless que vira imagem (`render_mapa.html`, `render_layout_mapa.html`); cada uma documenta no próprio
`<style>` "sem chrome nenhum" e usa cor fixa de cartografia, não cromo do produto."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"

# páginas de render headless server-side (item L2-12): sem chrome, não são tela do produto.
NAO_SAO_TELA = {"render_mapa.html", "render_layout_mapa.html"}

LINK_RE = re.compile(r'<link\s+rel="stylesheet"\s+href="([^"]+)">')


def _telas():
    for p in sorted(WEB.rglob("*.html")):
        if "vendor" in p.parts or "sdk" in p.parts or p.name in NAO_SAO_TELA:
            # web/sdk/exemplos/*.html é documentação de código para desenvolvedor externo (CSP própria
            # 'default-src none', sem chrome do produto) — não é tela.
            continue
        yield p


def test_toda_tela_carrega_tokens_css_antes_das_outras_folhas():
    sem_tokens = []
    fora_de_ordem = []
    for p in _telas():
        texto = p.read_text(encoding="utf-8")
        folhas = LINK_RE.findall(texto)
        if "/static/estilo/tokens.css" not in folhas:
            sem_tokens.append(str(p.relative_to(ROOT)))
            continue
        indice_tokens = folhas.index("/static/estilo/tokens.css")
        outras_antes = folhas[:indice_tokens]
        if outras_antes:
            fora_de_ordem.append(f"{p.relative_to(ROOT)}: {outras_antes} antes de tokens.css")
    assert sem_tokens == [], f"{len(sem_tokens)} tela(s) sem /static/estilo/tokens.css:\n" + "\n".join(sem_tokens)
    assert fora_de_ordem == [], "tokens.css carregado depois de outra folha (ordem importa):\n" + "\n".join(
        fora_de_ordem
    )


def test_a_lista_de_telas_nao_e_menor_que_a_medida_por_g4():
    """G4 mediu 19 telas HTML. Se a contagem cair abaixo disso sem ninguém decidir, é sinal de tela
    apagada por engano — não é o que este teste audita, mas vale um alarme barato."""
    total = sum(1 for _ in _telas())
    assert total >= 19, f"só {total} telas encontradas; G4 mediu 19"
