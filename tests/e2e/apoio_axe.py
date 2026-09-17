"""Acessibilidade medida no e2e (trilha de interface, UX-01 em diante): injeta o axe-core vendorizado em
tests/e2e/vendor (MPL-2.0, sha256 em VERSOES.txt; nunca vai ao navegador do produto) e devolve as violações.
`violacoes(page)` roda as regras WCAG 2.0/2.1 A e AA; `serias(page)` filtra impacto serious/critical — a cláusula
"axe 0 violações sérias" dos portões UX é `assert serias(page) == []`. A mensagem de falha traz regra, impacto,
descrição e os primeiros alvos, para o conserto ser localizável sem abrir o navegador."""

from pathlib import Path

# uma cópia só, a declarada com sha256 e licença em tests/e2e/vendor/VERSOES.txt (regra da casa: nada
# vendorizado sem procedência). A segunda cópia (4.10.3, sem linha no VERSOES) foi apagada no L0-14.
AXE = Path(__file__).resolve().parent / "vendor" / "axe-4.12.1.min.js"
IMPACTOS_SERIOS = {"serious", "critical"}


# O produto serve uma CSP estrita (`script-src 'self' 'nonce-...'`), e é assim que tem de ser: `add_script_tag`
# com `path=`/`content=` vira script INLINE e o navegador o recusa ("Executing inline script violates ...").
# Então o axe entra pela porta que a CSP admite: uma URL do MESMO domínio, atendida pelo playwright por
# interceptação de rota. Nada é escrito em web/ e o produto não ganha rota nova — o arquivo só existe dentro
# do navegador do teste. Medido no item L0-14 contra a instância local do ramo.
CAMINHO_FALSO = "/__axe_do_teste.js"


def injetar(page) -> None:
    if page.evaluate("() => typeof window.axe !== 'undefined'"):
        return
    fonte = AXE.read_text(encoding="utf-8")
    if not getattr(page, "_plat_rota_axe", False):
        page.route(
            f"**{CAMINHO_FALSO}",
            lambda rota: rota.fulfill(status=200, content_type="application/javascript; charset=utf-8", body=fonte),
        )
        page._plat_rota_axe = True
    page.add_script_tag(url=CAMINHO_FALSO)
    assert page.evaluate("() => typeof window.axe !== 'undefined'"), "axe-core não carregou sob a CSP do produto"


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
