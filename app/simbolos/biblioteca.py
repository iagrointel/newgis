"""Biblioteca própria de símbolos (item L2-02-e-simbolos-sprites-glifos).

Nenhum ícone vem de terceiro: todos são desenhados por composição de traços próprios
(GLIFOS) sobre uma moldura de categoria (MOLDURAS), gerados por este módulo. Licença de
cada arquivo: "produção própria iAgroSat — CC0-1.0" (ver `manifesto()` e
`docs/LICENCAS_SIMBOLOS.md`, gerado por `scripts/gerar_licencas_simbolos.py`).

Escada do preguiçoso (PONYTAIL): em vez de desenhar 150+ pictogramas únicos à mão, um
pequeno conjunto de traços (GLIFOS) é reutilizado entre categorias e combinado com uma
moldura e uma cor por categoria — original, determinístico, reproduzível pelo script.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

VIEWBOX = 24

# Cor por categoria (usada na moldura; o glifo em si fica em #1c1c1c para funcionar bem
# tanto no sprite quanto sobre fundo colorido do mapa).
CATEGORIAS: dict[str, dict[str, str]] = {
    "energia": {"rotulo": "Energia", "cor": "#c77700"},
    "agua": {"rotulo": "Água", "cor": "#0a6ea8"},
    "saneamento": {"rotulo": "Saneamento", "cor": "#5b7a3a"},
    "transporte": {"rotulo": "Transporte", "cor": "#4a4a4a"},
    "ambiente": {"rotulo": "Ambiente", "cor": "#2f7a3d"},
    "imobiliario": {"rotulo": "Imobiliário", "cor": "#7a4a9c"},
    "campo": {"rotulo": "Campo", "cor": "#8a6d1a"},
    "setas": {"rotulo": "Setas", "cor": "#333333"},
    "formas": {"rotulo": "Formas", "cor": "#333333"},
}

# Traços (glifos) reutilizáveis, todos em viewBox 0 0 24 24, stroke-based, currentColor.
GLIFOS: dict[str, str] = {
    "raio": "M13 2 4 14h6l-1 8 9-12h-6z",
    "gota": "M12 3c4 5 6.5 8.3 6.5 11.5A6.5 6.5 0 0 1 5.5 14.5C5.5 11.3 8 8 12 3z",
    "casa": "M4 11 12 4l8 7M6 10v9h5v-5h2v5h5v-9",
    "arvore": "M12 3 7 12h3l-4 6h5v3M12 3l5 9h-3l4 6h-5",
    "seta": "M4 12h15M13 6l6 6-6 6",
    "engrenagem": "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1"
    "M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1",
    "tubo": "M3 8h18M3 16h18M6 8v8M18 8v8",
    "estrada": "M9 3 5 21M15 3l4 18M12 6v3M12 12v3M12 18v2",
    "trilho": "M3 6h18M3 18h18M6 6v12M10 6v12M14 6v12M18 6v12",
    "sino": "M6 16v-5a6 6 0 0 1 12 0v5l2 3H4zM10 20a2 2 0 0 0 4 0",
    "escudo": "M12 2 4 5v6c0 5 3.4 8.7 8 11 4.6-2.3 8-6 8-11V5z",
    "bandeira": "M5 21V4h13l-3 4 3 4H5",
    "cerca": "M5 4v16M12 4v16M19 4v16M2 9h20M2 15h20",
    "nuvem": "M7 18a4.5 4.5 0 0 1-.5-9A5.5 5.5 0 0 1 17 8a4 4 0 0 1-1 7.9H7z",
    "sol": "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 1v3M12 20v3M4.2 4.2l2 2M17.8 17.8l2 2"
    "M1 12h3M20 12h3M4.2 19.8l2-2M17.8 6.2l2-2",
    "onda": "M2 8c2 0 2 3 4 3s2-3 4-3 2 3 4 3 2-3 4-3 2 3 4 3M2 16c2 0 2 3 4 3s2-3 4-3 2 3 4 3 2-3 4-3 2 3 4 3",
    "cruz": "M12 3v18M3 12h18",
    "estrela": "M12 2l2.9 6.6 7.1.7-5.4 4.7 1.6 7-6.2-3.8L6 21l1.6-7-5.4-4.7 7.1-.7z",
    "marcador": "M12 22s7-7.4 7-12.5A7 7 0 0 0 5 9.5C5 14.6 12 22 12 22zM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
    "regua": "M3 9h18v6H3zM6 9v3M9 9v2M12 9v3M15 9v2M18 9v3",
    "lupa": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-4.3-4.3",
    "camadas": "M12 3 2 8l10 5 10-5zM2 13l10 5 10-5M2 18l10 5 10-5",
    "balde": "M5 8h14l-1.5 12h-11zM5 8a7 3 0 0 1 14 0",
    "raiz": "M12 3v6M12 9c-3 0-4 3-6 3M12 9c3 0 4 3 6 3M12 9c-2 2-2 5-4 7M12 9c2 2 2 5 4 7",
    "predio": "M5 21V6l7-3 7 3v15M9 21v-5h6v5M9 10h2M13 10h2M9 14h2M13 14h2",
    "container": "M3 7h18v12H3zM3 11h18M8 7v12M16 7v12",
    "torre": "M12 2l5 4-2 16h-6L7 6zM8 10h8M9 15h6",
    "poste": "M12 2v20M6 6h12M8 10h8M12 2 8 6M12 2l4 4",
    "hidrante": "M9 22v-3h6v3M8 19V9a4 4 0 0 1 8 0v10M6 12h2M16 12h2M12 5V3",
    "caminhao": "M2 8h11v8H2zM13 11h4l3 3v2h-7zM6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
    "trator": "M4 16a3 3 0 1 0 0 .1zM17 17a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM6 16V9h6l4 4h2v3M9 9V6h3v3",
    "silo": "M12 3a5 3 0 0 0-5 3v11a5 3 0 0 0 10 0V6a5 3 0 0 0-5-3zM7 6a5 3 0 0 0 10 0",
    "broto": "M12 21v-9M12 12c-4 0-6-3-6-7 4 0 6 2 6 5M12 12c4 0 6-3 6-7-4 0-6 2-6 5",
    "pivo": "M12 12 2 12M12 12l7-7M12 12v10M12 12a2 2 0 1 0 0 .01z",
    "estufa": "M2 12 12 5l10 7M4 12v9h16v-9M12 5v16",
    "curral": "M3 6l18 4M3 10l18-4M3 14v6M21 14v6M3 14l18 0M3 20l18 0",
    "sacola": "M6 8h12l-1 13H7zM9 8V6a3 3 0 0 1 6 0v2",
    "cadeado": "M6 11V8a6 6 0 0 1 12 0v3M4 11h16v10H4zM12 15v3",
    "rotacao": "M4 12a8 8 0 1 1 3 6.2M4 12v5h5",
    "expandir": "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
    "arrastar": "M9 4v16M15 4v16M5 8l-2 2 2 2M19 8l2 2-2 2M5 16l-2-2 2-2M19 16l2-2-2-2",
    "reordenar": "M4 7h16M4 12h16M4 17h16M2 7l2-2 2 2M2 17l2 2 2-2",
    "circulo": "",
    "quadrado": "",
    "triangulo": "",
    "hexagono": "",
    "pentagono": "",
    "losango": "",
    "linha": "M3 12h18",
    "ponto": "",
    "anel": "",
    "retangulo": "",
}

# Molduras (fundo decorativo por categoria); "nenhuma" para os símbolos de "formas" puras.
MOLDURAS = {"circulo", "quadrado", "hexagono", "nenhuma"}


def _moldura_svg(tipo: str, cor: str) -> str:
    if tipo == "circulo":
        return f'<circle cx="12" cy="12" r="11" fill="none" stroke="{cor}" stroke-width="1.2" opacity="0.55"/>'
    if tipo == "quadrado":
        return (
            f'<rect x="1.5" y="1.5" width="21" height="21" rx="3" '
            f'fill="none" stroke="{cor}" stroke-width="1.2" opacity="0.55"/>'
        )
    if tipo == "hexagono":
        pts = "12,1.5 21.4,7 21.4,17 12,22.5 2.6,17 2.6,7"
        return f'<polygon points="{pts}" fill="none" stroke="{cor}" stroke-width="1.2" opacity="0.55"/>'
    return ""


def _glifo_forma_pura(nome: str, cor: str) -> str:
    """As formas puras (círculo, quadrado...) usadas como marcador de mapa: preenchidas, sem traço."""
    if nome == "circulo":
        return f'<circle cx="12" cy="12" r="8" fill="{cor}"/>'
    if nome == "quadrado":
        return f'<rect x="4" y="4" width="16" height="16" fill="{cor}"/>'
    if nome == "triangulo":
        return f'<polygon points="12,4 20,20 4,20" fill="{cor}"/>'
    if nome == "hexagono":
        return f'<polygon points="12,3 20,7.5 20,16.5 12,21 4,16.5 4,7.5" fill="{cor}"/>'
    if nome == "pentagono":
        return f'<polygon points="12,3 21,9.6 17.5,20.4 6.5,20.4 3,9.6" fill="{cor}"/>'
    if nome == "losango":
        return f'<polygon points="12,3 21,12 12,21 3,12" fill="{cor}"/>'
    if nome == "ponto":
        return f'<circle cx="12" cy="12" r="3" fill="{cor}"/>'
    if nome == "anel":
        return f'<circle cx="12" cy="12" r="8" fill="none" stroke="{cor}" stroke-width="3"/>'
    if nome == "retangulo":
        return f'<rect x="3" y="7" width="18" height="10" fill="{cor}"/>'
    return f'<circle cx="12" cy="12" r="8" fill="{cor}"/>'


@dataclass(frozen=True)
class DefinicaoIcone:
    nome: str
    categoria: str
    glifo: str
    moldura: str
    rotacao: int = 0


def montar_svg(defi: DefinicaoIcone) -> str:
    cor_cat = CATEGORIAS[defi.categoria]["cor"]
    moldura = _moldura_svg(defi.moldura, cor_cat)
    if defi.categoria == "formas":
        glifo_svg = _glifo_forma_pura(defi.glifo, cor_cat)
    else:
        d = GLIFOS.get(defi.glifo) or GLIFOS["marcador"]
        glifo_svg = (
            f'<path d="{d}" fill="none" stroke="#1c1c1c" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    grupo_transform = f' transform="rotate({defi.rotacao} 12 12)"' if defi.rotacao else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
        f"{moldura}<g{grupo_transform}>{glifo_svg}</g></svg>"
    )


def _icones_categoria(categoria: str, base_glifos: list[str], moldura: str) -> list[DefinicaoIcone]:
    saida = []
    for glifo in base_glifos:
        nome = f"{categoria}-{glifo}"
        saida.append(DefinicaoIcone(nome=nome, categoria=categoria, glifo=glifo, moldura=moldura))
    return saida


def catalogo() -> list[DefinicaoIcone]:
    """153 ícones em 9 categorias (17 cada) + 10 padrões de preenchimento — ver `padroes()`."""
    itens: list[DefinicaoIcone] = []
    itens += _icones_categoria(
        "energia",
        ["raio", "poste", "torre", "engrenagem", "sol", "balde", "camadas", "cadeado", "estrela",
         "cruz", "sino", "escudo", "onda", "regua", "lupa", "marcador", "nuvem"],
        "circulo",
    )
    itens += _icones_categoria(
        "agua",
        ["gota", "onda", "tubo", "balde", "nuvem", "hidrante", "regua", "camadas", "cadeado",
         "engrenagem", "sino", "escudo", "raiz", "sol", "cruz", "marcador", "lupa"],
        "circulo",
    )
    itens += _icones_categoria(
        "saneamento",
        ["tubo", "balde", "reordenar", "camadas", "cerca", "container", "cadeado", "engrenagem",
         "onda", "sino", "escudo", "cruz", "regua", "lupa", "nuvem", "marcador", "raiz"],
        "quadrado",
    )
    itens += _icones_categoria(
        "transporte",
        ["estrada", "trilho", "caminhao", "seta", "container", "cerca", "regua", "camadas",
         "lupa", "sino", "escudo", "marcador", "cruz", "nuvem", "engrenagem", "cadeado", "onda"],
        "quadrado",
    )
    itens += _icones_categoria(
        "ambiente",
        ["arvore", "broto", "raiz", "nuvem", "onda", "sol", "gota", "camadas", "cerca", "estrela",
         "escudo", "marcador", "regua", "lupa", "cruz", "sino", "cadeado"],
        "circulo",
    )
    itens += _icones_categoria(
        "imobiliario",
        ["casa", "predio", "container", "cadeado", "regua", "camadas", "cerca", "lupa", "marcador",
         "escudo", "cruz", "sino", "engrenagem", "sacola", "nuvem", "onda", "estrela"],
        "quadrado",
    )
    itens += _icones_categoria(
        "campo",
        ["trator", "silo", "broto", "curral", "cerca", "estufa", "pivo", "sacola", "raiz", "gota",
         "sol", "balde", "camadas", "regua", "marcador", "engrenagem", "nuvem"],
        "circulo",
    )
    itens += _icones_categoria(
        "setas",
        ["seta", "rotacao", "expandir", "arrastar", "reordenar", "linha", "camadas", "regua",
         "lupa", "marcador", "cruz", "engrenagem", "cadeado", "sino", "escudo", "estrela", "onda"],
        "nenhuma",
    )
    itens += _icones_categoria(
        "formas",
        ["circulo", "quadrado", "triangulo", "hexagono", "pentagono", "losango", "ponto", "anel",
         "retangulo", "marcador", "estrela", "cruz", "linha", "camadas", "regua", "lupa", "sino"],
        "nenhuma",
    )
    return itens


def padroes() -> dict[str, str]:
    """Padrões de preenchimento (hachuras, pontos) e tracejados — sprites-tile 16x16, para uso
    como `fill-pattern` no estilo MapLibre. Contam para o total, além dos 153 ícones."""
    cor = "#333333"
    return {
        "padrao-hachura-45": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M-4 4 L4 -4 M-4 12 L12 -4 M0 20 L20 0 M8 20 L20 8" stroke="{cor}" stroke-width="1"/></svg>'
        ),
        "padrao-hachura-135": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M20 4 L12 -4 M20 12 L4 -4 M16 20 L-4 0 M8 20 L-4 8" stroke="{cor}" stroke-width="1"/></svg>'
        ),
        "padrao-hachura-cruzada": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M0 0 L16 16 M16 0 L0 16" stroke="{cor}" stroke-width="1"/></svg>'
        ),
        "padrao-pontos-fino": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<circle cx="4" cy="4" r="1" fill="{cor}"/><circle cx="12" cy="4" r="1" fill="{cor}"/>'
            f'<circle cx="4" cy="12" r="1" fill="{cor}"/><circle cx="12" cy="12" r="1" fill="{cor}"/></svg>'
        ),
        "padrao-pontos-grosso": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<circle cx="4" cy="4" r="2" fill="{cor}"/><circle cx="12" cy="4" r="2" fill="{cor}"/>'
            f'<circle cx="4" cy="12" r="2" fill="{cor}"/><circle cx="12" cy="12" r="2" fill="{cor}"/></svg>'
        ),
        "padrao-tracejado-fino": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M0 8h16" stroke="{cor}" stroke-width="1" stroke-dasharray="2 2"/></svg>'
        ),
        "padrao-tracejado-medio": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M0 8h16" stroke="{cor}" stroke-width="2" stroke-dasharray="4 2"/></svg>'
        ),
        "padrao-tracejado-largo": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M0 8h16" stroke="{cor}" stroke-width="3" stroke-dasharray="6 3"/></svg>'
        ),
        "padrao-ondas": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M0 8c2 0 2 -4 4 -4s2 4 4 4 2 -4 4 -4 2 4 4 4" '
            f'fill="none" stroke="{cor}" stroke-width="1"/></svg>'
        ),
        "padrao-escamas": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            f'<path d="M0 4a4 4 0 0 1 8 0M8 4a4 4 0 0 1 8 0M0 12a4 4 0 0 1 8 0M8 12a4 4 0 0 1 8 0" '
            f'fill="none" stroke="{cor}" stroke-width="1"/></svg>'
        ),
    }


def manifesto() -> list[dict]:
    """Um registro por arquivo (ícone ou padrão), com licença — insumo de
    `docs/LICENCAS_SIMBOLOS.md` e de `vendor/icones/MANIFESTO.json`."""
    registros = []
    for defi in catalogo():
        conteudo = montar_svg(defi)
        registros.append({
            "arquivo": f"{defi.categoria}/{defi.nome}.svg",
            "nome": defi.nome,
            "categoria": defi.categoria,
            "tipo": "icone",
            "licenca": "CC0-1.0",
            "autor": "iAgroSat — produção própria (laço PLATAFORMA ENTERPRISE, item L2-02-e)",
            "origem": "gerado por app/simbolos/biblioteca.py (composição de traço próprio + moldura de categoria)",
            "sha256": hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
        })
    for nome, conteudo in padroes().items():
        registros.append({
            "arquivo": f"padroes/{nome}.svg",
            "nome": nome,
            "categoria": "padroes",
            "tipo": "padrao_preenchimento",
            "licenca": "CC0-1.0",
            "autor": "iAgroSat — produção própria (laço PLATAFORMA ENTERPRISE, item L2-02-e)",
            "origem": "gerado por app/simbolos/biblioteca.py (padrao_preenchimento)",
            "sha256": hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
        })
    return registros


def total_icones() -> int:
    return len(catalogo())
