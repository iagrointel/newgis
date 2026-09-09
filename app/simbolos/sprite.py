"""Composição do sprite por inquilino (item L2-02-e-simbolos-sprites-glifos).

Medido em 07/09 (ver ADR `docs/adr/20260907T1642-sprite-proprio-em-vez-de-martin.md`): o binário Martin
(`/usr/local/bin/martin`, v1.15.0) lê o diretório de `--sprite` UMA VEZ, na subida do processo — dois
pedidos ao mesmo sprite antes e depois de acrescentar um SVG novo, sem reiniciar, devolveram o MESMO
catálogo (reproduzido com `curl` puro, sem código nosso). Isso colide de frente com a cláusula "ícone novo
aparece no sprite em <= 5 s sem reinício": reiniciar um processo por inquilino a cada upload não é reinício
zero, e recarregar o Martin inteiro para 1 SVG novo penaliza todos os outros inquilinos. Por isso o sprite
do inquilino é composto por ESTE módulo, no mesmo formato que o Martin serve (sprite.json + sprite.png,
1x e 2x) — compatível com o consumo do MapLibre, só que calculado sob demanda e cacheado por versão (a
versão muda sozinha quando o inquilino sobe/apaga um ícone, sem esperar nenhum relógio). Os glifos de
fonte (que NÃO mudam em runtime) continuam vindo do Martin de verdade — ver `app/simbolos/fontes.py`.
"""
from __future__ import annotations

import io
import math
import threading

import cairosvg
from PIL import Image

from app.simbolos import biblioteca

CELULA = 24  # px, tamanho lógico de cada ícone (1x); @2x multiplica por 2 na rasterização, não no layout
_TRAVA = threading.Lock()
_CACHE: dict[tuple[int, int], "SpriteComposto"] = {}


class SpriteComposto:
    __slots__ = ("versao", "json_1x", "png_1x", "json_2x", "png_2x")

    def __init__(self, versao, json_1x, png_1x, json_2x, png_2x):
        self.versao = versao
        self.json_1x = json_1x
        self.png_1x = png_1x
        self.json_2x = json_2x
        self.png_2x = png_2x


def _base_itens() -> list[tuple[str, str]]:
    """[(nome_no_sprite, svg_texto)] dos ícones embutidos + padrões — nunca muda em runtime."""
    itens = [(d.nome, biblioteca.montar_svg(d)) for d in biblioteca.catalogo()]
    itens += list(biblioteca.padroes().items())
    return itens


_BASE = _base_itens()  # calculado uma vez por processo: são fixos (compilados do código), não de disco


def _grade(n: int) -> int:
    """Colunas de uma grade quase quadrada para n ícones."""
    return max(1, math.ceil(math.sqrt(n)))


def _rasterizar(svg_texto: str, lado_px: int) -> Image.Image:
    png_bytes = cairosvg.svg2png(
        bytestring=svg_texto.encode("utf-8"), output_width=lado_px, output_height=lado_px
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def _compor(itens: list[tuple[str, str]], pixel_ratio: int) -> tuple[bytes, dict]:
    lado = CELULA * pixel_ratio
    cols = _grade(len(itens)) if itens else 1
    linhas = math.ceil(len(itens) / cols) if itens else 1
    atlas = Image.new("RGBA", (cols * lado, max(1, linhas) * lado), (0, 0, 0, 0))
    indice: dict[str, dict] = {}
    for i, (nome, svg_texto) in enumerate(itens):
        x, y = (i % cols) * lado, (i // cols) * lado
        img = _rasterizar(svg_texto, lado)
        atlas.paste(img, (x, y), img)
        indice[nome] = {"width": lado, "height": lado, "x": x, "y": y, "pixelRatio": pixel_ratio}
    buffer = io.BytesIO()
    atlas.save(buffer, format="PNG")
    return buffer.getvalue(), indice


def _versao_tenant(cur, tenant_id: int) -> str:
    cur.execute(
        "SELECT count(*) AS n, coalesce(max(criado_em), 'epoch'::timestamptz) AS ultimo "
        "FROM plat.simbolo_upload WHERE tenant_id = %s",
        (tenant_id,),
    )
    linha = cur.fetchone()
    return f"{linha['n']}:{linha['ultimo'].isoformat()}"


def itens_do_tenant(cur, tenant_id: int) -> list[tuple[str, str]]:
    """Base embutida + upload do inquilino, namespaced em `personalizado/<nome>` — um upload NUNCA pode
    colidir com um ícone padrão nem com o de outro inquilino, porque o prefixo já garante o espaço próprio
    (é a defesa contra a refutação "sobe SVG com o mesmo nome de um ícone padrão": o nome que colidiria
    simplesmente vive num namespace diferente no sprite composto, os dois aparecem)."""
    cur.execute(
        "SELECT nome, conteudo_svg FROM plat.simbolo_upload WHERE tenant_id = %s ORDER BY nome", (tenant_id,)
    )
    tenant_itens = [(f"personalizado/{r['nome']}", r["conteudo_svg"]) for r in cur.fetchall()]
    return _BASE + tenant_itens


def montar_sprite_tenant(cur, tenant_id: int) -> SpriteComposto:
    """Cacheado por versão (contagem + carimbo do upload mais recente do inquilino): um ícone novo muda a
    versão na hora, então a PRÓXIMA leitura já compõe o sprite novo — não existe relógio de espera, então a
    cláusula "≤ 5 s sem reinício" vale com folga (é o tempo de uma requisição http, não de um temporizador)."""
    versao = _versao_tenant(cur, tenant_id)
    with _TRAVA:
        atual = _CACHE.get(tenant_id)
        if atual is not None and atual.versao == versao:
            return atual
    itens = itens_do_tenant(cur, tenant_id)
    png_1x, json_1x = _compor(itens, 1)
    png_2x, json_2x = _compor(itens, 2)
    composto = SpriteComposto(versao, json_1x, png_1x, json_2x, png_2x)
    with _TRAVA:
        _CACHE[tenant_id] = composto
    return composto


def limpar_cache_para_teste() -> None:
    with _TRAVA:
        _CACHE.clear()
