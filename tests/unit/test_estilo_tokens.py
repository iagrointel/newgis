"""Item L0-14-identidade-visual, cláusulas (a), (b), (c), (e) e (h) que se provam sem navegador:
(a) nenhuma cor nem medida escrita à mão em css/js fora de web/estilo/tokens.css — a varredura que o portão exige;
(b) as três famílias do par tipográfico vendorizadas com sha256 e licença aberta, e referenciadas pelos tokens;
(c) uma família de ícones só: todo icone('nome') usado no produto existe em web/js/base/icones.js, e nenhum
    emoji ou glifo de texto (marcas, setas, bolinhas) fora dela;
(e) toda tela liga as três folhas de web/estilo/ e o tema.js, e a rota /estilo está registrada;
(h) docs/IDENTIDADE.md existe e descreve o traço (a régua), que existe em código.
Exceções declaradas em docs/IDENTIDADE.md seção 2: valor de @media (o CSS não aceita var() em consulta de mídia)
e web/favicon.svg (imagem)."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
TOKENS = WEB / "estilo" / "tokens.css"
VENDOR = WEB / "vendor"

COR_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COR_FUNCAO = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(")
COR_NOME = re.compile(
    r"(?<![\w-])(?:white|black|red|green|blue|yellow|orange|gray|grey|silver|navy|teal|purple|cyan|magenta|"
    r"lime|maroon|olive|aqua|fuchsia|crimson|gold|indigo|violet|pink|brown|beige|tan|salmon|coral|khaki|"
    r"lavender|ivory|linen|snow|azure|tomato|chocolate|whitesmoke|gainsboro|dimgray|dimgrey|darkgray|"
    r"lightgray|lightgrey|darkgrey|slategray|slategrey|steelblue|royalblue|dodgerblue|skyblue|deepskyblue|"
    r"firebrick|darkred|darkgreen|darkblue|seagreen|forestgreen|goldenrod|orangered|hotpink|deeppink|"
    r"turquoise|plum|orchid|wheat|peru|sienna|honeydew|mintcream|aliceblue)(?![\w-])"
)
# propriedades cujo valor tem de ser token (medida): qualquer número com unidade ou número solto é literal
PROPRIEDADES_MEDIDA = ("font-size", "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
                       "margin", "margin-top", "margin-right", "margin-bottom", "margin-left", "gap", "row-gap",
                       "column-gap", "border-radius", "box-shadow", "letter-spacing", "line-height")
MEDIDA_LITERAL = re.compile(r"(?<![\w.-])-?\d*\.?\d+(?:px|rem|em|%|vh|vw|s|ms)?(?![\w.-])")
MEDIDAS_ADMITIDAS = {"0", "1", "100%", "auto", "inherit", "normal", "none", "initial"}

# carácter fora do bloco tipográfico admitido = glifo/emoji fora da família de ícones
GLIFOS_ADMITIDOS = set("–—…·×“”‘’«»°º²³ªµ→←↔≤≥≈−")
NOME_ICONE = re.compile(r"icone\(\s*'([a-z_]+)'")
NOME_ICONE_EM_DADO = re.compile(r"icone:\s*'([a-z_]+)'")


def _medida_e_literal(valor: str) -> bool:
    """0 (com ou sem unidade), 1 (line-height unitária), porcentagem e palavras admitidas passam; o resto é
    medida escrita à mão."""
    if valor in MEDIDAS_ADMITIDAS or valor.endswith("%"):
        return False
    if re.fullmatch(r"-?0+(?:\.0+)?(?:px|rem|em|vh|vw|s|ms)?", valor):
        return False
    return True


def _arquivos(ext: str, raiz: Path = WEB):
    for p in sorted(raiz.rglob(f"*.{ext}")):
        if "vendor" in p.parts or "dados" in p.parts:
            continue
        yield p


def _sem_comentarios_css(texto: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", texto)


def _sem_comentarios_js(texto: str) -> str:
    texto = re.sub(r"/\*[\s\S]*?\*/", "", texto)
    return re.sub(r"(^|[^:\\'\"])//[^\n]*", r"\1", texto)


def _linhas_css_fora_de_media(texto: str):
    """linhas de declaração; a linha de @media (única literal admitida) é pulada, o corpo dela não."""
    for n, linha in enumerate(texto.splitlines(), 1):
        if linha.lstrip().startswith("@media"):
            continue
        yield n, linha


def test_a_nenhuma_cor_literal_em_css_fora_dos_tokens():
    achados = []
    for p in _arquivos("css"):
        if p == TOKENS:
            continue
        for n, linha in _linhas_css_fora_de_media(_sem_comentarios_css(p.read_text(encoding="utf-8"))):
            if COR_HEX.search(linha) or COR_FUNCAO.search(linha) or COR_NOME.search(linha):
                achados.append(f"{p.relative_to(ROOT)}:{n}: {linha.strip()[:100]}")
    assert achados == [], "cor escrita à mão fora de web/estilo/tokens.css:\n" + "\n".join(achados)


def test_a_nenhuma_cor_literal_em_js():
    achados = []
    for p in _arquivos("js"):
        texto = _sem_comentarios_js(p.read_text(encoding="utf-8"))
        for n, linha in enumerate(texto.splitlines(), 1):
            # hex só conta dentro de string ('#abc' / "#abc"), senão âncora de URL (/conta#2fa) reprovaria
            hex_em_string = re.search(r"""['"`]#[0-9a-fA-F]{3,8}['"`]""", linha)
            nome_em_string = re.search(r"""['"](?:white|black|red|green|blue|yellow|orange|gray|grey)['"]""", linha)
            if hex_em_string or COR_FUNCAO.search(linha) or nome_em_string:
                achados.append(f"{p.relative_to(ROOT)}:{n}: {linha.strip()[:100]}")
    assert achados == [], "cor escrita à mão em JS:\n" + "\n".join(achados)


def test_a_nenhuma_medida_literal_nas_propriedades_de_ritmo():
    """font-size, padding, margin, gap, border-radius, box-shadow, letter-spacing e line-height só aceitam
    token (var(--i-*)), 0, auto, inherit ou 100 % fora de tokens.css: é isto que dá o ritmo único às telas."""
    achados = []
    for p in _arquivos("css"):
        if p == TOKENS:
            continue
        for n, linha in _linhas_css_fora_de_media(_sem_comentarios_css(p.read_text(encoding="utf-8"))):
            for decl in linha.split(";"):
                if ":" not in decl:
                    continue
                prop, _, valor = decl.partition(":")
                prop = prop.strip().split("{")[-1].strip()
                if prop not in PROPRIEDADES_MEDIDA:
                    continue
                valor_sem_var = re.sub(r"var\(--[\w-]+\)", "", valor)
                valor_sem_var = re.sub(r"calc\([^()]*\)", "", valor_sem_var)
                sobras = [m.group(0) for m in MEDIDA_LITERAL.finditer(valor_sem_var)]
                sobras = [s for s in sobras if _medida_e_literal(s)]
                if sobras:
                    achados.append(f"{p.relative_to(ROOT)}:{n}: {prop}: {valor.strip()[:80]} -> {sobras}")
    assert achados == [], "medida escrita à mão em propriedade de ritmo:\n" + "\n".join(achados)


def test_a_tokens_tem_os_grupos_do_portao_e_os_dois_temas_declaram_as_mesmas_cores():
    css = _sem_comentarios_css(TOKENS.read_text(encoding="utf-8"))
    nomes = set(re.findall(r"(--i-[a-z0-9-]+)\s*:", css))
    for grupo in ("--i-fundo", "--i-texto", "--i-acento", "--i-fonte-titulo", "--i-fonte-texto", "--i-fonte-dado",
                  "--i-t2", "--i-e4", "--i-raio", "--i-sombra", "--i-densidade", "--i-regua-passo"):
        assert grupo in nomes, grupo
    blocos = dict(re.findall(r"(:root[^{]*)\{([^}]*)\}", css))
    claro = set(re.findall(r"(--i-[a-z0-9-]+)\s*:", blocos[':root[data-theme="light"] ']))
    escuro = set(re.findall(r"(--i-[a-z0-9-]+)\s*:", blocos[':root[data-theme="dark"] ']))
    assert claro == escuro, claro ^ escuro
    assert "--i-texto" in claro and "--i-fundo" in claro
    # nomes de compatibilidade só apontam para tokens, nunca valor
    compat = re.search(r":root \{\s*--fundo:(.*?)\}", css, re.S).group(0)
    assert not COR_HEX.search(compat), "nome de compatibilidade com valor literal"


def test_b_par_tipografico_vendorizado_com_sha256_e_referenciado_pelos_tokens():
    css = TOKENS.read_text(encoding="utf-8")
    fontes = re.findall(r'url\("/static/vendor/([^"]+\.woff2)"\)', css)
    assert len(fontes) >= 3, fontes
    familias = set(re.findall(r'font-family:\s*"([^"]+)"', css))
    assert {"Big Shoulders Display", "IBM Plex Sans", "IBM Plex Mono"} <= familias, familias
    declarados = {}
    for linha in (VENDOR / "VERSOES.txt").read_text(encoding="utf-8").splitlines():
        if linha and not linha.startswith("#"):
            nome, _versao, sha, licenca, _origem = linha.split(maxsplit=4)
            declarados[nome] = (sha, licenca)
    for f in fontes:
        assert f in declarados, f"{f} sem linha em VERSOES.txt"
        sha, licenca = declarados[f]
        assert licenca == "OFL-1.1", (f, licenca)
        assert hashlib.sha256((VENDOR / f).read_bytes()).hexdigest() == sha, f
    # sem CDN de fonte ou de folha em nenhuma tela
    for p in _arquivos("html"):
        texto = p.read_text(encoding="utf-8")
        assert "fonts.googleapis" not in texto and "fonts.gstatic" not in texto and "cdn." not in texto, p
    # motivo escrito
    doc = (ROOT / "docs" / "IDENTIDADE.md").read_text(encoding="utf-8")
    assert "algarismos de largura fixa" in doc and "Big Shoulders" in doc and "IBM Plex" in doc


def test_c_icones_uma_familia_so_e_nenhum_glifo_fora_dela():
    icones_js = (WEB / "js" / "base" / "icones.js").read_text(encoding="utf-8")
    familia = set(re.findall(r"^\s{2}([a-z_]+):\s*\[", icones_js, re.M))
    assert len(familia) >= 60, len(familia)
    usados = set()
    for p in _arquivos("js"):
        texto = p.read_text(encoding="utf-8")
        usados |= set(NOME_ICONE.findall(texto)) | set(NOME_ICONE_EM_DADO.findall(texto))
    faltam = sorted(usados - familia)
    assert faltam == [], f"ícone usado fora da família: {faltam}"
    # glifos: nenhum carácter fora do bloco tipográfico admitido em html/css/js/json
    achados = []
    for ext in ("js", "css", "html", "json"):
        for p in _arquivos(ext):
            for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if p.name == "icones.js" or "PROVENIENCIA" in p.name:
                    continue
                ruins = sorted({c for c in linha if ord(c) > 0x2000 and c not in GLIFOS_ADMITIDOS and ord(c) != 0xFEFF})
                if ruins:
                    achados.append(f"{p.relative_to(ROOT)}:{n}: {''.join(ruins)} em {linha.strip()[:60]}")
    assert achados == [], "glifo ou emoji fora da família de ícones:\n" + "\n".join(achados)


def test_e_toda_tela_liga_as_tres_folhas_e_o_tema_e_a_rota_estilo_existe():
    from app import paginas

    assert paginas.PAGINAS.get("/estilo") == "estilo.html"
    assert (WEB / "estilo.html").is_file()
    for p in _arquivos("html"):
        texto = p.read_text(encoding="utf-8")
        for folha in ("/static/estilo/tokens.css", "/static/estilo/base.css", "/static/estilo/componentes.css"):
            assert folha in texto, (p.name, folha)
        assert '<script src="/static/js/base/tema.js"></script>' in texto, p.name
        assert "/static/style.css" not in texto, p.name
        assert 'lang="pt-BR"' in texto, p.name
    assert not (WEB / "style.css").exists(), "web/style.css ainda existe: a folha antiga tem de morrer"
    # a página viva lê o arquivo de tokens pela rede (gerada dos tokens, não copiada)
    estilo_js = (WEB / "js" / "estilo" / "estilo.js").read_text(encoding="utf-8")
    assert "/static/estilo/tokens.css" in estilo_js and "getComputedStyle" in estilo_js


def test_h_documento_de_identidade_descreve_a_regua_que_existe_em_codigo():
    doc = (ROOT / "docs" / "IDENTIDADE.md").read_text(encoding="utf-8")
    assert "régua" in doc and "procedência" in doc
    regua_js = (WEB / "js" / "base" / "regua.js").read_text(encoding="utf-8")
    assert "data-procedencia" in regua_js and "aria-label" in regua_js
    base = (WEB / "estilo" / "base.css").read_text(encoding="utf-8")
    assert ".regua {" in base and ".regua-tela" in base
    api = (WEB / "js" / "base" / "api.js").read_text(encoding="utf-8")
    assert "registrarChamada" in api
    # os dicionários de i18n têm as chaves novas que os componentes usam
    dic = json.loads((WEB / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    for chave in ("nav.estilo", "tema.claro", "busca.limpar", "dialogo.vazio", "form.vazio", "tabela.tentar_de_novo",
                  "paginacao.carregando"):
        assert chave in dic, chave
