"""Rotas das regras de atributo (item L2-10-d-regras-de-atributo):
  GET/PUT /api/camadas/{id}/regras     — ler/definir regras e campos virtuais (compila: expressão, campos, ciclo)
  POST    /api/camadas/{id}/validar    — enfileira o job camadas.validar (regras de validação -> camada de erros)
  GET     /api/camadas/{id}/feicoes    — leitura de feições COM os campos virtuais (o que popup/tabela consomem;
                                          o FeatureServer real é o L2-04, ainda parcial — esta é a leitura da casa)
  GET     /api/camadas/{id}/erros      — erros da última validação (tabela e_<hex16>)."""

from __future__ import annotations

import json

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Query, Request

from app import db, limites
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.edicao.servico import camada_ou_404
from app.erros import ErroAPI
from app.jobs import servico as jobs_servico
from app.jobs.contexto import ErroServico, dependencia_jobs, sessao_de
from app.regras import motor
from app.regras.modelos import ErrosSaida, FeicoesSaida, RegrasEntrada, RegrasSaida, ValidarSaida

router = APIRouter(tags=["regras"])
AUTH_JOBS = dependencia_jobs()  # singleton de módulo, como em app/jobs/rotas.py
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
DEFINIR = {"x-auth": "S/T", "x-privilegio": "conteudo.editar"}


def _ident(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def _exigir_edicao_do_item(cur, auth: Auth, iid: str) -> None:
    cur.execute("SELECT plat.pode_editar(%s::uuid) AS pode", (iid,))
    r = cur.fetchone()
    if not r or not r["pode"]:
        raise ErroAPI(403, "sem_permissao", "sem permissão de edição neste item")


def _saida(iid: str, dados: dict) -> RegrasSaida:
    comp = motor.compilar(dados)
    return RegrasSaida(
        camada_id=iid, regras=dados.get("regras") or [], campos_virtuais=dados.get("campos_virtuais") or [],
        validacao=dados.get("validacao"), ordem_de_avaliacao=[r.id for r in comp.regras],
    )


@router.get("/api/camadas/{id}/regras", response_model=RegrasSaida, openapi_extra=LER)
def regras_ler(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        _, dados = camada_ou_404(cur, iid)
    return _saida(iid, dados)


@router.put("/api/camadas/{id}/regras", response_model=RegrasSaida, openapi_extra=DEFINIR)
def regras_definir(
    id: str, corpo: RegrasEntrada, request: Request,
    auth: Auth = autenticado("conteudo.editar", escopo_token="camada:editar"),
):
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    regras = [r.model_dump(exclude_none=True) for r in corpo.regras]
    virtuais = [v.model_dump(exclude_none=True) for v in corpo.campos_virtuais]
    with db.db(auth.contexto()) as cur:
        item, dados = camada_ou_404(cur, iid)
        _exigir_edicao_do_item(cur, auth, iid)
        novos = {**dados, "regras": regras, "campos_virtuais": virtuais}
        comp = motor.compilar(novos)  # 422 nomeado antes de gravar (expressão, campo, ciclo)
        cur.execute(
            "UPDATE plat.item SET dados = dados || %s::jsonb, modificado_em = now(), modificado_por = %s "
            "WHERE id = %s::uuid",
            (json.dumps({"regras": regras, "campos_virtuais": virtuais}, ensure_ascii=False), auth.usuario_id, iid),
        )
        comum.registrar_evento(
            cur, request, "camadas/regras_definir", "item", iid,
            {"regras": len(regras), "campos_virtuais": len(virtuais), "ordem": [r.id for r in comp.regras],
             "tipos": {t: sum(1 for r in comp.regras if r.tipo == t) for t in motor.TIPOS}},
        )
    return _saida(iid, novos)


@router.post("/api/camadas/{id}/validar", response_model=ValidarSaida, status_code=201,
             openapi_extra={"x-auth": "S/T", "x-privilegio": "jobs.executar"})
def validar(id: str, request: Request, auth: Auth = AUTH_JOBS):
    """Enfileira `camadas.validar` para a camada: avalia toda regra de validação habilitada em cada feição e grava
    os erros em e_<hex16> + camada de erros (equivalente ao Evaluate Rules). Evento `jobs/criar` (do serviço)."""
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        _, dados = camada_ou_404(cur, iid)
        _exigir_edicao_do_item(cur, auth, iid)
        if not any(r.get("tipo") == "validacao" and r.get("habilitada", True) for r in dados.get("regras") or []):
            raise ErroAPI(422, "sem_regra_de_validacao", "a camada não tem regra de validação habilitada")
    try:
        job = jobs_servico.criar(sessao_de(auth), "camadas.validar", {"item_id": iid})
    except ErroServico as e:
        raise ErroAPI(e.status, e.codigo, e.mensagem, e.detalhe) from e
    return ValidarSaida(job_id=str(job["id"]), estado=job["estado"])


@router.get("/api/camadas/{id}/feicoes", response_model=FeicoesSaida, openapi_extra=LER)
def feicoes_ler(
    id: str,
    auth: Auth = autenticado(escopo_token="camada:ler"),
    limite: int = Query(100, ge=1, le=limites.REGRAS_FEICOES_LEITURA_MAX),
    deslocamento: int = Query(0, ge=0),
    fid: int | None = Query(None, ge=1),
):
    """Feições com atributos, geometria (GeoJSON) e os CAMPOS VIRTUAIS avaliados na leitura (só leitura; nunca
    gravados). É a leitura que popup e tabela usam até o FeatureServer (L2-04) entrar."""
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        _, dados = camada_ou_404(cur, iid)
        comp = motor.compilar(dados)
        schema, tabela = dados["schema"], dados["tabela"]
        tem_geom = dados.get("geometria") not in (None, "nenhuma")
        fixas = [_ident(c) for c in ("fid", "globalid", "versao")]
        colunas = ", ".join(fixas + [_ident(c) for c in sorted(comp.campos)])
        geom = ", ST_AsGeoJSON(geom)::json AS __geom" if tem_geom else ""
        onde = " WHERE fid = %s" if fid is not None else ""
        params: list = [fid] if fid is not None else []
        try:
            cur.execute(f'SELECT count(*) AS n FROM {_ident(schema)}.{_ident(tabela)}{onde}', params)
            total = cur.fetchone()["n"]
            cur.execute(
                f'SELECT {colunas}{geom} FROM {_ident(schema)}.{_ident(tabela)}{onde} ORDER BY fid LIMIT %s OFFSET %s',
                [*params, limite, deslocamento],
            )
            linhas = cur.fetchall()
        except psycopg2.Error as e:
            raise comum.erro_do_banco(e) from e
    itens = []
    for li in linhas:
        atributos = {k: motor.valor_para_contexto(v) for k, v in li.items() if k != "__geom"}
        atributos.update(motor.valores_virtuais(comp, li))
        itens.append({"fid": li["fid"], "id": str(li["globalid"]), "versao": li["versao"], "atributos": atributos,
                      "geometria": li.get("__geom")})
    return FeicoesSaida(total=total, itens=itens, campos_virtuais=[v.nome for v in comp.virtuais])


@router.get("/api/camadas/{id}/erros", response_model=ErrosSaida, openapi_extra=LER)
def erros_ler(
    id: str,
    auth: Auth = autenticado(escopo_token="camada:ler"),
    limite: int = Query(100, ge=1, le=limites.REGRAS_FEICOES_LEITURA_MAX),
    deslocamento: int = Query(0, ge=0),
):
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        _, dados = camada_ou_404(cur, iid)
        validacao = dados.get("validacao") or {}
        tabela = validacao.get("tabela_erros")
        if not tabela:
            return ErrosSaida(total=0, itens=[], validacao=validacao or None)
        try:
            cur.execute(f'SELECT count(*) AS n FROM {_ident(dados["schema"])}.{_ident(tabela)}')
            total = cur.fetchone()["n"]
            cur.execute(
                f"SELECT fid, feicao_fid, feicao_globalid::text AS feicao_id, regra, codigo, mensagem, em "
                f'FROM {_ident(dados["schema"])}.{_ident(tabela)} ORDER BY feicao_fid, regra LIMIT %s OFFSET %s',
                (limite, deslocamento),
            )
            linhas = [dict(r) for r in cur.fetchall()]
        except psycopg2.Error as e:
            raise comum.erro_do_banco(e) from e
    return ErrosSaida(total=total, itens=linhas, validacao=validacao)
