"""Relatório do método do motor multicritério em PDF (item L3-01-i-exportacao-metodo).

O PDF é gerado POR SCRIPT (scripts/metodo_exportar.py ou a função deste módulo) no desenho da
casa — retrato A4, tipografia sóbria, uma SEÇÃO por PÁGINA, no molde do relatório do Suitability
Modeler: resumo, diagrama do fluxo do modelo, uma página por fator (histograma bruto), pesos,
resultado final e ressalvas obrigatórias.

Regra de ouro do item: NENHUM número entra no PDF que não esteja no documento JSON
(app.amc.metodo). Por isso os números são impressos na mesma representação normalizada do
documento (4 decimais, vírgula decimal), os gráficos não têm rótulo numérico próprio e não há
numeração de página (o número da página não estaria no JSON). O teste do item extrai todos os
números do PDF e confere um a um contra `metodo.numeros_do_documento`.

Contagens, ids de unidade, descrições do combinador e da política fazem PARTE do documento — o
relatório não imprime nada que o documento não carregue. Tabelas listam no máximo 30 unidades
por página (a página é única por seção); quando há mais, o documento JSON é a referência completa
e o PDF o diz.

O PDF imprime o sha256 do documento; `metodo.confere_pdf` usa isso para recusar um PDF gerado de
outra versão do método (peso alterado = hash diferente = o PDF antigo não é do modelo novo). A
geração é determinística: o mesmo documento gera exatamente o mesmo arquivo (invariant=1 do
reportlab, sem relógio, sem metadado volátil).
"""

from __future__ import annotations

import io
import math

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.amc import metodo

LARGURA, ALTURA = A4
MARGEM = 54.0
LIMITE_LINHAS = 30
COR_TINTA = (0.13, 0.15, 0.18)
COR_LINHA = (0.75, 0.77, 0.80)
COR_BARRA = (0.36, 0.48, 0.58)
COR_CAIXA = (0.93, 0.94, 0.95)
FONTE = "Helvetica"
FONTE_NEG = "Helvetica-Bold"
FONTE_MONO = "Courier"


def _num_txt(v) -> str:
    """O número como o documento o guarda: inteiro sem casa decimal, senão 4 decimais com vírgula."""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, int):
        return str(v)
    f = metodo._num(v)
    if f == int(f):
        return str(int(f))
    return f"{f:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _quebra(texto: str, largura: float, tamanho: float = 9.5) -> list[str]:
    """Quebra um texto em linhas que cabem em `largura` (medida real da fonte, não estimativa)."""
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if atual and stringWidth(tentativa, FONTE, tamanho) > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = tentativa
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _secoes(documento: dict) -> list[tuple[str, callable]]:
    """(título, desenhadora). Cada seção ocupa exatamente UMA página — o portão do item pede
    páginas = seções."""
    secoes = [("resumo", _pag_resumo), ("fluxo do modelo", _pag_fluxo)]
    for f in documento["modelo"]["fatores"]:
        secoes.append((f"fator {f}", lambda c, d, f=f: _pag_fator(c, d, f)))
    secoes.append(("pesos", _pag_pesos))
    if documento.get("resultado"):
        secoes.append(("resultado final", _pag_resultado))
    secoes.append(("ressalvas", _pag_ressalvas))
    return secoes


def paginas_do_relatorio(documento: dict) -> int:
    """Quantas páginas (seções) o relatório do documento tem."""
    return len(_secoes(documento))


def gerar_pdf(documento: dict, caminho=None) -> bytes:
    """Gera o PDF do método canônico. Com `caminho`, grava e também devolve os bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle(f"plat — método {documento['nome']}")
    c.setSubject(f"{metodo.FORMATO} {documento['sha256']}")
    c.setAuthor("plat")
    for titulo, desenhar in _secoes(documento):
        _cabecalho(c, documento, titulo)
        desenhar(c, documento)
        c.showPage()
    c.save()
    dados = buf.getvalue()
    if caminho:
        with open(caminho, "wb") as arq:
            arq.write(dados)
    return dados


# ---------------------------------------------------------------- infra de página

def _cabecalho(c, documento: dict, titulo: str) -> None:
    c.setFillColorRGB(*COR_TINTA)
    c.setFont(FONTE_NEG, 17)
    y = ALTURA - MARGEM
    c.drawString(MARGEM, y, titulo)
    c.setFont(FONTE, 8.5)
    c.setFillColorRGB(0.45, 0.47, 0.50)
    c.drawRightString(LARGURA - MARGEM, y + 3, documento["nome"])
    c.setStrokeColorRGB(*COR_LINHA)
    c.setLineWidth(0.7)
    c.line(MARGEM, y - 8, LARGURA - MARGEM, y - 8)
    _rodape(c, documento)


def _rodape(c, documento: dict) -> None:
    c.setFont(FONTE, 8)
    c.setFillColorRGB(0.45, 0.47, 0.50)
    c.drawString(MARGEM, MARGEM / 2 - 6, f"{metodo.FORMATO} · motor {documento['motor']['versao']}")
    c.drawRightString(LARGURA - MARGEM, MARGEM / 2 - 6, documento["gerado_em"])


def _titulo_bloco(c, x: float, y: float, texto: str) -> float:
    c.setFillColorRGB(*COR_TINTA)
    c.setFont(FONTE_NEG, 11)
    c.drawString(x, y, texto)
    return y - 18


def _paragrafo(c, x: float, y: float, texto: str, largura: float, tamanho: float = 10, passo: float = 14.5) -> float:
    """Parágrafo com quebra simples por palavras; devolve o y depois do texto."""
    c.setFillColorRGB(*COR_TINTA)
    c.setFont(FONTE, tamanho)
    linha = ""
    for palavra in texto.split():
        tentativa = f"{linha} {palavra}".strip()
        if c.stringWidth(tentativa, FONTE, tamanho) > largura:
            c.drawString(x, y, linha)
            y -= passo
            linha = palavra
        else:
            linha = tentativa
    if linha:
        c.drawString(x, y, linha)
        y -= passo
    return y


def _tabela(c, x: float, y: float, colunas: list[float], linhas: list[list[str]], passo: float = 16.0) -> float:
    """Tabela simples sem bordas verticais. Os textos já chegam prontos (números normalizados)."""
    c.setFont(FONTE_NEG, 9.5)
    xa = x
    for larg, tit in zip(colunas, linhas[0], strict=True):
        c.drawString(xa, y, tit)
        xa += larg
    y -= 4
    c.setStrokeColorRGB(*COR_LINHA)
    c.setLineWidth(0.7)
    c.line(x, y, x + sum(colunas), y)
    y -= passo
    c.setFont(FONTE, 9.5)
    for linha in linhas[1:]:
        xa = x
        for larg, cel in zip(colunas, linha, strict=True):
            c.drawString(xa, y, cel)
            xa += larg
        y -= passo
    return y


def _caixa(c, x: float, y: float, larg: float, alt: float, titulo: str, corpo: str = "", tamanho: float = 9.5):
    c.setFillColorRGB(*COR_CAIXA)
    c.setStrokeColorRGB(*COR_LINHA)
    c.roundRect(x, y, larg, alt, 4, stroke=1, fill=1)
    c.setFillColorRGB(*COR_TINTA)
    c.setFont(FONTE_NEG, tamanho)
    c.drawCentredString(x + larg / 2, y + alt / 2 + (5 if corpo else -3), titulo)
    if corpo:
        c.setFont(FONTE, tamanho - 1.5)
        c.drawCentredString(x + larg / 2, y + alt / 2 - 8, corpo)


def _seta(c, x1: float, y1: float, x2: float, y2: float) -> None:
    c.setStrokeColorRGB(0.55, 0.57, 0.60)
    c.setFillColorRGB(0.55, 0.57, 0.60)
    c.setLineWidth(1)
    c.line(x1, y1, x2, y2)
    ang = math.atan2(y2 - y1, x2 - x1)
    tam = 5
    caminho = c.beginPath()
    caminho.moveTo(x2, y2)
    caminho.lineTo(x2 - tam * math.cos(ang - 0.45), y2 - tam * math.sin(ang - 0.45))
    caminho.lineTo(x2 - tam * math.cos(ang + 0.45), y2 - tam * math.sin(ang + 0.45))
    caminho.close()
    c.drawPath(caminho, stroke=0, fill=1)


# ---------------------------------------------------------------- seções

def _pag_resumo(c, d: dict) -> None:
    x = MARGEM
    larg = LARGURA - 2 * MARGEM
    y = ALTURA - MARGEM - 40
    y = _paragrafo(c, x, y, d["nome"], larg, tamanho=13, passo=18) - 2
    itens = [
        ("documento", d["formato"]),
        ("versão do documento", _num_txt(d["versao"])),
        ("gerado em", d["gerado_em"]),
        ("motor", f"versão {d['motor']['versao']}, sha {d['motor']['sha']}"),
        ("unidades de análise", _num_txt(d["entrada"]["unidades"])),
        ("fatores do modelo", _num_txt(d["modelo"]["contagem_de_fatores"])),
        ("camadas de entrada", _num_txt(d["camadas"]["contagem"])),
        ("combinador", f"{d['modelo']['combinador']} — {d['modelo']['descricao_combinador']}"),
        ("dado ausente", f"{d['modelo']['politica_ausente']} — {d['modelo']['descricao_politica']}"),
        ("escala das notas", f"{_num_txt(d['modelo']['escala']['min'])} a {_num_txt(d['modelo']['escala']['max'])}"),
    ]
    linhas = [["o que", "valor"]]
    for rotulo, valor in itens:
        pedacos = _quebra(valor, larg - 150.0 - 8)
        linhas.append([rotulo, pedacos[0]])
        linhas.extend(["", p] for p in pedacos[1:])
    y = _tabela(c, x, y, [150.0, larg - 150.0], linhas) - 10
    y = _paragrafo(c, x, y, d["aviso_pesos"], larg, tamanho=9.5) - 4
    if not d.get("resultado"):
        y = _paragrafo(c, x, y, "o método ainda não foi aplicado a dado nenhum: este relatório não tem "
                                "seção de resultado", larg, tamanho=9.5) - 4
    y -= 6
    y = _titulo_bloco(c, x, y, "sha256 do método") - 4
    c.setFont(FONTE_MONO, 8.5)
    sha = d["sha256"]
    for i in range(0, len(sha), 32):
        c.drawString(x, y, sha[i:i + 32])
        y -= 12


def _pag_fluxo(c, d: dict) -> None:
    fatores = d["modelo"]["fatores"]
    pesos = d["modelo"]["pesos"]
    x0 = MARGEM
    y_topo = ALTURA - MARGEM - 60
    caixa_l, caixa_a = 136.0, 26.0
    passo = min(34.0, (y_topo - 140.0) / max(len(fatores), 1))
    xc, combinador_l = 250.0, 140.0
    fav_x = LARGURA - MARGEM - 136.0
    meio = y_topo - (len(fatores) * passo) / 2
    y = y_topo
    for f in fatores:
        _caixa(c, x0, y - caixa_a, caixa_l, caixa_a, f, f"peso {_num_txt(pesos[f])}")
        _seta(c, x0 + caixa_l, y - caixa_a / 2, xc, min(max(meio, 100.0), max(y - caixa_a / 2, 100.0)))
        y -= passo
    _caixa(c, xc, meio - 24.0, combinador_l, 48.0, d["modelo"]["combinador"], "fatores com dado", 10)
    _seta(c, xc + combinador_l, meio, fav_x, meio)
    _caixa(c, fav_x, meio - 24.0, 136.0, 48.0, "favorabilidade",
           f"{_num_txt(d['modelo']['escala']['min'])} a {_num_txt(d['modelo']['escala']['max'])}", 10)
    if d["modelo"]["vetos"]:
        y = 110.0
        y = _titulo_bloco(c, x0, y, "restrições (veto)") - 6
        for f, v in d["modelo"]["vetos"].items():
            y = _paragrafo(c, x0, y, f"{f}: fração vetada {_num_txt(v)} da unidade",
                           LARGURA - 2 * MARGEM, 9.5)


def _pag_fator(c, d: dict, fator: str) -> None:
    i = d["modelo"]["fatores"].index(fator)
    coluna = [linha[i] for linha in d["entrada"]["matriz"]]
    x = MARGEM
    larg = LARGURA - 2 * MARGEM
    y = ALTURA - MARGEM - 40
    y = _paragrafo(c, x, y, f"peso {_num_txt(d['modelo']['pesos'][fator])} · peso normalizado "
                            f"{_num_txt(d['modelo']['pesos_normalizados'][fator])}", larg, 10.5) - 2
    if fator in d["modelo"]["vetos"]:
        y = _paragrafo(c, x, y, f"restrição: fração vetada {_num_txt(d['modelo']['vetos'][fator])} da unidade",
                       larg, 9.5) - 2
    transformacao = d["transformacoes"]["por_fator"].get(fator)
    if transformacao:
        y = _paragrafo(c, x, y, f"transformação: {transformacao}", larg, 9.5) - 2
    y = _paragrafo(c, x, y, f"cobertura do fator na entrada: {_num_txt(d['entrada']['cobertura_por_fator'][fator])} "
                            f"das unidades com dado", larg, 9.5) - 6
    # histograma bruto: barras sem rótulo numérico próprio — os valores estão na tabela abaixo e no JSON
    alt_graf = 120.0
    y_base = y - alt_graf
    c.setStrokeColorRGB(*COR_LINHA)
    c.line(x, y_base, x + larg, y_base)
    n = max(len(coluna), 1)
    passo_barra = larg / n
    larg_barra = max(passo_barra * 0.62, 1.5)
    c.setFillColorRGB(*COR_BARRA)
    for j, v in enumerate(coluna):
        if v is None:
            continue
        h = max(float(v) / 100.0 * alt_graf, 1.0)
        c.rect(x + j * passo_barra + (passo_barra - larg_barra) / 2, y_base, larg_barra, h, stroke=0, fill=1)
    y = y_base - 20
    y = _titulo_bloco(c, x, y, "valores brutos por unidade de análise") - 4
    linhas = [["unidade", "valor bruto"]]
    for j, v in enumerate(coluna[:LIMITE_LINHAS]):
        linhas.append([_num_txt(d["entrada"]["ids_unidades"][j]), "—" if v is None else _num_txt(v)])
    y = _tabela(c, x, y, [140.0, 140.0], linhas)
    if len(coluna) > LIMITE_LINHAS:
        _paragrafo(c, x, y, "a tabela lista as primeiras unidades; o documento JSON traz todas",
                   larg, 8.5)


def _pag_pesos(c, d: dict) -> None:
    x = MARGEM
    larg = LARGURA - 2 * MARGEM
    y = ALTURA - MARGEM - 40
    linhas = [["fator", "peso", "peso normalizado"]]
    for f in d["modelo"]["fatores"]:
        linhas.append([f, _num_txt(d["modelo"]["pesos"][f]), _num_txt(d["modelo"]["pesos_normalizados"][f])])
    y = _tabela(c, x, y, [larg - 220.0, 110.0, 110.0], linhas) - 12
    _paragrafo(c, x, y, d["aviso_pesos"], larg, 9.5)


def _pag_resultado(c, d: dict) -> None:
    x = MARGEM
    larg = LARGURA - 2 * MARGEM
    y = ALTURA - MARGEM - 40
    y = _paragrafo(c, x, y, "nota final por unidade de análise: favorabilidade combinada e cobertura "
                            "ponderada dos fatores com dado", larg, 9.5) - 8
    linhas = [["unidade", "favorabilidade", "cobertura", "vetada", "motivo"]]
    res = d["resultado"]
    for j, fav, cob, vet in list(zip(res["ids_unidades"], res["fav"], res["cobertura"],
                                     res["vetado"], strict=True))[:LIMITE_LINHAS]:
        linhas.append([_num_txt(j), "—" if fav is None else _num_txt(fav), _num_txt(cob),
                       "sim" if vet else "não", "restrição" if vet else ""])
    y = _tabela(c, x, y, [70.0, 120.0, 100.0, 60.0, larg - 350.0], linhas)
    if len(res["fav"]) > LIMITE_LINHAS:
        _paragrafo(c, x, y, "a tabela lista as primeiras unidades; o documento JSON traz todas", larg, 8.5)


def _pag_ressalvas(c, d: dict) -> None:
    x = MARGEM
    larg = LARGURA - 2 * MARGEM
    y = ALTURA - MARGEM - 40
    for texto in d["ressalvas"]:
        y = _paragrafo(c, x, y, "· " + texto, larg, 10.5) - 6
    extras = [
        "regiões: não calculadas neste método; o recorte de regiões depende de geometria de análise "
        "que o documento do método não carrega",
        "o mapa final e a curva de transformação por fator dependem das camadas geográficas e das "
        "transformações do modelo; neste relatório o fator aparece como histograma bruto e a nota "
        "final como tabela",
        "um relatório só vale para o documento com o sha256 impresso na página de resumo; método "
        "alterado tem outro hash e outro relatório",
    ]
    for texto in extras:
        y = _paragrafo(c, x, y, "· " + texto, larg, 10.5) - 6
