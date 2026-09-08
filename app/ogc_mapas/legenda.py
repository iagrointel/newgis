"""`GetLegendGraphic` (item L2-04-i): a legenda desenhada a partir das MESMAS classes que pintam o
mapa (`app/estilos/compilador.classes`), então legenda e imagem nunca discordam. Não é operação do
núcleo WMS 1.3.0, mas GeoServer, MapServer e QGIS Server servem, o QGIS pede sozinho ao adicionar a
camada, e sem ela a camada entra no cliente sem legenda nenhuma.

Cada classe é uma amostra de 20x20 px desenhada com o próprio símbolo (retângulo para polígono, traço
para linha, círculo para ponto) seguida do rótulo em fonte embutida do Pillow — sem arquivo de fonte,
para não depender do que está instalado na máquina.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from app.ogc_mapas.pintor import FUNDO_OPACO, _cor

AMOSTRA = 20
ESPACO = 6
MARGEM = 6
LINHA = AMOSTRA + ESPACO
LARGURA_MIN = 120
MAX_CLASSES = 60


def _fonte():
    try:
        return ImageFont.load_default()
    except OSError:                                   # pragma: no cover - Pillow sempre tem a embutida
        return None


def tamanho(classes: list[dict]) -> tuple[int, int]:
    """(largura, altura) que a legenda vai ter — o `GetCapabilities` publica isto no `LegendURL`."""
    n = min(len(classes or []), MAX_CLASSES)
    fonte = _fonte()
    largura_texto = 0
    for c in (classes or [])[:MAX_CLASSES]:
        rot = str(c.get("rotulo") or "")
        if fonte is not None:
            largura_texto = max(largura_texto, int(fonte.getlength(rot)))
        else:
            largura_texto = max(largura_texto, 7 * len(rot))
    largura = max(LARGURA_MIN, MARGEM * 2 + AMOSTRA + ESPACO + largura_texto)
    altura = MARGEM * 2 + max(1, n) * LINHA - ESPACO
    return (largura, altura)


def desenhar(estilo: dict, formato: str = "png") -> bytes:
    classes = (estilo.get("classes") or [{"rotulo": "camada", "cor": "#4e79a7"}])[:MAX_CLASSES]
    geometria = estilo.get("geometria") or "poligono"
    simbolo = estilo.get("simbolo") or {}
    largura, altura = tamanho(classes)
    transparente = formato != "jpeg"
    img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0) if transparente else (*FUNDO_OPACO, 255))
    d = ImageDraw.Draw(img, "RGBA")
    fonte = _fonte()
    alfa = max(0, min(255, int(round(float(simbolo.get("opacidade", 0.85)) * 255))))
    contorno = _cor(simbolo["contorno_cor"], 255) if simbolo.get("contorno_cor") else None
    y = MARGEM
    for c in classes:
        cor = _cor(c.get("cor") or "#4e79a7", alfa)
        x0, y0, x1, y1 = MARGEM, y, MARGEM + AMOSTRA, y + AMOSTRA
        if geometria == "linha":
            d.line([(x0, y1 - 4), (x1, y0 + 4)], fill=_cor(c.get("cor"), 255),
                   width=max(1, int(float(simbolo.get("largura", 2.0)))))
        elif geometria == "ponto":
            r = min(AMOSTRA // 2, max(3, int(float(simbolo.get("raio", 5.0)))))
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor, outline=contorno)
        else:
            d.rectangle([x0, y0, x1, y1], fill=cor, outline=contorno or _cor(c.get("cor"), 255))
        rot = str(c.get("rotulo") or "")
        d.text((x1 + ESPACO, y0 + 4), rot, fill=(30, 30, 30, 255), font=fonte)
        y += LINHA
    buf = io.BytesIO()
    if formato == "jpeg":
        Image.alpha_composite(Image.new("RGBA", img.size, (*FUNDO_OPACO, 255)), img).convert("RGB").save(
            buf, "JPEG", quality=90)
    elif formato == "png8":
        img.convert("P", palette=Image.ADAPTIVE, colors=255).save(buf, "PNG", optimize=True)
    else:
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
