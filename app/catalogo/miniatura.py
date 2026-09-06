"""Miniaturas 600×400 PNG (ADR 0004 seção 11): envio pela API (bytes decidem o formato; limite de 10 MB e 25 Mpx
contra bomba de descompressão, lido do cabeçalho antes de decodificar; EXIF/ICC/metadado descartados: a saída é uma
imagem nova), geração por job para camada vetorial (render das feições com Pillow ImageDraw, versão 1 do tipo),
objeto guardado pelo adaptador app/objetos.py e entregue pela API com ETag = sha256."""

import base64
import binascii
import io
import json
import warnings

from fastapi import Request, Response
from PIL import Image, ImageDraw, ImageOps

from app import limites, objetos
from app.erros import ErroAPI

Image.MAX_IMAGE_PIXELS = limites.MINIATURA_PIXELS_MAX
FORMATOS = {"PNG", "JPEG", "GIF"}
FUNDO = (245, 246, 248)
TRACO = (36, 99, 168)
PREENCHIMENTO = (120, 160, 210)


def decodificar_base64(conteudo: str) -> bytes:
    if len(conteudo) * 3 // 4 > limites.MINIATURA_BYTES_MAX + 4:
        raise ErroAPI(413, "miniatura_grande", f"miniatura acima de {limites.MINIATURA_BYTES_MAX // (1024 * 1024)} MB")
    if conteudo.startswith("data:"):
        conteudo = conteudo.split(",", 1)[-1]
    try:
        dados = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "validacao", "conteudo precisa ser base64 válido", {"campo": "conteudo"}) from e
    if len(dados) > limites.MINIATURA_BYTES_MAX:
        raise ErroAPI(413, "miniatura_grande", f"miniatura acima de {limites.MINIATURA_BYTES_MAX // (1024 * 1024)} MB")
    return dados


def normalizar(dados: bytes) -> bytes:
    """Bytes de PNG/JPEG/GIF → PNG 600×400 (corte central 3:2, LANCZOS), sem metadado. Levanta ErroAPI 415/422."""
    if len(dados) > limites.MINIATURA_BYTES_MAX:
        raise ErroAPI(413, "miniatura_grande", "miniatura acima do limite")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(dados))
            formato = (im.format or "").upper()
            if formato not in FORMATOS:
                raise ErroAPI(415, "formato_nao_aceito", "só PNG, JPEG ou GIF", {"formato": formato or None})
            largura, altura = im.size
            if largura * altura > limites.MINIATURA_PIXELS_MAX:
                raise ErroAPI(
                    422,
                    "imagem_grande",
                    "imagem com pixels demais",
                    {"largura": largura, "altura": altura, "maximo_px": limites.MINIATURA_PIXELS_MAX},
                )
            im.load()  # GIF animado: primeiro quadro
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise ErroAPI(
            422, "imagem_grande", "imagem com pixels demais", {"maximo_px": limites.MINIATURA_PIXELS_MAX}
        ) from e
    except ErroAPI:
        raise
    except Exception as e:  # noqa: BLE001 — Pillow não abriu: não é imagem aceita
        raise ErroAPI(415, "formato_nao_aceito", "só PNG, JPEG ou GIF", {"motivo": str(e)[:200]}) from e
    alvo = (limites.MINIATURA_LARGURA, limites.MINIATURA_ALTURA)
    ajustada = ImageOps.fit(im, alvo, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    limpa = Image.new("RGB", alvo, FUNDO)
    limpa.paste(ajustada, (0, 0), ajustada)  # imagem nova: sem info, sem EXIF, sem iCCP
    saida = io.BytesIO()
    limpa.save(saida, format="PNG", optimize=True)
    return saida.getvalue()


def guardar(cur, item_id: str, png: bytes) -> dict:
    o = objetos.guardar(cur, "miniatura", png, "image/png", item_id=item_id)
    cur.execute(
        "UPDATE plat.item SET miniatura_chave = %s, miniatura_sha256 = %s WHERE id = %s::uuid",
        (o["chave"], o["sha256"], item_id),
    )
    return o


CACHE_SESSAO = "private, max-age=300"


def entregar(r: dict, request: Request, cache: str = CACHE_SESSAO) -> Response:
    """GET da miniatura: 204 sem miniatura; ETag = sha256; 304 quando o cliente já tem. `cache` é o Cache-Control
    da resposta: o padrão vale para a sessão; a rota por link e a pública passam `no-store` (achado G2-6 do
    adversário: com max-age=300 o cliente continuava servindo a miniatura do cache 5 min depois da revogação)."""
    if not r["miniatura_chave"]:
        return Response(status_code=204, headers={"Cache-Control": cache})
    etag = f'"{r["miniatura_sha256"]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache})
    try:
        dados = objetos.ler(r["miniatura_chave"])
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "miniatura_inexistente", "miniatura ausente no armazenamento") from e
    return Response(
        dados,
        media_type="image/png",
        headers={"ETag": etag, "Cache-Control": cache, "X-Robots-Tag": "noindex, nofollow"},
    )


# ---------------------------------------------------------------- geração para camada vetorial (versão 1 do job)
def _projetar(x: float, y: float, bbox: tuple, larg: int, alt: int, margem: int) -> tuple[float, float]:
    xmin, ymin, xmax, ymax = bbox
    dx, dy = (xmax - xmin) or 1e-9, (ymax - ymin) or 1e-9
    escala = min((larg - 2 * margem) / dx, (alt - 2 * margem) / dy)
    ox = (larg - dx * escala) / 2
    oy = (alt - dy * escala) / 2
    return ox + (x - xmin) * escala, alt - (oy + (y - ymin) * escala)


def _desenhar_geom(draw: ImageDraw.ImageDraw, geom: dict, bbox: tuple, larg: int, alt: int, margem: int) -> None:
    t = geom.get("type")
    c = geom.get("coordinates") or []
    if t == "Point":
        x, y = _projetar(c[0], c[1], bbox, larg, alt, margem)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=TRACO)
    elif t == "MultiPoint":
        for p in c:
            _desenhar_geom(draw, {"type": "Point", "coordinates": p}, bbox, larg, alt, margem)
    elif t == "LineString":
        pts = [_projetar(p[0], p[1], bbox, larg, alt, margem) for p in c]
        if len(pts) > 1:
            draw.line(pts, fill=TRACO, width=2)
    elif t == "MultiLineString":
        for linha in c:
            _desenhar_geom(draw, {"type": "LineString", "coordinates": linha}, bbox, larg, alt, margem)
    elif t == "Polygon":
        for k, anel in enumerate(c):
            pts = [_projetar(p[0], p[1], bbox, larg, alt, margem) for p in anel]
            if len(pts) > 2:
                draw.polygon(pts, fill=PREENCHIMENTO if k == 0 else FUNDO, outline=TRACO)
    elif t == "MultiPolygon":
        for pol in c:
            _desenhar_geom(draw, {"type": "Polygon", "coordinates": pol}, bbox, larg, alt, margem)
    elif t == "GeometryCollection":
        for g in geom.get("geometries") or []:
            _desenhar_geom(draw, g, bbox, larg, alt, margem)


def render_camada(cur, schema: str, tabela: str, limite: int = 5000) -> bytes:
    """Render estático das feições (≤ limite, simplificadas a 1/600 do extent) em PNG 600×400."""
    import re

    if not re.match(r"^[a-z][a-z0-9_]{1,62}$", schema) or not re.match(r"^[a-z][a-z0-9_]{1,62}$", tabela):
        raise ValueError("nome de schema/tabela inválido")
    cur.execute(
        "SELECT f.column_name AS col FROM information_schema.columns f WHERE f.table_schema = %s AND f.table_name = %s "
        "AND f.udt_name = 'geometry' ORDER BY f.ordinal_position LIMIT 1",
        (schema, tabela),
    )
    g = cur.fetchone()
    if g is None:
        raise ValueError(f"{schema}.{tabela} sem coluna de geometria")
    col = g["col"]
    cur.execute(
        f"SELECT ST_XMin(e) AS xmin, ST_YMin(e) AS ymin, ST_XMax(e) AS xmax, ST_YMax(e) AS ymax FROM "
        f'(SELECT ST_Transform(ST_SetSRID(ST_Extent("{col}")::geometry, '
        f'coalesce(NULLIF(ST_SRID((SELECT "{col}" FROM "{schema}"."{tabela}" LIMIT 1)), 0), 4326)), 4326) AS e '
        f'FROM "{schema}"."{tabela}") x'
    )
    e = cur.fetchone()
    larg, alt, margem = limites.MINIATURA_LARGURA, limites.MINIATURA_ALTURA, 12
    im = Image.new("RGB", (larg, alt), FUNDO)
    draw = ImageDraw.Draw(im)
    if e and e["xmin"] is not None:
        bbox = (e["xmin"], e["ymin"], e["xmax"], e["ymax"])
        tol = max((bbox[2] - bbox[0]) / larg, (bbox[3] - bbox[1]) / alt)
        cur.execute(
            f'SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Transform(ST_SetSRID("{col}", '
            f'coalesce(NULLIF(ST_SRID("{col}"), 0), 4326)), 4326), %s)) AS gj '
            f'FROM "{schema}"."{tabela}" WHERE "{col}" IS NOT NULL LIMIT %s',
            (tol, limite),
        )
        for r in cur.fetchall():
            if r["gj"]:
                _desenhar_geom(draw, json.loads(r["gj"]), bbox, larg, alt, margem)
    saida = io.BytesIO()
    im.save(saida, format="PNG", optimize=True)
    return saida.getvalue()


GERADORES = {"camada_vetorial"}
