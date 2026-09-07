"""Rotas /api/itens (ADR 0004 seção 13): lista com busca, filtros laterais, facetas, tags, cursor; CRUD com JSON
Schema por tipo; lote; mover; versões (imutáveis, restaurar, publicar); relações (usado-por, criado-a-partir-de,
ordem de exclusão, PUT relacoes); lixeira lógica por DELETE. Toda rota declara x-auth/x-privilegio. Leituras aceitam
token catalogo:ler; escritas por token exigem admin:inquilino.

Documento de construtor (item L5-05-documento-versoes): `validar_grafo` roda logo depois de `tipos.validar` nas
duas rotas que gravam `dados` (id de nó ULID, sem duplicata, sem ligação pendente); `ver` migra o documento na
leitura quando `esquema_versao` do item está atrasada em relação ao tipo (`app/catalogo/documento.py`) e registra
o evento; `/api/esquemas` serve os mesmos JSON Schema que `tipos.validar` usa, para o editor e para o agente."""

import json
import uuid
from pathlib import Path

import psycopg2
import pydantic
from fastapi import APIRouter, Body, Query, Request, Response
from jsonschema import Draft202012Validator

from app import db, limites
from app.auth.comum import campos_json, paginacao
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo import busca as mod_busca
from app.catalogo import comum, diff, documento, metadado, relacoes, texto, tipos
from app.catalogo.comum import (
    carregar,
    exigir_edicao,
    item_json,
    item_ou_404,
    jsonb,
    ligar_lixeira,
    ligar_superadmin,
    registrar_evento,
    rotular_versao,
    uuid_ok,
)
from app.catalogo.modelos import (
    Item,
    ItemEditar,
    ItemEntrada,
    LoteEntrada,
    LoteSaida,
    MoverEntrada,
    OrdemExclusao,
    Pagina,
    RelacoesEntrada,
    RestaurarVersaoEntrada,
    TipoItem,
    UsadoPor,
    VersaoCompleta,
)
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(tags=["catalogo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}
CAMPOS_EDITAVEIS = frozenset(ItemEditar.model_fields)
CAMPOS_VERSAO = (
    "titulo",
    "resumo",
    "descricao",
    "tags",
    "creditos",
    "termos_de_uso",
    "extent",
    "extent_origem",
    "categorias",
    "classificacao",
    "url",
    "dados",
)
FROM_LISTA = "FROM plat.item i JOIN plat.tipo_item t ON t.nome = i.tipo JOIN plat.usuario d ON d.id = i.dono_id"


# ---------------------------------------------------------------- filtros e lista
def _lista_str(v) -> list[str]:
    saida = []
    for x in v or []:
        saida.extend(p.strip() for p in str(x).split(",") if p.strip())
    return saida


def _uuid_ou_422(v: str, campo: str) -> str:
    try:
        return str(uuid.UUID(v))
    except (ValueError, TypeError) as e:
        raise ErroAPI(422, "campo_invalido", f"{campo} exige uuid", {"campo": campo, "valor": v}) from e


def _data(v: str | None, campo: str, fim: bool):
    if not v:
        return None
    try:
        return mod_busca._data(campo, v, fim)
    except mod_busca.ErroSintaxe as e:
        raise mod_busca.erro_api(e) from e


def filtros_da_query(auth: Auth, p: dict, lixeira: bool = False) -> tuple[list[str], list, dict, mod_busca.Consulta]:
    """Devolve (condições, params, assinatura, consulta). p = parâmetros já lidos da query."""
    cond, params, chave = [], [], {"lixeira": lixeira}
    cond.append("i.apagado_em IS NOT NULL" if lixeira else "i.apagado_em IS NULL")
    try:
        consulta = mod_busca.traduzir(p.get("q") or "", set(tipos.todos()))
    except mod_busca.ErroSintaxe as e:
        raise mod_busca.erro_api(e) from e
    if consulta.sql != "true":
        cond.append(consulta.sql)
        params.extend(consulta.params)
        chave["q"] = p.get("q")
    for nome, coluna in (("tipo", "i.tipo"), ("familia", "t.familia"), ("status", "i.status"), ("acesso", "i.acesso")):
        valores = _lista_str(p.get(nome))
        if valores:
            if nome == "tipo":
                for v in valores:
                    tipos.obter(v)
            if nome == "status":
                # o status "sem status" é NULL na coluna; a faceta o conta como 'nenhum' (coalesce) e é esse o valor
                # que o cliente devolve no filtro. Sem este ramo, ?status=nenhum comparava com ANY e dava 0.
                for v in valores:
                    if v not in mod_busca.STATUS:
                        raise ErroAPI(422, "campo_invalido", f"status inválido: {v}", {"campo": "status", "valor": v})
                reais = [v for v in valores if v != "nenhum"]
                partes = ["i.status IS NULL"] if "nenhum" in valores else []
                if reais:
                    partes.append("i.status = ANY (%s)")
                    params.append(reais)
                cond.append("(" + " OR ".join(partes) + ")")
                chave[nome] = valores
                continue
            cond.append(f"{coluna} = ANY (%s)")
            params.append(valores)
            chave[nome] = valores
    donos = _lista_str(p.get("dono_id"))
    if donos:
        try:
            ids = [int(x) for x in donos]
        except ValueError as e:
            raise ErroAPI(422, "campo_invalido", "dono_id exige inteiro", {"campo": "dono_id"}) from e
        cond.append("i.dono_id = ANY (%s)")
        params.append(ids)
        chave["dono_id"] = ids
    tags = _lista_str(p.get("tags"))
    if tags:
        cond.append("i.tags @> %s::text[]")
        params.append(tags)
        chave["tags"] = tags
    cats = [_uuid_ou_422(c, "categoria") for c in _lista_str(p.get("categoria"))]
    if cats:
        cond.append(
            "i.categorias && ARRAY(SELECT k.id FROM plat.categoria k WHERE k.id = ANY (%s::uuid[]) OR EXISTS "
            "(SELECT 1 FROM plat.categoria a WHERE a.id = ANY (%s::uuid[]) AND k.caminho LIKE a.caminho || '/%%'))"
        )
        params.extend([cats, cats])
        chave["categoria"] = cats
    if p.get("pasta_id"):
        if p["pasta_id"] == "raiz":
            cond.append("i.pasta_id IS NULL")
        else:
            cond.append("i.pasta_id = %s::uuid")
            params.append(_uuid_ou_422(p["pasta_id"], "pasta_id"))
        chave["pasta_id"] = p["pasta_id"]
    if p.get("origem"):
        if p["origem"] not in mod_busca.ORIGENS:
            raise ErroAPI(422, "campo_invalido", "origem inválida", {"campo": "origem", "valor": p["origem"]})
        cond.append("i.origem = %s")
        params.append(p["origem"])
        chave["origem"] = p["origem"]
    for nome, coluna in (("criado", "i.criado_em"), ("modificado", "i.modificado_em"), ("apagado", "i.apagado_em")):
        de, ate = _data(p.get(f"{nome}_de"), nome, False), _data(p.get(f"{nome}_ate"), nome, True)
        if de:
            cond.append(f"{coluna} >= %s")
            params.append(de)
            chave[f"{nome}_de"] = p.get(f"{nome}_de")
        if ate:
            cond.append(f"{coluna} < %s")
            params.append(ate)
            chave[f"{nome}_ate"] = p.get(f"{nome}_ate")
    if p.get("bbox"):
        try:
            xmin, ymin, xmax, ymax = (float(x) for x in str(p["bbox"]).split(","))
            assert -180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90
        except (ValueError, AssertionError) as e:
            raise ErroAPI(
                422, "campo_invalido", "bbox exige xmin,ymin,xmax,ymax em EPSG:4326", {"campo": "bbox"}
            ) from e
        cond.append("i.extent && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
        params.extend([xmin, ymin, xmax, ymax])
        chave["bbox"] = [xmin, ymin, xmax, ymax]
    if p.get("favoritos"):
        cond.append("EXISTS (SELECT 1 FROM plat.favorito f WHERE f.item_id = i.id AND f.usuario_id = %s)")
        params.append(auth.usuario_id)
        chave["favoritos"] = True
    if p.get("meus"):
        cond.append("i.dono_id = %s")
        params.append(auth.usuario_id)
        chave["meus"] = True
    if p.get("grupo_id"):
        cond.append("EXISTS (SELECT 1 FROM plat.item_grupo ig WHERE ig.item_id = i.id AND ig.grupo_id = %s::uuid)")
        params.append(_uuid_ou_422(p["grupo_id"], "grupo_id"))
        chave["grupo_id"] = p["grupo_id"]
    return cond, params, chave, consulta


def _ordenacao(consulta: mod_busca.Consulta, ordenar: str | None, direcao: str | None):
    """Devolve (lista de (expr, params), direção, nome). Relevância: título exato, rank+status, modificado, id."""
    if ordenar:
        if ordenar not in mod_busca.ORDENACOES:
            raise ErroAPI(422, "campo_invalido", f"ordenar inválido: {ordenar}", {"campo": "ordenar", "valor": ordenar})
        expr, padrao = mod_busca.ORDENACOES[ordenar]
        d = (direcao or padrao).lower()
        if d not in ("asc", "desc"):
            raise ErroAPI(422, "campo_invalido", "direcao exige asc ou desc", {"campo": "direcao"})
        return [(expr, []), ("i.id", [])], d, ordenar
    if consulta.texto_rank:
        termo = " ".join(t.strip('"') for t in consulta.texto_rank)
        rank = (
            f"(ts_rank_cd(i.busca, websearch_to_tsquery({mod_busca.CFG}, %s), 32) + CASE i.status WHEN 'autoritativo' "
            f"THEN {limites.BUSCA_REFORCO_STATUS} WHEN 'obsoleto' THEN "
            f"-{limites.BUSCA_REFORCO_STATUS} ELSE 0 END)::float8"
        )
        return (
            [
                ("(lower(public.unaccent(i.titulo)) = lower(public.unaccent(%s)))::int", [termo]),
                (rank, [" ".join(consulta.texto_rank)]),
                ("i.modificado_em", []),
                ("i.id", []),
            ],
            "desc",
            "relevancia",
        )
    return [("i.modificado_em", []), ("i.id", [])], "desc", "modificado_em"


def listar_ids(cur, auth: Auth, p: dict, lixeira: bool = False) -> tuple[int, list[str], str | None, bool]:
    """(total, ids na ordem, próximo cursor, aproximado). Trigram como reserva quando o FTS não acha nada."""
    cond, params, chave, consulta = filtros_da_query(auth, p, lixeira)
    lim, desl = paginacao(p.get("limite"), p.get("deslocamento"), maximo=limites.ITENS_PAGINA_MAX)
    if desl > limites.ITENS_DESLOCAMENTO_MAX:
        raise ErroAPI(422, "deslocamento_alto", f"deslocamento acima de {limites.ITENS_DESLOCAMENTO_MAX}; use cursor")
    chaves, direcao, nome_ord = _ordenacao(consulta, p.get("ordenar"), p.get("direcao"))
    chave["ordenar"], chave["direcao"] = nome_ord, direcao
    assinatura = mod_busca.assinatura(chave)
    onde = " WHERE " + " AND ".join(cond)
    cur.execute(f"SELECT count(*) AS n {FROM_LISTA}{onde}", params)
    total = cur.fetchone()["n"]
    aproximado = False
    if (
        total == 0
        and consulta.termos == 1
        and consulta.ultimo_livre
        and len(consulta.ultimo_livre) >= 4
        and not p.get("ordenar")
    ):
        # 7.4: reserva por trigram no título
        cond2 = [c for c in cond if c != consulta.sql] + [
            "lower(public.unaccent(%s)) <%% lower(public.unaccent(i.titulo))"
        ]
        params2 = params[len(consulta.params) :] + [consulta.ultimo_livre]
        cur.execute(f"SET LOCAL pg_trgm.word_similarity_threshold = {limites.BUSCA_TRGM_LIMIAR}")
        onde2 = " WHERE " + " AND ".join(cond2)
        cur.execute(f"SELECT count(*) AS n {FROM_LISTA}{onde2}", params2)
        total = cur.fetchone()["n"]
        if total:
            aproximado = True
            cur.execute(
                f"SELECT i.id {FROM_LISTA}{onde2} "
                "ORDER BY word_similarity(lower(public.unaccent(%s)), lower(public.unaccent(i.titulo))) DESC, "
                "i.modificado_em DESC, i.id DESC "
                "LIMIT %s OFFSET %s",
                params2 + [consulta.ultimo_livre, lim, desl],
            )
            return total, [str(r["id"]) for r in cur.fetchall()], None, True
    exprs = [e for e, _ in chaves]
    ord_params = [x for _, ps in chaves for x in ps]
    ordem = ", ".join(f"{e} {direcao.upper()}" for e in exprs)
    prefixo_ordem = ""
    if consulta.ultimo_livre and p.get("prefixo") and consulta.termos == 1:
        # prefixo ao vivo: acrescenta :* ao único termo; websearch_to_tsquery vazio (stopword) fica como está
        cond = [c for c in cond if c != consulta.sql] + [
            f"i.busca @@ (CASE WHEN numnode(websearch_to_tsquery({mod_busca.CFG}, %s)) = 1 THEN "
            f"(websearch_to_tsquery({mod_busca.CFG}, %s)::text || ':*')::tsquery ELSE "
            f"websearch_to_tsquery({mod_busca.CFG}, %s) END)"
        ]
        params = params[len(consulta.params) :] + [consulta.ultimo_livre] * 3
        onde = " WHERE " + " AND ".join(cond)
        cur.execute(f"SELECT count(*) AS n {FROM_LISTA}{onde}", params)
        total = cur.fetchone()["n"]
    cursor_params: list = []
    if p.get("cursor"):
        c = mod_busca.cursor_decodificar(p["cursor"], assinatura)
        valores = list(c["v"]) + [c["id"]]
        if len(valores) != len(exprs):
            raise ErroAPI(400, "cursor_invalido", "cursor de outra ordenação")
        op = "<" if direcao == "desc" else ">"
        marcadores = ", ".join(["%s::uuid" if e == "i.id" else "%s" for e in exprs])
        prefixo_ordem = f" AND ROW({', '.join(exprs)}) {op} ROW({marcadores})"
        cursor_params = ord_params + valores
        desl = 0
    sql = (
        f"SELECT i.id, {', '.join(f'({e}) AS k{n}' for n, e in enumerate(exprs))} {FROM_LISTA}{onde}{prefixo_ordem} "
        f"ORDER BY {ordem} LIMIT %s OFFSET %s"
    )
    cur.execute(sql, ord_params + params + cursor_params + ord_params + [lim + 1, desl])
    linhas = cur.fetchall()
    proximo = None
    if len(linhas) > lim:
        linhas = linhas[:lim]
        ultimo = linhas[-1]
        valores = [ultimo[f"k{n}"] for n in range(len(exprs) - 1)]
        proximo = mod_busca.cursor_codificar(
            nome_ord,
            direcao,
            [v.isoformat() if hasattr(v, "isoformat") else v for v in valores],
            str(ultimo["id"]),
            assinatura,
        )
    return total, [str(r["id"]) for r in linhas], proximo, aproximado


_CONTAGENS_VAZIAS = {"usado_por": 0, "criado_a_partir_de": 0, "grupos": 0, "links_ativos": 0}


def carregar_varios(cur, ids: list[str], auth: Auth, completo: bool = False) -> list[dict]:
    """Uma consulta para os N itens (sem as contagens por LATERAL nem os campos pesados, ver SQL_ITEM_LISTA) + UMA
    consulta em lote para usado_por/criado_a_partir_de/grupos/links_ativos dos N (comum.contagens_lote) — nunca N
    chamadas de função. completo=True não tem hoje nenhum chamador (rotas_itens/rotas_favoritos/rotas_lixeira usam
    o padrão False); se algum dia precisar, cai para SQL_ITEM cheio em vez de devolver descricao/dados vazios."""
    if not ids:
        return []
    cur.execute((comum.SQL_ITEM if completo else comum.SQL_ITEM_LISTA) + " WHERE i.id = ANY (%s::uuid[])", (ids,))
    por_id = {str(r["id"]): r for r in cur.fetchall()}
    contagens = comum.contagens_lote(cur, ids)
    for iid, r in por_id.items():
        c = contagens.get(iid, _CONTAGENS_VAZIAS)
        r["usado_por"] = c["usado_por"]
        r["criado_a_partir_de"] = c["criado_a_partir_de"]
        r["compartilhado_com_grupos"] = c["grupos"]
        r["links_ativos"] = c["links_ativos"]
    return [item_json(por_id[i], auth, completo=completo) for i in ids if i in por_id]


def _params_lista(request: Request, limite, deslocamento) -> dict:
    p = {}
    for chave, valor in request.query_params.multi_items():
        if chave in ("tipo", "familia", "dono_id", "tags", "categoria", "status", "acesso"):
            p.setdefault(chave, []).append(valor)
        else:
            p[chave] = valor
    p["limite"], p["deslocamento"] = limite, deslocamento
    for b in ("favoritos", "meus", "prefixo"):
        p[b] = str(p.get(b, "")).lower() in ("1", "true", "sim")
    return p


@router.get(
    "/api/tipos-item", response_model=list[TipoItem], openapi_extra={"x-auth": "S/T", "x-privilegio": "vocabulario"}
)
def tipos_item(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    return [dict(t) for t in tipos.todos().values()]


_RAIZ = Path(__file__).resolve().parents[2]
_ESQUEMAS_HISTORICOS = _RAIZ / "docs" / "esquemas"


@router.get(
    "/api/esquemas",
    openapi_extra={"x-auth": "S/T", "x-privilegio": "vocabulario"},
)
def esquemas_listar(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Lista dos tipos com JSON Schema publicado (item L5-05-documento-versoes, D2 do L5_CONCEITO): a mesma
    fonte que `tipos.validar` usa, para o editor construir o painel de propriedades e para o agente escrever
    documento contra o mesmo contrato."""
    return [
        {"tipo": t["nome"], "familia": t["familia"], "esquema_versao": t["esquema_versao"]}
        for t in sorted(tipos.todos().values(), key=lambda t: t["nome"])
    ]


@router.get(
    "/api/esquemas/{tipo}",
    openapi_extra={"x-auth": "S/T", "x-privilegio": "vocabulario"},
)
def esquema_ver(tipo: str, versao: int | None = None, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    t = tipos.obter(tipo)
    if versao is None or versao == t["esquema_versao"]:
        return t["esquema"]
    caminho = _ESQUEMAS_HISTORICOS / f"{tipo}-v{versao}.json"
    if not caminho.is_file():
        raise ErroAPI(
            404, "esquema_inexistente", f"esquema {tipo} v{versao} inexistente", {"tipo": tipo, "versao": versao}
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


@router.get("/api/itens", response_model=Pagina, openapi_extra=LER)
def listar(
    request: Request,
    resposta: Response,
    q: str | None = None,
    ordenar: str | None = None,
    direcao: str | None = None,
    tipo: list[str] | None = Query(None),
    familia: list[str] | None = Query(None),
    dono_id: list[str] | None = Query(None),
    tags: list[str] | None = Query(None),
    categoria: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    acesso: list[str] | None = Query(None),
    pasta_id: str | None = None,
    origem: str | None = None,
    criado_de: str | None = None,
    criado_ate: str | None = None,
    modificado_de: str | None = None,
    modificado_ate: str | None = None,
    bbox: str | None = None,
    grupo_id: str | None = None,
    favoritos: bool = False,
    meus: bool = False,
    prefixo: bool = False,
    limite: int | None = None,
    deslocamento: int | None = None,
    cursor: str | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    p = _params_lista(request, limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        total, ids, proximo, aproximado = listar_ids(cur, auth, p)
        itens = carregar_varios(cur, ids, auth)
    if proximo:
        resposta.headers["Link"] = f'<{request.url.path}?cursor={proximo}>; rel="next"'
    saida = {"total": total, "itens": itens, "proximo_cursor": proximo}
    if aproximado:
        saida["aproximado"] = True
    return saida


@router.get("/api/itens/facetas", openapi_extra=LER)
def facetas(request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    p = _params_lista(request, None, None)
    with db.db(auth.contexto()) as cur:
        cond, params, _chave, _consulta = filtros_da_query(auth, p)
        onde = " WHERE " + " AND ".join(cond)
        saida = {}
        for nome, expr in (
            ("tipo", "i.tipo"),
            ("familia", "t.familia"),
            ("status", "coalesce(i.status, 'nenhum')"),
            ("acesso", "i.acesso"),
        ):
            cur.execute(
                f"SELECT {expr} AS valor, count(*) AS n {FROM_LISTA}{onde} GROUP BY 1 ORDER BY n DESC, 1 LIMIT 100",
                params,
            )
            saida[nome] = [{"valor": r["valor"], "n": r["n"]} for r in cur.fetchall()]
        # dono: o filtro lateral é ?dono_id=<int>, logo a faceta devolve o id junto com o login e o nome. Sem o id,
        # dono sem item na página carregada sumia da lista (o cliente resolvia o id pelo objeto dono da lista).
        cur.execute(
            f"SELECT d.id, d.login, d.nome, count(*) AS n {FROM_LISTA}{onde} "
            "GROUP BY 1, 2, 3 ORDER BY n DESC, 2 LIMIT 100",
            params,
        )
        saida["dono"] = [
            {"valor": r["login"], "id": r["id"], "rotulo": r["nome"], "n": r["n"]} for r in cur.fetchall()
        ]
        cur.execute(
            f"SELECT tag AS valor, count(*) AS n FROM (SELECT unnest(i.tags) AS tag {FROM_LISTA}{onde}) x "
            "GROUP BY 1 ORDER BY n DESC, 1 LIMIT 30",
            params,
        )
        saida["tags"] = [{"valor": r["valor"], "n": r["n"]} for r in cur.fetchall()]
        cur.execute(
            "SELECT k.id, k.caminho AS valor, count(*) AS n FROM (SELECT unnest(i.categorias) AS cid "
            f"{FROM_LISTA}{onde}) x "
            "JOIN plat.categoria k ON k.id = x.cid GROUP BY 1, 2 ORDER BY n DESC, 2 LIMIT 100",
            params,
        )
        saida["categoria"] = [{"id": str(r["id"]), "valor": r["valor"], "n": r["n"]} for r in cur.fetchall()]
    return saida


@router.get("/api/itens/tags", openapi_extra=LER)
def tags_sugerir(q: str = "", auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT tag, count(*) AS n FROM (SELECT unnest(tags) AS tag FROM plat.item WHERE apagado_em IS NULL) x "
            "WHERE tag ILIKE %s || '%%' GROUP BY 1 ORDER BY n DESC, 1 LIMIT 20",
            (q.replace("%", "").replace("_", "\\_")[:128],),
        )
        return [{"tag": r["tag"], "n": r["n"]} for r in cur.fetchall()]


# ---------------------------------------------------------------- criação e edição
def _classificacao(auth: Auth, valor: dict | None, novo: bool) -> None:
    cfg = (auth.config or {}).get("catalogo", {}).get("classificacao") or {}
    if not cfg.get("ativa"):
        return
    if valor is None:
        if novo and cfg.get("obrigatoria"):
            raise ErroAPI(422, "classificacao_obrigatoria", "o inquilino exige classificação em item novo")
        return
    esquema = cfg.get("esquema") or {"type": "object"}
    erros = [
        {"campo": ".".join(str(x) for x in e.absolute_path) or "(raiz)", "erro": e.message[:300], "regra": e.validator}
        for e in Draft202012Validator(esquema).iter_errors(valor)
    ]
    if erros:
        raise ErroAPI(422, "classificacao_invalida", "classificação fora do esquema do inquilino", erros)


def _pasta_existe(cur, pasta_id: str | None) -> None:
    if pasta_id is None:
        return
    cur.execute("SELECT 1 FROM plat.pasta WHERE id = %s::uuid", (pasta_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "pasta_inexistente", "pasta inexistente")


def _categorias_existem(cur, categorias: list[str]) -> list[str]:
    ids = [uuid_ok(c, "categoria_inexistente", "categoria inexistente") for c in categorias]
    if not ids:
        return []
    cur.execute("SELECT id FROM plat.categoria WHERE id = ANY (%s::uuid[])", (ids,))
    achadas = {str(r["id"]) for r in cur.fetchall()}
    faltam = [c for c in ids if c not in achadas]
    if faltam:
        raise ErroAPI(404, "categoria_inexistente", "categoria inexistente", {"ids": faltam})
    return list(dict.fromkeys(ids))


def _extent_sql(extent: list[float] | None) -> tuple[str, list]:
    if extent is None:
        return "NULL", []
    return "ST_MakeEnvelope(%s, %s, %s, %s, 4326)", list(extent)


def _publicar_tipo(auth: Auth, tipo: str) -> None:
    exigido = {
        "camada_vetorial": "conteudo.publicar_camada",
        "vista_de_camada": "conteudo.publicar_camada",
        "raster": "conteudo.publicar_raster",
        "conexao": "conteudo.registrar_fonte",
    }.get(tipo)
    if exigido and not auth.tem(exigido):
        raise ErroAPI(403, "sem_privilegio", f"a operação exige o privilégio {exigido}", {"exigido": exigido})


@router.post(
    "/api/itens",
    response_model=Item,
    status_code=201,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.criar"},
)
def criar(corpo: ItemEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    tipos.obter(corpo.tipo)
    _publicar_tipo(auth, corpo.tipo)
    tipos.validar(corpo.tipo, corpo.dados)
    documento.validar_grafo(corpo.tipo, corpo.dados)
    _classificacao(auth, corpo.classificacao, novo=True)
    iid = str(uuid.UUID(corpo.id)) if corpo.id else str(uuid.uuid4())
    ext_sql, ext_params = _extent_sql(corpo.extent)
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                "SELECT plat.cota_itens(%s) AS cota, (SELECT count(*) FROM plat.item WHERE tenant_id = %s) AS n",
                (auth.tenant_id, auth.tenant_id),
            )
            r = cur.fetchone()
            if r["n"] >= r["cota"]:
                raise ErroAPI(
                    413, "cota_itens", f"cota de itens do inquilino esgotada ({r['cota']})", {"cota": r["cota"]}
                )
            _pasta_existe(cur, corpo.pasta_id)
            cats = _categorias_existem(cur, corpo.categorias)
            cur.execute("SELECT 1 FROM plat.item WHERE id = %s::uuid", (iid,))
            if corpo.id and cur.fetchone() is not None:
                raise ErroAPI(409, "conflito", "já existe item com esse id")
            cur.execute(
                f"""
                INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, descricao, descricao_html, tags, creditos,
                                      termos_de_uso, termos_de_uso_html, dono_id, pasta_id, extent, extent_origem,
                                      dados, classificacao, categorias, origem, url, criado_por, modificado_por)
                VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s::text[], %s, %s, %s, %s, %s::uuid, {ext_sql}, %s, %s, %s,
                        %s::uuid[], %s, %s, %s, %s)""",
                [
                    iid,
                    auth.tenant_id,
                    corpo.tipo,
                    corpo.titulo.strip(),
                    corpo.resumo,
                    corpo.descricao,
                    texto.markdown_para_html(corpo.descricao),
                    corpo.tags,
                    corpo.creditos,
                    corpo.termos_de_uso,
                    texto.markdown_para_html(corpo.termos_de_uso),
                    auth.usuario_id,
                    corpo.pasta_id,
                ]
                + ext_params
                + [
                    corpo.extent_origem or ("usuario" if corpo.extent else None),
                    jsonb(corpo.dados),
                    jsonb(corpo.classificacao) if corpo.classificacao is not None else None,
                    cats,
                    corpo.origem,
                    corpo.url,
                    auth.usuario_id,
                    auth.usuario_id,
                ],
            )
            if relacoes.tem_extrator(corpo.tipo):
                relacoes.sincronizar(cur, auth.tenant_id, iid, relacoes.extrair(corpo.tipo, corpo.dados))
            registrar_evento(
                cur, request, "itens/adicionar", "item", iid, {"tipo": corpo.tipo, "titulo": corpo.titulo.strip()[:250]}
            )
            return item_json(item_ou_404(cur, iid), auth)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/itens/{id}", response_model=Item, openapi_extra=LER)
def ver(id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        r = item_ou_404(cur, id)
        j = item_json(r, auth)
        if isinstance(j.get("dados"), dict):
            migrado, mudou, de, para = documento.migrar_para_leitura(r["tipo"], j["dados"])
            if mudou:
                j["dados"] = migrado
                registrar_evento(
                    cur, request, "itens/esquema_migrado", "item", r["id"], {"tipo": r["tipo"], "de": de, "para": para}
                )
        return j


@router.get("/api/itens/{id}/metadado.xml", openapi_extra=LER)
def metadado_iso(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Metadado ISO 19139/GMD do item (item L0-09-metadado-catalogo; ADR 0004 D17). Validado contra o XSD
    oficial ANTES de sair (docs/xsd/cache/, baixado por docs/xsd/baixar_iso19139.py); `item_ou_404` + RLS de
    `plat.item` garantem que o token/sessão de um inquilino nunca gera o XML de item de outro."""
    with db.db(auth.contexto()) as cur:
        r = item_ou_404(cur, id)
    try:
        xml = metadado.gerar_xml(r, auth.tenant_nome, settings.PLAT_URL_PUBLICA.rstrip("/"))
        metadado.validar(xml)
    except metadado.ErroXSDAusente as e:
        raise ErroAPI(503, "indisponivel", "cache do XSD ISO 19139 ausente nesta máquina") from e
    except metadado.ErroMetadadoInvalido as e:
        # nunca deveria acontecer para um item bem formado; erro de build do gerador, não do pedido do cliente
        raise ErroAPI(500, "metadado_invalido", "metadado gerado não validou contra o XSD", e.erros) from e
    return Response(content=xml, media_type="application/xml")


def editar_item(
    cur, request: Request, auth: Auth, iid: str, campos: dict, rotulo: str | None = None, comentario: str | None = None
) -> dict:
    """Núcleo do PUT/PATCH e da restauração de versão: valida, grava, sincroniza relações, registra eventos."""
    r = exigir_edicao(cur, iid)
    try:
        e = ItemEditar.model_validate(campos)
    except pydantic.ValidationError as exc:
        # o corpo do PUT/PATCH já passou pelo modelo da rota; aqui entram os campos que só o núcleo conhece
        # (categorias, classificacao, dados de restauração de versão): o erro tem de sair no mesmo contrato 422
        # do tratador de app/erros.py, nunca como 500
        raise ErroAPI(
            422,
            "validacao",
            "pedido inválido: corpo ou parâmetros fora do esquema",
            [
                {
                    "campo": ".".join(str(x) for x in d.get("loc", ())),
                    "erro": d.get("msg", ""),
                    "tipo": d.get("type", ""),
                }
                for d in exc.errors()
            ],
        ) from exc
    campos = e.model_dump(exclude_unset=True)
    if "versao_atual" in campos:
        if campos["versao_atual"] is not None and campos["versao_atual"] != r["versao_atual"]:
            raise ErroAPI(
                409,
                "versao_conflito",
                "o item foi editado por outra pessoa; recarregue",
                {"versao_atual": r["versao_atual"]},
            )
        campos.pop("versao_atual")
    if not campos:
        raise ErroAPI(422, "validacao", "nada a alterar")
    dados = campos.get("dados", r["dados"])
    if "dados" in campos:
        tipos.validar(r["tipo"], dados)
        documento.validar_grafo(r["tipo"], dados)
    if "classificacao" in campos:
        _classificacao(auth, campos["classificacao"], novo=False)
    cats = (
        _categorias_existem(cur, campos["categorias"]) if "categorias" in campos else [str(c) for c in r["categorias"]]
    )
    status_novo = r["status"]
    if "status" in campos:
        status_novo = None if campos["status"] in (None, "nenhum") else campos["status"]
        if status_novo != r["status"]:
            if (status_novo == "autoritativo" or r["status"] == "autoritativo") and not auth.tem(
                "conteudo.editar_tudo"
            ):
                raise ErroAPI(
                    403,
                    "sem_privilegio",
                    "status autoritativo exige conteudo.editar_tudo",
                    {"exigido": "conteudo.editar_tudo"},
                )
    protegido = campos.get("protegido", r["protegido"])
    if protegido is None:
        protegido = r["protegido"]
    extent = campos.get("extent", None if r["xmin"] is None else [r["xmin"], r["ymin"], r["xmax"], r["ymax"]])
    ext_sql, ext_params = _extent_sql(extent)
    descricao = campos.get("descricao", r["descricao"])
    termos = campos.get("termos_de_uso", r["termos_de_uso"])
    if rotulo:
        rotular_versao(cur, rotulo, comentario)
    cur.execute(
        f"""
        UPDATE plat.item SET titulo = %s, resumo = %s, descricao = %s, descricao_html = %s,
               tags = %s::text[], creditos = %s,
               termos_de_uso = %s, termos_de_uso_html = %s, extent = {ext_sql}, extent_origem = %s,
                      categorias = %s::uuid[],
               classificacao = %s, url = %s, origem = %s, dados = %s, protegido = %s, status = %s
        WHERE id = %s::uuid""",
        [
            campos.get("titulo", r["titulo"]).strip(),
            campos.get("resumo", r["resumo"]),
            descricao,
            texto.markdown_para_html(descricao) if "descricao" in campos else r["descricao_html"],
            campos.get("tags", list(r["tags"] or [])),
            campos.get("creditos", r["creditos"]),
            termos,
            texto.markdown_para_html(termos) if "termos_de_uso" in campos else r["termos_de_uso_html"],
        ]
        + ext_params
        + [
            campos.get("extent_origem", r["extent_origem"] if "extent" not in campos else "usuario"),
            cats,
            jsonb(campos["classificacao"])
            if "classificacao" in campos and campos["classificacao"] is not None
            else (
                None
                if "classificacao" in campos
                else (jsonb(r["classificacao"]) if r["classificacao"] is not None else None)
            ),
            campos.get("url", r["url"]),
            campos.get("origem", r["origem"]),
            jsonb(dados),
            protegido,
            status_novo,
            iid,
        ],
    )
    if "dados" in campos and relacoes.tem_extrator(r["tipo"]):
        relacoes.sincronizar(cur, auth.tenant_id, iid, relacoes.extrair(r["tipo"], dados))
    novo = item_ou_404(cur, iid)
    mudados = sorted(k for k in campos if k in CAMPOS_VERSAO)
    if mudados:
        registrar_evento(
            cur, request, "itens/atualizar", "item", iid, {"campos": mudados, "versao": novo["versao_atual"]}
        )
    if status_novo != r["status"]:
        registrar_evento(cur, request, "itens/status", "item", iid, {"de": r["status"], "para": status_novo})
    if protegido != r["protegido"]:
        registrar_evento(cur, request, "itens/proteger" if protegido else "itens/desproteger", "item", iid)
    return novo


def _editar(id: str, corpo, request: Request, auth: Auth, rotulo: str | None = None) -> dict:
    iid = uuid_ok(id)
    campos = campos_json(corpo, set(CAMPOS_EDITAVEIS))
    try:
        with db.db(auth.contexto()) as cur:
            return item_json(editar_item(cur, request, auth, iid, campos, rotulo=rotulo), auth)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.put("/api/itens/{id}", response_model=Item, openapi_extra=EDITAR)
def editar(id: str, request: Request, corpo: dict = Body(...), auth: Auth = autenticado()):  # noqa: B008
    return _editar(id, corpo, request, auth)


@router.patch("/api/itens/{id}", response_model=Item, openapi_extra=EDITAR)
def editar_parcial(
    id: str,
    request: Request,
    corpo: dict = Body(...),  # noqa: B008
    rotulo: str | None = Query(default=None, pattern="^rascunho$"),
    auth: Auth = autenticado(),
):
    """item L5-09-desfazer-refazer-rascunho: `?rotulo=rascunho` é a ÚNICA forma de rótulo que o cliente pode
    pedir por fora (as outras — 'restauracao', 'publicacao', 'compactada', 'migracao' — só o servidor grava,
    ver `restaurar_versao`/`app/catalogo/comum.py::rotular_versao`). Grava uma versão nova rotulada 'rascunho'
    do MESMO jeito que o PATCH normal grava 'edicao': não toca `versao_publicada` (só
    `.../versoes/{n}/publicar` muda isso), então o link público de quem já publicou não se altera."""
    return _editar(id, corpo, request, auth, rotulo=rotulo)


# ---------------------------------------------------------------- exclusão lógica (lixeira) e lote
def apagar_item(cur, request: Request, auth: Auth, iid: str, cascata: bool, forcado: bool = False) -> list[str]:
    """Envia o item (e, com cascata, os dependentes na ordem) para a lixeira. Devolve os ids apagados."""
    r = item_ou_404(cur, iid)
    if not (r["pode_editar"] or auth.tem("conteudo.apagar_tudo") or forcado):
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    ordem = relacoes.ordem_de_exclusao(cur, iid)
    if ordem["ordem"] or ordem["ocultos"]:
        if not cascata or ordem["ocultos"] or any(not x["pode_editar"] for x in ordem["ordem"]):
            raise ErroAPI(
                409,
                "possui_dependentes",
                "outros itens dependem deste; apague-os antes ou use cascata=true",
                {"ordem": ordem["ordem"], "ocultos": ordem["ocultos"]},
            )
    apagados = []
    for dep in ordem["ordem"] if cascata else []:
        cur.execute("SELECT plat.item_lixeira(%s::uuid, true) AS ok", (dep["id"],))
        if cur.fetchone()["ok"]:
            apagados.append(dep["id"])
            registrar_evento(
                cur, request, "itens/apagar", "item", dep["id"], {"cascata": True, "de": iid, "forcado": forcado}
            )
    cur.execute("SELECT plat.item_lixeira(%s::uuid, true) AS ok", (iid,))
    if not cur.fetchone()["ok"]:
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    apagados.append(iid)
    props = {"cascata": cascata, "titulo": r["titulo"][:250]}
    if forcado:
        props.update({"forcado": True, "protegido_em": r["protegido"]})
    registrar_evento(cur, request, "itens/apagar", "item", iid, props)
    return apagados


@router.delete(
    "/api/itens/{id}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.apagar_tudo"},
)
def apagar(id: str, request: Request, cascata: bool = False, auth: Auth = autenticado(superadmin_pode_ler=True)):
    iid = uuid_ok(id)
    forcado = bool(auth.superadmin and auth.modo == "sessao" and auth.leitura_inquilino is not None)
    ctx = auth.contexto_leitura() if forcado else auth.contexto()
    try:
        with db.db(ctx) as cur:
            if forcado:
                ligar_superadmin(cur)
            apagar_item(cur, request, auth, iid, cascata, forcado)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    return Response(status_code=204)


@router.post("/api/itens/lote", response_model=LoteSaida, openapi_extra=EDITAR)
def lote(corpo: LoteEntrada, request: Request, auth: Auth = autenticado()):
    feitos, recusados = 0, []
    ids = [uuid_ok(i) for i in dict.fromkeys(corpo.ids)]
    for iid in ids:
        try:
            with db.db(auth.contexto()) as cur:
                if corpo.acao == "apagar":
                    apagar_item(cur, request, auth, iid, corpo.cascata)
                elif corpo.acao == "restaurar":
                    ligar_lixeira(cur)
                    cur.execute("SELECT plat.item_lixeira(%s::uuid, false) AS ok", (iid,))
                    if not cur.fetchone()["ok"]:
                        raise ErroAPI(404, "item_inexistente", "item inexistente")
                    registrar_evento(cur, request, "itens/restaurar", "item", iid)
                elif corpo.acao == "mover":
                    mover_item(cur, request, auth, iid, corpo.pasta_id)
                elif corpo.acao == "tags":
                    r = exigir_edicao(cur, iid)
                    atuais = list(r["tags"] or [])
                    if corpo.de is not None:
                        atuais = [corpo.para if t == corpo.de else t for t in atuais if corpo.para or t != corpo.de]
                    for t in corpo.tags or []:
                        if t not in atuais:
                            atuais.append(t)
                    editar_item(cur, request, auth, iid, {"tags": list(dict.fromkeys(atuais))[: limites.ITEM_TAGS_MAX]})
                elif corpo.acao == "categorias":
                    editar_item(cur, request, auth, iid, {"categorias": corpo.categorias or []})
                elif corpo.acao in ("proteger", "desproteger"):
                    editar_item(cur, request, auth, iid, {"protegido": corpo.acao == "proteger"})
                elif corpo.acao == "status":
                    editar_item(cur, request, auth, iid, {"status": corpo.status or "nenhum"})
                elif corpo.acao == "compartilhar":
                    from app.catalogo.rotas_compartilhamento import aplicar_compartilhamento

                    aplicar_compartilhamento(cur, request, auth, iid, corpo.acesso, corpo.grupos, None)
            feitos += 1
        except ErroAPI as e:
            recusados.append({"id": iid, "erro": e.erro, "mensagem": e.mensagem})
        except psycopg2.Error as e:
            err = comum.erro_do_banco(e)
            recusados.append({"id": iid, "erro": err.erro, "mensagem": err.mensagem})
    return {"feitos": feitos, "recusados": recusados}


def mover_item(cur, request: Request, auth: Auth, iid: str, pasta_id: str | None) -> dict:
    r = exigir_edicao(cur, iid)
    _pasta_existe(cur, pasta_id)
    cur.execute("UPDATE plat.item SET pasta_id = %s::uuid WHERE id = %s::uuid", (pasta_id, iid))
    registrar_evento(
        cur,
        request,
        "itens/mover",
        "item",
        iid,
        {"de_pasta": str(r["pasta_id"]) if r["pasta_id"] else None, "para_pasta": pasta_id},
    )
    return item_ou_404(cur, iid)


@router.post("/api/itens/{id}/mover", response_model=Item, openapi_extra=EDITAR)
def mover(id: str, corpo: MoverEntrada, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            return item_json(mover_item(cur, request, auth, iid, corpo.pasta_id), auth)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


# ---------------------------------------------------------------- versões
def _sha256_canonico_da_versao(r: dict) -> str | None:
    """`item_versao.sha256` (trigger `plat.tg_item_versao`) vem de `corpo::text` do jsonb inteiro — estável
    DENTRO deste Postgres, mas a serialização de jsonb (ordem de chave por comprimento, espaço depois de
    ':'/',') não é o que um `sha256sum` de fora reproduz sem reimplementar o formato interno do jsonb (item
    L5-05-documento-versoes, `app/catalogo/documento.py`). `sha256_canonico` é a conta À PARTE, sobre
    `dados.corpo` (json.dumps(sort_keys=True, separators=(",", ":"))) — reproduzível por qualquer ferramenta
    padrão. Vale para todo tipo cujo `dados` tenha um `corpo` objeto (não só as famílias de grafo: é genérico)."""
    dados = (r.get("corpo") or {}).get("dados")
    corpo = dados.get("corpo") if isinstance(dados, dict) else None
    return documento.sha256_canonico(corpo) if isinstance(corpo, dict) else None


def _versao_json(r: dict) -> dict:
    return {
        "versao": r["versao"],
        "sha256": r["sha256"],
        "sha256_canonico": _sha256_canonico_da_versao(r),
        "autor": None if r["autor_id"] is None else {"id": r["autor_id"], "login": r["autor_login"]},
        "rotulo": r["rotulo"],
        "comentario": r["comentario"],
        "compactou": r["compactou"],
        "criado_em": iso(r["criado_em"]),
    }


SQL_VERSAO = (
    "SELECT v.*, u.login AS autor_login FROM plat.item_versao v LEFT JOIN plat.usuario u ON u.id = v.autor_id "
    "WHERE v.item_id = %s::uuid"
)


@router.get("/api/itens/{id}/versoes", response_model=Pagina, openapi_extra=LER)
def versoes(
    id: str,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    iid = uuid_ok(id)
    lim, desl = paginacao(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, iid)
        cur.execute("SELECT count(*) AS n FROM plat.item_versao WHERE item_id = %s::uuid", (iid,))
        total = cur.fetchone()["n"]
        cur.execute(SQL_VERSAO + " ORDER BY v.versao DESC LIMIT %s OFFSET %s", (iid, lim, desl))
        return {"total": total, "itens": [_versao_json(r) for r in cur.fetchall()]}


@router.get("/api/itens/{id}/versoes/{n}", response_model=VersaoCompleta, openapi_extra=LER)
def versao(id: str, n: int, diff_de: int | None = None, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, iid)
        cur.execute(SQL_VERSAO + " AND v.versao = %s", (iid, n))
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "versao_inexistente", "versão inexistente")
        saida = _versao_json(r)
        saida["corpo"] = r["corpo"]
        if diff_de is not None:
            cur.execute("SELECT corpo FROM plat.item_versao WHERE item_id = %s::uuid AND versao = %s", (iid, diff_de))
            base = cur.fetchone()
            if base is None:
                raise ErroAPI(404, "versao_inexistente", "versão de comparação inexistente")
            saida["diff"] = diff.patch(base["corpo"], r["corpo"])
            saida["diff_de"] = diff_de
        return saida


@router.post("/api/itens/{id}/versoes/{n}/restaurar", response_model=Item, openapi_extra=EDITAR)
def restaurar_versao(
    id: str, n: int, request: Request, corpo: RestaurarVersaoEntrada | None = None, auth: Auth = autenticado()
):
    iid = uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            exigir_edicao(cur, iid)
            cur.execute("SELECT corpo FROM plat.item_versao WHERE item_id = %s::uuid AND versao = %s", (iid, n))
            v = cur.fetchone()
            if v is None:
                raise ErroAPI(404, "versao_inexistente", "versão inexistente")
            campos = {k: v["corpo"].get(k) for k in CAMPOS_VERSAO}
            comentario = (corpo.comentario if corpo else None) or f"restaurada da versão {n}"
            novo = editar_item(cur, request, auth, iid, campos, rotulo="restauracao", comentario=comentario)
            registrar_evento(
                cur, request, "itens/versao_restaurar", "item", iid, {"versao": n, "nova_versao": novo["versao_atual"]}
            )
            return item_json(novo, auth)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.post("/api/itens/{id}/versoes/{n}/publicar", response_model=Item, openapi_extra=EDITAR)
def publicar_versao(id: str, n: int, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        exigir_edicao(cur, iid)
        cur.execute("SELECT 1 FROM plat.item_versao WHERE item_id = %s::uuid AND versao = %s", (iid, n))
        if cur.fetchone() is None:
            raise ErroAPI(404, "versao_inexistente", "versão inexistente")
        cur.execute("UPDATE plat.item SET versao_publicada = %s WHERE id = %s::uuid", (n, iid))
        registrar_evento(cur, request, "itens/versao_publicar", "item", iid, {"versao": n})
        return item_json(item_ou_404(cur, iid), auth)


@router.get("/api/itens/{id}/integridade", openapi_extra=LER)
def integridade(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """item L5-05-documento-versoes: recomputa `sha256` de cada versão a partir do `corpo` GRAVADO em
    `plat.item_versao` e compara com o `sha256` da própria linha. As duas colunas só nascem juntas pelo gatilho
    `plat.tg_item_versao` (`app/catalogo/documento.py` explica por que o hash não é reproduzível por `sha256sum`
    puro fora deste Postgres — é `dados.corpo`, não `item_versao.corpo` inteiro, que tem o hash canônico
    externo); editar `corpo` direto no banco, por fora do gatilho, é exatamente o que este endpoint pega."""
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, iid)
        cur.execute(
            "SELECT versao, sha256 = encode(digest(corpo::text, 'sha256'), 'hex') AS integro "
            "FROM plat.item_versao WHERE item_id = %s::uuid ORDER BY versao",
            (iid,),
        )
        linhas = cur.fetchall()
        corrompidas = [r["versao"] for r in linhas if not r["integro"]]
        return {"integro": not corrompidas, "versoes": len(linhas), "versoes_corrompidas": corrompidas}


# ---------------------------------------------------------------- relações
@router.get("/api/itens/{id}/usado-por", response_model=list[UsadoPor], openapi_extra=LER)
def usado_por(id: str, profundidade: int = 2, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    profundidade = max(1, min(int(profundidade), limites.USADO_POR_PROFUNDIDADE_MAX))
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, iid)
        return relacoes.usado_por(cur, iid, profundidade)


@router.get("/api/itens/{id}/criado-a-partir-de", response_model=list[UsadoPor], openapi_extra=LER)
def criado_a_partir_de(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, iid)
        return relacoes.criado_a_partir_de(cur, iid)


@router.get("/api/itens/{id}/ordem-de-exclusao", response_model=OrdemExclusao, openapi_extra=LER)
def ordem_de_exclusao(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, iid)
        return relacoes.ordem_de_exclusao(cur, iid)


@router.put("/api/itens/{id}/relacoes", response_model=list[UsadoPor], openapi_extra=EDITAR)
def relacoes_definir(id: str, corpo: RelacoesEntrada, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            r = exigir_edicao(cur, iid)
            if relacoes.tem_extrator(r["tipo"]):
                raise ErroAPI(409, "relacoes_pelo_tipo", f"as relações de {r['tipo']} saem de dados; edite o item")
            cur.execute("SELECT nome FROM plat.relacao_tipo")
            vocab = {x["nome"] for x in cur.fetchall()}
            for rel in corpo.relacoes:
                if rel.tipo not in vocab:
                    raise ErroAPI(
                        422, "relacao_familia_invalida", "tipo de relação fora do vocabulário", {"tipo": rel.tipo}
                    )
            resultado = relacoes.sincronizar(
                cur, auth.tenant_id, iid, [(str(uuid.UUID(x.destino)), x.tipo, x.posicao) for x in corpo.relacoes]
            )
            registrar_evento(cur, request, "itens/relacoes", "item", iid, resultado)
            return relacoes.criado_a_partir_de(cur, iid)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


__all__ = ["router", "carregar", "listar_ids", "carregar_varios", "editar_item", "apagar_item", "mover_item"]
