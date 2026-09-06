"""Fachada Esri `unitIdentifiers` do UtilityNetworkServer (item L4-28-identificadores-e-numeracao).

Fonte: developers.arcgis.com/rest/services-reference/enterprise/unitIdentifiers-utility-network-server/
(+ /query-unitIdentifiers- e /reserve-unitIdentifiers-, lidas em 06/09/2026; recurso introduzido na 12.1).
Cobertura registrada em docs/PARIDADE.md. O mapeamento do modelo (a Esri descreve o recurso para a rede de
domínio de TELECOM; aqui ele serve qualquer disciplina do pacote de ativos):

  - "unit-identifiable object" da Esri  -> nosso TIPO de ativo (plat.rede_tipo). No protocolo, `globalId`
    do objeto é o uuid do tipo; `sourceId` é livre (o cliente escolhe; ecoamos de volta, como a Esri);
  - unit identifier (inteiro)            -> nosso `numero` automático por tipo (plat.rede_ativo.numero);
  - reserve                              -> nossa reserva de faixa (plat.rede_faixa) para o usuário do
                                            token: com `firstUnit`/`lastUnit` reserva o bloco exato; sem
                                            eles, exige a EXTENSÃO `count` e aloca o próximo bloco livre;
  - query                                -> por objeto: `unitIdentifiers` = faixas abertas do tipo
                                            (firstUnit/lastUnit; globalId = uuid da faixa) e `gaps` =
                                            números do espaço já alocado que ainda não viraram ativo.

Divergências declaradas: (1) erro segue o contrato da plataforma (HTTP 4xx + {"erro": ...}), não o
envelope {"success": false, "error": {...}} da Esri; (2) `gdbVersion`, `sessionID` e `moment` são aceitos
e ignorados — não há versionamento de geodatabase nesta plataforma; (3) as operações `reset` e `resize`
da Esri não existem aqui: o contador nunca anda para trás e o tamanho de uma faixa não muda (libera-se e
reserva-se outra); (4) a resposta do reserve usa a forma do query (unitIdentifiers com first/last), não
o envelope `serviceEdits` da Esri, que é interno da tabela de UN deles.

Autenticação: como o GeocodeServer (app/geocodificador/rotas_esri.py) — sessão/cabeçalho do plat ou
`?token=` (protocolo Esri). query exige escopo de token `catalogo:ler`; reserve exige `camada:editar`
e o privilégio `rede.editar`."""

import json
import logging

from fastapi import APIRouter, Request

from app import db
from app.auth import escopos as esc
from app.auth import sessao as auth_sessao
from app.erros import ErroAPI
from app.rede_utilidades import identificadores as ident

log = logging.getLogger("plat.rede_utilidades.esri_un")
router = APIRouter(tags=["rede de utilidades — fachada Esri unitIdentifiers"])


def _autenticar(request: Request, escopo: str, privilegio: str | None = None):
    """Sessão/cabeçalho Authorization normal OU `?token=`/form `token=` (protocolo Esri) — mesmo desenho
    do GeocodeServer compatível (app/geocodificador/rotas_esri.py)."""
    try:
        auth = auth_sessao.resolver(request)
    except ErroAPI:
        auth = None
    if auth is None:
        tok = request.query_params.get("token")
        if not tok:
            raise ErroAPI(401, "token_requerido", "informe token=<token de serviço plat> (protocolo Esri) ou "
                          "o cabeçalho Authorization: Bearer")
        auth = auth_sessao._auth_de_token(request, tok)  # noqa: SLF001 — reuso deliberado, mesmo pacote app
        request.state.auth = auth
    esc.exigir_escopo(auth, escopo)
    if privilegio and not auth.tem(privilegio):
        raise ErroAPI(403, "sem_privilegio", f"a operação exige o privilégio {privilegio}",
                      {"exigido": privilegio})
    return auth


async def _parametros(request: Request) -> dict:
    """Esri aceita GET (querystring) e POST (application/x-www-form-urlencoded ou querystring). O corpo
    urlencoded é lido na mão (urllib) porque esta máquina não tem python-multipart e o protocolo Esri não
    usa multipart nestas operações — só querystring e form urlencoded."""
    p = dict(request.query_params)
    if request.method == "POST" and "application/x-www-form-urlencoded" in request.headers.get("content-type", ""):
        from urllib.parse import parse_qsl

        p.update(parse_qsl((await request.body()).decode("utf-8"), keep_blank_values=True))
    return p


def _rede_do_servico(cur, servico: str) -> dict:
    """O nome do serviço na URL é o uuid da rede OU o nome exato (sem distinção de maiúsculas)."""
    try:
        cur.execute("SELECT id, nome FROM plat.rede WHERE id = %s::uuid", (str(ident.uuid_mod.UUID(servico)),))
    except (ValueError, AttributeError, TypeError):
        cur.execute("SELECT id, nome FROM plat.rede WHERE lower(nome) = lower(%s)", (servico,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "servico_inexistente", "não há rede de utilidades publicada com esse nome de serviço")
    return r


def _inteiro(p: dict, nome: str) -> int | None:
    v = p.get(nome)
    if v in (None, ""):
        return None
    try:
        return int(v)
    except ValueError as e:
        raise ErroAPI(422, "parametro_invalido", f"o parâmetro {nome} tem de ser inteiro") from e


def _objeto(p: dict) -> dict:
    """O parâmetro `object` da Esri (JSON {"sourceId": ..., "globalId": ...}); globalId = uuid do tipo."""
    bruto = p.get("object")
    if not bruto:
        raise ErroAPI(422, "parametro_ausente", "falta o parâmetro object ({sourceId, globalId})")
    try:
        obj = json.loads(bruto)
        gid = str(ident.uuid_mod.UUID(obj["globalId"]))
    except (ValueError, AttributeError, TypeError, KeyError) as e:
        raise ErroAPI(422, "parametro_invalido",
                      "o parâmetro object tem de ser JSON com globalId (uuid do tipo de ativo)") from e
    return {"sourceId": obj.get("sourceId"), "globalId": gid}


PREFIXO = "/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers"


@router.get(PREFIXO, openapi_extra={"x-auth": "S/T"}, operation_id="rede_un_identificadores_descritor_get")
@router.post(PREFIXO, openapi_extra={"x-auth": "S/T"}, operation_id="rede_un_identificadores_descritor_post")
async def descritor(servico: str, request: Request):
    """Descritor do recurso unitIdentifiers (a forma da Esri: currentVersion + operações)."""
    _autenticar(request, "catalogo:ler")
    return {
        "currentVersion": 12.1,
        "description": "Identificadores de unidade da rede de utilidades plat — numeração automática por "
                       "tipo de ativo com faixas reservadas por usuário. Análise / beta privado.",
        "operations": ["query", "reserve"],
    }


@router.get(PREFIXO + "/query", openapi_extra={"x-auth": "S/T"}, operation_id="rede_un_query_get")
@router.post(PREFIXO + "/query", openapi_extra={"x-auth": "S/T"}, operation_id="rede_un_query_post")
async def consultar(servico: str, request: Request):
    """query da Esri: por objeto (tipo de ativo), as faixas abertas (unitIdentifiers) e as lacunas do
    espaço já alocado que ainda não viraram ativo (gaps)."""
    auth = _autenticar(request, "catalogo:ler")
    p = await _parametros(request)
    bruto = p.get("objects")
    if not bruto:
        raise ErroAPI(422, "parametro_ausente", "falta o parâmetro objects ([{sourceId, globalIds}])")
    try:
        objetos = json.loads(bruto)
        assert isinstance(objetos, list)
    except (ValueError, AssertionError) as e:
        raise ErroAPI(422, "parametro_invalido", "objects tem de ser uma lista JSON") from e
    with db.db(auth.contexto()) as cur:
        rede = _rede_do_servico(cur, servico)
        saida = []
        for obj in objetos:
            source_id = obj.get("sourceId")
            gids = obj.get("globalIds") or []
            for gid_bruto in gids:
                gid = ident.uuid_ok(str(gid_bruto), "tipo_inexistente")
                tipo = ident.tipo_da_rede(cur, str(rede["id"]), gid)
                cur.execute(
                    "SELECT proximo FROM plat.rede_numeracao WHERE tipo_id = %s::uuid", (gid,))
                linha = cur.fetchone()
                proximo = linha["proximo"] if linha else 1
                cur.execute(
                    "SELECT id, inicio, fim FROM plat.rede_faixa "
                    "WHERE tipo_id = %s::uuid AND liberada_em IS NULL ORDER BY inicio", (gid,))
                faixas = cur.fetchall()
                cur.execute(
                    "SELECT numero FROM plat.rede_ativo WHERE tipo_id = %s::uuid ORDER BY numero", (gid,))
                usados = {r["numero"] for r in cur.fetchall()}
                # lacunas: números do espaço já alocado [1, proximo-1] que não viraram ativo
                # (faixa aberta não é lacuna: está reservada — já tem dono)
                reservados = set()
                for f in faixas:
                    reservados.update(range(f["inicio"], f["fim"] + 1))
                gaps = []
                inicio_gap = None
                for n in range(1, proximo):
                    livre = n not in usados and n not in reservados
                    if livre and inicio_gap is None:
                        inicio_gap = n
                    elif not livre and inicio_gap is not None:
                        gaps.append({"start": inicio_gap, "end": n - 1})
                        inicio_gap = None
                if inicio_gap is not None:
                    gaps.append({"start": inicio_gap, "end": proximo - 1})
                saida.append({
                    "sourceId": source_id,
                    "globalId": gid,
                    "tipo": {"chave": tipo["chave"], "nome": tipo["nome"], "codigo": tipo["codigo"]},
                    "gaps": gaps,
                    "unitIdentifiers": [
                        {"sourceId": source_id, "globalId": str(f["id"]),
                         "firstUnit": f["inicio"], "lastUnit": f["fim"]} for f in faixas
                    ],
                })
    return {"objects": saida, "success": True}


@router.get(PREFIXO + "/reserve", openapi_extra={"x-auth": "S/T"}, operation_id="rede_un_reservar_get")
@router.post(PREFIXO + "/reserve", openapi_extra={"x-auth": "S/T"}, operation_id="rede_un_reservar_post")
async def reservar(servico: str, request: Request):
    """reserve da Esri: com firstUnit/lastUnit reserva o bloco exato; sem eles, a EXTENSÃO `count` aloca o
    próximo bloco livre (é o que o cliente de campo pede antes de sair desconectado)."""
    auth = _autenticar(request, "camada:editar", privilegio="rede.editar")
    p = await _parametros(request)
    obj = _objeto(p)
    primeiro, ultimo, quantidade = _inteiro(p, "firstUnit"), _inteiro(p, "lastUnit"), _inteiro(p, "count")
    with db.db(auth.contexto()) as cur:
        rede = _rede_do_servico(cur, servico)
        rid = str(rede["id"])
        ident.tipo_da_rede(cur, rid, obj["globalId"])
        if (primeiro is None) != (ultimo is None):
            raise ErroAPI(422, "parametro_invalido", "firstUnit e lastUnit vêm juntos, ou nenhum dos dois")
        if primeiro is not None:
            r = ident.reservar_faixa_explicita(cur, auth.tenant_id, rid, obj["globalId"],
                                               auth.usuario_id, primeiro, ultimo)
        elif quantidade is not None:
            r = ident.reservar_faixa(cur, auth.tenant_id, rid, obj["globalId"],
                                     auth.usuario_id, quantidade)
        else:
            raise ErroAPI(422, "parametro_ausente",
                          "informe firstUnit+lastUnit (bloco exato) ou count (próximo bloco livre)")
    return {
        "success": True,
        "unitIdentifiers": [{"sourceId": obj["sourceId"], "globalId": str(r["id"]),
                             "firstUnit": r["inicio"], "lastUnit": r["fim"]}],
    }
