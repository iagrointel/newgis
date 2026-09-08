"""Compositor de layout (item L2-12-b-layouts-elementos-exportacao): documento de layout + definição de mapa →
página em PDF (texto selecionável, mapa como raster no DPI pedido), PNG, JPG ou SVG.

Como funciona, em ordem:
1. cada elemento do documento vira PRIMITIVAS em milímetros (retângulo, imagem, texto, linha, polígono,
   círculo) — uma lista só, sem HTML no meio; é o que o SVG e o HTML consomem;
2. o quadro de mapa é resolvido por `app.layout.geometria` (escala ↔ zoom ↔ pixels) e desenhado pela função
   `fontes.render_quadro` (o motor de render do L2-12-a, injetado — este módulo não conhece navegador);
3. o HTML (texto como <div>, formas em um único <svg> de página, imagens <img>) vai ao WeasyPrint com
   `@page { size: W H }` exato → PDF vetorial; PNG/JPG saem do PDF pelo PyMuPDF no DPI pedido; SVG sai
   direto das primitivas (texto como <text>, mapa raster embutido).
4. o RELATÓRIO diz o que foi desenhado, o que foi aproximado (resolução efetiva do quadro quando o pixel
   pedido passa do teto, legenda truncada) e o que ficou de fora (rotação com grade, expressão de feição).

Tudo o que é número (escala, barra, grade) vem de `geometria.py`; o adversário refuta com régua sobre o PDF.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app import limites
from app.layout import geometria as geo
from app.layout.geometria import Quadro

WEB = Path(__file__).resolve().parents[2] / "web"
FONTE_SANS = WEB / "vendor" / "ibm-plex-sans-3.201.woff2"
FONTE_MONO = WEB / "vendor" / "ibm-plex-mono-regular-2.3.woff2"
COR_TEXTO = "#111416"
COR_FRACA = "#5a6461"
COR_LINHA = "#333a3c"
COR_GRADE = "#2f6fb0"
ATRIBUICAO_BASE = {"osm-guarulhos": "© colaboradores do OpenStreetMap — ODbL 1.0"}
ALTURA_LINHA_LEGENDA_MM = 5.0
PT_MM = 25.4 / 72.0


class ErroComposicao(RuntimeError):
    pass


@dataclass
class Fontes:
    """Tudo o que o compositor pede a quem o chama (banco, motor de render, objetos). Funções puras de fora."""

    ficha_camada: Callable[[str], dict | None]
    render_quadro: Callable[[Quadro, dict, dict], bytes]  # (quadro, mapa, elemento) -> PNG
    logo_png: Callable[[], bytes | None] = lambda: None
    imagem_por_sha: Callable[[str, str], tuple[bytes, str] | None] = lambda sha, classe: None
    linhas_tabela: Callable[[dict], tuple[list[str], list[list[Any]]]] = lambda el: ([], [])
    inquilino_nome: str = ""
    autor: str = ""


@dataclass
class Composicao:
    dados: bytes
    content_type: str
    nome_arquivo: str
    relatorio: dict
    primitivas: list[dict] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------- utilitários de primitivas
def _ret(x, y, w, h, preenchimento=None, borda=None, espessura=0.25, clip=None):
    return {
        "t": "ret",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "preenchimento": preenchimento,
        "borda": borda,
        "espessura": espessura,
        "clip": clip,
    }


def _txt(
    x,
    y,
    w,
    h,
    texto,
    pt=10.0,
    alinhamento="esquerda",
    negrito=False,
    cor=COR_TEXTO,
    familia="sans",
    vertical="topo",
    id_=None,
):
    return {
        "t": "txt",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "texto": texto,
        "pt": pt,
        "alinhamento": alinhamento,
        "negrito": negrito,
        "cor": cor,
        "familia": familia,
        "vertical": vertical,
        "id": id_,
    }


def _linha(pontos, cor=COR_LINHA, espessura=0.3, clip=None, tracejado=None):
    return {"t": "linha", "pontos": pontos, "cor": cor, "espessura": espessura, "clip": clip, "tracejado": tracejado}


def _poli(pontos, preenchimento=None, borda=None, espessura=0.3):
    return {"t": "poli", "pontos": pontos, "preenchimento": preenchimento, "borda": borda, "espessura": espessura}


def _circ(cx, cy, r, preenchimento=None, borda=None, espessura=0.3):
    return {
        "t": "circ",
        "cx": cx,
        "cy": cy,
        "r": r,
        "preenchimento": preenchimento,
        "borda": borda,
        "espessura": espessura,
    }


def _img(x, y, w, h, dados, mime="image/png", id_=None):
    return {"t": "img", "x": x, "y": y, "w": w, "h": h, "dados": dados, "mime": mime, "id": id_}


def formatar_escala(escala: float) -> str:
    n = int(round(escala))
    return "1:" + f"{n:,}".replace(",", ".")


# ---------------------------------------------------------------- composição
class Compositor:
    def __init__(self, layout: dict, mapa: dict, fontes: Fontes, dpi: int):
        self.layout = layout
        self.mapa = mapa or {}
        self.fontes = fontes
        self.dpi = int(dpi)
        self.largura, self.altura = geo.dimensoes_papel(layout["papel"], layout["orientacao"])
        self.prim: list[dict] = []
        self.quadros: dict[str, tuple[dict, Quadro, float]] = {}  # id -> (elemento, quadro, dpi_efetivo)
        self.relatorio: dict = {
            "elementos": [],
            "avisos": [],
            "escala": {},
            "resolucao_efetiva_dpi": self.dpi,
            "legenda": {"itens": 0, "truncados": 0},
            "papel": layout["papel"],
            "orientacao": layout["orientacao"],
            "dpi": self.dpi,
        }
        self._fichas: dict[str, dict | None] = {}

    # ---- fichas das camadas do mapa
    def _camadas_do_mapa(self) -> list[dict]:
        saida = []
        for c in self.mapa.get("camadas") or []:
            cid = c.get("camada_id") or c.get("id")
            if not cid:
                continue
            saida.append(
                {
                    "camada_id": str(cid),
                    "visivel": c.get("visivel", True) is not False,
                    "opacidade": float(c.get("opacidade", 1.0)),
                }
            )
        return saida

    def _ficha(self, camada_id: str) -> dict | None:
        if camada_id not in self._fichas:
            self._fichas[camada_id] = self.fontes.ficha_camada(camada_id)
        return self._fichas[camada_id]

    def _registrar(self, el: dict, estado: str, nota: str = "") -> None:
        self.relatorio["elementos"].append({"id": el.get("id"), "tipo": el.get("tipo"), "estado": estado, "nota": nota})

    # ---- expressões de texto
    def _expressoes(self) -> dict[str, str]:
        agora = dt.date.today()
        meses = [
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        principal = self._quadro_principal()
        escala = formatar_escala(principal[1].escala) if principal else "—"
        return {
            "data": agora.strftime("%d/%m/%Y"),
            "data_longa": f"{agora.day} de {meses[agora.month - 1]} de {agora.year}",
            "escala": escala,
            "autor": self.fontes.autor or "",
            "titulo_mapa": str(self.mapa.get("titulo") or self.layout.get("nome") or "Mapa"),
            "inquilino": self.fontes.inquilino_nome or "",
            "pagina": "1/1",
        }

    def _expandir(self, texto: str, el: dict) -> str:
        valores = self._expressoes()

        def troca(m):
            chave = m.group(1)
            if chave in valores:
                return valores[chave]
            if chave.startswith("campo:"):
                self.relatorio["avisos"].append(
                    f"{el.get('id')}: expressão de feição {{{chave}}} fica para o L5-29 (mantida literal)"
                )
            return m.group(0)

        import re

        return re.sub(r"\{([a-z_:]+)\}", troca, texto)

    def _quadro_principal(self):
        for el, q, dpi in self.quadros.values():
            if el.get("papel_do_quadro", "principal") == "principal":
                return el, q, dpi
        return next(iter(self.quadros.values()), None)

    # ---- elementos
    def compor(self) -> list[dict]:
        elementos = list(self.layout["elementos"])
        # quadros primeiro: escala, grade e norte dependem deles
        for el in elementos:
            if el["tipo"] == "mapa":
                self._mapa(el)
        tem_atribuicao = any(e["tipo"] == "atribuicao" for e in elementos)
        for el in elementos:
            tipo = el["tipo"]
            if tipo == "mapa":
                continue
            getattr(self, f"_{tipo}")(el)
        if self.quadros and not tem_atribuicao:
            # atribuição do mapa-base é obrigatória: quando o layout não a tem, entra no rodapé do maior quadro
            el, q, _ = max(self.quadros.values(), key=lambda t: t[0]["w"] * t[0]["h"])
            auto = {
                "tipo": "atribuicao",
                "id": "atribuicao-automatica",
                "x": el["x"],
                "y": el["y"] + el["h"] - 4,
                "w": el["w"],
                "h": 4,
                "_fundo": True,
            }
            self._atribuicao(auto)
            self.relatorio["avisos"].append(
                "atribuição do mapa-base acrescentada automaticamente (o layout não a tinha)"
            )
        return self.prim

    def _mapa(self, el: dict) -> None:
        w_px, h_px = geo.mm_para_px(el["w"], self.dpi), geo.mm_para_px(el["h"], self.dpi)
        teto = limites.LAYOUT_QUADRO_PIXELS_MAX
        dpi_ef = self.dpi
        if max(w_px, h_px) > teto:
            fator = teto / max(w_px, h_px)
            w_px, h_px = max(1, int(w_px * fator)), max(1, int(h_px * fator))
            dpi_ef = self.dpi * fator
            self.relatorio["resolucao_efetiva_dpi"] = min(self.relatorio["resolucao_efetiva_dpi"], round(dpi_ef, 1))
        # o zoom é calculado com o DPI EFETIVO: o quadro cobre o mesmo terreno com menos pixels (a escala no
        # papel não muda; a nitidez sim, e isso vai no relatório)
        if el["modo"] == "escala":
            quadro = geo.quadro_por_escala(
                tuple(el["centro"]), float(el["escala"]), w_px, h_px, int(round(dpi_ef)) or 1
            )
            # o arredondamento do DPI efetivo entra na conta do zoom: refazemos com o valor exato
            quadro = Quadro(
                quadro.centro, geo.zoom_da_escala(float(el["escala"]), dpi_ef, el["centro"][1]), w_px, h_px, self.dpi
            )
        else:
            ext = el.get("extensao") or self.mapa.get("extensao")
            if not ext and self.mapa.get("centro") and self.mapa.get("zoom") is not None:
                # vista do mapa (centro + zoom do visualizador): vira extensão pela mesma matemática do quadro
                visto = Quadro(tuple(self.mapa["centro"]), float(self.mapa["zoom"]), w_px, h_px, self.dpi)
                ext = list(visto.extensao())
            if not ext:
                ext = [-46.70, -23.55, -46.40, -23.35]
                self.relatorio["avisos"].append(
                    f"{el['id']}: sem extensão no layout nem no mapa; usada a extensão padrão"
                )
            quadro = geo.quadro_por_extensao(tuple(ext), w_px, h_px, self.dpi)
        escala_real = geo.metros_por_pixel_web_mercator(quadro.centro[1], quadro.zoom) / (el["w"] / 1000.0 / w_px)
        try:
            png = self.fontes.render_quadro(quadro, self.mapa, el)
        except Exception as e:  # noqa: BLE001 — o relatório nomeia; a página sai com o quadro vazio e a moldura
            png = None
            self.relatorio["avisos"].append(f"{el['id']}: o quadro não foi desenhado ({e})")
            self._registrar(el, "fora", f"render falhou: {e}")
        if png:
            self.prim.append(_img(el["x"], el["y"], el["w"], el["h"], png, "image/png", id_=el["id"]))
            estado = "ok" if dpi_ef == self.dpi else "aproximado"
            nota = "" if estado == "ok" else f"pixel acima do teto {teto}: quadro desenhado a {dpi_ef:.0f} DPI efetivos"
            self._registrar(el, estado, nota)
        else:
            self.prim.append(_ret(el["x"], el["y"], el["w"], el["h"], preenchimento="#eef1f0"))
        if el.get("moldura", True):
            self.prim.append(_ret(el["x"], el["y"], el["w"], el["h"], borda=COR_LINHA, espessura=0.4))
        self.quadros[el["id"]] = (el, quadro, dpi_ef)
        self.relatorio["escala"][el["id"]] = {
            "escala": round(escala_real, 3),
            "zoom": round(quadro.zoom, 5),
            "centro": list(quadro.centro),
            "extensao": list(quadro.extensao()),
            "largura_px": w_px,
            "altura_px": h_px,
            "rotacao": el.get("rotacao", 0.0),
        }
        if el.get("rotacao"):
            self.relatorio["avisos"].append(
                f"{el['id']}: rotação {el['rotacao']}° aplicada ao desenho; "
                "grade e escala impressa valem para rotação 0 (declarado)"
            )

    def _quadro_para(self, el: dict):
        alvo = el.get("quadro")
        if alvo and alvo in self.quadros:
            return self.quadros[alvo]
        return self._quadro_principal()

    def _legenda(self, el: dict) -> None:
        itens: list[dict] = []
        escolhidas = set(el.get("camadas") or [])
        for c in self._camadas_do_mapa():
            if el.get("so_visivel", True) and not c["visivel"]:
                continue
            if escolhidas and c["camada_id"] not in escolhidas:
                continue
            ficha = self._ficha(c["camada_id"])
            if not ficha:
                continue
            entradas = ficha.get("legenda") or []
            for i, e in enumerate(entradas):
                rotulo = e.get("rotulo") or ""
                if len(entradas) == 1 and not rotulo:
                    rotulo = ficha.get("titulo") or ""
                elif len(entradas) > 1 and i == 0:
                    itens.append({"cabecalho": ficha.get("titulo") or c["camada_id"]})
                itens.append(
                    {
                        "rotulo": rotulo or ficha.get("titulo") or "",
                        "cor": e.get("cor") or "#888888",
                        "forma": e.get("forma") or "poligono",
                        "opacidade": c["opacidade"],
                    }
                )
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        colunas = int(el.get("colunas") or 1)
        topo = y
        if el.get("titulo"):
            self.prim.append(_txt(x, y, w, 6, el["titulo"], pt=10, negrito=True))
            topo = y + 7
        linhas_por_coluna = max(1, int((y + h - topo) // ALTURA_LINHA_LEGENDA_MM))
        capacidade = linhas_por_coluna * colunas
        truncados = 0
        if len(itens) > capacidade:
            truncados = len(itens) - (capacidade - 1)
            itens = itens[: capacidade - 1] + [{"rotulo": f"+{truncados} itens não cabem nesta legenda", "aviso": True}]
        larg_col = w / colunas
        for i, it in enumerate(itens):
            col, lin = divmod(i, linhas_por_coluna)
            cx = x + col * larg_col
            cy = topo + lin * ALTURA_LINHA_LEGENDA_MM
            if "cabecalho" in it:
                self.prim.append(
                    _txt(
                        cx,
                        cy,
                        larg_col,
                        ALTURA_LINHA_LEGENDA_MM,
                        it["cabecalho"],
                        pt=7.5,
                        negrito=True,
                        vertical="meio",
                    )
                )
                continue
            if it.get("aviso"):
                self.prim.append(
                    _txt(cx, cy, larg_col, ALTURA_LINHA_LEGENDA_MM, it["rotulo"], pt=7, cor=COR_FRACA, vertical="meio")
                )
                continue
            sx, sy, sw, sh = cx, cy + 1.0, 6.0, 3.0
            cor = it["cor"]
            if it["forma"] == "poligono":
                self.prim.append(_ret(sx, sy, sw, sh, preenchimento=cor, borda=COR_LINHA, espessura=0.2))
            elif it["forma"] == "linha":
                self.prim.append(_linha([(sx, sy + sh / 2), (sx + sw, sy + sh / 2)], cor=cor, espessura=0.8))
            else:
                self.prim.append(
                    _circ(sx + sw / 2, sy + sh / 2, 1.4, preenchimento=cor, borda=COR_LINHA, espessura=0.2)
                )
            self.prim.append(
                _txt(cx + sw + 2, cy, larg_col - sw - 2, ALTURA_LINHA_LEGENDA_MM, it["rotulo"], pt=7.5, vertical="meio")
            )
        self.relatorio["legenda"] = {"itens": len(itens), "truncados": truncados, "colunas": colunas}
        if not itens:
            self.prim.append(_txt(x, topo, w, 5, "sem camada visível", pt=7.5, cor=COR_FRACA))
            self._registrar(el, "aproximado", "nenhuma camada visível para listar")
        else:
            self._registrar(
                el,
                "ok" if not truncados else "aproximado",
                "" if not truncados else f"{truncados} itens não caberam (paginação da legenda declarada)",
            )

    def _escala(self, el: dict) -> None:
        alvo = self._quadro_para(el)
        if not alvo:
            self._registrar(el, "fora", "sem quadro de mapa")
            return
        _, quadro, _ = alvo
        escala = quadro.escala
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        comprimento_m = geo.comprimento_bonito_m(w - 10, escala)
        unidade = el.get("unidade", "auto")
        if unidade == "km" or (unidade == "auto" and comprimento_m >= 1000):
            rot = lambda m: f"{m / 1000:g}".replace(".", ",") + " km"  # noqa: E731
        else:
            rot = lambda m: f"{m:g}".replace(".", ",") + " m"  # noqa: E731
        largura_mm = comprimento_m * 1000.0 / escala
        divisoes = int(el.get("divisoes") or 4)
        bx, by, bh = x + 2, y + h - 7, 2.0
        for i in range(divisoes):
            self.prim.append(
                _ret(
                    bx + i * largura_mm / divisoes,
                    by,
                    largura_mm / divisoes,
                    bh,
                    preenchimento=COR_TEXTO if i % 2 == 0 else "#ffffff",
                    borda=COR_TEXTO,
                    espessura=0.25,
                )
            )
        for i in range(divisoes + 1):
            tx = bx + i * largura_mm / divisoes
            self.prim.append(_linha([(tx, by - 0.8), (tx, by + bh)], cor=COR_TEXTO, espessura=0.25))
            texto = "0" if i == 0 else rot(comprimento_m * i / divisoes) if i == divisoes else ""
            if texto:
                self.prim.append(_txt(tx - 12, by + bh + 0.5, 24, 4, texto, pt=7, alinhamento="centro"))
        self.prim.append(
            _txt(x, y, w, 5, f"Escala {formatar_escala(escala)} · {rot(comprimento_m)}", pt=7.5, cor=COR_FRACA)
        )
        self._registrar(el, "ok", f"barra de {comprimento_m:g} m = {largura_mm:.2f} mm a 1:{escala:.0f}")

    def _norte(self, el: dict) -> None:
        alvo = self._quadro_para(el)
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        cx, cy = x + w / 2, y + h * 0.55
        r = min(w, h) * 0.38
        angulo = 0.0
        nota = "norte verdadeiro"
        if el.get("referencia") == "grade" and alvo:
            lon, lat = alvo[1].centro
            angulo = geo.convergencia_meridiana_graus(lon, lat)
            nota = f"norte de grade UTM (convergência {angulo:+.2f}°)"
        a = math.radians(angulo)

        def rot(px, py):
            dx, dy = px - cx, py - cy
            return (cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a))

        ponta, base_e, base_d, meio = (
            rot(cx, cy - r),
            rot(cx - r * 0.35, cy + r * 0.6),
            rot(cx + r * 0.35, cy + r * 0.6),
            rot(cx, cy + r * 0.25),
        )
        self.prim.append(_poli([ponta, base_e, meio], preenchimento=COR_TEXTO, borda=COR_TEXTO, espessura=0.2))
        self.prim.append(_poli([ponta, base_d, meio], preenchimento="#ffffff", borda=COR_TEXTO, espessura=0.2))
        self.prim.append(
            _txt(
                x,
                y,
                w,
                4.5,
                "N" if el.get("referencia") != "grade" else "N (grade)",
                pt=8,
                alinhamento="centro",
                negrito=True,
            )
        )
        self._registrar(el, "ok", nota)

    def _grade(self, el: dict) -> None:
        alvo = self._quadro_para(el)
        if not alvo:
            self._registrar(el, "fora", "sem quadro de mapa")
            return
        q_el, quadro, _ = alvo
        if q_el.get("rotacao"):
            self._registrar(el, "fora", "grade não é desenhada sobre quadro com rotação (declarado)")
            return
        fx, fy, fw, fh = q_el["x"], q_el["y"], q_el["w"], q_el["h"]
        clip = (fx, fy, fw, fh)
        px_mm = fw / quadro.largura_px  # mm por pixel do quadro

        def mm_de(px, py):
            return fx + px * px_mm, fy + py * px_mm

        o, s, le, n = quadro.extensao()
        rotulos: list[tuple[float, float, str, str]] = []  # x, y, texto, borda
        linhas = 0
        if el.get("crs") == "utm":
            epsg = geo.epsg_utm(*quadro.centro)
            ida, volta = geo.transformador_utm(epsg)
            cantos = [ida.transform(lo, la) for lo, la in ((o, s), (le, s), (le, n), (o, n))]
            emin, emax = min(c[0] for c in cantos), max(c[0] for c in cantos)
            nmin, nmax = min(c[1] for c in cantos), max(c[1] for c in cantos)
            passo = float(el.get("intervalo") or geo.passo_bonito(max(emax - emin, nmax - nmin), 4))
            e0 = math.ceil(emin / passo) * passo
            valores_e = []
            v = e0
            while v <= emax and len(valores_e) < 200:
                valores_e.append(v)
                v += passo
            n0 = math.ceil(nmin / passo) * passo
            valores_n = []
            v = n0
            while v <= nmax and len(valores_n) < 200:
                valores_n.append(v)
                v += passo
            for e in valores_e:
                pontos = []
                for k in range(41):
                    nn = nmin + (nmax - nmin) * k / 40
                    lo, la = volta.transform(e, nn)
                    pontos.append(mm_de(*quadro.para_pixel(lo, la)))
                self.prim.append(_linha(pontos, cor=COR_GRADE, espessura=0.25, clip=clip))
                linhas += 1
                cruz = _cruzamento(pontos, fy + fh, eixo="y")  # borda inferior
                if cruz is not None:
                    rotulos.append((cruz, fy + fh + 0.6, f"{e:.0f} E", "inferior"))
            for nn in valores_n:
                pontos = []
                for k in range(41):
                    e = emin + (emax - emin) * k / 40
                    lo, la = volta.transform(e, nn)
                    pontos.append(mm_de(*quadro.para_pixel(lo, la)))
                self.prim.append(_linha(pontos, cor=COR_GRADE, espessura=0.25, clip=clip))
                linhas += 1
                cruz = _cruzamento(pontos, fx, eixo="x")  # borda esquerda
                if cruz is not None:
                    rotulos.append((fx - 0.6, cruz, f"{nn:.0f} N", "esquerda"))
            nota = f"UTM EPSG:{epsg}, passo {passo:g} m, {linhas} linhas"
        else:
            passo = float(el.get("intervalo") or geo.passo_bonito_graus(max(le - o, n - s), 4))
            lon0 = math.ceil(o / passo) * passo
            lon = lon0
            while lon <= le and linhas < 200:
                pontos = [mm_de(*quadro.para_pixel(lon, s + (n - s) * k / 20)) for k in range(21)]
                self.prim.append(_linha(pontos, cor=COR_GRADE, espessura=0.25, clip=clip))
                linhas += 1
                rotulos.append((pontos[0][0], fy + fh + 0.6, geo.graus_para_gms(lon, "lon"), "inferior"))
                lon += passo
            lat = math.ceil(s / passo) * passo
            while lat <= n and linhas < 400:
                pontos = [mm_de(*quadro.para_pixel(o + (le - o) * k / 20, lat)) for k in range(21)]
                self.prim.append(_linha(pontos, cor=COR_GRADE, espessura=0.25, clip=clip))
                linhas += 1
                rotulos.append((fx - 0.6, pontos[0][1], geo.graus_para_gms(lat, "lat"), "esquerda"))
                lat += passo
            nota = f"geográfica (EPSG:4326) em GMS, passo {passo:g}°, {linhas} linhas"
        if el.get("rotulos", True):
            for rx, ry, texto, borda in rotulos:
                if borda == "inferior":
                    self.prim.append(_txt(rx - 15, ry, 30, 3.5, texto, pt=6, alinhamento="centro", cor=COR_GRADE))
                else:
                    self.prim.append(
                        _txt(rx - 22, ry - 1.7, 21.5, 3.5, texto, pt=6, alinhamento="direita", cor=COR_GRADE)
                    )
        self.relatorio["grade"] = {"crs": el.get("crs"), "linhas": linhas, "rotulos": [r[2] for r in rotulos]}
        self._registrar(el, "ok", nota)

    def _titulo(self, el: dict) -> None:
        texto = self._expandir(el.get("texto") or "", el)
        self.prim.append(
            _txt(
                el["x"],
                el["y"],
                el["w"],
                el["h"],
                texto,
                pt=el.get("tamanho_pt", 18),
                negrito=True,
                alinhamento=el.get("alinhamento", "esquerda"),
                id_=el["id"],
            )
        )
        self._registrar(el, "ok")

    def _texto(self, el: dict) -> None:
        texto = self._expandir(el.get("texto") or "", el)
        self.prim.append(
            _txt(
                el["x"],
                el["y"],
                el["w"],
                el["h"],
                texto,
                pt=el.get("tamanho_pt", 10),
                negrito=bool(el.get("negrito")),
                alinhamento=el.get("alinhamento", "esquerda"),
                id_=el["id"],
            )
        )
        self._registrar(el, "ok")

    def _data(self, el: dict) -> None:
        v = self._expressoes()
        texto = v["data_longa"] if el.get("formato", "longa") == "longa" else v["data"]
        self.prim.append(_txt(el["x"], el["y"], el["w"], el["h"], texto, pt=el.get("tamanho_pt", 8), cor=COR_FRACA))
        self._registrar(el, "ok")

    def _imagem(self, el: dict) -> None:
        dados = None
        mime = "image/png"
        if el.get("origem", "logo") == "logo":
            dados = self.fontes.logo_png()
            if not dados:
                self._registrar(el, "fora", "o inquilino não tem logotipo")
                return
        else:
            achado = self.fontes.imagem_por_sha(el["sha256"], el.get("classe") or "objeto")
            if not achado:
                self._registrar(el, "fora", "imagem inexistente")
                return
            dados, mime = achado
        self.prim.append(_img(el["x"], el["y"], el["w"], el["h"], dados, mime, id_=el["id"]))
        self._registrar(el, "ok")

    def _tabela(self, el: dict) -> None:
        colunas, linhas = self.fontes.linhas_tabela(el)
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        if not colunas:
            self.prim.append(_txt(x, y, w, 5, "tabela sem dados", pt=7.5, cor=COR_FRACA))
            self._registrar(el, "aproximado", "sem colunas/linhas")
            return
        alt = 5.0
        larg = w / len(colunas)
        cabe = max(0, int(h // alt) - 1)
        mostradas = linhas[:cabe]
        for j, c in enumerate(colunas):
            self.prim.append(_txt(x + j * larg + 0.5, y, larg - 1, alt, str(c), pt=7, negrito=True, vertical="meio"))
        self.prim.append(_linha([(x, y + alt), (x + w, y + alt)], cor=COR_LINHA, espessura=0.3))
        for i, linha in enumerate(mostradas):
            for j, valor in enumerate(linha):
                self.prim.append(
                    _txt(
                        x + j * larg + 0.5,
                        y + (i + 1) * alt,
                        larg - 1,
                        alt,
                        "" if valor is None else str(valor),
                        pt=7,
                        vertical="meio",
                    )
                )
        if len(linhas) > cabe:
            self.relatorio["avisos"].append(f"{el['id']}: tabela mostra {cabe} de {len(linhas)} linhas")
        self._registrar(el, "ok" if len(linhas) <= cabe else "aproximado", f"{len(mostradas)} de {len(linhas)} linhas")

    def _atribuicao(self, el: dict) -> None:
        partes = []
        base = self.mapa.get("base") or "osm-guarulhos"
        if base in ATRIBUICAO_BASE:
            partes.append(ATRIBUICAO_BASE[base])
        for c in self._camadas_do_mapa():
            ficha = self._ficha(c["camada_id"])
            prov = ((ficha or {}).get("dados") or {}).get("proveniencia") or {}
            fonte = prov.get("fonte") or prov.get("orgao")
            if fonte and fonte not in partes:
                partes.append(str(fonte))
        if el.get("texto_extra"):
            partes.append(str(el["texto_extra"]))
        texto = " · ".join(partes) if partes else "fontes: ver o catálogo do mapa"
        if el.get("_fundo"):
            self.prim.append(_ret(el["x"], el["y"], el["w"], el["h"], preenchimento="#ffffffcc"))
        self.prim.append(
            _txt(el["x"] + 0.5, el["y"], el["w"] - 1, el["h"], texto, pt=6, cor=COR_FRACA, vertical="meio")
        )
        self._registrar(el, "ok", texto)


def _cruzamento(pontos: list[tuple[float, float]], valor: float, eixo: str) -> float | None:
    """coordenada da outra dimensão onde a polilinha cruza x=valor (eixo 'x') ou y=valor (eixo 'y')."""
    i = 0 if eixo == "x" else 1
    j = 1 - i
    for a, b in zip(pontos, pontos[1:], strict=False):
        if (a[i] - valor) * (b[i] - valor) <= 0 and a[i] != b[i]:
            f = (valor - a[i]) / (b[i] - a[i])
            return a[j] + f * (b[j] - a[j])
    return None


# ---------------------------------------------------------------- serialização
def _css_fontes() -> str:
    css = []
    if FONTE_SANS.exists():
        css.append(f"@font-face {{ font-family: 'plat-sans'; src: url('{FONTE_SANS.as_uri()}') format('woff2'); }}")
    if FONTE_MONO.exists():
        css.append(f"@font-face {{ font-family: 'plat-mono'; src: url('{FONTE_MONO.as_uri()}') format('woff2'); }}")
    return "\n".join(css)


def _svg_formas(prim: list[dict], largura: float, altura: float, com_texto: bool, com_imagens: bool) -> str:
    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{largura}mm" height="{altura}mm" viewBox="0 0 {largura} {altura}">'
    ]
    clips: dict[tuple, str] = {}
    defs = []
    for p in prim:
        c = p.get("clip")
        if c and c not in clips:
            cid = f"clip{len(clips)}"
            clips[c] = cid
            defs.append(f'<clipPath id="{cid}"><rect x="{c[0]}" y="{c[1]}" width="{c[2]}" height="{c[3]}"/></clipPath>')
    if defs:
        partes.append("<defs>" + "".join(defs) + "</defs>")
    for p in prim:
        t = p["t"]
        clip = f' clip-path="url(#{clips[p["clip"]]})"' if p.get("clip") else ""
        if t == "img" and com_imagens:
            b64 = base64.b64encode(p["dados"]).decode()
            partes.append(
                f'<image x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" '
                f'preserveAspectRatio="{"none" if p.get("id") else "xMidYMid meet"}" '
                f'xlink:href="data:{p["mime"]};base64,{b64}"/>'
            )
        elif t == "ret":
            fill = p["preenchimento"] or "none"
            stroke = p["borda"] or "none"
            partes.append(
                f'<rect x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="{p["espessura"]}"{clip}/>'
            )
        elif t == "linha":
            d = " ".join(f"{x:.3f},{y:.3f}" for x, y in p["pontos"])
            tr = f' stroke-dasharray="{p["tracejado"]}"' if p.get("tracejado") else ""
            partes.append(
                f'<polyline points="{d}" fill="none" stroke="{p["cor"]}" stroke-width="{p["espessura"]}"{tr}{clip}/>'
            )
        elif t == "poli":
            d = " ".join(f"{x:.3f},{y:.3f}" for x, y in p["pontos"])
            partes.append(
                f'<polygon points="{d}" fill="{p["preenchimento"] or "none"}" stroke="{p["borda"] or "none"}" '
                f'stroke-width="{p["espessura"]}"/>'
            )
        elif t == "circ":
            partes.append(
                f'<circle cx="{p["cx"]}" cy="{p["cy"]}" r="{p["r"]}" fill="{p["preenchimento"] or "none"}" '
                f'stroke="{p["borda"] or "none"}" stroke-width="{p["espessura"]}"/>'
            )
        elif t == "txt" and com_texto:
            tam_mm = p["pt"] * PT_MM
            anchor = {"esquerda": "start", "centro": "middle", "direita": "end"}[p["alinhamento"]]
            tx = p["x"] if anchor == "start" else p["x"] + p["w"] / 2 if anchor == "middle" else p["x"] + p["w"]
            linhas = str(p["texto"]).split("\n")
            ty0 = p["y"] + tam_mm * 0.95 if p["vertical"] == "topo" else p["y"] + p["h"] / 2 + tam_mm * 0.35
            fam = "plat-mono, monospace" if p["familia"] == "mono" else "plat-sans, sans-serif"
            peso = "700" if p["negrito"] else "400"
            for k, linha in enumerate(linhas):
                partes.append(
                    f'<text x="{tx:.3f}" y="{ty0 + k * tam_mm * 1.25:.3f}" font-size="{tam_mm:.3f}" '
                    f'font-family="{fam}" font-weight="{peso}" fill="{p["cor"]}" text-anchor="{anchor}">'
                    f"{html.escape(linha)}</text>"
                )
    partes.append("</svg>")
    return "".join(partes)


def html_da_pagina(prim: list[dict], largura: float, altura: float) -> str:
    """Texto como <div> (selecionável no PDF), imagens como <img>, formas em um único <svg> de página."""
    blocos = [
        f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><style>{_css_fontes()}"
        f"@page {{ size: {largura}mm {altura}mm; margin: 0; }} html, body {{ margin: 0; padding: 0; }}"
        f".pagina {{ position: relative; width: {largura}mm; height: {altura}mm; overflow: hidden; "
        f"font-family: 'plat-sans', sans-serif; color: {COR_TEXTO}; }} .el {{ position: absolute; }}"
        f".txt {{ white-space: pre-wrap; line-height: 1.25; overflow: hidden; }}"
        f"img {{ display: block; width: 100%; height: 100%; object-fit: fill; }}"
        "</style></head><body><div class='pagina'>"
    ]
    for p in prim:
        if p["t"] == "img":
            b64 = base64.b64encode(p["dados"]).decode()
            ajuste = "fill" if p.get("id") and p["mime"] == "image/png" and p.get("id") != "logo" else "contain"
            blocos.append(
                f'<img class="el" style="left:{p["x"]}mm;top:{p["y"]}mm;width:{p["w"]}mm;height:{p["h"]}mm;'
                f'object-fit:{ajuste}" src="data:{p["mime"]};base64,{b64}" alt="">'
            )
    blocos.append(
        f'<div class="el" style="left:0;top:0;width:{largura}mm;height:{altura}mm">'
        + _svg_formas(prim, largura, altura, com_texto=False, com_imagens=False)
        + "</div>"
    )
    for p in prim:
        if p["t"] != "txt":
            continue
        alin = {"esquerda": "left", "centro": "center", "direita": "right"}[p["alinhamento"]]
        fam = "'plat-mono', monospace" if p["familia"] == "mono" else "'plat-sans', sans-serif"
        estilo = (
            f"left:{p['x']}mm;top:{p['y']}mm;width:{p['w']}mm;height:{p['h']}mm;font-size:{p['pt']}pt;"
            f"text-align:{alin};color:{p['cor']};font-family:{fam};font-weight:{700 if p['negrito'] else 400};"
        )
        if p["vertical"] == "meio":
            estilo += "display:flex;align-items:center;"
            if alin != "left":
                estilo += f"justify-content:{'center' if alin == 'center' else 'flex-end'};"
        ident = f' id="{html.escape(p["id"])}"' if p.get("id") else ""
        blocos.append(f'<div class="el txt"{ident} style="{estilo}">{html.escape(str(p["texto"]))}</div>')
    blocos.append("</div></body></html>")
    return "".join(blocos)


def svg_da_pagina(prim: list[dict], largura: float, altura: float) -> str:
    return _svg_formas(prim, largura, altura, com_texto=True, com_imagens=True)


def pdf_de_html(texto_html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=texto_html, base_url=str(WEB)).write_pdf()


def raster_de_pdf(pdf: bytes, dpi: int, formato: str) -> bytes:
    import pymupdf

    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        pagina = doc[0]
        pix = pagina.get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png" if formato == "png" else "jpg")
    finally:
        doc.close()


def compor(layout: dict, mapa: dict, fontes: Fontes, *, dpi: int, formato: str, nome: str = "layout") -> Composicao:
    if formato not in ("pdf", "png", "jpg", "svg"):
        raise ErroComposicao(f"formato desconhecido: {formato}")
    dpi = max(limites.LAYOUT_DPI_MIN, min(limites.LAYOUT_DPI_MAX, int(dpi)))
    c = Compositor(layout, mapa, fontes, dpi)
    prim = c.compor()
    largura, altura = c.largura, c.altura
    if formato == "svg":
        dados = svg_da_pagina(prim, largura, altura).encode("utf-8")
        return Composicao(dados, "image/svg+xml", f"{nome}.svg", c.relatorio, prim)
    pdf = pdf_de_html(html_da_pagina(prim, largura, altura))
    if formato == "pdf":
        return Composicao(pdf, "application/pdf", f"{nome}.pdf", c.relatorio, prim)
    dados = raster_de_pdf(pdf, dpi, formato)
    return Composicao(dados, "image/png" if formato == "png" else "image/jpeg", f"{nome}.{formato}", c.relatorio, prim)


def mapa_de_item(item: dict | None) -> dict:
    """Definição de mapa a partir de um item `mapa` do catálogo (dados.corpo) — ou vazia."""
    if not item:
        return {}
    dados = item.get("dados") or {}
    corpo = dados.get("corpo") or {}
    camadas = []
    for c in corpo.get("camadas") or []:
        if isinstance(c, dict) and (c.get("camada_id") or c.get("id")):
            camadas.append(
                {
                    "camada_id": str(c.get("camada_id") or c.get("id")),
                    "visivel": c.get("visivel", True),
                    "opacidade": c.get("opacidade", 1.0),
                }
            )
    return {
        "titulo": item.get("titulo"),
        "camadas": camadas,
        "base": corpo.get("base") or "osm-guarulhos",
        "centro": corpo.get("centro"),
        "zoom": corpo.get("zoom"),
        "id": item.get("id"),
    }


def png_vazio(largura_px: int, altura_px: int) -> bytes:
    """PNG cinza claro do tamanho do quadro — só para pré-visualização sem motor de render."""
    import struct
    import zlib

    linha = b"\x00" + b"\xee\xf1\xf0" * largura_px
    bruto = linha * altura_px

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", struct.pack(">IIBBBBB", largura_px, altura_px, 8, 2, 0, 0, 0))
        + bloco(b"IDAT", zlib.compress(bruto, 6))
        + bloco(b"IEND", b"")
    )


def imagem_dimensoes(png: bytes) -> tuple[int, int]:
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ErroComposicao("não é PNG")
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    return w, h
