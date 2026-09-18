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
# NOTAÇÃO, não ícone: ′ e ″ são minuto e segundo de arco (coordenada em grau-minuto-segundo), ∞ é o
# infinito de uma faixa aberta e ≠ é "diferente" na mensagem de sha256 que não bate. Nenhum deles é
# rótulo de botão nem emoji: são o símbolo correto do que a linha diz, e trocá-los por palavra piora.
GLIFOS_ADMITIDOS = set("–—…·×“”‘’«»°º²³ªµ→←↔≤≥≈−′″∞≠")
NOME_ICONE = re.compile(r"(?<![\w.])icone\(\s*'([a-z_0-9]+)'")
NOME_ICONE_EM_DADO = re.compile(r"icone:\s*'([a-z_0-9]+)'")


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
    """segunda leitura da mesma medida, por um caminho independente do de test_tokens_cor.py: se as duas
    varreduras discordarem, uma delas está com buraco. Aqui o `var(--x, #reserva)` NÃO é perdoado."""
    achados = []
    for p in _arquivos("css"):
        if p == TOKENS:
            continue
        for n, linha in _linhas_css_fora_de_media(_sem_comentarios_css(p.read_text(encoding="utf-8"))):
            if COR_HEX.search(linha) or COR_FUNCAO.search(linha) or COR_NOME.search(linha):
                achados.append(f"{p.relative_to(ROOT)}:{n}: {linha.strip()[:100]}")
    assert achados == [], "cor escrita à mão fora de web/estilo/tokens.css:\n" + "\n".join(achados)


def test_a_nenhuma_cor_literal_em_js_fora_do_orcamento_declarado():
    """Existe UMA varredura de cor no repositório — `tests/unit/test_tokens_cor.py` — e este teste a chama, em
    vez de manter uma segunda cópia que poderia discordar dela. Regra: CSS em zero absoluto; no JS que não
    resolve `var(--...)` por construção (paint do MapLibre, cena 3D, SVG montado em memória) a cor é
    cartografia ou dado, e cada arquivo tem orçamento CONTADO em `tests/tokens_cor.excecoes` — literal novo
    estoura o orçamento e reprova."""
    from tests.unit import test_tokens_cor as varredura

    _, orcamentos = varredura._carregar_excecoes()
    achados = varredura._achados_css() + varredura._achados_js()
    fora = [f"{rel}:{n}: {linha}" for rel, n, linha in achados if rel not in orcamentos]
    assert fora == [], "cor escrita à mão sem orçamento declarado:\n" + "\n".join(fora)
    assert [f"{rel}:{n}" for rel, n, _l in varredura._achados_css()] == [], "CSS tem de ficar em zero absoluto"


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
    # [a-z_0-9]: há ícone com dígito no nome (modelo3d, foto360); o padrão sem dígito perdia dois e a
    # contagem da família dava 84 onde a página /estilo desenhava 86 (achado ao fechar a cláusula (g)).
    familia = set(re.findall(r"^\s{2}([a-z_0-9]+):\s*\[", icones_js, re.M))
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


# Catraca da migração de folha (cláusula (e)/(g) do portão). O que já é ABSOLUTO: a rota /estilo existe, a
# página é gerada dos tokens, e TODA tela carrega tokens.css antes de qualquer outra folha (provado em
# tests/unit/test_telas_carregam_tokens.py). O que ainda é catraca: 63 das 94 telas seguem na folha antiga
# `web/style.css` em vez de estilo/base.css + estilo/componentes.css. Migrar as 63 é restilar tela por tela
# com captura antes e depois, o que esta máquina não faz (sem navegador — o headless quebra aqui). Enquanto
# isso, o número não pode CRESCER: tela nova nasce na folha nova. Baixe o número no mesmo commit em que
# migrar uma tela; quando chegar a 0, troque a catraca por `assert restantes == []` e apague web/style.css.
TELAS_NA_FOLHA_ANTIGA = 23


COMPONENTES_DA_BASE = ["plat-aviso", "plat-busca", "plat-formulario", "plat-paginacao", "plat-tabela",
                       "plat-dialogo"]
ESTADOS_DO_PORTAO = ["repouso", "foco", "ativo", "desativado", "carregando", "vazio", "erro"]


def test_d_os_seis_componentes_da_base_tem_os_sete_estados():
    """cláusula (d). Medida em três lugares que têm de concordar: a lista que a página viva percorre, o
    desenho de cada estado em estilo/componentes.css, e o foco VISÍVEL, que é o estado que some primeiro
    quando alguém mexe no CSS (`outline: none` sem substituto)."""
    estilo_js = (WEB / "js" / "estilo" / "estilo.js").read_text(encoding="utf-8")
    for nome in COMPONENTES_DA_BASE:
        assert f"'{nome}'" in estilo_js, f"{nome} não está na lista de componentes da página /estilo"
    lista_estados = re.search(r"const ESTADOS = \[([^\]]*)\]", estilo_js)
    assert lista_estados, "a página /estilo não declara a lista de estados"
    declarados = re.findall(r"'([a-z]+)'", lista_estados.group(1))
    assert declarados == ESTADOS_DO_PORTAO, declarados

    componentes_css = (WEB / "estilo" / "componentes.css").read_text(encoding="utf-8")
    for estado in ESTADOS_DO_PORTAO:
        assert estado in componentes_css, f"nenhum desenho para o estado '{estado}' em componentes.css"
    # foco visível: nenhuma regra de :focus pode apagar o anel sem devolver outra marca no lugar. Fora de
    # :focus o `outline: none` é neutro (contêiner de canvas, por exemplo) e não entra.
    SUBSTITUTOS = ("box-shadow", "stroke-width", "border-width", "background", "filter")
    for p in _arquivos("css"):
        texto = _sem_comentarios_css(p.read_text(encoding="utf-8"))
        for seletor, bloco in re.findall(r"([^{}]+)\{([^}]*)\}", texto):
            if ":focus" not in seletor:
                continue
            if re.search(r"outline\s*:\s*(none|0)\b", bloco) and not any(s in bloco for s in SUBSTITUTOS):
                raise AssertionError(
                    f"{p.relative_to(ROOT)}: `{seletor.strip()[:60]}` apaga o foco sem substituto: "
                    f"{bloco.strip()[:80]}"
                )
    # o anel de foco é UM só, declarado uma vez em base.css para todo elemento focalizável — é por isso que
    # nenhum componente precisa repeti-lo, e é por isso que apagá-lo em qualquer folha (acima) reprova.
    base_css = (WEB / "estilo" / "base.css").read_text(encoding="utf-8")
    anel = re.search(r"(?<![\w.#\[-]):focus-visible\s*\{([^}]*)\}", base_css)
    assert anel, "base.css não declara o anel de foco universal"
    assert "--i-foco-largura" in anel.group(1) and "--i-foco" in anel.group(1), anel.group(1)
    # e os estados de espera/erro têm papel anunciado, não só cor
    assert 'aria-busy="true"' in componentes_css, "estado carregando sem aria-busy no desenho"


def test_e_rota_estilo_existe_e_a_pagina_e_gerada_dos_tokens():
    from app import paginas

    assert paginas.PAGINAS.get("/estilo") == "estilo.html"
    assert (WEB / "estilo.html").is_file()
    estilo_html = (WEB / "estilo.html").read_text(encoding="utf-8")
    for folha in ("/static/estilo/tokens.css", "/static/estilo/base.css", "/static/estilo/componentes.css"):
        assert folha in estilo_html, folha
    # a página viva LÊ o arquivo de tokens pela rede e mede a cor calculada: gerada dos tokens, não copiada
    estilo_js = (WEB / "js" / "estilo" / "estilo.js").read_text(encoding="utf-8")
    assert "/static/estilo/tokens.css" in estilo_js and "getComputedStyle" in estilo_js
    # e mostra o que o portão pede: paleta, tipos, grade, forma, ícones, componentes com estados, densidade
    for secao in ("sec-paleta", "sec-tipografia", "sec-espaco", "sec-forma", "sec-icones", "sec-componentes"):
        assert f'id="{secao}"' in estilo_html, secao
    assert "controle-densidade" in estilo_html and "controle-tema" in estilo_html


def test_e_catraca_da_migracao_de_folha_nao_pode_crescer():
    antigas = sorted(
        str(p.relative_to(ROOT)) for p in _arquivos("html") if "/static/style.css" in p.read_text(encoding="utf-8")
    )
    assert len(antigas) <= TELAS_NA_FOLHA_ANTIGA, (
        f"{len(antigas)} telas na folha antiga web/style.css, acima da catraca de {TELAS_NA_FOLHA_ANTIGA}: "
        "tela nova nasce em estilo/base.css + estilo/componentes.css.\n" + "\n".join(antigas)
    )
    if len(antigas) < TELAS_NA_FOLHA_ANTIGA:
        raise AssertionError(
            f"catraca desatualizada: só {len(antigas)} telas na folha antiga, mas TELAS_NA_FOLHA_ANTIGA diz "
            f"{TELAS_NA_FOLHA_ANTIGA}. Baixe o número no mesmo commit da migração."
        )
    # toda TELA, migrada ou não, carrega tokens.css e declara idioma. As duas páginas de render headless
    # (item L2-12) não são tela: são o viewport de um navegador sem interface que vira imagem, documentado
    # em web/estilo/tokens_excecoes.json e em tests/unit/test_telas_carregam_tokens.py.
    NAO_SAO_TELA = {"render_mapa.html", "render_layout_mapa.html"}
    for p in _arquivos("html"):
        texto = p.read_text(encoding="utf-8")
        assert 'lang="pt-BR"' in texto, p.name
        if p.name in NAO_SAO_TELA:
            continue
        assert "/static/estilo/tokens.css" in texto, p.name


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


def test_formulario_de_senha_nunca_cai_para_get():
    """Achado ao fechar a cláusula (g): a tela de entrada da instância de produção mandou a senha na QUERY
    STRING. O ouvinte de submit em js/auth/login.js chama POST /api/login e não navega — mas formulário sem
    `method` usa GET por padrão, e se o módulo não ligar a tempo o navegador envia sozinho: senha na barra de
    endereço, no histórico e no log. Todo formulário com campo de senha declara method="post"."""
    faltam = []
    for p in _arquivos("html"):
        texto = p.read_text(encoding="utf-8")
        for m in re.finditer(r"<form\b[^>]*>(.*?)</form>", texto, re.S | re.I):
            if not re.search(r"""<input\b[^>]*type=["']password["']""", m.group(1), re.I):
                continue
            if not re.search(r"""\bmethod=["']post["']""", m.group(0), re.I):
                faltam.append(f"{p.relative_to(ROOT)}: <form> com campo de senha e sem method=\"post\"")
    assert faltam == [], "\n".join(faltam)
