"""Rotas /api/multiescala (item L3-19-multiescala): área de estudo, fator, amostra e execução macro/micro do
motor de grades aninhadas. Ver `app/multiescala/motor.py` para a mecânica (aninhamento aritmético, custo por
bloco na escala nativa) e `db/migracoes/20260906T1640_multiescala.sql` para o modelo de dado e o RLS.

Todas as tabelas são do INQUILINO (tenant_id + RLS, como conexão externa — não é registro compartilhado como
o acervo): qualquer usuário do inquilino lê tudo do inquilino e cria conjunto/fator/execução; não há um dono
exclusivo que bloqueie os demais (a política de INSERT da migração só exige `usuario_do_inquilino()`), então
o privilégio publicado é `rls:visibilidade`, igual ao resto do catálogo por inquilino."""

import json

import psycopg2
from fastapi import APIRouter, Query, Request

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.comum import paginacao, registrar_evento
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import uuid_ok
from app.erros import ErroAPI
from app.multiescala import crs as crs_mod
from app.multiescala import motor
from app.multiescala.modelos import (
    AmostrasEntrada,
    AmostrasResultado,
    Conjunto,
    ConjuntoEntrada,
    ConjuntoPagina,
    Execucao,
    ExecucaoEntrada,
    ExecucaoPagina,
    Fator,
    FatorEntrada,
    FatorPagina,
)

router = APIRouter(prefix="/api/multiescala", tags=["multiescala"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCOPO = "multiescala:usar"


# ------------------------------------------------------------------ apoio


def _conjunto_json(r: dict) -> dict:
    # `area` (GeoJSON) só quando a consulta a trouxe como texto (ST_AsGeoJSON): a tela do motor desenha o polígono
    area = r.get("area_geojson")
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "area": json.loads(area) if isinstance(area, str) else (area if isinstance(area, dict) else None),
        "srid_trabalho": r["srid_trabalho"],
        "srid_nome": crs_mod.nome_do_srid(r["srid_trabalho"]),
        "origem_x_m": float(r["origem_x_m"]),
        "origem_y_m": float(r["origem_y_m"]),
        "largura_m": float(r["largura_m"]),
        "altura_m": float(r["altura_m"]),
        "criado_em": iso(r["criado_em"]),
    }


def _fator_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "resolucao_fonte_m": float(r["resolucao_fonte_m"]),
        "papel": r["papel"],
        "unidade": r["unidade"],
        "fonte": r["fonte"],
        "criado_em": iso(r["criado_em"]),
    }


def _carregar_conjunto(cur, cid: str) -> dict:
    cur.execute("SELECT *, ST_AsGeoJSON(area, 7) AS area_geojson FROM plat.escala_conjunto WHERE id = %s::uuid", (cid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "conjunto_inexistente", "área de estudo inexistente")
    return r


def _carregar_fator(cur, fid: str) -> dict:
    cur.execute("SELECT * FROM plat.escala_fator WHERE id = %s::uuid", (fid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "fator_inexistente", "fator inexistente")
    return r


def _carregar_grade(cur, gid: str) -> dict:
    cur.execute("SELECT * FROM plat.escala_grade WHERE id = %s::uuid", (gid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "grade_inexistente", "grade inexistente")
    return r


def _carregar_execucao(cur, eid: str) -> dict:
    cur.execute("SELECT * FROM plat.escala_execucao WHERE id = %s::uuid", (eid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "execucao_inexistente", "execução inexistente")
    return r


def _relatorio(cur, execucao: dict) -> dict:
    """Execução + grade + o relatório por fator (nome, escala declarada, `escala_grosseira`) — é este relatório
    que prova a cláusula do portão ('relatório declara a escala de cada fator') e a refutação exigida."""
    grade = _carregar_grade(cur, str(execucao["grade_id"]))
    cur.execute(
        "SELECT ef.fator_id, f.nome, ef.peso, ef.resolucao_fonte_m, ef.resolucao_grade_m, ef.razao_escala, "
        "ef.escala, ef.escala_grosseira, ef.blocos_usados, ef.blocos_calculados, ef.celulas_com_dado, "
        "ef.valor_min, ef.valor_max "
        "FROM plat.escala_execucao_fator ef JOIN plat.escala_fator f ON f.id = ef.fator_id "
        "WHERE ef.execucao_id = %s::uuid ORDER BY f.nome",
        (str(execucao["id"]),),
    )
    fatores = [
        {
            "fator_id": str(f["fator_id"]),
            "nome": f["nome"],
            "peso": float(f["peso"]),
            "resolucao_fonte_m": float(f["resolucao_fonte_m"]),
            "resolucao_grade_m": float(f["resolucao_grade_m"]),
            "razao_escala": float(f["razao_escala"]),
            "escala": f["escala"],
            "escala_grosseira": bool(f["escala_grosseira"]),
            "blocos_usados": f["blocos_usados"],
            "blocos_calculados": f["blocos_calculados"],
            "celulas_com_dado": f["celulas_com_dado"],
            "valor_min": float(f["valor_min"]) if f["valor_min"] is not None else None,
            "valor_max": float(f["valor_max"]) if f["valor_max"] is not None else None,
        }
        for f in cur.fetchall()
    ]
    return {
        "id": str(execucao["id"]),
        "conjunto_id": str(execucao["conjunto_id"]),
        "nivel": execucao["nivel"],
        "execucao_pai_id": str(execucao["execucao_pai_id"]) if execucao["execucao_pai_id"] else None,
        "aprovacao_tipo": execucao["aprovacao_tipo"],
        "aprovacao_valor": float(execucao["aprovacao_valor"]),
        "celulas": execucao["celulas"],
        "celulas_possiveis": execucao["celulas_possiveis"],
        "celulas_com_nota": execucao["celulas_com_nota"],
        "celulas_aprovadas": execucao["celulas_aprovadas"],
        "duracao_ms": execucao["duracao_ms"],
        "criado_em": iso(execucao["criado_em"]),
        "grade": {
            "id": str(grade["id"]),
            "nivel": grade["nivel"],
            "resolucao_m": float(grade["resolucao_m"]),
            "fator_aninhamento": grade["fator_aninhamento"],
            "colunas": grade["colunas"],
            "linhas": grade["linhas"],
            "celulas": grade["celulas"],
            "celulas_possiveis": grade["celulas_possiveis"],
        },
        "fatores": fatores,
    }


def _aprovacao_valor_ok(tipo: str, valor: float) -> None:
    if tipo == "top_pct" and not (0 < valor <= 100):
        raise ErroAPI(422, "aprovacao_valor_invalido", "aprovacao_valor de top_pct precisa estar em (0, 100]")
    if tipo == "limiar" and not (0 <= valor <= 100):
        raise ErroAPI(422, "aprovacao_valor_invalido", "aprovacao_valor de limiar precisa estar em [0, 100]")


# ------------------------------------------------------------------ conjunto (área de estudo)


@router.post("/conjuntos", response_model=Conjunto, status_code=201, openapi_extra=LER)
def criar_conjunto(corpo: ConjuntoEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    with db.db(auth.contexto()) as cur:
        try:
            r = motor.criar_conjunto(cur, auth.tenant_id, auth.usuario_id, " ".join(corpo.nome.split()), corpo.area)
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe uma área de estudo com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "multiescala/conjunto", "escala_conjunto", r["id"],
                         {"nome": r["nome"], "srid_trabalho": r["srid_trabalho"]})
        return _conjunto_json(r)


@router.get("/conjuntos", response_model=ConjuntoPagina, openapi_extra=LER)
def listar_conjuntos(limite: int | None = None, deslocamento: int | None = None,
                     auth: Auth = autenticado(escopo_token=ESCOPO)):
    lim, desl = paginacao(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.escala_conjunto")
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT *, ST_AsGeoJSON(area, 7) AS area_geojson FROM plat.escala_conjunto ORDER BY lower(nome) "
            "LIMIT %s OFFSET %s",
            (lim, desl),
        )
        itens = [_conjunto_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/conjuntos/{id}", response_model=Conjunto, openapi_extra=LER)
def ver_conjunto(id: str, auth: Auth = autenticado(escopo_token=ESCOPO)):
    cid = uuid_ok(id, "conjunto_inexistente", "área de estudo inexistente")
    with db.db(auth.contexto()) as cur:
        return _conjunto_json(_carregar_conjunto(cur, cid))


@router.delete("/conjuntos/{id}", status_code=204, openapi_extra=LER)
def apagar_conjunto(id: str, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Cascata (FK `ON DELETE CASCADE` da migração): apaga grades, células, execuções e seus fatores/resultados
    do conjunto inteiro. Nenhum fator é apagado (fatores são do inquilino, reusáveis entre conjuntos)."""
    cid = uuid_ok(id, "conjunto_inexistente", "área de estudo inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar_conjunto(cur, cid)
        cur.execute("DELETE FROM plat.escala_conjunto WHERE id = %s::uuid", (cid,))
        registrar_evento(cur, request, "multiescala/conjunto_apagar", "escala_conjunto", cid, {"nome": r["nome"]})


# ------------------------------------------------------------------ fator


@router.post("/fatores", response_model=Fator, status_code=201, openapi_extra=LER)
def criar_fator(corpo: FatorEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.escala_fator(tenant_id, nome, resolucao_fonte_m, papel, unidade, fonte, dono_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (auth.tenant_id, " ".join(corpo.nome.split()), corpo.resolucao_fonte_m, corpo.papel,
                 corpo.unidade, corpo.fonte, auth.usuario_id),
            )
            r = cur.fetchone()
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe um fator com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "multiescala/fator", "escala_fator", r["id"],
                         {"nome": r["nome"], "resolucao_fonte_m": float(r["resolucao_fonte_m"]), "papel": r["papel"]})
        return _fator_json(r)


@router.get("/fatores", response_model=FatorPagina, openapi_extra=LER)
def listar_fatores(limite: int | None = None, deslocamento: int | None = None,
                   auth: Auth = autenticado(escopo_token=ESCOPO)):
    lim, desl = paginacao(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.escala_fator")
        total = cur.fetchone()["n"]
        cur.execute("SELECT * FROM plat.escala_fator ORDER BY lower(nome) LIMIT %s OFFSET %s", (lim, desl))
        itens = [_fator_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/fatores/{id}", response_model=Fator, openapi_extra=LER)
def ver_fator(id: str, auth: Auth = autenticado(escopo_token=ESCOPO)):
    fid = uuid_ok(id, "fator_inexistente", "fator inexistente")
    with db.db(auth.contexto()) as cur:
        return _fator_json(_carregar_fator(cur, fid))


@router.delete("/fatores/{id}", status_code=204, openapi_extra=LER)
def apagar_fator(id: str, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Cascata: amostras, blocos calculados e as linhas do fator em qualquer execução (passada ou futura) que
    o tenha usado. A execução em si (e o resultado por célula dos OUTROS fatores dela) não é afetada."""
    fid = uuid_ok(id, "fator_inexistente", "fator inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar_fator(cur, fid)
        cur.execute("DELETE FROM plat.escala_fator WHERE id = %s::uuid", (fid,))
        registrar_evento(cur, request, "multiescala/fator_apagar", "escala_fator", fid, {"nome": r["nome"]})


@router.post("/fatores/{id}/amostras", response_model=AmostrasResultado, status_code=201, openapi_extra=LER)
def carregar_amostras(id: str, corpo: AmostrasEntrada, request: Request,
                      auth: Auth = autenticado(escopo_token=ESCOPO)):
    fid = uuid_ok(id, "fator_inexistente", "fator inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar_fator(cur, fid)
        cur.executemany(
            "INSERT INTO plat.escala_amostra(tenant_id, fator_id, geom, valor) "
            "VALUES (%s, %s::uuid, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)",
            [(auth.tenant_id, fid, a.lon, a.lat, a.valor) for a in corpo.amostras],
        )
        gravadas = len(corpo.amostras)
        registrar_evento(cur, request, "multiescala/amostras", "escala_fator", fid, {"quantidade": gravadas})
        return {"fator_id": fid, "gravadas": gravadas}


# ------------------------------------------------------------------ execução macro e micro


@router.post("/conjuntos/{id}/macro", response_model=Execucao, status_code=201, openapi_extra=LER)
def executar_macro(id: str, corpo: ExecucaoEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Gera a grade macro sobre a área inteira e executa a combinação — a primeira das 'duas execuções
    ligadas' do portão. `aprovacao_tipo`/`aprovacao_valor` decidem as regiões que seguem para o micro."""
    cid = uuid_ok(id, "conjunto_inexistente", "área de estudo inexistente")
    _aprovacao_valor_ok(corpo.aprovacao_tipo, corpo.aprovacao_valor)
    with db.db(auth.contexto()) as cur:
        conjunto = _carregar_conjunto(cur, cid)
        grade = motor.gerar_grade_macro(cur, auth.tenant_id, conjunto, corpo.resolucao_m)
        fatores = [motor.FatorPedido(f.fator_id, f.peso) for f in corpo.fatores]
        execucao = motor.executar(cur, auth.tenant_id, auth.usuario_id, conjunto, grade, fatores,
                                  corpo.aprovacao_tipo, corpo.aprovacao_valor)
        registrar_evento(cur, request, "multiescala/macro", "escala_execucao", execucao["id"], {
            "conjunto_id": cid, "resolucao_m": corpo.resolucao_m, "celulas": execucao["celulas"],
            "celulas_aprovadas": execucao["celulas_aprovadas"],
        })
        return _relatorio(cur, execucao)


@router.get("/execucoes/{id}/celulas", openapi_extra=LER)
def celulas_da_execucao(id: str, limite: int | None = Query(None, ge=1, le=limites.ESCALA_CELULAS_GEOJSON_MAX),
                        auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Item UX-08: as células de uma execução como FeatureCollection (nota 0-100, cobertura, aprovada, col, lin)
    para o visualizador pintar a grade. Só leitura; até ESCALA_CELULAS_GEOJSON_MAX feições, ordenadas por linha e
    coluna; a resposta declara `total` e `truncado` para a tela nunca fingir que mostrou tudo."""
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    lim = limite or limites.ESCALA_CELULAS_GEOJSON_MAX
    with db.db(auth.contexto()) as cur:
        execucao = _carregar_execucao(cur, eid)
        cur.execute(
            "SELECT count(*) AS n FROM plat.escala_resultado WHERE execucao_id = %s::uuid", (eid,)
        )
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT c.col, c.lin, r.nota, r.cobertura, r.aprovada, ST_AsGeoJSON(c.geom, 7) AS geom "
            "FROM plat.escala_resultado r JOIN plat.escala_celula c ON c.id = r.celula_id "
            "WHERE r.execucao_id = %s::uuid ORDER BY c.lin, c.col LIMIT %s",
            (eid, lim),
        )
        feicoes = [
            {
                "type": "Feature",
                "geometry": json.loads(f["geom"]),
                "properties": {
                    "col": f["col"], "lin": f["lin"],
                    "nota": float(f["nota"]) if f["nota"] is not None else None,
                    "cobertura": float(f["cobertura"]), "aprovada": bool(f["aprovada"]),
                },
            }
            for f in cur.fetchall()
        ]
    return {
        "type": "FeatureCollection", "features": feicoes,
        "execucao_id": str(execucao["id"]), "nivel": execucao["nivel"], "total": total,
        "truncado": total > len(feicoes),
    }


@router.post("/execucoes/{id}/micro", response_model=Execucao, status_code=201, openapi_extra=LER)
def executar_micro(id: str, corpo: ExecucaoEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Gera a grade micro SÓ dentro das regiões aprovadas pela execução macro `id` e executa a combinação — a
    segunda das 'duas execuções ligadas'. Célula micro fora das regiões macro nunca é gerada (aritmético, não
    filtrado depois): é a cláusula central do portão."""
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    _aprovacao_valor_ok(corpo.aprovacao_tipo, corpo.aprovacao_valor)
    with db.db(auth.contexto()) as cur:
        execucao_pai = _carregar_execucao(cur, eid)
        if execucao_pai["nivel"] != "macro":
            raise ErroAPI(422, "nivel_invalido", "o micro só pode ser ligado a uma execução macro")
        conjunto = _carregar_conjunto(cur, str(execucao_pai["conjunto_id"]))
        macro_grade = _carregar_grade(cur, str(execucao_pai["grade_id"]))
        grade = motor.gerar_grade_micro(cur, auth.tenant_id, conjunto, macro_grade, eid, corpo.resolucao_m)
        fatores = [motor.FatorPedido(f.fator_id, f.peso) for f in corpo.fatores]
        execucao = motor.executar(cur, auth.tenant_id, auth.usuario_id, conjunto, grade, fatores,
                                  corpo.aprovacao_tipo, corpo.aprovacao_valor, execucao_pai_id=eid)
        economia_pct = (
            100.0 * (1.0 - execucao["celulas"] / execucao["celulas_possiveis"])
            if execucao["celulas_possiveis"] else 0.0
        )
        registrar_evento(cur, request, "multiescala/micro", "escala_execucao", execucao["id"], {
            "execucao_pai_id": eid, "resolucao_m": corpo.resolucao_m, "celulas": execucao["celulas"],
            "celulas_possiveis": execucao["celulas_possiveis"], "economia_pct": round(economia_pct, 1),
        })
        return _relatorio(cur, execucao)


@router.get("/execucoes/{id}", response_model=Execucao, openapi_extra=LER)
def ver_execucao(id: str, auth: Auth = autenticado(escopo_token=ESCOPO)):
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    with db.db(auth.contexto()) as cur:
        execucao = _carregar_execucao(cur, eid)
        return _relatorio(cur, execucao)


@router.get("/execucoes", response_model=ExecucaoPagina, openapi_extra=LER)
def listar_execucoes(conjunto_id: str | None = Query(default=None), limite: int | None = None,
                     deslocamento: int | None = None, auth: Auth = autenticado(escopo_token=ESCOPO)):
    lim, desl = paginacao(limite, deslocamento)
    onde, params = ["true"], []
    if conjunto_id:
        onde.append("conjunto_id = %s::uuid")
        params.append(conjunto_id)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.escala_execucao WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT * FROM plat.escala_execucao WHERE {filtro} ORDER BY criado_em DESC LIMIT %s OFFSET %s",  # noqa: S608
            [*params, lim, desl],
        )
        itens = [_relatorio(cur, r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}
