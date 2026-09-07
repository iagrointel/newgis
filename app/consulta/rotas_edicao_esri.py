"""Escrita compatível com o protocolo Esri sobre a porta única de escrita da casa (item L2-04-d).

Rotas montadas na mesma raiz da operação `query` (item L2-04-c), sob
`/rest/services/{item}/FeatureServer/{camada}`: `applyEdits` (na camada e no serviço), `addFeatures`,
`updateFeatures`, `deleteFeatures`, `calculate`, os anexos (`attachments`, `addAttachment`,
`updateAttachment`, `deleteAttachments`, `queryAttachments`) e `uploads/upload`.

Três decisões que valem para o arquivo inteiro (ADR 20260907T1927):

1. Nada aqui escreve feição por conta própria: tudo vira `EdicoesEntrada` e passa por
   `app.edicao.servico.aplicar_edicoes` (item L2-03-a), que já valida tipo, domínio, CRS, propriedade e
   concorrência. O que este arquivo faz é traduzir nomes e devolver o resultado no formato Esri.
2. Erro: a Esri devolve HTTP 200 com o erro no CORPO. Nós devolvemos o código HTTP REAL (403, 404, 400)
   E o corpo no formato dela (`{"error": {"code", "message", "details"}}`). Cliente que lê o corpo
   continua funcionando; cliente que lê o status passa a receber a verdade.
3. `rollbackOnFailure` (padrão `true`, como no Enterprise): o lote roda dentro de um SAVEPOINT; havendo
   qualquer falha, volta ao ponto e NADA é gravado — mas a resposta ainda traz o vetor de resultados
   feição a feição, para o cliente saber qual falhou.

Toda edição que entra por aqui grava `origem = 'featureserver'` no histórico de feição (parâmetro de
sessão `plat.origem`, migração 20260907T1927)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import db
from app.consulta import campos as campos_mod
from app.consulta import esri_edicao as tr
from app.consulta import where_ast
from app.consulta.geometria_esri import MAX_VERTICES, contar_vertices, para_ewkt, sr_wkid
from app.consulta.rotas_query import _autenticar, _parametros
from app.edicao import anexos as anexos_mod
from app.edicao.modelos import EdicoesEntrada
from app.edicao.servico import _schema_tabela, aplicar_edicoes, camada_ou_404
from app.erros import ErroAPI
from app.expressao.avaliador_py import ErroExpressao, avaliar_texto

router = APIRouter(tags=["edicao-esri"])
SERVICO = "/rest/services/{item_id}/FeatureServer"
PREFIXO = SERVICO + "/{camada_id}"
ESCOPO_EDITAR = "camada:editar"
ESCOPO_LER = "camada:ler"
ABERTURA = {"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"}
ABERTURA_LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
LOTE_MAX = 1000  # teto de feições por pedido; acima disto é 400, nunca uma transação de tamanho aberto


def _erro_esri(e: ErroAPI) -> JSONResponse:
    detalhes = [json.dumps(e.detalhe, default=str, ensure_ascii=False)] if e.detalhe is not None else []
    return JSONResponse(
        tr.corpo_erro_esri(e.status_code, f"{e.erro}: {e.mensagem}", detalhes), status_code=e.status_code
    )


def _json(corpo: dict) -> JSONResponse:
    return JSONResponse(json.loads(json.dumps(corpo, default=str)))


def _bool(valor: Any, padrao: bool) -> bool:
    if valor is None or valor == "":
        return padrao
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("true", "1", "yes", "sim")


def _lista_json(valor: Any, nome: str) -> list:
    """Parâmetro que a Esri manda como JSON em texto (form) ou já decodificado (corpo JSON)."""
    if valor in (None, ""):
        return []
    if isinstance(valor, list):
        return valor
    try:
        obj = json.loads(valor)
    except (TypeError, json.JSONDecodeError) as e:
        raise ErroAPI(400, "parametro_invalido", f"{nome} não é JSON válido") from e
    if not isinstance(obj, list):
        raise ErroAPI(400, "parametro_invalido", f"{nome} precisa ser uma lista")
    return obj


def _dicionario_json(valor: Any, nome: str) -> dict:
    if valor in (None, ""):
        return {}
    if isinstance(valor, dict):
        return valor
    try:
        obj = json.loads(valor)
    except (TypeError, json.JSONDecodeError) as e:
        raise ErroAPI(400, "parametro_invalido", f"{nome} não é JSON válido") from e
    if not isinstance(obj, dict):
        raise ErroAPI(400, "parametro_invalido", f"{nome} precisa ser um objeto")
    return obj


def _abrir(request: Request, item_id: str, camada_id: str | None, editar: bool):
    """Autenticação (sessão OU token, inclusive `?token=`, como o resto do protocolo Esri) + escopo +
    privilégio de edição. O privilégio é conferido ANTES de qualquer leitura de corpo."""
    # ordem do ADR 0002 seção 5, e é o que `tests/api/test_privilegios_matriz.py` exige: autenticação e
    # escopo, DEPOIS privilégio, só então a forma do caminho. Conferir o id da camada antes faria a rota
    # responder 404 a quem não tem privilégio nenhum — um 404 que conta o que existe.
    auth = _autenticar(request, item_id, ESCOPO_EDITAR if editar else ESCOPO_LER)
    if editar and not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
            {"exigido": "feicoes.editar|feicoes.editar_total"},
        )
    if camada_id is not None and camada_id != "0":
        raise ErroAPI(404, "camada_nao_encontrada", "esta implementação publica uma camada só (id 0) por item")
    return auth


def _marcar_origem(cur) -> None:
    cur.execute("SELECT set_config('plat.origem', 'featureserver', true)")


# ---------------------------------------------------------------- resolução de alvo (objectId/globalId)
def _alvo(cur, schema: str, tabela: str, entrada: Any, usar_globalid: bool) -> dict:
    """Localiza a feição citada pelo cliente e devolve `{fid, globalid, versao}`. `entrada` é o objeto de
    feição (com `attributes`) ou o identificador cru (lista de `deletes`)."""
    if isinstance(entrada, dict):
        atributos = entrada.get("attributes") or {}
        gid = entrada.get("globalId") or tr.valor_por_nome(atributos, tr.NOMES_GLOBALID)
        oid = entrada.get("objectId") or tr.valor_por_nome(atributos, tr.NOMES_OBJECTID)
    else:
        gid, oid = (entrada, None) if usar_globalid else (None, entrada)
    if usar_globalid:
        if not gid:
            raise ErroAPI(400, "globalid_ausente", "useGlobalIds=true exige globalId em cada feição")
        try:
            chave, valor = "globalid = %s::uuid", str(uuid.UUID(str(gid)))
        except (ValueError, AttributeError, TypeError) as e:
            raise ErroAPI(400, "globalid_invalido", f"globalId não é uuid: {gid!r}") from e
    else:
        if oid in (None, ""):
            raise ErroAPI(400, "objectid_ausente", "a feição não traz objectId (nem OBJECTID nos atributos)")
        try:
            chave, valor = "fid = %s", int(oid)
        except (ValueError, TypeError) as e:
            raise ErroAPI(400, "objectid_invalido", f"objectId não é inteiro: {oid!r}") from e
    cur.execute(f'SELECT fid, globalid, versao FROM "{schema}"."{tabela}" WHERE {chave}', (valor,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta camada", {"alvo": str(valor)})
    return {"fid": linha["fid"], "globalid": str(linha["globalid"]), "versao": linha["versao"]}


def _geometria_da_feicao(cur, feicao: dict, srid_camada: int, crs: dict) -> dict | None:
    geom = feicao.get("geometry")
    if geom in (None, {}, ""):
        return None
    geojson, declarado = tr.geojson_de_esri(cur, geom, srid_camada)
    if declarado is not None:
        if crs.get("srid") not in (None, declarado):
            raise ErroAPI(
                400, "crs_misturado",
                "todas as geometrias do lote têm de declarar a mesma spatialReference",
                {"visto": crs.get("srid"), "agora": declarado},
            )
        crs["srid"] = declarado
    return geojson


# ---------------------------------------------------------------- applyEdits de UMA camada
def _aplicar(cur, request: Request, auth, item_id: str, edits: dict, opcoes: dict) -> dict:
    """Traduz um bloco de edições Esri, chama a porta única de escrita e devolve os três vetores de
    resultado. Falha de tradução (objectId inexistente, geometria impossível) vira resultado com
    `success:false` na posição certa — nunca derruba o lote inteiro com um 4xx."""
    _item, dados = camada_ou_404(cur, item_id)
    schema, tabela = _schema_tabela(dados)
    srid_camada = int(dados["srid"])
    usar_globalid = _bool(opcoes.get("useGlobalIds"), False)

    adds = edits.get("adds") or []
    updates = edits.get("updates") or []
    deletes = edits.get("deletes") or []
    if not isinstance(adds, list) or not isinstance(updates, list) or not isinstance(deletes, list):
        raise ErroAPI(400, "edits_invalido", "adds, updates e deletes precisam ser listas")
    if len(adds) + len(updates) + len(deletes) > LOTE_MAX:
        raise ErroAPI(
            400, "lote_grande", f"pedido acima de {LOTE_MAX} feições; divida em lotes",
            {"recebido": len(adds) + len(updates) + len(deletes), "limite": LOTE_MAX},
        )

    crs: dict = {}
    corpo: dict[str, list] = {"adicionar": [], "atualizar": [], "apagar": []}
    # posição na lista da casa -> posição na lista Esri, e falhas já conhecidas antes de escrever
    mapa: dict[str, list[int]] = {"adicionar": [], "atualizar": [], "apagar": []}
    saida: dict[str, list[dict | None]] = {
        "adicionar": [None] * len(adds), "atualizar": [None] * len(updates), "apagar": [None] * len(deletes)
    }
    alvos: dict[str, list[dict]] = {"atualizar": [], "apagar": []}

    for i, feicao in enumerate(adds):
        try:
            if not isinstance(feicao, dict):
                raise ErroAPI(400, "feicao_invalida", "cada item de adds precisa ser um objeto")
            geometria = _geometria_da_feicao(cur, feicao, srid_camada, crs)
            corpo["adicionar"].append(
                {"atributos": tr.atributos_limpos(feicao.get("attributes")), "geometria": geometria}
            )
            mapa["adicionar"].append(i)
        except ErroAPI as e:
            saida["adicionar"][i] = tr.resultado_erro(None, None, e.status_code, f"{e.erro}: {e.mensagem}")

    for i, feicao in enumerate(updates):
        try:
            if not isinstance(feicao, dict):
                raise ErroAPI(400, "feicao_invalida", "cada item de updates precisa ser um objeto")
            alvo = _alvo(cur, schema, tabela, feicao, usar_globalid)
            geometria = _geometria_da_feicao(cur, feicao, srid_camada, crs)
            corpo["atualizar"].append({
                "id": alvo["globalid"], "versao": alvo["versao"],
                "atributos": tr.atributos_limpos(feicao.get("attributes")) or None,
                "geometria": geometria,
            })
            alvos["atualizar"].append(alvo)
            mapa["atualizar"].append(i)
        except ErroAPI as e:
            saida["atualizar"][i] = tr.resultado_erro(None, None, e.status_code, f"{e.erro}: {e.mensagem}")

    for i, entrada in enumerate(deletes):
        try:
            alvo = _alvo(cur, schema, tabela, entrada, usar_globalid)
            corpo["apagar"].append({"id": alvo["globalid"], "versao": alvo["versao"]})
            alvos["apagar"].append(alvo)
            mapa["apagar"].append(i)
        except ErroAPI as e:
            saida["apagar"][i] = tr.resultado_erro(None, None, e.status_code, f"{e.erro}: {e.mensagem}")

    entrada_casa = EdicoesEntrada(
        modo="parcial",  # o tudo-ou-nada do protocolo Esri é o SAVEPOINT de fora, ver `_com_rollback`
        crs={"srid": crs["srid"]} if crs.get("srid") else None,
        adicionar=corpo["adicionar"], atualizar=corpo["atualizar"], apagar=corpo["apagar"],
    )
    resultado = aplicar_edicoes(cur, request, auth, item_id, entrada_casa)

    for chave_casa, lista in (("adicionar", resultado.adicionar), ("atualizar", resultado.atualizar),
                              ("apagar", resultado.apagar)):
        for posicao, r in enumerate(lista):
            i = mapa[chave_casa][posicao]
            if r.sucesso:
                if chave_casa == "adicionar":
                    saida[chave_casa][i] = tr.resultado_ok(r.fid, r.id)
                else:
                    alvo = alvos[chave_casa][posicao]
                    saida[chave_casa][i] = tr.resultado_ok(alvo["fid"], alvo["globalid"])
            else:
                alvo = alvos[chave_casa][posicao] if chave_casa != "adicionar" else {}
                saida[chave_casa][i] = tr.resultado_erro(
                    alvo.get("fid"), alvo.get("globalid"), 400, f"{r.erro}: {r.mensagem}"
                )
    return {
        "addResults": saida["adicionar"], "updateResults": saida["atualizar"],
        "deleteResults": saida["apagar"], "avisos": resultado.avisos,
    }


def _falhou(resultado: dict) -> bool:
    for chave in ("addResults", "updateResults", "deleteResults"):
        if any(not r.get("success") for r in resultado.get(chave) or []):
            return True
    for r in (resultado.get("attachments") or {}).values():
        if isinstance(r, list) and any(not x.get("success") for x in r):
            return True
    return False


# ---------------------------------------------------------------- anexos dentro do applyEdits
def _conteudo_do_anexo(cur, anexo: dict) -> tuple[str, str, str]:
    """(nome, content_type, base64). Aceita `data` (base64 no próprio pedido) OU `uploadId` (arquivo já
    enviado por `/uploads/upload`), que é como o cliente Esri manda anexo grande."""
    upload_id = anexo.get("uploadId")
    if upload_id:
        try:
            chave_uuid = str(uuid.UUID(str(upload_id)))
        except (ValueError, AttributeError, TypeError) as e:
            raise ErroAPI(400, "upload_invalido", f"uploadId não é uuid: {upload_id!r}") from e
        cur.execute(
            "SELECT nome, content_type, chave FROM plat.esri_upload WHERE id = %s::uuid", (chave_uuid,)
        )
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "upload_inexistente", "uploadId não encontrado para este inquilino")
        import base64

        from app import objetos
        return (
            anexo.get("name") or linha["nome"],
            anexo.get("contentType") or linha["content_type"],
            base64.b64encode(objetos.ler(linha["chave"])).decode("ascii"),
        )
    dados = anexo.get("data")
    if not dados:
        raise ErroAPI(400, "anexo_sem_conteudo", "o anexo precisa de `data` (base64) ou `uploadId`")
    return anexo.get("name") or "anexo", anexo.get("contentType") or "application/octet-stream", str(dados)


def _aplicar_anexos(cur, request: Request, auth, item_id: str, bloco: dict) -> dict:
    saida = {"addResults": [], "updateResults": [], "deleteResults": []}
    for anexo in bloco.get("adds") or []:
        pai = anexo.get("parentGlobalId")
        try:
            if not pai:
                raise ErroAPI(400, "anexo_sem_pai", "anexo em applyEdits exige parentGlobalId")
            nome, tipo, conteudo = _conteudo_do_anexo(cur, anexo)
            r = anexos_mod.enviar(cur, auth, request, item_id, str(uuid.UUID(str(pai))), nome, tipo, conteudo)
            saida["addResults"].append(tr.resultado_ok(r["numero"], r["id"]))
        except (ErroAPI, ValueError) as e:
            codigo = e.status_code if isinstance(e, ErroAPI) else 400
            saida["addResults"].append(tr.resultado_erro(None, anexo.get("globalId"), codigo, str(e)))
    for anexo in bloco.get("updates") or []:
        try:
            pai = str(uuid.UUID(str(anexo.get("parentGlobalId"))))
            alvo = str(uuid.UUID(str(anexo.get("globalId"))))
            nome, tipo, conteudo = _conteudo_do_anexo(cur, anexo)
            r = anexos_mod.substituir(cur, auth, request, item_id, pai, alvo, nome, tipo, conteudo)
            saida["updateResults"].append(tr.resultado_ok(r["numero"], r["id"]))
        except (ErroAPI, ValueError, TypeError) as e:
            codigo = e.status_code if isinstance(e, ErroAPI) else 400
            saida["updateResults"].append(tr.resultado_erro(None, anexo.get("globalId"), codigo, str(e)))
    for alvo in bloco.get("deletes") or []:
        try:
            gid = str(uuid.UUID(str(alvo)))
            cur.execute(
                "SELECT globalid, numero FROM plat.feicao_anexo WHERE id = %s::uuid AND apagado_em IS NULL",
                (gid,),
            )
            linha = cur.fetchone()
            if linha is None:
                raise ErroAPI(404, "anexo_inexistente", "anexo inexistente")
            anexos_mod.apagar(cur, auth, request, item_id, str(linha["globalid"]), gid)
            saida["deleteResults"].append(tr.resultado_ok(linha["numero"], gid))
        except (ErroAPI, ValueError, TypeError) as e:
            codigo = e.status_code if isinstance(e, ErroAPI) else 400
            saida["deleteResults"].append(tr.resultado_erro(None, str(alvo), codigo, str(e)))
    return saida


# ---------------------------------------------------------------- rotas de escrita de feição
def _com_rollback(cur, resultado: dict, rollback: bool, momento: int | None) -> dict:
    if rollback and _falhou(resultado):
        cur.execute("ROLLBACK TO SAVEPOINT esri_lote")
        resultado["rolledBack"] = True
    cur.execute("RELEASE SAVEPOINT esri_lote")
    if momento is not None:
        resultado["editMoment"] = momento
    resultado.pop("avisos", None)
    return resultado


@router.post(f"{PREFIXO}/applyEdits", openapi_extra=ABERTURA, operation_id="esri_apply_edits_camada")
async def apply_edits_camada(request: Request, item_id: str, camada_id: str):
    try:
        p = await _parametros(request)
        auth = _abrir(request, item_id, camada_id, editar=True)
        rollback = _bool(p.get("rollbackOnFailure"), True)
        momento = int(time.time() * 1000) if _bool(p.get("returnEditMoment"), False) else None
        edits = {
            "adds": _lista_json(p.get("adds"), "adds"),
            "updates": _lista_json(p.get("updates"), "updates"),
            "deletes": _lista_json(p.get("deletes"), "deletes"),
        }
        anexos_bloco = _dicionario_json(p.get("attachments"), "attachments")
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            cur.execute("SAVEPOINT esri_lote")
            resultado = _aplicar(cur, request, auth, item_id, edits, p)
            if anexos_bloco:
                resultado["attachments"] = _aplicar_anexos(cur, request, auth, item_id, anexos_bloco)
            return _json(_com_rollback(cur, resultado, rollback, momento))
    except ErroAPI as e:
        return _erro_esri(e)


@router.post(f"{SERVICO}/applyEdits", openapi_extra=ABERTURA, operation_id="esri_apply_edits_servico")
async def apply_edits_servico(request: Request, item_id: str):
    """`applyEdits` do SERVIÇO: uma lista `edits`, uma entrada por camada. Este serviço publica uma camada
    só (id 0), então a lista tem no máximo uma entrada — o formato de resposta (lista por camada) é o
    mesmo que o cliente Esri espera quando houver mais."""
    try:
        p = await _parametros(request)
        auth = _abrir(request, item_id, None, editar=True)
        rollback = _bool(p.get("rollbackOnFailure"), True)
        momento = int(time.time() * 1000) if _bool(p.get("returnEditMoment"), False) else None
        edits = _lista_json(p.get("edits"), "edits")
        if not edits:
            raise ErroAPI(400, "edits_ausente", "informe edits=[{id: 0, adds: [...], ...}]")
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            cur.execute("SAVEPOINT esri_lote")
            saida = []
            for bloco in edits:
                if not isinstance(bloco, dict):
                    raise ErroAPI(400, "edits_invalido", "cada entrada de edits precisa ser um objeto")
                if str(bloco.get("id", "0")) != "0":
                    raise ErroAPI(404, "camada_nao_encontrada", "este serviço publica uma camada só (id 0)")
                r = _aplicar(cur, request, auth, item_id, bloco, p)
                if bloco.get("attachments"):
                    r["attachments"] = _aplicar_anexos(cur, request, auth, item_id, bloco["attachments"])
                r["id"] = 0
                saida.append(r)
            falhou = any(_falhou(r) for r in saida)
            if rollback and falhou:
                cur.execute("ROLLBACK TO SAVEPOINT esri_lote")
                for r in saida:
                    r["rolledBack"] = True
            cur.execute("RELEASE SAVEPOINT esri_lote")
            for r in saida:
                r.pop("avisos", None)
                if momento is not None:
                    r["editMoment"] = momento
            return _json({"resultados": saida}) if False else JSONResponse(
                json.loads(json.dumps(saida, default=str))
            )
    except ErroAPI as e:
        return _erro_esri(e)


async def _uma_operacao(request: Request, item_id: str, camada_id: str, chave: str, parametro: str):
    try:
        p = await _parametros(request)
        auth = _abrir(request, item_id, camada_id, editar=True)
        rollback = _bool(p.get("rollbackOnFailure"), True)
        momento = int(time.time() * 1000) if _bool(p.get("returnEditMoment"), False) else None
        edits = {chave: _lista_json(p.get(parametro), parametro)}
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            cur.execute("SAVEPOINT esri_lote")
            resultado = _aplicar(cur, request, auth, item_id, edits, p)
            resultado = _com_rollback(cur, resultado, rollback, momento)
        nome = {"adds": "addResults", "updates": "updateResults", "deletes": "deleteResults"}[chave]
        corpo = {nome: resultado[nome]}
        if "editMoment" in resultado:
            corpo["editMoment"] = resultado["editMoment"]
        if resultado.get("rolledBack"):
            corpo["rolledBack"] = True
        return _json(corpo)
    except ErroAPI as e:
        return _erro_esri(e)


@router.post(f"{PREFIXO}/addFeatures", openapi_extra=ABERTURA, operation_id="esri_add_features")
async def add_features(request: Request, item_id: str, camada_id: str):
    return await _uma_operacao(request, item_id, camada_id, "adds", "features")


@router.post(f"{PREFIXO}/updateFeatures", openapi_extra=ABERTURA, operation_id="esri_update_features")
async def update_features(request: Request, item_id: str, camada_id: str):
    return await _uma_operacao(request, item_id, camada_id, "updates", "features")


def _where_sql(onde: str | None, colunas) -> tuple[str, list]:
    """`where` do cliente -> SQL parametrizado pelo MESMO analisador da operação `query` (AST, lista
    branca de colunas). Vazio ou `1=1` é "sem filtro" (mesma convenção de `app/consulta/motor.py`), e
    erro de sintaxe vira 400 nomeado, nunca SQL."""
    if not onde or onde.strip() in ("", "1=1"):
        return "TRUE", []
    try:
        c = where_ast.compilar_where(onde, colunas)
    except where_ast.ErroWhere as e:
        raise ErroAPI(400, e.codigo, e.mensagem, e.detalhe) from e
    return c.sql, list(c.params)


def _ids_por_filtro(cur, schema: str, tabela: str, meta: list[dict], onde: str, geometria: Any,
                    srid_camada: int) -> list[int]:
    """`deleteFeatures` por `where` (+ `geometry` opcional): o filtro passa pelo MESMO analisador de
    `where` da operação `query` (AST, lista branca de colunas, valor sempre por parâmetro) — não existe
    caminho em que o texto do cliente vire SQL."""
    onde_sql, parametros = _where_sql(onde, campos_mod.lista_branca(meta))
    sql = f'SELECT fid FROM "{schema}"."{tabela}" WHERE {onde_sql}'
    if geometria not in (None, ""):
        obj = json.loads(geometria) if isinstance(geometria, str) else geometria
        if not isinstance(obj, dict):
            raise ErroAPI(400, "geometria_invalida", "geometry precisa ser um objeto")
        tipo = tr._tipo_esri_do_objeto(obj)
        if contar_vertices(obj, tipo) > MAX_VERTICES:
            raise ErroAPI(400, "geometria_grande", f"geometria acima de {MAX_VERTICES} vértices")
        wkid = sr_wkid(obj.get("spatialReference")) or srid_camada
        ewkt = para_ewkt(obj, tipo, wkid)
        sql += " AND ST_Intersects(geom, ST_Transform(ST_GeomFromEWKT(%s), %s))"
        parametros += [ewkt, srid_camada]
    cur.execute(sql, parametros)
    return [linha["fid"] for linha in cur.fetchall()]


@router.post(f"{PREFIXO}/deleteFeatures", openapi_extra=ABERTURA, operation_id="esri_delete_features")
async def delete_features(request: Request, item_id: str, camada_id: str):
    try:
        p = await _parametros(request)
        auth = _abrir(request, item_id, camada_id, editar=True)
        rollback = _bool(p.get("rollbackOnFailure"), True)
        momento = int(time.time() * 1000) if _bool(p.get("returnEditMoment"), False) else None
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            _item, dados = camada_ou_404(cur, item_id)
            schema, tabela = _schema_tabela(dados)
            bruto = p.get("objectIds")
            if bruto not in (None, ""):
                ids = [int(x) for x in str(bruto).replace(" ", "").split(",") if x != ""]
            elif p.get("where") or p.get("geometry"):
                meta = campos_mod.campos_da_camada(cur, schema, tabela)
                ids = _ids_por_filtro(
                    cur, schema, tabela, meta, p.get("where"), p.get("geometry"), int(dados["srid"])
                )
            else:
                raise ErroAPI(400, "filtro_ausente", "informe objectIds, ou where (e/ou geometry)")
            cur.execute("SAVEPOINT esri_lote")
            resultado = _aplicar(cur, request, auth, item_id, {"deletes": ids}, p)
            resultado = _com_rollback(cur, resultado, rollback, momento)
        corpo = {"deleteResults": resultado["deleteResults"]}
        if "editMoment" in resultado:
            corpo["editMoment"] = resultado["editMoment"]
        if resultado.get("rolledBack"):
            corpo["rolledBack"] = True
        return _json(corpo)
    except (ErroAPI, ValueError) as e:
        return _erro_esri(e if isinstance(e, ErroAPI) else ErroAPI(400, "objectids_invalido", str(e)))


# ---------------------------------------------------------------- calculate (sqlExpression -> L2-03-f)
@router.post(f"{PREFIXO}/calculate", openapi_extra=ABERTURA, operation_id="esri_calculate")
async def calculate(request: Request, item_id: str, camada_id: str):
    try:
        p = await _parametros(request)
        auth = _abrir(request, item_id, camada_id, editar=True)
        expressoes = _lista_json(p.get("calcExpression"), "calcExpression")
        if not expressoes:
            raise ErroAPI(400, "calc_expression_ausente", "informe calcExpression=[{field, sqlExpression}]")
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            _item, dados = camada_ou_404(cur, item_id)
            schema, tabela = _schema_tabela(dados)
            nomes = {c["nome"] for c in dados.get("campos") or []}
            meta = campos_mod.campos_da_camada(cur, schema, tabela)
            onde_sql, parametros = _where_sql(p.get("where"), campos_mod.lista_branca(meta))
            cur.execute(
                f'SELECT * FROM "{schema}"."{tabela}" WHERE {onde_sql} ORDER BY fid LIMIT {LOTE_MAX + 1}',
                parametros,
            )
            linhas = cur.fetchall()
            if len(linhas) > LOTE_MAX:
                raise ErroAPI(400, "lote_grande", f"where seleciona mais de {LOTE_MAX} feições; refine")
            traduzidas = []
            for e in expressoes:
                if not isinstance(e, dict) or not e.get("field"):
                    raise ErroAPI(400, "calc_invalido", "cada calcExpression precisa de `field`")
                campo = e["field"]
                if campo not in nomes:
                    raise ErroAPI(400, "campo_inexistente", f"campo inexistente nesta camada: {campo}")
                if "sqlExpression" in e and e["sqlExpression"] not in (None, ""):
                    traduzidas.append((campo, tr.traduzir_sql_para_expressao(e["sqlExpression"], nomes), None))
                elif "value" in e:
                    traduzidas.append((campo, None, e["value"]))
                else:
                    raise ErroAPI(400, "calc_expressao_vazia", "informe sqlExpression ou value")
            atualizar = []
            for linha in linhas:
                contexto = {c: linha.get(c) for c in nomes}
                novos = {}
                for campo, expressao, valor in traduzidas:
                    if expressao is None:
                        novos[campo] = valor
                    else:
                        try:
                            novos[campo] = avaliar_texto(expressao, contexto)
                        except ErroExpressao as ex:
                            raise ErroAPI(400, "calc_erro", f"{ex}", {"campo": campo}) from ex
                atualizar.append({"id": str(linha["globalid"]), "versao": linha["versao"], "atributos": novos})
            resultado = aplicar_edicoes(
                cur, request, auth, item_id, EdicoesEntrada(modo="transacao", atualizar=atualizar)
            )
        return _json({"success": True, "updatedFeatureCount": sum(1 for r in resultado.atualizar if r.sucesso)})
    except ErroAPI as e:
        return _erro_esri(e)


# ---------------------------------------------------------------- anexos no protocolo Esri
def _globalid_da_feicao(cur, dados: dict, object_id: str) -> str:
    schema, tabela = _schema_tabela(dados)
    try:
        fid = int(object_id)
    except (TypeError, ValueError) as e:
        raise ErroAPI(400, "objectid_invalido", f"objectId não é inteiro: {object_id!r}") from e
    cur.execute(f'SELECT globalid FROM "{schema}"."{tabela}" WHERE fid = %s', (fid,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta camada", {"objectId": fid})
    return str(linha["globalid"])


def _info_anexo(fid: int, a: dict) -> dict:
    return {
        "id": a["numero"], "globalId": a["id"], "parentObjectId": fid, "name": a["nome"],
        "contentType": a["content_type"], "size": a["bytes"], "keywords": "", "exifInfo": None,
    }


@router.get(f"{PREFIXO}/{{object_id}}/attachments", openapi_extra=ABERTURA_LER,
            operation_id="esri_attachment_infos")
async def attachment_infos(request: Request, item_id: str, camada_id: str, object_id: str):
    try:
        auth = _abrir(request, item_id, camada_id, editar=False)
        with db.db(auth.contexto()) as cur:
            _item, dados = camada_ou_404(cur, item_id)
            gid = _globalid_da_feicao(cur, dados, object_id)
            lista = anexos_mod.listar(cur, item_id, gid)
        return _json({"attachmentInfos": [_info_anexo(int(object_id), a) for a in lista]})
    except ErroAPI as e:
        return _erro_esri(e)


@router.get(f"{PREFIXO}/{{object_id}}/attachments/{{anexo_numero}}", openapi_extra=ABERTURA_LER,
            operation_id="esri_attachment_baixar")
async def attachment_baixar(request: Request, item_id: str, camada_id: str, object_id: str, anexo_numero: str):
    try:
        auth = _abrir(request, item_id, camada_id, editar=False)
        with db.db(auth.contexto()) as cur:
            _item, dados = camada_ou_404(cur, item_id)
            gid = _globalid_da_feicao(cur, dados, object_id)
            anexo_id = _anexo_por_numero(cur, gid, anexo_numero)
            conteudo, tipo, nome = anexos_mod.baixar(cur, item_id, gid, anexo_id)
        return Response(
            content=conteudo, media_type=tipo, headers={"Content-Disposition": f'inline; filename="{nome}"'}
        )
    except ErroAPI as e:
        return _erro_esri(e)


def _anexo_por_numero(cur, globalid: str, numero: str) -> str:
    try:
        n = int(numero)
    except (TypeError, ValueError) as e:
        raise ErroAPI(400, "anexo_invalido", f"attachmentId não é inteiro: {numero!r}") from e
    cur.execute(
        "SELECT id FROM plat.feicao_anexo WHERE numero = %s AND globalid = %s::uuid AND apagado_em IS NULL",
        (n, globalid),
    )
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "anexo_inexistente", "anexo inexistente para esta feição")
    return str(linha["id"])


async def _arquivo_do_formulario(request: Request, nomes: tuple[str, ...]) -> tuple[str, str, str]:
    import base64
    formulario = await request.form()
    for nome in nomes:
        arquivo = formulario.get(nome)
        if arquivo is not None and hasattr(arquivo, "read"):
            conteudo = await arquivo.read()
            return (
                arquivo.filename or nome,
                arquivo.content_type or "application/octet-stream",
                base64.b64encode(conteudo).decode("ascii"),
            )
    raise ErroAPI(400, "arquivo_ausente", f"envie o arquivo em multipart no campo {nomes[0]}")


@router.post(f"{PREFIXO}/{{object_id}}/addAttachment", openapi_extra=ABERTURA,
             operation_id="esri_add_attachment")
async def add_attachment(request: Request, item_id: str, camada_id: str, object_id: str):
    try:
        auth = _abrir(request, item_id, camada_id, editar=True)
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            _item, dados = camada_ou_404(cur, item_id)
            gid = _globalid_da_feicao(cur, dados, object_id)
            # o formulário só é lido DEPOIS de a camada e a feição existirem: pedido contra item de outro
            # inquilino morre em 404 sem passar por leitura de corpo (varredura cruzada, ADR 0002 §16.1)
            nome, tipo, conteudo = await _arquivo_do_formulario(request, ("attachment", "file"))
            r = anexos_mod.enviar(cur, auth, request, item_id, gid, nome, tipo, conteudo)
        return _json({"addAttachmentResult": tr.resultado_ok(r["numero"], r["id"])})
    except ErroAPI as e:
        return _erro_esri(e)


@router.post(f"{PREFIXO}/{{object_id}}/updateAttachment", openapi_extra=ABERTURA,
             operation_id="esri_update_attachment")
async def update_attachment(request: Request, item_id: str, camada_id: str, object_id: str):
    try:
        auth = _abrir(request, item_id, camada_id, editar=True)
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            _item, dados = camada_ou_404(cur, item_id)
            gid = _globalid_da_feicao(cur, dados, object_id)
            formulario = await request.form()
            numero = formulario.get("attachmentId") or request.query_params.get("attachmentId")
            if numero in (None, ""):
                raise ErroAPI(400, "anexo_ausente", "informe attachmentId")
            nome, tipo, conteudo = await _arquivo_do_formulario(request, ("attachment", "file"))
            anexo_id = _anexo_por_numero(cur, gid, str(numero))
            r = anexos_mod.substituir(cur, auth, request, item_id, gid, anexo_id, nome, tipo, conteudo)
        return _json({"updateAttachmentResult": tr.resultado_ok(r["numero"], r["id"])})
    except ErroAPI as e:
        return _erro_esri(e)


@router.post(f"{PREFIXO}/{{object_id}}/deleteAttachments", openapi_extra=ABERTURA,
             operation_id="esri_delete_attachments")
async def delete_attachments(request: Request, item_id: str, camada_id: str, object_id: str):
    try:
        p = await _parametros(request)
        auth = _abrir(request, item_id, camada_id, editar=True)
        bruto = p.get("attachmentIds")
        if bruto in (None, ""):
            raise ErroAPI(400, "anexos_ausentes", "informe attachmentIds=1,2,3")
        numeros = [x for x in str(bruto).replace(" ", "").split(",") if x != ""]
        saida = []
        with db.db(auth.contexto()) as cur:
            _marcar_origem(cur)
            _item, dados = camada_ou_404(cur, item_id)
            gid = _globalid_da_feicao(cur, dados, object_id)
            for numero in numeros:
                try:
                    anexo_id = _anexo_por_numero(cur, gid, numero)
                    anexos_mod.apagar(cur, auth, request, item_id, gid, anexo_id)
                    saida.append(tr.resultado_ok(int(numero), anexo_id))
                except ErroAPI as e:
                    saida.append(tr.resultado_erro(None, None, e.status_code, f"{e.erro}: {e.mensagem}"))
        return _json({"deleteAttachmentResults": saida})
    except ErroAPI as e:
        return _erro_esri(e)


async def _query_attachments(request: Request, item_id: str, camada_id: str):
    try:
        p = await _parametros(request)
        auth = _abrir(request, item_id, camada_id, editar=False)
        bruto = p.get("objectIds")
        if bruto in (None, ""):
            raise ErroAPI(400, "objectids_ausente", "informe objectIds=1,2,3")
        fids = [int(x) for x in str(bruto).replace(" ", "").split(",") if x != ""]
        grupos = []
        with db.db(auth.contexto()) as cur:
            _item, dados = camada_ou_404(cur, item_id)
            for fid in fids:
                gid = _globalid_da_feicao(cur, dados, str(fid))
                lista = anexos_mod.listar(cur, item_id, gid)
                grupos.append({
                    "parentObjectId": fid, "parentGlobalId": gid,
                    "attachmentInfos": [_info_anexo(fid, a) for a in lista],
                })
        return _json({"attachmentGroups": grupos})
    except (ErroAPI, ValueError) as e:
        return _erro_esri(e if isinstance(e, ErroAPI) else ErroAPI(400, "objectids_invalido", str(e)))


@router.get(f"{PREFIXO}/queryAttachments", openapi_extra=ABERTURA_LER,
            operation_id="esri_query_attachments_get")
async def query_attachments_get(request: Request, item_id: str, camada_id: str):
    return await _query_attachments(request, item_id, camada_id)


@router.post(f"{PREFIXO}/queryAttachments", openapi_extra=ABERTURA_LER,
             operation_id="esri_query_attachments_post")
async def query_attachments_post(request: Request, item_id: str, camada_id: str):
    return await _query_attachments(request, item_id, camada_id)


# ---------------------------------------------------------------- uploads (anexo grande em dois tempos)
@router.post(f"{SERVICO}/uploads/upload", openapi_extra=ABERTURA, operation_id="esri_upload")
async def upload(request: Request, item_id: str):
    """`/uploads/upload`: recebe o arquivo antes de existir feição-pai e devolve o `itemID` que o cliente
    cita depois como `uploadId` no `applyEdits`. O bloco vai para o mesmo depósito de objetos de todo o
    resto (cota e dedup por sha256 do item L0-11); esta rota só guarda o bilhete."""
    import base64

    from app import objetos
    from app.catalogo import comum
    from app.varredura_conteudo import ConteudoRecusado, escanear_cabecalho
    try:
        from app import limites
        auth = _abrir(request, item_id, None, editar=True)
        with db.db(auth.contexto()) as cur:
            item, _dados = camada_ou_404(cur, item_id)  # antes de ler o corpo, como no addAttachment
            nome, tipo, conteudo_b64 = await _arquivo_do_formulario(request, ("file", "attachment"))
            bruto = base64.b64decode(conteudo_b64)
            tipo_limpo = (tipo or "").split(";")[0].strip().lower()
            if tipo_limpo not in limites.ANEXO_TIPOS_PERMITIDOS:
                raise ErroAPI(415, "tipo_nao_permitido", f"tipo não permitido: {tipo_limpo!r}")
            if len(bruto) > limites.ANEXO_TAMANHO_MAX:
                raise ErroAPI(422, "anexo_grande", f"acima de {limites.ANEXO_TAMANHO_MAX} bytes")
            try:
                escanear_cabecalho(bruto, tipo_limpo)
            except ConteudoRecusado as e:
                raise ErroAPI(415, "conteudo_recusado", str(e)) from e
            obj = objetos.guardar(cur, "feicao_anexo", bruto, tipo_limpo, item_id=item_id,
                                  usuario_id=auth.usuario_id)
            cur.execute(
                "INSERT INTO plat.esri_upload (tenant_id, nome, content_type, bytes, sha256, chave, "
                "criado_por) VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s) RETURNING id, criado_em",
                (nome[:255], tipo_limpo, obj["bytes"], obj["sha256"], obj["chave"], auth.usuario_id),
            )
            r = cur.fetchone()
            comum.registrar_evento(
                cur, request, "camadas/upload_esri", "item", item["id"],
                {"upload_id": str(r["id"]), "bytes": obj["bytes"], "content_type": tipo_limpo},
            )
            criado = r["criado_em"]
        return _json({
            "success": True,
            "item": {
                "itemID": str(r["id"]), "itemName": nome[:255], "description": None,
                "date": int(criado.timestamp() * 1000), "committed": True,
            },
        })
    except ErroAPI as e:
        return _erro_esri(e)
