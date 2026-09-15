"""Mosaico = busca STAC registrada no pgstac (item L1-07; ADR 20260910T2330).

`registrar()` chama `pgstac.search_query()` — a MESMA função SQL que o `POST /searches/register` do
titiler-pgstac usa por baixo — para obter o hash determinístico da busca (coleções, bbox, datetime,
filtro CQL2, ordenação). O que NÃO vem do titiler-pgstac é a composição do pixel: isto é feito em
casa por `app/imagens/tiles.py` (ver ADR seção 1).

`plat.mosaico` é a tabela-espelho que AUTORIZA (mesmo padrão de `raster_item.py`): o pgstac guarda a
busca (`pgstac.searches`, sem tenant_id, PK = hash global), esta tabela decide quem pode ver o quê.
O id exposto ao cliente é um uuid PRÓPRIO (não o hash md5), porque o vocabulário de escopo de token
(`app/auth/escopos.py`) só aceita `tiles:ler:<uuid>` e a validação de criação de token exige uma
linha em `plat.item` — por isso todo mosaico registrado também é um item de catálogo (tipo
`mosaico`), com o MESMO id."""

from __future__ import annotations

import re
from typing import Any

import psycopg2

from app.catalogo.comum import jsonb
from app.erros import ErroAPI
from app.imagens import pgstac as ps

NOME_MAX = 250
LIMITE_TILE_PADRAO = 6
LIMITE_TILE_MAX = 12
LIMITE_PEGADAS = 2000  # teto de segurança: uma busca larga não pagina infinito na resposta de pegadas
PADRAO_HASH = re.compile(r"^[0-9a-f]{32}$")
SELECOES_PIXEL = frozenset({"first", "last", "lowest", "highest", "mean", "median", "stdev"})


def validar_regras(corpo: dict[str, Any]) -> dict:
    """Contrato persistido do mosaico: sortby STAC, pixel_selection e lock (id STAC).

    Ex.: {"sortby": [{"field": "eo:cloud_cover", "direction": "asc"}],
          "pixel_selection": "median", "lock": null}.
    O lock restringe a busca às coleções autorizadas e aos demais critérios; nunca há fallback.
    """
    sortby = corpo.get("sortby", [{"field": "datetime", "direction": "desc"}])
    if not isinstance(sortby, list) or not sortby or len(sortby) > 10:
        raise ErroAPI(422, "sortby_invalido", "sortby exige de 1 a 10 campos STAC com direction asc/desc")
    for ordem in sortby:
        if (not isinstance(ordem, dict) or set(ordem) != {"field", "direction"}
                or not isinstance(ordem["field"], str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:]{0,199}", ordem["field"])
                or ordem["direction"] not in ("asc", "desc")):
            raise ErroAPI(422, "sortby_invalido", "cada ordem exige field STAC e direction asc/desc")
    selecao = corpo.get("pixel_selection", "first")
    if not isinstance(selecao, str) or selecao not in SELECOES_PIXEL:
        raise ErroAPI(422, "pixel_selection_invalido", "pixel_selection: " + ", ".join(sorted(SELECOES_PIXEL)))
    lock = corpo.get("lock")
    if lock is not None and (not isinstance(lock, str) or not lock.strip() or len(lock) > 250):
        raise ErroAPI(422, "lock_invalido", "lock deve ser o id STAC de uma única cena")
    return {"sortby": sortby, "pixel_selection": selecao, "lock": lock}


def _validar_nome(nome: Any) -> str:
    if not isinstance(nome, str) or not (1 <= len(nome.strip()) <= NOME_MAX):
        raise ErroAPI(422, "nome_invalido", f"nome do mosaico: 1 a {NOME_MAX} caracteres")
    return nome.strip()


def _validar_limite(limite: Any) -> int:
    if limite is None:
        return LIMITE_TILE_PADRAO
    if type(limite) is not int or not (1 <= limite <= LIMITE_TILE_MAX):
        raise ErroAPI(422, "limite_invalido", f"limite de cenas por ladrilho: 1 a {LIMITE_TILE_MAX}")
    return limite


def registrar(cur, tenant_id: int, usuario_id: int | None, corpo: dict[str, Any]) -> dict:
    """Registra (ou reaproveita, se os critérios já existirem) um mosaico. Devolve a linha de
    `plat.mosaico` como dict. Idempotente por (tenant_id, hash): a MESMA busca (mesmas coleções,
    bbox, datetime, filtro, ordenação — o `nome` NÃO entra no hash, propositalmente, senão "a mesma
    busca registrada duas vezes" com nomes diferentes contaria como duas buscas) devolve o mesmo id."""
    nome = _validar_nome(corpo.get("nome"))
    limite_tile = _validar_limite(corpo.get("limite"))
    regras = validar_regras(corpo)
    colecoes_pedidas = corpo.get("collections") or corpo.get("colecoes")
    if not colecoes_pedidas or not isinstance(colecoes_pedidas, list):
        raise ErroAPI(422, "colecoes_obrigatorias", "informe ao menos uma coleção (collections)")

    payload = ps.parametros_busca(
        tenant_id, cur,
        collections=colecoes_pedidas,
        bbox=corpo.get("bbox"),
        datetime_=corpo.get("datetime"),
        sortby=regras["sortby"],
        ids=[regras["lock"]] if regras["lock"] else None,
        filtro=corpo.get("filter"),
        filtro_lang=corpo.get("filter-lang"),
    )
    if not payload["collections"]:
        raise ErroAPI(422, "colecoes_inexistentes", "nenhuma das coleções pedidas pertence a este inquilino",
                      {"pedidas": colecoes_pedidas})

    # A identidade inclui a composição e o limite: a mesma busca pode ter mosaicos first/median
    # distintos. O nome continua fora do hash. Defaults preservam a identidade dos registros L1-07.
    metadata = {}
    if regras["pixel_selection"] != "first":
        metadata["pixel_selection"] = regras["pixel_selection"]
    if limite_tile != LIMITE_TILE_PADRAO:
        metadata["limite"] = limite_tile
    cur.execute("SET LOCAL search_path = pgstac, public")
    try:
        cur.execute("SELECT hash FROM pgstac.search_query(%s::jsonb, false, %s::jsonb)",
                    (jsonb(payload), jsonb(metadata)))
    except psycopg2.Error as e:
        raise ErroAPI(422, "busca_invalida", "critérios de mosaico rejeitados pelo catálogo",
                      {"motivo": str(e).strip()}) from e
    hash_pgstac = cur.fetchone()["hash"]
    cur.execute("SET LOCAL search_path = plat, public")  # devolve o search_path da sessão (app/db.py)

    # achado do adversário independente (10/09): `pgstac.search_query` só calcula hash/where/orderby —
    # NÃO executa a busca, então um filtro CQL2 sintaticamente aceitável mas semanticamente quebrado
    # (`filter` como string crua, `args` fora de lista) passava no registro (201) e só quebrava depois,
    # ao servir o primeiro tile/pegada. Uma busca de teste (limit=1) AQUI, na mesma transação, garante
    # que "registrado com sucesso" significa "esta busca RODA de verdade" — `ps.buscar` já converte
    # erro do banco em 422 `busca_invalida`, nunca deixa a exceção crua escapar.
    prova = ps.buscar(cur, {**payload, "limit": 1})
    if regras["lock"] and not prova.get("features"):
        raise ErroAPI(422, "lock_indisponivel", "a cena travada não pertence à busca autorizada do mosaico")

    criterios = {
        "bbox": corpo.get("bbox"), "datetime": corpo.get("datetime"),
        "filter": corpo.get("filter"), "filter-lang": corpo.get("filter-lang"),
        **regras, "limite": limite_tile,
    }
    cur.execute(
        """
        INSERT INTO plat.mosaico (tenant_id, hash, nome, colecoes, criterios, busca, criado_por)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (tenant_id, hash) DO UPDATE SET atualizado_em = now(), estado = 'ativo',
            criterios = EXCLUDED.criterios
        RETURNING id, tenant_id, hash, nome, colecoes, criterios, busca, estado, criado_em, atualizado_em
        """,
        (tenant_id, hash_pgstac, nome, payload["collections"], jsonb(criterios), jsonb(payload), usuario_id),
    )
    linha = dict(cur.fetchone())

    # linha de catálogo (plat.item, tipo 'mosaico') com o MESMO id: só assim um token pode ganhar
    # tiles:ler:<uuid> (app/auth/escopos.py exige uuid + item_legivel exige uma linha em plat.item).
    # ON CONFLICT DO NOTHING: reaproveitar um mosaico já registrado não deve sobrescrever o item.
    cur.execute(
        """
        INSERT INTO plat.item (id, tenant_id, tipo, titulo, resumo, dono_id, dados, criado_por, modificado_por)
        VALUES (%s::uuid, %s, 'mosaico', %s, %s, %s, %s::jsonb, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            linha["id"], tenant_id, nome,
            f"mosaico de {len(payload['collections'])} coleção(ões) — L1-07",
            usuario_id, jsonb({"colecoes": payload["collections"], "hash_pgstac": hash_pgstac,
                                "criterios": criterios}),
            usuario_id, usuario_id,
        ),
    )
    return linha


def listar(cur, tenant_id: int) -> list[dict]:
    cur.execute(
        "SELECT id, tenant_id, hash, nome, colecoes, criterios, estado, criado_em, atualizado_em "
        "FROM plat.mosaico WHERE tenant_id = %s AND estado = 'ativo' ORDER BY criado_em DESC",
        (tenant_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def eh_uuid(valor: str) -> bool:
    """Distingue `<uuid-do-mosaico>` de `<tenant_id>-<slug>` (nome de coleção) no MESMO segmento de
    caminho `/svc/<token>/mosaico/<X>/...` — usado por `rotas_tiles.py` para decidir entre mosaico
    REGISTRADO (este item) e o comportamento ad-hoc antigo (coleção inteira), sem rota colidente."""
    import uuid as _uuid
    try:
        _uuid.UUID(str(valor))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def obter(cur, tenant_id: int, mosaico_id: str) -> dict | None:
    """None tanto para 'não existe' quanto para 'é de outro inquilino' (mesma regra de item/coleção
    do resto do módulo: nunca confirmar a existência alheia). Também None se `mosaico_id` não é um
    uuid sintaticamente válido (evita erro de tipo do Postgres virando 500)."""
    if not eh_uuid(mosaico_id):
        return None
    cur.execute(
        "SELECT id, tenant_id, hash, nome, colecoes, criterios, busca, estado, criado_em, atualizado_em "
        "FROM plat.mosaico WHERE tenant_id = %s AND id = %s::uuid AND estado = 'ativo'",
        (tenant_id, mosaico_id),
    )
    r = cur.fetchone()
    return dict(r) if r else None


def remover(cur, tenant_id: int, mosaico_id: str) -> bool:
    """Marca `removido` (a busca em pgstac.searches fica — é inerte sem esta linha, e outro mosaico
    idêntico registrado depois reaproveita o mesmo hash) e apaga a linha de catálogo correspondente."""
    if not eh_uuid(mosaico_id):
        return False
    cur.execute(
        "UPDATE plat.mosaico SET estado = 'removido' WHERE tenant_id = %s AND id = %s::uuid AND estado = 'ativo' "
        "RETURNING id",
        (tenant_id, mosaico_id),
    )
    achou = cur.fetchone() is not None
    if achou:
        cur.execute("DELETE FROM plat.item WHERE tenant_id = %s AND id = %s::uuid AND tipo = 'mosaico'",
                    (tenant_id, mosaico_id))
    return achou


def _bbox_intersecta(
    a: list[float] | None, b: tuple[float, float, float, float]
) -> tuple[float, float, float, float] | None:
    """Interseção de dois bbox 2D (oeste, sul, leste, norte); None se não há registrado (usa `b` inteiro)
    ou se a interseção é vazia (mosaico com AOI que não toca este tile — devolve None = sem candidata,
    sem ir ao banco)."""
    if not a:
        return b
    ao, asu, al, an = a[0], a[1], a[2], a[3]
    bo, bs, bl, bn = b
    oeste, sul, leste, norte = max(ao, bo), max(asu, bs), min(al, bl), min(an, bn)
    if oeste >= leste or sul >= norte:
        return None
    return (oeste, sul, leste, norte)


def candidatas_para_tile(cur, linha: dict, bbox_tile: tuple[float, float, float, float], limite: int) -> list[dict]:
    """Feições STAC candidatas a cobrir este ladrilho, na ordem registrada (padrão datetime desc —
    "primeira com dado vence", a mesma regra do mosaico ad-hoc de coleção). `linha` é o resultado de
    `obter()`. Devolve [] sem consultar o banco quando o bbox registrado não toca o tile."""
    bbox_efetivo = _bbox_intersecta(linha["criterios"].get("bbox"), bbox_tile)
    if bbox_efetivo is None:
        return []
    payload = dict(linha["busca"])
    payload["bbox"] = list(bbox_efetivo)
    payload.pop("intersects", None)
    payload["limit"] = limite
    resultado = ps.buscar(cur, payload)
    return resultado.get("features") or []


def pegadas(cur, linha: dict, limite: int = LIMITE_PEGADAS) -> dict:
    """FeatureCollection GeoJSON das pegadas (geometria + id/datetime/nuvem/coleção) de todos os itens
    que casam com a busca registrada — equivalente à sublayer 'Footprint' de um mosaic dataset Esri."""
    payload = dict(linha["busca"])
    payload["limit"] = min(limite, LIMITE_PEGADAS)
    payload.pop("fields", None)
    features = []
    token = None
    paginas_restantes = (LIMITE_PEGADAS // max(payload["limit"], 1)) + 1
    while paginas_restantes > 0:
        if token:
            payload["token"] = token
        resultado = ps.buscar(cur, payload)
        pagina = resultado.get("features") or []
        for f in pagina:
            propriedades = f.get("properties") or {}
            features.append({
                "type": "Feature",
                "id": f.get("id"),
                "geometry": f.get("geometry"),
                "bbox": f.get("bbox"),
                "properties": {
                    "id": f.get("id"),
                    "collection": f.get("collection"),
                    "datetime": propriedades.get("datetime"),
                    "eo:cloud_cover": propriedades.get("eo:cloud_cover"),
                },
            })
        if len(features) >= LIMITE_PEGADAS or len(pagina) < payload["limit"]:
            break
        prox = next((link for link in resultado.get("links", []) if link.get("rel") == "next"), None)
        if not prox or "token=" not in prox.get("href", ""):
            break
        token = prox["href"].split("token=", 1)[1]
        paginas_restantes -= 1
    return {"type": "FeatureCollection", "features": features}


__all__ = [
    "LIMITE_TILE_MAX", "LIMITE_TILE_PADRAO", "candidatas_para_tile", "eh_uuid", "listar", "obter",
    "pegadas", "registrar", "remover",
]
