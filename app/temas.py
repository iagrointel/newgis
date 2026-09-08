"""Temas de marca (item L5-10-temas-marca): um tema é um conjunto de tokens CSS (cores, tipografia, raio,
espaçamento e sombra) em JSON, com modo claro e/ou escuro. Módulo PURO — sem banco e sem FastAPI além do
contrato de erro — para o MESMO validador valer nos três lugares onde um tema entra:

1. tema do inquilino (`plat.tenant.config` -> chave `tema`, gravado por PUT /api/org/tema);
2. tema por documento (`corpo.tema` dos tipos `app`/`painel`, validado em `app/catalogo/documento.py`);
3. os 6 temas padrão da plataforma, definidos aqui e servidos por GET /api/temas (referência de paridade:
   os 6 temas padrão dos StoryMaps e os temas do Web AppBuilder — um tema pronto por clima visual).

Cadeia de resolução na renderização (executor `/executar`, editor de tema `/temas` e depois as páginas
publicadas do L5-14): `documento.corpo.tema` (por `id` ou com `definicao` própria) SOBRE o tema do
inquilino, que SOBRE o padrão `padrao`. Documento sem tema nenhum renderiza com o padrão.

Segurança do formato (refutação do adversário): todo token é validado por FORMATO ESTRICTO antes de virar
CSS custom property — cor só em hexadecimal, fonte só da lista de famílias permitidas (as vendorizadas em
web/vendor/ e as genéricas do CSS), medida só com unidade conhecida, sombra só com campos numéricos. Um
token como `url(javascript:...)` ou `expression(...)` não casa com nenhuma das formas e é recusado com 422
`tema_invalido` nomeando o token — injeção de CSS nunca chega ao navegador.

Contraste (WCAG 2.1, critério 1.4.3 "Contraste mínimo"): `avaliar_contraste` calcula a razão dos 10 pares
de texto de cada modo; par com razão abaixo de 4,5:1 vira aviso (o tema continua aceito — quem decide é a
marca do inquilino — mas o aviso aparece no editor e no GET /api/temas).
"""

from __future__ import annotations

import re

from app.erros import ErroAPI

# ---------------------------------------------------------------- formas aceitas (refutação: validação por formato)

COR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
MEDIDA_RE = re.compile(r"^(?:0|\d+(?:\.\d+)?(?:px|rem|em|%))$")
# famílias vendorizadas (web/vendor/VERSOES.txt) + genéricas do CSS; lista FECHADA de propósito
FAMILIAS = (
    "Big Shoulders Display",
    "IBM Plex Sans",
    "IBM Plex Mono",
    "serif",
    "sans-serif",
    "monospace",
    "system-ui",
)

CHAVES_MODO = ("cores", "tipografia", "raio", "espacamento", "sombra")
CORES = (
    "fundo",
    "superficie",
    "texto",
    "texto_suave",
    "acento",
    "texto_sobre_acento",
    "borda",
    "sucesso",
    "erro",
)
FONTES = ("familia_texto", "familia_titulo", "familia_dado")
MEDIDAS = ("raio", "espacamento")
NIVEIS = ("pequeno", "medio", "grande")
CAMPOS_SOMBRA = ("x", "y", "desfoque", "cor")
LIMITE_SOMBRA = 100  # px; valor de sombra acima disso é erro de digitação, não estética

# pares de TEXTO avaliados pelo critério 1.4.3 (10 pares por modo; razão mínima 4,5:1)
PARES_TEXTO = (
    ("texto", "fundo"),
    ("texto", "superficie"),
    ("texto_suave", "fundo"),
    ("texto_suave", "superficie"),
    ("texto_sobre_acento", "acento"),
    ("erro", "fundo"),
    ("erro", "superficie"),
    ("sucesso", "fundo"),
    ("sucesso", "superficie"),
    ("acento", "fundo"),  # o acento também é cor de link/texto destacado sobre o fundo
)
CONTRASTE_MINIMO = 4.5

# ---------------------------------------------------------------- 6 temas padrão (paridade StoryMaps/Web AppBuilder)

TEMAS_PADRAO: dict[str, dict] = {
    "padrao": {
        "nome": "Padrão (instrumento)",
        "tokens": {
            "claro": {
                "cores": {
                    "fundo": "#f4f5f7", "superficie": "#ffffff", "texto": "#1c2430",
                    "texto_suave": "#4e5d6e", "acento": "#0b5cad", "texto_sobre_acento": "#ffffff",
                    "borda": "#c9d1d9", "sucesso": "#1a6b3c", "erro": "#a12622",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "Big Shoulders Display",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "2px", "medio": "4px", "grande": "8px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "24px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 3, "cor": "#1c243055"},
                    "nivel_2": {"x": 0, "y": 4, "desfoque": 12, "cor": "#1c243066"},
                },
            },
            "escuro": {
                "cores": {
                    "fundo": "#10151c", "superficie": "#1a222d", "texto": "#e8edf3",
                    "texto_suave": "#a9b6c4", "acento": "#58a9ea", "texto_sobre_acento": "#0b1622",
                    "borda": "#33404f", "sucesso": "#58c98a", "erro": "#e77370",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "Big Shoulders Display",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "2px", "medio": "4px", "grande": "8px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "24px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 3, "cor": "#00000088"},
                    "nivel_2": {"x": 0, "y": 4, "desfoque": 12, "cor": "#00000099"},
                },
            },
        },
    },
    "lamina": {
        "nome": "Lâmina (tons de cinza)",
        "tokens": {
            "claro": {
                "cores": {
                    "fundo": "#ececec", "superficie": "#fafafa", "texto": "#191919",
                    "texto_suave": "#4a4a4a", "acento": "#333333", "texto_sobre_acento": "#fafafa",
                    "borda": "#c4c4c4", "sucesso": "#3d3d3d", "erro": "#616161",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "0px", "medio": "0px", "grande": "2px"},
                "espacamento": {"pequeno": "6px", "medio": "14px", "grande": "28px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 2, "cor": "#19191944"},
                    "nivel_2": {"x": 0, "y": 3, "desfoque": 10, "cor": "#19191955"},
                },
            },
            "escuro": {
                "cores": {
                    "fundo": "#141414", "superficie": "#1f1f1f", "texto": "#ededed",
                    "texto_suave": "#b0b0b0", "acento": "#d4d4d4", "texto_sobre_acento": "#141414",
                    "borda": "#3a3a3a", "sucesso": "#c2c2c2", "erro": "#8a8a8a",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "0px", "medio": "0px", "grande": "2px"},
                "espacamento": {"pequeno": "6px", "medio": "14px", "grande": "28px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 2, "cor": "#00000077"},
                    "nivel_2": {"x": 0, "y": 3, "desfoque": 10, "cor": "#00000088"},
                },
            },
        },
    },
    "mare": {
        "nome": "Maré (azuis claros)",
        "tokens": {
            "claro": {
                "cores": {
                    "fundo": "#eef5f9", "superficie": "#ffffff", "texto": "#12303f",
                    "texto_suave": "#3f6274", "acento": "#0d5f86", "texto_sobre_acento": "#ffffff",
                    "borda": "#bcd3de", "sucesso": "#0f6b4f", "erro": "#9c2b2f",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "3px", "medio": "6px", "grande": "12px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "24px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 4, "cor": "#12303f40"},
                    "nivel_2": {"x": 0, "y": 5, "desfoque": 14, "cor": "#12303f59"},
                },
            },
            "escuro": {
                "cores": {
                    "fundo": "#0d1b24", "superficie": "#152734", "texto": "#e3eef4",
                    "texto_suave": "#a3bccb", "acento": "#62b6dd", "texto_sobre_acento": "#0d1b24",
                    "borda": "#2d4759", "sucesso": "#5fc49b", "erro": "#e5797b",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "3px", "medio": "6px", "grande": "12px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "24px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 4, "cor": "#00000080"},
                    "nivel_2": {"x": 0, "y": 5, "desfoque": 14, "cor": "#00000099"},
                },
            },
        },
    },
    "prado": {
        "nome": "Prado (verdes)",
        "tokens": {
            "claro": {
                "cores": {
                    "fundo": "#f1f6ee", "superficie": "#ffffff", "texto": "#1d3120",
                    "texto_suave": "#4c6650", "acento": "#2c6e3f", "texto_sobre_acento": "#ffffff",
                    "borda": "#c6d8c3", "sucesso": "#256a35", "erro": "#9d2f22",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "2px", "medio": "5px", "grande": "10px"},
                "espacamento": {"pequeno": "5px", "medio": "13px", "grande": "26px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 3, "cor": "#1d312040"},
                    "nivel_2": {"x": 0, "y": 4, "desfoque": 12, "cor": "#1d312050"},
                },
            },
            "escuro": {
                "cores": {
                    "fundo": "#111b12", "superficie": "#1a2a1c", "texto": "#e6f0e4",
                    "texto_suave": "#a9c2a8", "acento": "#7cc98a", "texto_sobre_acento": "#111b12",
                    "borda": "#314633", "sucesso": "#79c988", "erro": "#e5796f",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "2px", "medio": "5px", "grande": "10px"},
                "espacamento": {"pequeno": "5px", "medio": "13px", "grande": "26px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 3, "cor": "#00000080"},
                    "nivel_2": {"x": 0, "y": 4, "desfoque": 12, "cor": "#00000099"},
                },
            },
        },
    },
    "terra": {
        "nome": "Terra (tons terrosos)",
        "tokens": {
            "claro": {
                "cores": {
                    "fundo": "#f7f2ea", "superficie": "#fffdf9", "texto": "#33261a",
                    "texto_suave": "#6b5847", "acento": "#8a4b1f", "texto_sobre_acento": "#fffdf9",
                    "borda": "#dbcbba", "sucesso": "#4e6b2a", "erro": "#9e2b25",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "Big Shoulders Display",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "1px", "medio": "3px", "grande": "6px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "22px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 2, "cor": "#33261a3d"},
                    "nivel_2": {"x": 0, "y": 3, "desfoque": 9, "cor": "#33261a52"},
                },
            },
            "escuro": {
                "cores": {
                    "fundo": "#1c140d", "superficie": "#292016", "texto": "#f3eadd",
                    "texto_suave": "#c4b09a", "acento": "#d99a5b", "texto_sobre_acento": "#1c140d",
                    "borda": "#4a3b2a", "sucesso": "#a9c46f", "erro": "#e8837c",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "Big Shoulders Display",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "1px", "medio": "3px", "grande": "6px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "22px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 1, "desfoque": 2, "cor": "#0000007d"},
                    "nivel_2": {"x": 0, "y": 3, "desfoque": 9, "cor": "#0000008f"},
                },
            },
        },
    },
    "alto_contraste": {
        "nome": "Alto contraste (acessibilidade)",
        "tokens": {
            "claro": {
                "cores": {
                    "fundo": "#ffffff", "superficie": "#ffffff", "texto": "#000000",
                    "texto_suave": "#1a1a1a", "acento": "#0000cc", "texto_sobre_acento": "#ffffff",
                    "borda": "#000000", "sucesso": "#005a20", "erro": "#a10000",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "0px", "medio": "0px", "grande": "0px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "24px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 0, "desfoque": 0, "cor": "#00000000"},
                    "nivel_2": {"x": 2, "y": 2, "desfoque": 0, "cor": "#000000ff"},
                },
            },
            "escuro": {
                "cores": {
                    "fundo": "#000000", "superficie": "#000000", "texto": "#ffffff",
                    "texto_suave": "#f0f0f0", "acento": "#ffff00", "texto_sobre_acento": "#000000",
                    "borda": "#ffffff", "sucesso": "#7dffa0", "erro": "#ff9c9c",
                },
                "tipografia": {
                    "familia_texto": "IBM Plex Sans",
                    "familia_titulo": "IBM Plex Sans",
                    "familia_dado": "IBM Plex Mono",
                },
                "raio": {"pequeno": "0px", "medio": "0px", "grande": "0px"},
                "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "24px"},
                "sombra": {
                    "nivel_1": {"x": 0, "y": 0, "desfoque": 0, "cor": "#00000000"},
                    "nivel_2": {"x": 2, "y": 2, "desfoque": 0, "cor": "#ffffffff"},
                },
            },
        },
    },
}

ID_PADRAO = "padrao"          # tema que tudo usa quando não há escolha em cima
ID_INQUILINO = "inquilino"    # pseudo-id de `corpo.tema` = "use o tema do inquilino"

# ---------------------------------------------------------------- validação


def _falha(token: str, motivo: str, esperado: str) -> ErroAPI:
    return ErroAPI(
        422,
        "tema_invalido",
        f"token de tema inválido: {token} ({motivo})",
        [{"token": token, "erro": motivo, "esperado": esperado}],
    )


def validar_modo(modo, prefixo: str = "") -> dict:
    """Valida um modo (claro/escuro) e devolve os tokens normalizados. Recusa chave desconhecida (o tema é
    strict: token digitado errado não pode passar em silêncio) e todo valor fora do formato."""
    if not isinstance(modo, dict):
        raise _falha(prefixo or "modo", "modo precisa ser um objeto",
                     "objeto com cores/tipografia/raio/espacamento/sombra")
    desconhecidas = sorted(set(modo) - set(CHAVES_MODO))
    if desconhecidas:
        raise _falha(f"{prefixo}.{desconhecidas[0]}" if prefixo else desconhecidas[0],
                     f"seção desconhecida: {desconhecidas[0]}", "uma de " + ", ".join(CHAVES_MODO))
    saida: dict = {}

    cores = modo.get("cores")
    if cores is not None:
        if not isinstance(cores, dict):
            raise _falha(f"{prefixo}cores", "cores precisa ser um objeto", "objeto cor -> hexadecimal")
        for k, v in cores.items():
            if k not in CORES:
                raise _falha(f"{prefixo}cores.{k}", f"cor desconhecida: {k}", "uma de " + ", ".join(CORES))
            if not isinstance(v, str) or not COR_RE.match(v):
                raise _falha(f"{prefixo}cores.{k}", "cor fora do formato hexadecimal",
                             "#RGB, #RGBA, #RRGGBB ou #RRGGBBAA")
            saida.setdefault("cores", {})[k] = v.lower()

    tipografia = modo.get("tipografia")
    if tipografia is not None:
        if not isinstance(tipografia, dict):
            raise _falha(f"{prefixo}tipografia", "tipografia precisa ser um objeto", "objeto papel -> família")
        for k, v in tipografia.items():
            if k not in FONTES:
                raise _falha(f"{prefixo}tipografia.{k}", f"papel tipográfico desconhecido: {k}",
                             "uma de " + ", ".join(FONTES))
            if v not in FAMILIAS:
                raise _falha(f"{prefixo}tipografia.{k}", "família de fonte fora da lista permitida",
                             "uma de " + ", ".join(FAMILIAS))
            saida.setdefault("tipografia", {})[k] = v

    for secao in MEDIDAS:
        valores = modo.get(secao)
        if valores is None:
            continue
        if not isinstance(valores, dict):
            raise _falha(f"{prefixo}{secao}", f"{secao} precisa ser um objeto", "objeto nível -> medida CSS")
        for k, v in valores.items():
            if k not in NIVEIS:
                raise _falha(f"{prefixo}{secao}.{k}", f"nível desconhecido: {k}", "uma de " + ", ".join(NIVEIS))
            if not isinstance(v, str) or not MEDIDA_RE.match(v):
                raise _falha(f"{prefixo}{secao}.{k}", "medida fora do formato", "número seguido de px, rem, em ou %")
            saida.setdefault(secao, {})[k] = v

    sombra = modo.get("sombra")
    if sombra is not None:
        if not isinstance(sombra, dict):
            raise _falha(f"{prefixo}sombra", "sombra precisa ser um objeto", "objeto nível -> campos numéricos")
        for k, v in sombra.items():
            if k not in ("nivel_1", "nivel_2"):
                raise _falha(f"{prefixo}sombra.{k}", f"nível de sombra desconhecido: {k}", "nivel_1 ou nivel_2")
            if not isinstance(v, dict) or set(v) != set(CAMPOS_SOMBRA):
                raise _falha(f"{prefixo}sombra.{k}", "sombra precisa ter exatamente x, y, desfoque e cor",
                             "objeto com x, y, desfoque (números) e cor (hexadecimal)")
            for campo in ("x", "y", "desfoque"):
                valor = v[campo]
                if isinstance(valor, bool) or not isinstance(valor, (int, float)) or abs(valor) > LIMITE_SOMBRA:
                    raise _falha(f"{prefixo}sombra.{k}.{campo}", "deslocamento precisa ser número entre -100 e 100",
                             f"número com |valor| <= {LIMITE_SOMBRA}")
            if not isinstance(v["cor"], str) or not COR_RE.match(v["cor"]):
                raise _falha(f"{prefixo}sombra.{k}.cor", "cor da sombra fora do formato hexadecimal",
                             "#RGB, #RGBA, #RRGGBB ou #RRGGBBAA")
            saida.setdefault("sombra", {})[k] = {c: v[c] for c in CAMPOS_SOMBRA}
    return saida


def validar_tema(tema) -> dict:
    """Valida a definição INTEIRA de um tema (sem o envelope nome/modo — a definição em si, como guardada em
    `tenant.config.tema` e em `corpo.tema.definicao`) e devolve o tema normalizado."""
    if not isinstance(tema, dict):
        raise _falha("tema", "tema precisa ser um objeto", "objeto de tokens com modo claro e/ou escuro")
    desconhecidas = sorted(set(tema) - {"claro", "escuro"})
    if desconhecidas:
        raise _falha(desconhecidas[0], f"chave desconhecida: {desconhecidas[0]}", "claro e/ou escuro")
    if "claro" not in tema and "escuro" not in tema:
        raise _falha("modo", "tema sem nenhum modo", "ao menos um de claro/escuro")
    saida = {}
    for modo in ("claro", "escuro"):
        if modo in tema:
            saida[modo] = validar_modo(tema[modo], f"{modo}.")
    return saida


def validar_referencia_de_documento(tema) -> None:
    """Valida `corpo.tema` de um documento (tipos app/painel): ou {"id": ...} apontando para um padrão ou
    para o inquilino, ou {"definicao": ...} com a definição completa. Recusa os dois juntos e id desconhecido."""
    if not isinstance(tema, dict):
        raise _falha("corpo.tema", "tema do documento precisa ser um objeto", '{"id": ...} ou {"definicao": ...}')
    if "id" in tema and "definicao" in tema:
        raise _falha("corpo.tema", "tema com id e definicao juntos", "escolha um dos dois")
    if "id" in tema:
        if not isinstance(tema["id"], str) or not (1 <= len(tema["id"]) <= 60):
            raise _falha("corpo.tema.id", "id de tema precisa ser texto de 1 a 60 caracteres",
                         "id de padrão ou 'inquilino'")
        if tema["id"] != ID_INQUILINO and tema["id"] not in TEMAS_PADRAO:
            raise _falha("corpo.tema.id", f"tema desconhecido: {tema['id']}",
                         "um de " + ", ".join(sorted(TEMAS_PADRAO)) + f", {ID_INQUILINO}")
        return
    if "definicao" in tema:
        validar_tema(tema["definicao"])
        return
    raise _falha("corpo.tema", "tema do documento sem id nem definicao", '{"id": ...} ou {"definicao": ...}')


# ---------------------------------------------------------------- contraste (WCAG 2.1 1.4.3)


def _canal(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminancia(cor: str) -> float:
    """Luminância relativa WCAG a partir de #RGB/#RGBA/#RRGGBB/#RRGGBBAA (alfa é ignorado — o critério 1.4.3
    compara cores opacas; tema com alfa é responsabilidade de quem escolhe)."""
    h = cor.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h[:3])
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _canal(r) + 0.7152 * _canal(g) + 0.0722 * _canal(b)


def contraste(cor1: str, cor2: str) -> float:
    """Razão de contraste (1,0 a 21,0) entre duas cores, maior sobre menor."""
    l1, l2 = sorted((_luminancia(cor1), _luminancia(cor2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def avaliar_modo(modo: dict) -> list[dict]:
    """Os pares de texto de um modo que TÊM as duas cores declaradas, com a razão e o veredito do critério
    1.4.3 (>= 4,5:1). Um tema completo (as 9 cores) é sempre avaliado nos 10 pares — a regra do portão;
    um tema PARCIAL (sobreposição de só alguns tokens, forma legítima de tema) avalia só o que dá para
    calcular: par sem cor é par silenciado, nunca erro — quem sobrepõe um acento não precisa redeclarar o
    fundo para poder gravar o tema."""
    cores = (modo or {}).get("cores") or {}
    saida = []
    for frente, fundo in PARES_TEXTO:
        if frente not in cores or fundo not in cores:
            continue
        razao = round(contraste(cores[frente], cores[fundo]), 2)
        saida.append({"par": f"{frente}/{fundo}", "razao": razao, "minimo": CONTRASTE_MINIMO,
                      "ok": razao >= CONTRASTE_MINIMO})
    return saida


def avaliar_contraste(tema: dict) -> dict[str, list[dict]]:
    """Pares avaliados por modo presente no tema ({'claro': [...], 'escuro': [...]})."""
    return {modo: avaliar_modo(modo_val) for modo, modo_val in (tema or {}).items() if isinstance(modo_val, dict)}


def avisos_do_tema(tema: dict) -> list[dict]:
    """Só os pares abaixo de 4,5:1 — o que o editor e o GET /api/temas mostram como aviso."""
    avisos = []
    for modo, pares in avaliar_contraste(tema).items():
        for p in pares:
            if not p["ok"]:
                avisos.append({"modo": modo, **{k: p[k] for k in ("par", "razao", "minimo")}})
    return avisos


# ---------------------------------------------------------------- resolução da cadeia e CSS


def resolver(tema_do_documento=None, tema_do_inquilino=None) -> tuple[dict | None, str]:
    """Cadeia documento -> inquilino -> padrão. `tema_do_documento` é o `corpo.tema` já validado
    ({"id": ...} ou {"definicao": ...}); devolve (definicao_de_tokens, origem) com origem em
    documento|inquilino|padrao. Nunca devolve None com origem 'padrao' — o padrão sempre existe."""
    if isinstance(tema_do_documento, dict):
        if "definicao" in tema_do_documento:
            return tema_do_documento["definicao"], "documento"
        if tema_do_documento.get("id") == ID_INQUILINO:
            pass  # o documento PEDIU o inquilino: segue a cadeia (e se o inquilino não tem, cai no padrão)
        elif isinstance(tema_do_documento.get("id"), str) and tema_do_documento["id"] in TEMAS_PADRAO:
            return TEMAS_PADRAO[tema_do_documento["id"]]["tokens"], "documento"
    if isinstance(tema_do_inquilino, dict) and tema_do_inquilino:
        return tema_do_inquilino, "inquilino"
    return TEMAS_PADRAO[ID_PADRAO]["tokens"], "padrao"


def css_variaveis(modo: dict) -> dict[str, str]:
    """Tokens de um modo -> CSS custom properties `--t-*` (nomes com hífen, prontos para style.setProperty).
    É o ÚNICO ponto que conhece o nome das variáveis; o front-end nunca inventa nome de token."""
    saida: dict[str, str] = {}
    for k, v in ((modo or {}).get("cores") or {}).items():
        saida[f"--t-{k.replace('_', '-')}"] = v
    for k, v in ((modo or {}).get("tipografia") or {}).items():
        saida[f"--t-{k.replace('_', '-')}"] = v
    for secao in MEDIDAS:
        for k, v in ((modo or {}).get(secao) or {}).items():
            saida[f"--t-{secao}-{k}"] = v
    for k, v in ((modo or {}).get("sombra") or {}).items():
        saida[f"--t-sombra-{k.replace('_', '-')}"] = (
            f"{v['x']}px {v['y']}px {v['desfoque']}px {v['cor']}"
        )
    return saida
