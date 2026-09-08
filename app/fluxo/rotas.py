"""API de gestão das fontes de fluxo (item L2-14-a-ingestao-de-fluxos). Vive no processo da APLICAÇÃO, como
qualquer outro objeto do inquilino; quem recebe evento é o processo `plat-fluxo` (app/fluxo/receptor.py).

  GET    /api/fluxos                    lista as fontes do inquilino (RLS) com a métrica de cada uma
  POST   /api/fluxos                    cria (privilégio `conteudo.registrar_fonte`, o mesmo de conexão)
  GET    /api/fluxos/{id}               uma fonte
  PATCH  /api/fluxos/{id}               edita (dono ou `conteudo.editar_tudo`); `estado` pausa e retoma
  DELETE /api/fluxos/{id}               apaga a fonte e expurga os eventos dela
  GET    /api/fluxos/{id}/eventos       lê os eventos gravados (janela por tempo, por rastro)
  POST   /api/fluxos/{id}/simular       aplica mapeamento e filtro a um registro de exemplo, sem gravar
  DELETE /api/fluxos/{id}/eventos       expurga eventos anteriores a um corte

Toda escrita registra evento de domínio (`plat.evento_tipo`, migração do item). Nenhuma rota devolve a
credencial da fonte.
"""

import datetime
import json

import psycopg2
from fastapi import APIRouter, Request

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento, uuid_ok
from app.conexao import credencial as credencial_mod
from app.erros import ErroAPI
from app.fluxo import mapeamento as mod_mapeamento
from app.fluxo import tipos as mod_tipos
from app.fluxo.filtro import ErroFiltro, compilar
from app.fluxo.modelos import (
    EventoPagina,
    Expurgo,
    Fonte,
    FonteEditar,
    FonteEntrada,
    FontePagina,
    Simulacao,
)
from app.settings import settings

router = APIRouter(prefix="/api/fluxos", tags=["fluxos"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}

CAMPOS = (
    "f.id, f.tipo, f.nome, f.estado, f.config, f.mapeamento, f.esquema_destino, f.filtro, "
    "f.limite_eventos_s, (f.credencial_cifrada IS NOT NULL) AS tem_credencial, f.dono_id, "
    "u.login AS dono_login, u.nome AS dono_nome, f.criado_em, f.atualizado_em, "
    "m.recebidos, m.aceitos, m.descartados_filtro, m.descartados_limite, m.descartados_invalido, "
    "m.atraso_ms_ultimo, m.atraso_ms_p50, m.ultimo_evento_em, m.atualizado_em AS metrica_em"
)
SQL_BASE = (
    f"SELECT {CAMPOS} FROM plat.fluxo_fonte f JOIN plat.usuario u ON u.id = f.dono_id "  # noqa: S608
    "LEFT JOIN plat.fluxo_metrica m ON m.fonte_id = f.id"
)


def _endereco(r: dict) -> str | None:
    """Onde o remetente manda o evento. Só existe para tipo receptor — conector ativo vai buscar."""
    if r["tipo"] not in mod_tipos.TIPOS_RECEPTOR:
        return None
    caminho = "ws" if r["tipo"] == "websocket_servidor" else "eventos"
    return f"{settings.PLAT_URL_PUBLICA.rstrip('/')}/fluxo/{r['id']}/{caminho}"


def _json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "tipo": r["tipo"],
        "nome": r["nome"],
        "estado": r["estado"],
        "config": r["config"] or {},
        "mapeamento": r["mapeamento"] or {},
        "esquema_destino": r["esquema_destino"] or [],
        "filtro": r["filtro"],
        "limite_eventos_s": r["limite_eventos_s"],
        "tem_credencial": bool(r["tem_credencial"]),
        "endereco_receptor": _endereco(r),
        "dono": {"id": r["dono_id"], "login": r["dono_login"], "nome": r["dono_nome"]},
        "metrica": {
            "recebidos": r["recebidos"] or 0, "aceitos": r["aceitos"] or 0,
            "descartados_filtro": r["descartados_filtro"] or 0,
            "descartados_limite": r["descartados_limite"] or 0,
            "descartados_invalido": r["descartados_invalido"] or 0,
            "atraso_ms_ultimo": r["atraso_ms_ultimo"], "atraso_ms_p50": r["atraso_ms_p50"],
            "ultimo_evento_em": iso(r["ultimo_evento_em"]), "atualizado_em": iso(r["metrica_em"]),
        },
        "criado_em": iso(r["criado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


def _carregar(cur, fid: str) -> dict:
    cur.execute(SQL_BASE + " WHERE f.id = %s::uuid", (fid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "fonte_inexistente", "fonte de fluxo inexistente")
    return r


def _pode_editar(r: dict, auth: Auth) -> None:
    if r["dono_id"] != auth.usuario_id and not auth.tem("conteudo.editar_tudo"):
        raise ErroAPI(403, "sem_permissao", "só o dono da fonte ou conteudo.editar_tudo")


def _config_ok(tipo: str, config: dict) -> dict:
    try:
        return mod_tipos.validar_config(tipo, config)
    except mod_tipos.ErroConfig as e:
        raise ErroAPI(422, e.motivo, e.detalhe, {"tipo": tipo}) from e


def _mapeamento_ok(bruto: dict):
    try:
        return mod_mapeamento.validar(bruto or {})
    except mod_mapeamento.ErroMapeamento as e:
        raise ErroAPI(422, e.motivo, e.detalhe) from e


def _filtro_ok(texto: str | None):
    try:
        return compilar(texto)
    except ErroFiltro as e:
        raise ErroAPI(422, "filtro_invalido", e.detalhe) from e


@router.get("", response_model=FontePagina, openapi_extra=LER)
def listar(tipo: str | None = None, auth: Auth = autenticado(escopo_token="fluxo:ler")):
    onde, params = ["true"], []
    if tipo:
        onde.append("f.tipo = %s")
        params.append(tipo)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.fluxo_fonte f WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(f"{SQL_BASE} WHERE {filtro} ORDER BY lower(f.nome)", params)  # noqa: S608
        itens = [_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.post("", response_model=Fonte, status_code=201, openapi_extra=CRIAR)
def criar(corpo: FonteEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
                      {"exigido": "conteudo.registrar_fonte"})
    config = _config_ok(corpo.tipo, corpo.config)
    mapa, esquema = _mapeamento_ok(corpo.mapeamento)
    _filtro_ok(corpo.filtro)
    cifrada = credencial_mod.cifrar(corpo.credencial, settings.PLAT_SECRET) if corpo.credencial else None
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.fluxo_fonte(tenant_id, tipo, nome, config, mapeamento, esquema_destino, "
                "filtro, limite_eventos_s, credencial_cifrada, dono_id) "
                "VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s) RETURNING id",
                (auth.tenant_id, corpo.tipo, " ".join(corpo.nome.split()),
                 json.dumps(config, ensure_ascii=False),
                 json.dumps(mod_mapeamento.para_json(mapa), ensure_ascii=False),
                 json.dumps(esquema, ensure_ascii=False),
                 corpo.filtro, corpo.limite_eventos_s, cifrada, auth.usuario_id),
            )
            fid = str(cur.fetchone()["id"])
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe uma fonte de fluxo com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "fluxos/criar", "fluxo_fonte", fid,
                         {"tipo": corpo.tipo, "nome": corpo.nome})
        return _json(_carregar(cur, fid))


@router.get("/{id}", response_model=Fonte, openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="fluxo:ler")):
    fid = uuid_ok(id, "fonte_inexistente", "fonte de fluxo inexistente")
    with db.db(auth.contexto()) as cur:
        return _json(_carregar(cur, fid))


@router.patch("/{id}", response_model=Fonte, openapi_extra=EDITAR)
def editar(id: str, corpo: FonteEditar, request: Request, auth: Auth = autenticado()):
    fid = uuid_ok(id, "fonte_inexistente", "fonte de fluxo inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, fid)
        _pode_editar(r, auth)
        campos, params, evento_estado = [], [], None
        if corpo.nome is not None:
            campos.append("nome = %s")
            params.append(" ".join(corpo.nome.split()))
        if corpo.estado is not None and corpo.estado != r["estado"]:
            campos.append("estado = %s")
            params.append(corpo.estado)
            evento_estado = "fluxos/pausar" if corpo.estado == "pausada" else "fluxos/retomar"
        if corpo.config is not None:
            campos.append("config = %s::jsonb")
            params.append(json.dumps(_config_ok(r["tipo"], corpo.config), ensure_ascii=False))
        if corpo.mapeamento is not None:
            mapa, esquema = _mapeamento_ok(corpo.mapeamento)
            campos.append("mapeamento = %s::jsonb")
            params.append(json.dumps(mod_mapeamento.para_json(mapa), ensure_ascii=False))
            campos.append("esquema_destino = %s::jsonb")
            params.append(json.dumps(esquema, ensure_ascii=False))
        if corpo.remover_filtro:
            campos.append("filtro = NULL")
        elif corpo.filtro is not None:
            _filtro_ok(corpo.filtro)
            campos.append("filtro = %s")
            params.append(corpo.filtro)
        if corpo.limite_eventos_s is not None:
            campos.append("limite_eventos_s = %s")
            params.append(corpo.limite_eventos_s)
        if corpo.remover_credencial:
            campos.append("credencial_cifrada = NULL")
        elif corpo.credencial is not None:
            campos.append("credencial_cifrada = %s")
            params.append(credencial_mod.cifrar(corpo.credencial, settings.PLAT_SECRET))
        if campos:
            try:
                cur.execute(f"UPDATE plat.fluxo_fonte SET {', '.join(campos)} WHERE id = %s::uuid",  # noqa: S608
                            (*params, fid))
            except psycopg2.errors.UniqueViolation as e:
                raise ErroAPI(409, "nome_existente", "já existe uma fonte de fluxo com esse nome") from e
            except psycopg2.Error as e:
                raise auth_comum.erro_do_banco(e) from e
            registrar_evento(cur, request, evento_estado or "fluxos/editar", "fluxo_fonte", fid,
                             {"campos": [c.split(" =")[0] for c in campos]})
        return _json(_carregar(cur, fid))


@router.delete("/{id}", status_code=204, openapi_extra=EDITAR)
def apagar(id: str, request: Request, auth: Auth = autenticado()):
    fid = uuid_ok(id, "fonte_inexistente", "fonte de fluxo inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, fid)
        _pode_editar(r, auth)
        # os eventos não têm chave estrangeira para a fonte (custo por linha no lote): o expurgo é explícito
        cur.execute("DELETE FROM plat.fluxo_evento WHERE fonte_id = %s::uuid", (fid,))
        cur.execute("DELETE FROM plat.fluxo_fonte WHERE id = %s::uuid", (fid,))
        registrar_evento(cur, request, "fluxos/apagar", "fluxo_fonte", fid, {"nome": r["nome"]})


@router.get("/{id}/eventos", response_model=EventoPagina, openapi_extra=LER)
def eventos(id: str, desde: str | None = None, ate: str | None = None, rastro: str | None = None,
            limite: int = limites.FLUXO_EVENTOS_LISTA_MAX,
            auth: Auth = autenticado(escopo_token="fluxo:ler")):
    fid = uuid_ok(id, "fonte_inexistente", "fonte de fluxo inexistente")
    limite = max(1, min(limite, limites.FLUXO_EVENTOS_LISTA_MAX))
    onde, params = ["e.fonte_id = %s::uuid"], [fid]
    for nome, valor, operador in (("desde", desde, ">="), ("ate", ate, "<=")):
        if valor:
            onde.append(f"e.recebido_em {operador} %s::timestamptz")
            params.append(_instante(valor, nome))
    if rastro:
        onde.append("e.rastro_id = %s")
        params.append(rastro[:limites.FLUXO_RASTRO_MAX])
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, fid)  # 404 de fonte alheia antes de qualquer consulta a evento
        cur.execute(f"SELECT count(*) AS n FROM plat.fluxo_evento e WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT e.rastro_id, e.tempo_evento, e.recebido_em, ST_X(e.geom) AS lon, ST_Y(e.geom) AS lat, "  # noqa: S608
            f"e.atributos FROM plat.fluxo_evento e WHERE {filtro} ORDER BY e.recebido_em DESC LIMIT %s",
            (*params, limite),
        )
        itens = [{
            "rastro_id": r["rastro_id"], "tempo_evento": iso(r["tempo_evento"]),
            "recebido_em": iso(r["recebido_em"]), "lon": r["lon"], "lat": r["lat"],
            "atributos": r["atributos"] or {},
        } for r in cur.fetchall()]
    return {"total": total, "itens": itens, "limite": limite}


@router.delete("/{id}/eventos", response_model=Expurgo, openapi_extra=EDITAR)
def expurgar(id: str, antes_de: str, request: Request, auth: Auth = autenticado()):
    fid = uuid_ok(id, "fonte_inexistente", "fonte de fluxo inexistente")
    corte = _instante(antes_de, "antes_de")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, fid)
        _pode_editar(r, auth)
        cur.execute("DELETE FROM plat.fluxo_evento WHERE fonte_id = %s::uuid AND recebido_em < %s::timestamptz",
                    (fid, corte))
        apagados = cur.rowcount
        registrar_evento(cur, request, "fluxos/expurgar", "fluxo_fonte", fid,
                         {"antes_de": corte, "apagados": apagados})
    return {"apagados": apagados}


@router.post("/{id}/simular", response_model=Simulacao, openapi_extra=LER)
def simular(id: str, corpo: dict, auth: Auth = autenticado(escopo_token="fluxo:ler")):
    """Aplica mapeamento e filtro a UM registro de exemplo, sem gravar nada e sem consumir o teto por
    segundo. É como se confere o fuso e o filtro antes de apontar o remetente para a fonte."""
    fid = uuid_ok(id, "fonte_inexistente", "fonte de fluxo inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, fid)
    mapa = mod_mapeamento.de_json(r["mapeamento"] or {})
    evento = mod_mapeamento.aplicar(mapa, corpo)
    if isinstance(evento, mod_mapeamento.ErroEvento):
        return {"aceito": False, "motivo": evento.motivo}
    from app.fluxo import filtro as mod_filtro

    try:
        passou = mod_filtro.aceita(compilar(r["filtro"]), evento)
    except ErroFiltro as e:
        return {"aceito": False, "motivo": e.motivo}
    return {
        "aceito": bool(passou), "motivo": None if passou else "filtro",
        "rastro_id": evento.rastro_id, "tempo_evento": evento.tempo_evento.isoformat(),
        "lon": evento.lon, "lat": evento.lat, "atributos": evento.atributos,
    }


def _instante(valor: str, campo: str) -> str:
    try:
        return datetime.datetime.fromisoformat(valor.replace("Z", "+00:00")).isoformat()
    except (TypeError, ValueError) as e:
        raise ErroAPI(422, "instante_invalido", f"{campo} tem de ser um instante ISO 8601") from e


