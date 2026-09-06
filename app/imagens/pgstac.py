"""Wrappers finos sobre as funções SQL do pgstac (item L1-01-a). Nenhuma regra de negócio mora no pgstac:
ele guarda coleção/item STAC; QUEM PODE VER O QUÊ é sempre decidido aqui, nunca deixado para o cliente.

Isolamento por inquilino (hipótese do item): toda coleção se chama `<tenant_id>-<slug>` e a API SEMPRE
passa `collections` explícito para `pgstac.search` — mesmo lista vazia — porque o pgstac só filtra por
coleção quando a chave `collections` existe no JSON de busca (`stac_search_to_where`, `IF j ? 'collections'
THEN ...`); omitir a chave busca em qualquer coleção de qualquer inquilino. Por isso `parametros_busca`
nunca deixa a chamadora esquecer a chave, e `colecoes_do_tenant` é a única fonte da lista permitida.
"""

import datetime as _dt
import re
from typing import Any

import psycopg2

from app import limites
from app.catalogo.comum import jsonb
from app.erros import ErroAPI

PADRAO_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,58}$")


def slug_valido(slug: str) -> bool:
    return isinstance(slug, str) and bool(PADRAO_SLUG.match(slug))


def nome_colecao(tenant_id: int, slug: str) -> str:
    return f"{tenant_id}-{slug}"


def colecao_pertence(colecao: str, tenant_id: int) -> bool:
    """Confere o prefixo `<tenant_id>-` de forma exata (sem ambiguidade entre tenant 1 e tenant 12: o
    caractere seguinte ao número tem de ser '-')."""
    prefixo = f"{tenant_id}-"
    return isinstance(colecao, str) and colecao.startswith(prefixo) and len(colecao) > len(prefixo)


def slug_de(colecao: str, tenant_id: int) -> str:
    return colecao[len(f"{tenant_id}-"):]


def colecoes_do_tenant(cur, tenant_id: int) -> list[str]:
    """Única fonte de verdade de 'quais coleções este inquilino tem' — direto do pgstac, filtrado pelo
    PREFIXO do nome (nunca por uma tabela de mapeamento à parte, que poderia divergir)."""
    cur.execute("SELECT id FROM pgstac.collections WHERE id LIKE %s ORDER BY id", (f"{tenant_id}-%",))
    return [r["id"] for r in cur.fetchall() if colecao_pertence(r["id"], tenant_id)]


def colecoes_listar(cur, tenant_id: int) -> list[dict]:
    cur.execute(
        "SELECT content FROM pgstac.collections WHERE id LIKE %s ORDER BY id", (f"{tenant_id}-%",)
    )
    return [r["content"] for r in cur.fetchall() if colecao_pertence(r["content"]["id"], tenant_id)]


def colecao_obter(cur, tenant_id: int, colecao_id: str) -> dict | None:
    """None tanto para 'não existe' quanto para 'existe mas não é sua' — os dois casos são
    indistinguíveis de propósito (clausula inegociável do item: nunca confirmar a existência alheia)."""
    if not colecao_pertence(colecao_id, tenant_id):
        return None
    cur.execute("SELECT content FROM pgstac.collections WHERE id = %s", (colecao_id,))
    r = cur.fetchone()
    return r["content"] if r else None


def colecao_criar(cur, tenant_id: int, slug: str, corpo: dict[str, Any]) -> dict:
    if not slug_valido(slug):
        raise ErroAPI(
            422, "slug_invalido",
            "slug: minúsculas, dígitos e hífen, até 58 caracteres, sem começar por hífen",
        )
    colecao_id = nome_colecao(tenant_id, slug)
    if corpo.get("id") not in (None, colecao_id):
        raise ErroAPI(422, "id_fora_da_convencao", f"id da coleção tem de ser '{colecao_id}' (<tenant_id>-<slug>)")
    conteudo = {**corpo, "id": colecao_id, "type": "Collection", "stac_version": corpo.get("stac_version", "1.0.0")}
    conteudo.setdefault("description", conteudo.get("title") or colecao_id)
    conteudo.setdefault("license", "proprietary")
    conteudo.setdefault(
        "extent", {"spatial": {"bbox": [[-180, -90, 180, 90]]}, "temporal": {"interval": [[None, None]]}}
    )
    conteudo.setdefault("links", [])
    cur.execute("SELECT pgstac.create_collection(%s::jsonb)", (jsonb(conteudo),))
    return conteudo


def item_obter(cur, tenant_id: int, colecao_id: str, item_id: str) -> dict | None:
    if not colecao_pertence(colecao_id, tenant_id):
        return None
    cur.execute("SELECT pgstac.get_item(%s, %s) AS item", (item_id, colecao_id))
    r = cur.fetchone()
    conteudo = r["item"] if r else None
    return conteudo  # get_item devolve null (não erro) quando não existe


def item_criar(cur, tenant_id: int, colecao_id: str, corpo: dict[str, Any]) -> dict:
    if colecao_obter(cur, tenant_id, colecao_id) is None:
        raise ErroAPI(404, "colecao_inexistente", "coleção inexistente")
    item_id = corpo.get("id")
    if not item_id or not (1 <= len(str(item_id)) <= 256):
        raise ErroAPI(422, "item_id_invalido", "id do item é obrigatório (1-256 caracteres)")
    if corpo.get("collection") not in (None, colecao_id):
        raise ErroAPI(422, "colecao_divergente", "properties.collection do corpo diverge da URL")
    conteudo = {
        **corpo,
        "type": "Feature",
        "stac_version": corpo.get("stac_version", "1.0.0"),
        "collection": colecao_id,
    }
    conteudo.setdefault("properties", {})
    conteudo.setdefault("assets", {})
    conteudo.setdefault("links", [])
    conteudo.setdefault("geometry", None)
    cur.execute("SELECT pgstac.create_item(%s::jsonb)", (jsonb(conteudo),))
    return conteudo


def itens_criar_lote(cur, colecao_id: str, itens: list[dict]) -> int:
    """Ingestão em massa direto no `items_staging` do pgstac (usada pela semeadura sintética de teste,
    tests/api/imagens/test_medida_10000.py) — o CALLER já garantiu que `colecao_id` é do inquilino e que
    todo item em `itens` tem `collection == colecao_id`."""
    if not itens:
        return 0
    cur.execute("SELECT pgstac.create_items(%s::jsonb)", (jsonb(itens),))
    return len(itens)


def _validar_bbox(bbox: list[float]) -> None:
    if len(bbox) not in (4, 6):
        raise ErroAPI(422, "bbox_invalido", "bbox precisa ter 4 (2D) ou 6 (3D) números", {"recebido": len(bbox)})
    meio = len(bbox) // 2
    minimos, maximos = bbox[:meio], bbox[meio:]
    # só longitude (índice 0) pode "dar a volta" (antimeridiano); latitude/altura sempre min <= max
    for eixo in range(1, meio):
        if minimos[eixo] > maximos[eixo]:
            raise ErroAPI(
                422, "bbox_invalido",
                f"eixo {eixo}: mínimo ({minimos[eixo]}) maior que o máximo ({maximos[eixo]})",
            )


def _validar_datetime(valor: str) -> None:
    """RFC 3339 (STAC API Item Search): instante único ou intervalo `ini/fim`, com lado aberto marcado por
    `..` OU string vazia (as duas formas aparecem na spec/nos clientes; um item com `properties.datetime`
    tal vira `/<data>` ou `<data>/` quando algum lado é omitido). `datetime.fromisoformat` (py3.12) já
    valida calendário/hora — o objetivo aqui é nunca deixar o pgstac levantar uma exceção crua (500) por
    causa de um datetime malformado vindo do cliente."""
    ABERTO = ("..", "")
    partes = valor.split("/")
    if len(partes) > 2 or valor in ABERTO or (len(partes) == 2 and partes[0] in ABERTO and partes[1] in ABERTO):
        raise ErroAPI(422, "datetime_invalido", f"datetime malformado: {valor!r}")
    instantes: list[_dt.datetime | None] = []
    for p in partes:
        if p in ABERTO:
            instantes.append(None)
            continue
        texto = f"{p[:-1]}+00:00" if p.endswith("Z") else p
        try:
            instantes.append(_dt.datetime.fromisoformat(texto))
        except ValueError as e:
            raise ErroAPI(422, "datetime_invalido", f"datetime malformado: {p!r} (use RFC 3339)") from e
    if len(instantes) == 2 and instantes[0] is not None and instantes[1] is not None and instantes[0] > instantes[1]:
        raise ErroAPI(422, "datetime_invalido", "o início do intervalo vem depois do fim")


def parametros_busca(
    tenant_id: int,
    cur,
    *,
    collections: list[str] | None = None,
    ids: list[str] | None = None,
    bbox: list[float] | None = None,
    intersects: dict | None = None,
    datetime_: str | None = None,
    limit: int | None = None,
    token: str | None = None,
    sortby: list[dict] | None = None,
    filtro: dict | None = None,
    filtro_lang: str | None = None,
    fields: dict | None = None,
    query: dict | None = None,
) -> dict:
    """Monta o JSON que vai para `pgstac.search`, restringindo `collections` à interseção do pedido com
    o que o inquilino tem — SEMPRE presente na saída, mesmo vazia (ver docstring do módulo). Também valida
    o que o pgstac aceitaria sem checar e devolveria como exceção crua (500): bbox/intersects juntos,
    contagem de bbox, ordem min/max e formato de datetime."""
    if bbox and intersects:
        raise ErroAPI(422, "bbox_e_intersects", "use bbox OU intersects, nunca os dois no mesmo pedido")
    if bbox:
        _validar_bbox(bbox)
    if datetime_:
        _validar_datetime(datetime_)
    if limit is not None:
        if limit < 1:
            raise ErroAPI(422, "limit_invalido", "limit precisa ser >= 1", {"recebido": limit})
        limit = min(limit, limites.STAC_PAGINA_MAX)  # acima do teto: a spec manda usar o teto, não recusar

    permitidas = set(colecoes_do_tenant(cur, tenant_id))
    if collections:
        pedidas = [c for c in collections if c in permitidas]
    else:
        pedidas = sorted(permitidas)
    saida: dict[str, Any] = {"collections": pedidas}
    if ids:
        saida["ids"] = ids
    if bbox:
        saida["bbox"] = bbox
    if intersects:
        saida["intersects"] = intersects
    if datetime_:
        saida["datetime"] = datetime_
    if limit is not None:
        saida["limit"] = limit
    if token:
        saida["token"] = token
    if sortby:
        saida["sortby"] = sortby
    if filtro:
        saida["filter"] = filtro
        saida["filter-lang"] = filtro_lang or "cql2-json"
    if fields:
        saida["fields"] = fields
    if query:
        saida["query"] = query
    return saida


def _entrar_no_pgstac(cur) -> None:
    """`pgstac.search` e `pgstac.get_queryables` (ao contrário de `create_item`/`create_collection`/
    `get_item`, que já trazem `SET SEARCH_PATH TO pgstac,public` na própria definição) resolvem `collections`/
    `items`/`queryables` SEM qualificar o schema — dependem do search_path de quem chama. A sessão da API
    está com `search_path = plat_t<trilha>, public` (app/db.py, para o resto do app funcionar por trilha);
    `SET LOCAL` restringe a troca à transação atual, sem afetar nada fora desta chamada."""
    cur.execute("SET LOCAL search_path = pgstac, public")


def buscar(cur, payload: dict) -> dict:
    """`_validar_datetime`/`_validar_bbox` pegam a maioria do lixo antes de chegar aqui, mas nem tudo é
    detectável em Python (ex.: `datetime` com vírgula no lugar do ponto decimal — `fromisoformat` aceita,
    o parser do pgstac não): NUNCA deixar uma exceção do banco escapar como 500 por causa de entrada do
    cliente. Não faz `rollback()` aqui: levantar `ErroAPI` dentro do `with db.db(...)` do chamador já
    aciona o rollback do próprio `db.db` (app/db.py), o mesmo caminho que qualquer outro erro de banco."""
    _entrar_no_pgstac(cur)
    try:
        cur.execute("SELECT pgstac.search(%s::jsonb) AS resultado", (jsonb(payload),))
    except psycopg2.Error as e:
        raise ErroAPI(
            422, "busca_invalida", "parâmetros de busca rejeitados pelo catálogo", {"motivo": str(e).strip()}
        ) from e
    return cur.fetchone()["resultado"]


def queryables(cur, colecao_id: str | None = None) -> dict:
    """`pgstac.get_queryables` tem 3 sobrecargas (sem argumento, `_collection text`, `_collection_ids
    text[]`) — sem o `::text[]` explícito o Postgres não escolhe (`AmbiguousFunction`)."""
    _entrar_no_pgstac(cur)
    if colecao_id:
        cur.execute("SELECT pgstac.get_queryables(ARRAY[%s]::text[]) AS q", (colecao_id,))
    else:
        cur.execute("SELECT pgstac.get_queryables(NULL::text[]) AS q")
    return cur.fetchone()["q"]
