"""Rotas de área suja e validação incremental (item L4-03-d-areas-sujas-e-validacao; ADR
docs/adr/20260907T1243-areas-sujas-e-validacao.md).

Cinco pontas, além do que `rotas_regras.apply_edits` já grava (uma área suja por feição tocada, ver lá):

- `GET /api/rede/{rede_id}/areas_sujas` — camada (GeoJSON `FeatureCollection`) das áreas sujas ATIVAS; é
  isso que "editar 1 trecho cria 1 área suja visível no mapa" quer dizer na prática.
- `POST /api/rede/{rede_id}/validar_extensao` — valida só dentro de uma extensão (corpo com `extensao`
  GeoJSON) ou de TODAS as áreas sujas ativas (`extensao: null`, "validar tudo"). Roda as 15 checagens de
  `validacao.py` restritas ao escopo, grava os erros como feição em `plat.rede_erro` (substituindo os
  antigos DAS MESMAS feições, para revalidar não duplicar) e marca as áreas processadas como limpas. Mede
  `feicoes_em_escopo` contra `feicoes_total` — é a prova de "contagem de linhas reescritas ≪ total".
- `GET /api/rede/{rede_id}/erros` — camada dos erros vigentes (a mesma ideia de "aparecem como camada").
- `GET /api/rede/{rede_id}/tracar` — ponto de partida de um traçado (feição existente ou geometria solta,
  em query string); GET porque só lê (nunca deriva conexão nem grava nada) — a mesma classe de rota que
  `regras.csv` GET ou `regras` GET, `rls:visibilidade`, não `rede.editar`. Se cruza uma área suja ativa,
  devolve aviso com o polígono (200) ou recusa (409), conforme `rede.tracado_sobre_area_suja_modo`.
- `PUT /api/rede/{rede_id}/area_sujas/modo` — troca 'avisar'/'bloquear'. Só `rede.administrar`, mesmo padrão
  de `rotas_regras.ativar_regras`: comporta de configuração, não campo de edição de feição."""

import datetime
import json
import os
import time

from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import areas_sujas, deposito, validacao
from app.rede_utilidades.modelos import (
    ModoTracadoEntrada,
    ModoTracadoResultado,
    TracadoResultado,
    ValidacaoExtensaoEntrada,
    ValidacaoExtensaoResultado,
)
from app.rede_utilidades.rotas import _uuid_ok
from app.rede_utilidades.rotas_regras import _carregar_rede, _exigir_pacote

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
ADMIN = {"x-auth": "S/T", "x-privilegio": "rede.administrar"}


def _carga_maquina() -> tuple[float, float]:
    """`(carga_1min, ram_livre_gb)` — gravados junto de toda medida de tempo/taxa (regra do brief de
    07/09: número de desempenho sem a carga ao lado não vale como prova)."""
    try:
        carga_1min = os.getloadavg()[0]
    except OSError:
        carga_1min = -1.0
    ram_livre_gb = -1.0
    try:
        with open("/proc/meminfo") as fh:
            info = {}
            for linha in fh:
                partes = linha.split(":")
                if len(partes) == 2:
                    info[partes[0].strip()] = partes[1].strip()
        disponivel_kb = info.get("MemAvailable", "0 kB").split()[0]
        ram_livre_gb = round(int(disponivel_kb) / 1024 / 1024, 2)
    except OSError:
        pass
    return carga_1min, ram_livre_gb


def _feicao_geojson(campo) -> dict | None:
    return json.loads(campo) if campo else None


@router.get("/{rede_id}/areas_sujas", openapi_extra=LER)
def listar_areas_sujas(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _carregar_rede(cur, rid)
        linhas = areas_sujas.listar(cur, rid, apenas_ativas=True)
    features = [
        {
            "type": "Feature",
            "id": str(r["id"]),
            "geometry": _feicao_geojson(r["geojson"]),
            "properties": {
                "feicao_id": str(r["feicao_id"]) if r["feicao_id"] else None,
                "versao": r["versao"],
                "criado_em": r["criado_em"].isoformat() if hasattr(r["criado_em"], "isoformat") else r["criado_em"],
            },
        }
        for r in linhas
    ]
    return {"type": "FeatureCollection", "features": features, "numberReturned": len(features)}


@router.get("/{rede_id}/erros", openapi_extra=LER)
def listar_erros(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _carregar_rede(cur, rid)
        cur.execute(
            "SELECT id, codigo, mensagem, feicao_id, tipo_referencia, detalhe, versao, gerado_em, "
            "ST_AsGeoJSON(geometria) AS geojson FROM plat.rede_erro WHERE rede_id = %s::uuid ORDER BY gerado_em",
            (rid,),
        )
        linhas = cur.fetchall()
    features = [
        {
            "type": "Feature",
            "id": str(r["id"]),
            "geometry": _feicao_geojson(r["geojson"]),
            "properties": {
                "codigo": r["codigo"], "mensagem": r["mensagem"],
                "feicao_id": str(r["feicao_id"]) if r["feicao_id"] else None,
                "tipo_referencia": r["tipo_referencia"], "detalhe": r["detalhe"], "versao": r["versao"],
                "gerado_em": r["gerado_em"].isoformat() if hasattr(r["gerado_em"], "isoformat") else r["gerado_em"],
            },
        }
        for r in linhas
    ]
    return {"type": "FeatureCollection", "features": features, "numberReturned": len(features)}


def _feicoes_total(cur, rid: str) -> int:
    cur.execute(
        "SELECT count(*) AS n FROM plat.rede_feicao WHERE rede_id = %s::uuid AND geometria IS NOT NULL",
        (rid,),
    )
    return cur.fetchone()["n"]


def _gravar_erros(cur, tenant_id: int, rid: str, versao: int, feicao_ids: list[str], erros: list[dict]) -> int:
    """Substitui os erros vigentes DAS FEIÇÕES DO ESCOPO (não da rede inteira — revalidar uma extensão
    pequena não apaga o que outra extensão gravou) e insere os novos. Erros de âmbito da rede (feicao_id
    NULL, ex. `tipo_sem_regra_no_pacote` sem exemplo no escopo) são substituídos por CÓDIGO, já que não têm
    feição para escopar."""
    if feicao_ids:
        cur.execute(
            "DELETE FROM plat.rede_erro WHERE rede_id = %s::uuid AND feicao_id = ANY(%s::uuid[])",
            (rid, feicao_ids),
        )
    codigos_sem_feicao = {e["codigo"] for e in erros if e.get("feicao_id") is None}
    if codigos_sem_feicao:
        cur.execute(
            "DELETE FROM plat.rede_erro WHERE rede_id = %s::uuid AND feicao_id IS NULL AND codigo = ANY(%s)",
            (rid, list(codigos_sem_feicao)),
        )
    for e in erros:
        cur.execute(
            "INSERT INTO plat.rede_erro(tenant_id, rede_id, codigo, mensagem, feicao_id, tipo_referencia, "
            "detalhe, geometria, versao) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s)",
            (tenant_id, rid, e["codigo"], e["mensagem"], e.get("feicao_id"), e.get("tipo_referencia", "feicao"),
             json.dumps(e.get("detalhe") or {}, ensure_ascii=False), e.get("geometria"), versao),
        )
    return len(erros)


@router.post("/{rede_id}/validar_extensao", response_model=ValidacaoExtensaoResultado, openapi_extra=EDITAR)
def validar_extensao(rede_id: str, corpo: ValidacaoExtensaoEntrada, request: Request,
                     auth: Auth = autenticado("rede.editar")):
    """Validação incremental: reconstrói a topologia (as 15 checagens estruturais) só dentro das áreas
    sujas ativas que tocam `corpo.extensao` (ou todas, se `extensao` vier `null` — "validar tudo"). Marca as
    áreas processadas como limpas e grava os erros como feição em `plat.rede_erro`."""
    rid = _uuid_ok(rede_id)
    inicio = time.monotonic()
    carga_1min, ram_livre_gb = _carga_maquina()
    with db.db(auth.contexto()) as cur:
        rede = _carregar_rede(cur, rid)
        _exigir_pacote(rede)
        mapas = deposito.mapas_catalogo(cur, rid)

        areas = areas_sujas.intersectando(cur, rid, corpo.extensao)
        area_ids = [str(a["id"]) for a in areas]
        uniao = areas_sujas.uniao_geometria(cur, rid, area_ids) if area_ids else None
        feicao_ids = areas_sujas.feicoes_em_escopo(cur, rid, uniao) if area_ids else []
        total = _feicoes_total(cur, rid)

        erros = validacao.rodar_todas(cur, rid, feicao_ids, mapas["terminais"]) if feicao_ids else []
        total_erros = _gravar_erros(cur, auth.tenant_id, rid, rede["versao_edicao"], feicao_ids, erros)
        limpas = areas_sujas.limpar(cur, rid, area_ids) if area_ids else 0
        cur.execute(
            "SELECT count(*) AS n FROM plat.rede_area_suja WHERE rede_id = %s::uuid AND limpa_em IS NULL",
            (rid,),
        )
        restantes = cur.fetchone()["n"]

        tempo_ms = round((time.monotonic() - inicio) * 1000, 2)
        registrar_evento(cur, request, "redes/validar_extensao", "rede", rid, {
            "areas_processadas": limpas, "feicoes_em_escopo": len(feicao_ids), "feicoes_total": total,
            "total_erros": total_erros, "tempo_ms": tempo_ms,
        })
        return {
            "rede_id": rid, "versao_edicao": rede["versao_edicao"], "areas_processadas": limpas,
            "areas_ativas_restantes": restantes, "feicoes_em_escopo": len(feicao_ids),
            "feicoes_total": total, "total_erros": total_erros, "erros": erros, "tempo_ms": tempo_ms,
            "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
            "medido_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


@router.get("/{rede_id}/tracar", response_model=TracadoResultado, openapi_extra=LER)
def tracar(rede_id: str, feicao_id: str | None = None, geometria: str | None = None,
          auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Ponto de partida de um traçado: `feicao_id` (uuid de uma feição já gravada) OU `geometria` (GeoJSON
    de ponto/linha, codificado como string de query). Só lê: não deriva conexão nem grava nada — a checagem
    de área suja aqui é a mesma que a rota de rota (`L2-11-c`) chamaria antes de rodar o algoritmo pesado."""
    rid = _uuid_ok(rede_id)
    if feicao_id is None and geometria is None:
        raise ErroAPI(422, "entrada_vazia", "informe feicao_id ou geometria", {"campo": "feicao_id"})
    geometria_dict = None
    if geometria is not None:
        try:
            geometria_dict = json.loads(geometria)
        except json.JSONDecodeError as e:
            raise ErroAPI(422, "geometria_invalida", "geometria precisa ser GeoJSON válido codificado em "
                          "JSON na query", {"campo": "geometria"}) from e
    with db.db(auth.contexto()) as cur:
        rede = _carregar_rede(cur, rid)
        modo = rede["tracado_sobre_area_suja_modo"]
        if feicao_id is not None:
            achado = areas_sujas.cruza_area_suja(cur, rid, feicao_id, por_id=True)
        else:
            achado = areas_sujas.cruza_area_suja_geojson(cur, rid, geometria_dict)
    cruza = achado is not None
    bloqueado = cruza and modo == "bloquear"
    resultado = {"rede_id": rid, "cruza_area_suja": cruza, "bloqueado": bloqueado, "modo": modo,
                 "area_suja": achado}
    if bloqueado:
        raise ErroAPI(409, "tracado_sobre_area_suja",
                      "o ponto de partida do traçado cai dentro de uma área suja ainda não validada; "
                      "valide a extensão antes de traçar", resultado)
    return resultado


@router.put("/{rede_id}/area_sujas/modo", response_model=ModoTracadoResultado, openapi_extra=ADMIN)
def trocar_modo_tracado(rede_id: str, corpo: ModoTracadoEntrada, request: Request,
                        auth: Auth = autenticado("rede.administrar")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _carregar_rede(cur, rid)
        cur.execute(
            "UPDATE plat.rede SET tracado_sobre_area_suja_modo = %s WHERE id = %s::uuid",
            (corpo.modo, rid),
        )
        registrar_evento(cur, request, "redes/area_sujas_modo", "rede", rid, {"modo": corpo.modo})
    return {"rede_id": rid, "modo": corpo.modo}
