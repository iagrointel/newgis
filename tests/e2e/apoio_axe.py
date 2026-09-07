"""Acessibilidade medida no e2e (trilha de interface, UX-01 em diante): injeta o axe-core vendorizado em
tests/e2e/vendor (MPL-2.0, sha256 em VERSOES.txt; nunca vai ao navegador do produto) e devolve as violações.
`violacoes(page)` roda as regras WCAG 2.0/2.1 A e AA; `serias(page)` filtra impacto serious/critical — a cláusula
"axe 0 violações sérias" dos portões UX é `assert serias(page) == []`. A mensagem de falha traz regra, impacto,
descrição e os primeiros alvos, para o conserto ser localizável sem abrir o navegador."""

from pathlib import Path

AXE = Path(__file__).resolve().parent / "vendor" / "axe-core-4.10.3.min.js"
IMPACTOS_SERIOS = {"serious", "critical"}


def injetar(page) -> None:
    if not page.evaluate("() => typeof window.axe !== 'undefined'"):
        page.add_script_tag(path=str(AXE))


def violacoes(page, seletor: str | None = None) -> list[dict]:
    injetar(page)
    alvo = seletor or "document"
    resultado = page.evaluate(
        "async (alvo) => { const r = await axe.run(alvo === 'document' ? document : alvo, "
        "{ runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } }); return r.violations; }",
        alvo,
    )
    return [
        {
            "regra": v["id"], "impacto": v.get("impact"), "descricao": v.get("help"),
            "alvos": [n.get("target") for n in v.get("nodes", [])[:5]],
            "n": len(v.get("nodes", [])),
        }
        for v in resultado
    ]


def serias(page, seletor: str | None = None) -> list[dict]:
    return [v for v in violacoes(page, seletor) if v["impacto"] in IMPACTOS_SERIOS]


def resumo(lista: list[dict]) -> str:
    return "\n".join(f"{v['regra']} [{v['impacto']}] {v['descricao']} — {v['n']} nó(s): {v['alvos']}" for v in lista)
