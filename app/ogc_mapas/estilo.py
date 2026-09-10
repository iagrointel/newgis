"""Estilo efetivo de uma camada para desenhar (item L2-04-i). Uma só função resolve as três origens
que o WMS aceita, nesta ordem: (1) `SLD_BODY`/`SLD` do próprio pedido, (2) `STYLES=<uuid>` apontando um
item `estilo` do catálogo (o modelo do L2-02-a), (3) o estilo padrão determinista da camada
(`app/estilos/padrao.estilo_padrao`) — a MESMA cor que o visualizador usa, então a imagem do WMS não
destoa do mapa da casa.

A saída é sempre o vocabulário que `pintor.pintar` consome: `{geometria, classes, simbolo, padrao}`.
"""

from __future__ import annotations

from app.erros import ErroAPI
from app.estilos import compilador
from app.estilos.padrao import GEOMETRIA_PARA_PLAT, estilo_padrao
from app.ogc_mapas import sld_leitura

# geometria da camada (vocabulário do catálogo) -> vocabulário do construtor de estilo
GEOM_CATALOGO_PARA_PLAT = {
    "Point": "ponto", "MultiPoint": "ponto",
    "LineString": "linha", "MultiLineString": "linha",
    "Polygon": "poligono", "MultiPolygon": "poligono",
    "Geometry": "poligono", "GeometryCollection": "poligono",
}
NOME_PADRAO = "padrao"


def geometria_plat(dados: dict) -> str:
    g = (dados or {}).get("geometria") or "Polygon"
    return GEOM_CATALOGO_PARA_PLAT.get(g, GEOMETRIA_PARA_PLAT.get(str(g).lower(), "poligono"))


def _do_construtor(pc: dict) -> dict:
    try:
        classes = compilador.classes(pc)
    except compilador.EstiloInvalido as e:
        raise ErroAPI(400, "estilo_invalido", str(e)) from e
    return {"geometria": pc.get("geometria") or "poligono", "classes": classes,
            "simbolo": pc.get("simbolo") or {}, "padrao": True, "plat_construtor": pc}


def estilo_padrao_da_camada(item_id: str, dados: dict) -> dict:
    doc = estilo_padrao(item_id, geometria_plat(dados))
    return _do_construtor(doc["corpo"]["plat_construtor"])


def _estilo_do_item(cur, estilo_id: str) -> dict:
    cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid AND tipo = 'estilo'", (estilo_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "estilo_nao_encontrado", f"item de estilo inexistente ou sem permissão: {estilo_id}")
    pc = ((r["dados"] or {}).get("corpo") or {}).get("plat_construtor")
    if not pc:
        raise ErroAPI(422, "estilo_sem_construtor", "item de estilo sem `plat_construtor` no corpo")
    return _do_construtor(pc)


def resolver(cur, item_id: str, dados: dict, *, nome_estilo: str | None = None,
             sld_texto: str | None = None) -> dict:
    """Estilo efetivo. `nome_estilo` vazio ou `padrao` = estilo determinista da camada; um uuid = item
    `estilo` do catálogo (a RLS decide se ele existe para quem pediu); `sld_texto` vence tudo."""
    if sld_texto:
        try:
            return sld_leitura.ler(sld_texto)
        except sld_leitura.SldInvalido as e:
            raise ErroAPI(400, "sld_invalido", e.mensagem, [{"detalhe": e.detalhe}] if e.detalhe else None) from e
    nome = (nome_estilo or "").strip()
    if not nome or nome.lower() in (NOME_PADRAO, "default"):
        return estilo_padrao_da_camada(item_id, dados)
    if len(nome) == 36 and nome.count("-") == 4:
        return _estilo_do_item(cur, nome)
    raise ErroAPI(400, "estilo_desconhecido",
                  f"estilo {nome!r}: use vazio, 'padrao' ou o uuid de um item de estilo")


def estilos_publicados(item_id: str, dados: dict) -> list[dict]:
    """O que vai no `GetCapabilities`: só o estilo padrão é NOMEADO (o item de estilo é referenciado
    por uuid, e publicar a lista inteira de estilos do inquilino em cada camada seria vazamento)."""
    est = estilo_padrao_da_camada(item_id, dados)
    return [{"nome": NOME_PADRAO, "titulo": "padrão", "padrao": True, "classes": est["classes"]}]
