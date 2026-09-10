"""Sincronização de réplica no protocolo Esri (item L2-04-k) sobre o mecanismo de réplica da casa
(item L2-13-b, `app/replica/servico.py`).

Rotas do SERVIÇO, na mesma raiz da `query` e do `applyEdits`: `createReplica`, `synchronizeReplica`,
`extractChanges`, `replicas`, `replicas/{replica_id}` (replicaInfo), `unRegisterReplica` e o estado do
job assíncrono (`jobs/{job_id}`) que o `createReplica` com `async=true` devolve em `statusUrl`.

Quatro decisões que valem ler antes de mexer:

1. NADA aqui escreve feição nem empacota por conta própria. `createReplica` é `servico.criar` + o MESMO
   job `replicas.criar` que o worker executa; `synchronizeReplica` vira `servico.sincronizar` (idempotência
   por chave, política de conflito, ponteiro por camada); `extractChanges` é `servico._baixar_camada` SEM
   avançar ponteiro — leitura de janela, nunca conta como sincronização (é o que a Esri faz). Este arquivo
   traduz nomes; a porta única do L2-13-b decide.

2. `serverGen` por camada é o ponteiro no relógio lógico (`plat.feicao_historico.id`): `replica_camada.
   geracao_servidor` guarda até onde o cliente já leu, `servico.relogio` dá a hora atual. A casa só tem
   `syncModel=perLayer` (uma geração por camada, nunca uma por réplica) — é o que este arquivo devolve em
   `layerServerGens` e o que os metadados do serviço anunciam (rotas_servico.py).

3. Erro: código HTTP REAL + corpo no formato Esri, mesma decisão de rotas_edicao_esri (ADR 20260907T1927).

4. EXTENSÃO DA CASA, declarada em docs/PARIDADE.md: este serviço publica UMA camada (id "0"), então o
   cliente Esri manda `layers=["0"]`. A PWA da casa anda no MESMO caminho (hipótese do item: não haver dois
   mecanismos) e pode citar OUTRAS camadas do inquilino pelo uuid no lugar do id — virando a mesma lista de
   `CamadaEntrada` do L2-13-b. Qualquer outra coisa é 404. Duas extensões menores na mesma linha: o
   `createReplica` aceita `politicaConflito` (a política é da réplica na casa) e o `synchronizeReplica`
   EXIGE a versão lida do pacote (coluna `versao` de `plat_sync`) em cada `update` — sem ela não há
   detecção de conflito, e conflito é cláusula do item.

Não implementado, declarado: `dataFormat=sqlite` no `synchronizeReplica` (só o `createReplica` exporta
GeoPackage; a sincronização devolve json embutido); `rollbackOnFailure=false` (o lote da casa é um lote só:
aplicar metade e devolver erro não é uma opção); `syncDirection=snapshot`; `queryOption=none` (recorte
só de esquema); anexos dentro do `edits` do `synchronizeReplica` (o pacote da casa leva anexos no
`createReplica`, `returnAttachments=true`).

Referência do protocolo: developers.arcgis.com/rest/services-reference/enterprise — create-replica/,
synchronize-replica/, extract-changes-feature-service/, replicas-feature-service/,
unregister-replica-feature-service/.
"""

from __future__ import annotations

import datetime
import json
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request, Response

from app import db, limites, objetos
from app.auth import escopos as esc
from app.catalogo import comum
from app.consulta import esri_edicao as tr
from app.consulta.geometria_esri import sr_wkid
from app.consulta.rotas_edicao_esri import (
    SERVICO,
    _bool,
    _dicionario_json,
    _erro_esri,
    _json,
    _lista_json,
)
from app.consulta.rotas_query import _autenticar, _parametros
from app.edicao import servico as edicao
from app.edicao.modelos import FeicaoAdicionar, FeicaoApagar, FeicaoAtualizar
from app.erros import ErroAPI
from app.jobs import servico as jobs
from app.jobs.contexto import sessao_de
from app.replica import servico
from app.replica.modelos import (
    CamadaEntrada,
    CamadaMudancas,
    MudancaServidor,
    ReplicaEntrada,
    SincronizarEntrada,
)

router = APIRouter(tags=["replicas-esri"])
ESCOPO_LER = "camada:ler"
ESCOPO_EDITAR = "camada:editar"
# o openapi_extra declara o privilégio principal; o que o código exige de fato está no corpo da rota
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CAMPO = {"x-auth": "S/T", "x-privilegio": "campo.coletar"}

ESTADOS_JOB = {
    "pendente": "esriJobSubmitted",
    "rodando": "esriJobExecuting",
    "concluido": "esriJobSucceeded",
    "falhou": "esriJobFailed",
    "cancelado": "esriJobCancelled",
}
STATUS_JOB = {
    "pendente": "Pending",
    "rodando": "InProgress",
    "concluido": "Completed",
    "falhou": "Failed",
    "cancelado": "Failed",
}


# ---------------------------------------------------------------- conversões de formato
def _valor_json(valor: Any) -> Any:
    """O protocolo Esri leva data como epoch em milissegundos e Decimal como número (mesma regra de
    app/consulta/serializar.py para a `query`)."""
    if isinstance(valor, datetime.datetime):
        dt = valor if valor.tzinfo else valor.replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(valor, datetime.date):
        return int(datetime.datetime(valor.year, valor.month, valor.day, tzinfo=datetime.timezone.utc).timestamp())
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    return valor


def _epoch(valor: Any) -> int | None:
    return _valor_json(valor) if isinstance(valor, (datetime.datetime, datetime.date)) else None


def _geojson_para_esri(g: dict | None) -> dict | None:
    """Inverso de `serializar._esri_geom_para_geojson` — o que desce para o campo sai no vocabulário
    x/y, paths, rings. MultiPolygon vira a lista de anéis de todos os polígonos, na ordem."""
    if g is None:
        return None
    tipo, c = g.get("type"), g.get("coordinates")
    if tipo == "Point":
        return {"x": c[0], "y": c[1]}
    if tipo == "MultiPoint":
        return {"points": [list(p) for p in c]}
    if tipo == "LineString":
        return {"paths": [c]}
    if tipo == "MultiLineString":
        return {"paths": c}
    if tipo == "Polygon":
        return {"rings": c}
    if tipo == "MultiPolygon":
        return {"rings": [anel for poligono in c for anel in poligono]}
    return None


def _feicao_esri(mudanca: MudancaServidor) -> dict:
    """`{attributes, geometry}` no formato Esri; `fid` e `globalid` são as colunas reais de oid/globalid
    desta implementação (mesmos nomes que o descritor da camada anuncia em objectIdField/globalIdField)."""
    atributos = {c: _valor_json(v) for c, v in (mudanca.atributos or {}).items()}
    atributos["fid"] = mudanca.fid
    atributos["globalid"] = mudanca.id
    saida: dict[str, Any] = {"attributes": atributos}
    geometria = _geojson_para_esri(mudanca.geometria)
    if geometria is not None:
        saida["geometry"] = geometria
    return saida


def _ids_de(valor: Any) -> list[str]:
    """`layers` chega como JSON em texto, lista já decodificada ou lista separada por vírgula (o form
    do services directory manda `0` ou `0,1`)."""
    if valor in (None, ""):
        return []
    if isinstance(valor, list):
        return [str(v) for v in valor]
    try:
        obj = json.loads(valor)
    except (TypeError, json.JSONDecodeError):
        obj = None
    if isinstance(obj, list):
        return [str(v) for v in obj]
    return [p.strip() for p in str(valor).split(",") if p.strip()]


def _chave_para_camada_id(item_id: str, chave: Any) -> str:
    """EXTENSÃO DA CASA (decisão 4): "0" é a camada deste serviço; uuid é outra camada do inquilino,
    resolvida com RLS dentro da transação (por `servico.criar`/`servico.sincronizar`). O resto é 404."""
    texto = str(chave)
    if texto == "0":
        return item_id
    try:
        return str(uuid.UUID(texto))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(
            404, "camada_nao_encontrada",
            "id de camada desconhecido: só '0' (a camada do serviço) ou uuid de camada do inquilino",
            {"id": texto},
        ) from e


def _chave_de_camada(camada_id: str, item_id: str) -> str | int:
    """A chave que o CLIENTE usa para citar a camada nas respostas: `0` para a camada do serviço
    (número, como a Esri devolve), o próprio uuid para as camadas da extensão."""
    return 0 if camada_id == item_id else camada_id


def _camadas_entrada(cur, item_id: str, ids: list[str], queries_texto: Any) -> list[CamadaEntrada]:
    """`layers` + `layerQueries` -> `CamadaEntrada` do L2-13-b. `queryOption` aceito: `useFilter`
    (exige `where`, na MESMA linguagem da `query` da casa) e `all` (recorte inteiro)."""
    queries = _dicionario_json(queries_texto, "layerQueries")
    saida: list[CamadaEntrada] = []
    for chave in ids:
        camada_id = _chave_para_camada_id(item_id, chave)
        consulta = queries.get(chave)
        filtro = None
        if isinstance(consulta, dict):
            opcao = consulta.get("queryOption") or ("useFilter" if consulta.get("where") else "all")
            if opcao == "useFilter":
                filtro = consulta.get("where")
                if not filtro:
                    raise ErroAPI(400, "where_ausente", f"layerQueries[{chave}] pede useFilter sem where")
            elif opcao != "all":
                raise ErroAPI(
                    422, "queryoption_nao_suportado",
                    "queryOption aceita 'useFilter' e 'all'; 'none' (recorte só de esquema) não é suportado",
                    {"camada": chave, "recebido": opcao},
                )
        saida.append(CamadaEntrada(camada_id=camada_id, filtro=filtro))
    return saida


def _extensao(cur, geometry: Any, in_sr: Any, srid_camada: int) -> dict | None:
    """`geometry` (+ `inSR`) do createReplica -> Polygon GeoJSON em EPSG:4326, que é o que
    `plat.replica.extensao` guarda. Envelope simples vira polígono aqui; as outras formas passam pelo
    conversor da escrita Esri (`esri_edicao.geojson_de_esri`), que já lê o spatialReference declarado."""
    if geometry in (None, ""):
        return None
    geom = _dicionario_json(geometry, "geometry")
    if all(k in geom for k in ("xmin", "ymin", "xmax", "ymax")):
        geojson = {"type": "Polygon", "coordinates": [[
            [geom["xmin"], geom["ymin"]], [geom["xmax"], geom["ymin"]],
            [geom["xmax"], geom["ymax"]], [geom["xmin"], geom["ymax"]], [geom["xmin"], geom["ymin"]],
        ]]}
        srid = sr_wkid(geom.get("spatialReference")) or (int(in_sr) if in_sr not in (None, "") else 4326)
    else:
        geojson, declarado = tr.geojson_de_esri(cur, geom, srid_camada)
        srid = declarado or (int(in_sr) if in_sr not in (None, "") else srid_camada)
    if srid != 4326:
        cur.execute(
            "SELECT ST_AsGeoJSON(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), %s), 4326)) AS g",
            (json.dumps(geojson), srid),
        )
        linha = cur.fetchone()
        if not linha or not linha["g"]:
            raise ErroAPI(400, "extensao_invalida", "a geometria do createReplica não pôde ser convertida")
        geojson = json.loads(linha["g"])
    return geojson


def _abs(request: Request, item_id: str, caminho: str) -> str:
    return str(request.base_url).rstrip("/") + f"/rest/services/{item_id}/FeatureServer/{caminho}"


def _gens_de(camadas: list[dict], item_id: str) -> list[dict]:
    return [{"id": _chave_de_camada(c["camada_id"], item_id), "serverGen": int(c["geracao_servidor"])}
            for c in camadas]


def _exigir_editar_feicao(auth) -> None:
    """Mesma exigência de `_abrir(editar=True)` (rotas_edicao_esri): subir lote escreve feição."""
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
            {"exigido": "feicoes.editar|feicoes.editar_total"},
        )


def _replica_do_servico(cur, auth, item_id: str, replica_id: str, para_escrita: bool = False) -> dict:
    """Réplica por uuid + dono + pertencimento a este serviço. RLS já isola inquilino (404)."""
    replica = servico._replica_ou_404(cur, replica_id, para_escrita=para_escrita)
    servico._exigir_dono(auth, replica)
    camadas = servico._camadas_da_replica(cur, replica)
    if item_id not in {c["camada_id"] for c in camadas}:
        raise ErroAPI(404, "replica_fora_do_servico", "esta réplica não contém a camada deste serviço")
    return replica


# ---------------------------------------------------------------- createReplica
@router.post(f"{SERVICO}/createReplica", openapi_extra=CAMPO, operation_id="esri_create_replica")
async def create_replica(request: Request, item_id: str):
    try:
        p = await _parametros(request)
        auth = _autenticar(request, item_id, ESCOPO_LER)
        esc.exigir_escopo(auth, "campo.coletar")
        ids = _ids_de(p.get("layers"))
        if not ids:
            raise ErroAPI(
                400, "layers_ausente",
                "informe layers=0 (ou 0 junto com uuid de outra camada, extensão da casa)",
            )
        assincrono = _bool(p.get("async"), False)
        transporte = p.get("transportType") or "esriTransportTypeUrl"
        formato = p.get("dataFormat") or "sqlite"
        if formato not in ("sqlite", "json"):
            raise ErroAPI(
                422, "dataformat_nao_suportado",
                "dataFormat aceita 'sqlite' (GeoPackage por URL) e 'json' (feições embutidas)",
                {"recebido": formato},
            )
        if formato == "json" and transporte != "esriTransportTypeEmbedded":
            raise ErroAPI(422, "transporte_invalido",
                          "dataFormat json é devolvido embutido: transportType=esriTransportTypeEmbedded")
        if formato == "sqlite" and transporte != "esriTransportTypeUrl":
            raise ErroAPI(422, "transporte_invalido",
                          "o GeoPackage sai por URL: transportType=esriTransportTypeUrl")
        with db.db(auth.contexto()) as cur:
            _item, dados = edicao.camada_ou_404(cur, item_id)
            camadas = _camadas_entrada(cur, item_id, ids, p.get("layerQueries"))
            corpo = ReplicaEntrada(
                nome=(p.get("replicaName") or f"replica-{datetime.datetime.now(datetime.timezone.utc):%Y%m%d%H%M%S}")
                [: limites.REPLICA_NOME_MAX],
                camadas=camadas,
                dispositivo=(str(p.get("dispositivo"))[:200] if p.get("dispositivo") else "protocolo-esri"),
                politica_conflito=p.get("politicaConflito") or "servidor_vence",
                extensao=_extensao(cur, p.get("geometry"), p.get("inSR"), int(dados["srid"])),
                anexos=_bool(p.get("returnAttachments"), False),
            )
            # `criar` valida filtro e extensão AGORA (422 na cara do usuário, nunca job falho depois)
            replica = servico.criar(cur, request, auth, corpo)
            replica_id = str(replica["id"])
        # o job fica FORA da transação de propósito, como em app/replica/rotas.py: criado depois de
        # a réplica existir, senão o worker pode pegá-lo antes do commit e não achar a réplica
        job = jobs.criar(sessao_de(auth), "replicas.criar", {"replica_id": replica_id})
        with db.db(auth.contexto()) as cur:
            cur.execute("UPDATE plat.replica SET job_id = %s::uuid WHERE id = %s::uuid",
                        (job["id"], replica_id))
        if assincrono:
            # além de statusUrl/jobId, a resposta assíncrona também carrega replicaID/replicaName:
            # o cliente pode desistir e dar unRegisterReplica SEM esperar o job terminar (e o teste
            # consegue limpar o que criou). O Esri tolera campos a mais na resposta do submit.
            return _json({
                "replicaName": replica["nome"],
                "replicaID": replica_id,
                "statusUrl": _abs(request, item_id, f"jobs/{job['id']}"),
                "jobId": str(job["id"]),
            })
        # async=false: gera o pacote na hora — o MESMO `gerar_pacote` que a tarefa `replicas.criar`
        # executa no worker (app/replica/tarefas.py); aqui sem depender de worker de pé
        with db.db(auth.contexto()) as cur:
            servico.gerar_pacote(cur, replica_id)
            replica = servico._replica_ou_404(cur, replica_id)
            camadas_rep = servico._camadas_da_replica(cur, replica)
        base = {
            "replicaName": replica["nome"],
            "replicaID": replica_id,
            "serviceUrl": _abs(request, item_id, ""),
            "syncModel": "perLayer",
            "layerServerGens": _gens_de(camadas_rep, item_id),
        }
        if formato == "sqlite":
            return _json({
                **base,
                "transportType": "esriTransportTypeUrl",
                "responseType": "esriReplicaResponseTypeData",
                "URL": _abs(request, item_id, f"replicas/{replica_id}/pacote"),
                "size": replica["pacote_bytes"],
                "count": sum(c["feicoes"] for c in camadas_rep),
            })
        # json embutido: as feições do recorte na própria resposta, no estado da geração do pacote
        embutidas = []
        with db.db(auth.contexto(), somente_leitura=True) as cur_leitura:
            for c in camadas_rep:
                baixada = servico._baixar_camada(cur_leitura, dict(c), int(c["geracao_servidor"]), set(),
                                                 replica.get("extensao_geojson"))
                embutidas.append({
                    "id": _chave_de_camada(c["camada_id"], item_id),
                    "features": {"adds": [_feicao_esri(m) for m in baixada.mudancas if m.operacao != "apagar"]},
                })
        return _json({
            **base,
            "transportType": "esriTransportTypeEmbedded",
            "responseType": "esriReplicaResponseTypeData",
            "layers": embutidas,
        })
    except ErroAPI as e:
        return _erro_esri(e)


# ---------------------------------------------------------------- synchronizeReplica
def _mudancas_da_entrada(cur, item_id: str, entrada: dict, dados_por_camada: dict[str, dict],
                         pedido: dict) -> CamadaMudancas:
    """Uma entrada de `edits` (`{id, features: {adds, updates, deleteIds}}`) -> `CamadaMudancas` da casa,
    e um `pedido` com os identificadores do cliente para os vetores de resultado da resposta."""
    chave = entrada.get("id")
    camada_id = _chave_para_camada_id(item_id, chave)
    linha = dados_por_camada.get(camada_id)
    if linha is None:
        raise ErroAPI(404, "camada_fora_da_replica", "a camada não faz parte desta réplica",
                      {"camada_id": camada_id})
    srid = int(linha["dados"]["srid"])
    fei = entrada.get("features") or {}
    if not isinstance(fei, dict):
        raise ErroAPI(400, "edits_invalido", f"edits[{chave}].features precisa ser um objeto")

    adiciona: list[FeicaoAdicionar] = []
    for f in fei.get("adds") or []:
        if not isinstance(f, dict):
            raise ErroAPI(400, "edits_invalido", f"edits[{chave}].adds tem de ser lista de feições")
        geometria = None
        if f.get("geometry") not in (None, {}, ""):
            geojson, _declarado = tr.geojson_de_esri(cur, f["geometry"], srid)
            geometria = geojson
        adiciona.append(FeicaoAdicionar(
            atributos=tr.atributos_limpos(f.get("attributes")),
            geometria=geometria,
        ))

    atualiza: list[FeicaoAtualizar] = []
    for f in fei.get("updates") or []:
        if not isinstance(f, dict):
            raise ErroAPI(400, "edits_invalido", f"edits[{chave}].updates tem de ser lista de feições")
        atributos = f.get("attributes") or {}
        globalid = f.get("globalId") or tr.valor_por_nome(atributos, tr.NOMES_GLOBALID)
        if not globalid:
            raise ErroAPI(400, "globalid_ausente", f"edits[{chave}].updates: toda feição precisa de globalId")
        globalid = str(globalid)
        try:
            uuid.UUID(globalid)
        except (ValueError, AttributeError, TypeError) as e:
            raise ErroAPI(400, "globalid_invalido", f"edits[{chave}].updates: globalId não é uuid: {globalid!r}") from e
        versao = f.get("versao") or f.get("version") or atributos.get("versao")
        if versao in (None, ""):
            # extensão da casa (decisão 4): sem a versão lida no pacote não há detecção de conflito
            raise ErroAPI(
                400, "versao_ausente",
                f"edits[{chave}].updates: informe a versão lida no pacote (coluna versao da tabela plat_sync)",
                {"globalId": globalid},
            )
        geometria = None
        if f.get("geometry") not in (None, {}, ""):
            geojson, _declarado = tr.geojson_de_esri(cur, f["geometry"], srid)
            geometria = geojson
        limpos = tr.atributos_limpos(atributos)
        limpos.pop("versao", None)
        atualiza.append(FeicaoAtualizar(id=globalid, versao=int(versao), atributos=limpos or None,
                                        geometria=geometria))

    apagas: list[FeicaoApagar] = []
    for alvo in fei.get("deleteIds") or fei.get("deletes") or []:
        globalid = str(alvo)
        try:
            uuid.UUID(globalid)
        except (ValueError, AttributeError, TypeError) as e:
            raise ErroAPI(400, "globalid_invalido", f"edits[{chave}].deleteIds: não é uuid: {globalid!r}") from e
        apagas.append(FeicaoApagar(id=globalid))

    pedido.update({
        "adds": [None] * len(adiciona),  # o servidor atribui o globalid; o vetor sai na ordem enviada
        "updates": [f.id for f in atualiza],
        "deletes": [f.id for f in apagas],
    })
    return CamadaMudancas(camada_id=camada_id, adicionar=adiciona, atualizar=atualiza, apagar=apagas)


@router.post(f"{SERVICO}/synchronizeReplica", openapi_extra=CAMPO, operation_id="esri_synchronize_replica")
async def synchronize_replica(request: Request, item_id: str):
    try:
        p = await _parametros(request)
        auth = _autenticar(request, item_id, ESCOPO_EDITAR)
        esc.exigir_escopo(auth, "campo.coletar")
        _exigir_editar_feicao(auth)
        replica_id = p.get("replicaID")
        if replica_id in (None, ""):
            raise ErroAPI(400, "replicaid_ausente", "informe replicaID")
        replica_id = comum.uuid_ok(str(replica_id), "replicaid_invalido", "replicaID não é uuid")
        direcao = p.get("syncDirection") or "bidirectional"
        if direcao not in ("download", "upload", "bidirectional"):
            raise ErroAPI(
                422, "syncdirection_nao_suportado",
                "syncDirection aceita 'download', 'upload' e 'bidirectional'; 'snapshot' não é suportado",
                {"recebido": direcao},
            )
        if "rollbackOnFailure" in p and not _bool(p.get("rollbackOnFailure"), True):
            raise ErroAPI(
                422, "rollback_on_failure_falso_nao_suportado",
                "o lote da casa é um lote só: qualquer falha volta tudo (rollbackOnFailure=false não é opção)",
            )
        formato = p.get("dataFormat") or "json"
        if formato != "json":
            raise ErroAPI(422, "dataformat_nao_suportado",
                          "synchronizeReplica devolve json embutido; sqlite só no createReplica",
                          {"recebido": formato})
        edits_cli = _lista_json(p.get("edits"), "edits")
        # idempotência (refutação do item): a mesma chave de lote aplicada duas vezes devolve a MESMA
        # resposta e aplica ZERO — chaveada pelo replicaClientGen do cliente (ou pela chave da casa)
        cliente_gen = p.get("replicaClientGen")
        idempotencia = (
            p.get("idempotencia")
            or (f"esri-sinc:{replica_id}:{cliente_gen}" if cliente_gen not in (None, "")
                else f"esri-sinc:{replica_id}:{uuid.uuid4()}")
        )
        with db.db(auth.contexto()) as cur:
            replica = _replica_do_servico(cur, auth, item_id, replica_id, para_escrita=True)
            camadas = {c["camada_id"]: c for c in servico._camadas_da_replica(cur, replica)}
            pedidos: list[dict] = []
            lotes: list[CamadaMudancas] = []
            for entrada in edits_cli:
                if not isinstance(entrada, dict) or "id" not in entrada:
                    raise ErroAPI(400, "edits_invalido", "cada entrada de edits precisa de id e features")
                pedido: dict = {"chave": str(entrada["id"]), "camada_id": _chave_para_camada_id(item_id, entrada["id"])}
                pedidos.append(pedido)
                lotes.append(_mudancas_da_entrada(cur, item_id, entrada, camadas, pedido))
            corpo = SincronizarEntrada(idempotencia=str(idempotencia), camadas=lotes,
                                       baixar=(direcao != "upload"))
            saida = servico.sincronizar(cur, request, auth, replica_id, corpo)
            gens_agora = servico._camadas_da_replica(cur, servico._replica_ou_404(cur, replica_id))
        gens = _gens_de(gens_agora, item_id)
        if saida.baixadas:
            # resposta repetida tem de ser idêntica à original: usa a geração GRAVADA, não a de agora
            por_camada = {b.camada_id: b.ate for b in saida.baixadas}
            gens = [{"id": _chave_de_camada(c["camada_id"], item_id),
                     "serverGen": por_camada.get(c["camada_id"], int(c["geracao_servidor"]))}
                    for c in gens_agora]

        conflitos = {(c.camada_id, c.operacao, c.id): c for c in saida.conflitos}

        def _resultado_de(camada_id: str, operacao: str, gid: str) -> dict:
            conflito = conflitos.get((camada_id, operacao, gid))
            if conflito is not None and conflito.resolucao != "cliente":
                # o lote do cliente NÃO venceu nesta feição: resultado de erro, como a Esri devolve
                return tr.resultado_erro(None, gid, 409,
                                         f"conflito resolvido: {conflito.resolucao}")
            return tr.resultado_ok(None, gid)

        resultado = {
            "replicaID": replica_id,
            "transportType": "esriTransportTypeEmbedded",
            "responseType": ("esriReplicaResponseTypeNoEdits"
                             if not saida.subidas and not saida.baixadas
                             else "esriReplicaResponseTypeEdits"),
            "syncModel": "perLayer",
            "layerServerGens": gens,
            "repetida": saida.repetida,  # extensão da casa: o cliente lê que este lote já tinha sido aplicado
            "edits": [],
        }
        baixadas_por_camada = {b.camada_id: b for b in saida.baixadas}
        vistos: set[str] = set()
        for pedido in pedidos:
            camada_id = pedido["camada_id"]
            vistos.add(camada_id)
            features: dict[str, Any] = {
                "addResults": [tr.resultado_ok(None, None) for _ in pedido["adds"]],
                "updateResults": [_resultado_de(camada_id, "atualizar", gid) for gid in pedido["updates"]],
                "deleteResults": [_resultado_de(camada_id, "apagar", gid) for gid in pedido["deletes"]],
            }
            baixada = baixadas_por_camada.get(camada_id)
            if baixada is not None:
                features["adds"] = [_feicao_esri(m) for m in baixada.mudancas if m.operacao == "inserir"]
                features["updates"] = [_feicao_esri(m) for m in baixada.mudancas if m.operacao == "atualizar"]
                features["deleteIds"] = [m.id for m in baixada.mudancas if m.operacao == "apagar"]
                if baixada.truncado:
                    features["exceededTransferLimit"] = True
            resultado["edits"].append({"id": _chave_de_camada(camada_id, item_id), "features": features})
        if direcao != "upload":
            for camada_id, baixada in baixadas_por_camada.items():
                if camada_id in vistos:
                    continue
                features: dict[str, Any] = {
                    "addResults": [], "updateResults": [], "deleteResults": [],
                    "adds": [_feicao_esri(m) for m in baixada.mudancas if m.operacao == "inserir"],
                    "updates": [_feicao_esri(m) for m in baixada.mudancas if m.operacao == "atualizar"],
                    "deleteIds": [m.id for m in baixada.mudancas if m.operacao == "apagar"],
                }
                if baixada.truncado:
                    features["exceededTransferLimit"] = True
                resultado["edits"].append({"id": _chave_de_camada(camada_id, item_id), "features": features})
        return _json(resultado)
    except ErroAPI as e:
        return _erro_esri(e)


# ---------------------------------------------------------------- extractChanges
@router.post(f"{SERVICO}/extractChanges", openapi_extra=CAMPO, operation_id="esri_extract_changes")
async def extract_changes(request: Request, item_id: str):
    try:
        p = await _parametros(request)
        auth = _autenticar(request, item_id, ESCOPO_LER)
        esc.exigir_escopo(auth, "campo.coletar")
        replica_id = p.get("replicaID")
        if replica_id in (None, ""):
            raise ErroAPI(400, "replicaid_ausente", "informe replicaID")
        replica_id = comum.uuid_ok(str(replica_id), "replicaid_invalido", "replicaID não é uuid")
        formato = p.get("dataFormat") or "json"
        if formato not in ("json", ""):
            raise ErroAPI(422, "dataformat_nao_suportado", "extractChanges devolve json embutido",
                          {"recebido": formato})
        pedidos_gens = _lista_json(p.get("layerServerGens"), "layerServerGens")
        server_gens = p.get("serverGens")
        if not pedidos_gens and server_gens not in (None, ""):
            # forma perReplica: um número (ou par [min,max]) vale para todas as camadas da réplica
            if isinstance(server_gens, str):
                try:
                    server_gens = json.loads(server_gens)
                except json.JSONDecodeError as e:
                    raise ErroAPI(400, "servergens_invalido", "serverGens não é JSON válido") from e
            gen = server_gens[0] if isinstance(server_gens, list) else server_gens
            pedidos_gens = [{"id": "*", "serverGen": gen}]
        if not pedidos_gens:
            raise ErroAPI(400, "servergens_ausente",
                          "informe layerServerGens=[{id, serverGen}] ou serverGens")
        devolve_insere = _bool(p.get("returnInserts"), True)
        devolve_atualiza = _bool(p.get("returnUpdates"), True)
        devolve_apaga = _bool(p.get("returnDeletes"), True)
        edits: list[dict] = []
        gens_saida: list[dict] = []
        with db.db(auth.contexto(), somente_leitura=True) as cur:
            replica = _replica_do_servico(cur, auth, item_id, replica_id)
            servico._exigir_viva(replica)  # mesma regra do sincronizar: vencida não serve rastreio
            camadas = {c["camada_id"]: c for c in servico._camadas_da_replica(cur, replica)}
            for pedido in pedidos_gens:
                if not isinstance(pedido, dict) or "serverGen" not in pedido:
                    raise ErroAPI(400, "servergens_invalido",
                                  "cada layerServerGens precisa de id e serverGen")
                chave = pedido["id"]
                camada = camadas.get(item_id if str(chave) == "0" else _chave_para_camada_id(item_id, chave))
                if camada is None:
                    raise ErroAPI(404, "camada_fora_da_replica", "a camada não faz parte desta réplica",
                                  {"camada_id": str(chave)})
                desde = int(pedido["serverGen"])
                copia = dict(camada)
                copia["geracao_servidor"] = desde
                ate = servico.relogio(cur, camada["dados"])
                # leitura de janela SEM avançar ponteiro: extractChanges não conta como sincronização
                baixada = servico._baixar_camada(cur, copia, ate, set(), replica.get("extensao_geojson"))
                mudancas = [
                    m for m in baixada.mudancas
                    if (m.operacao == "inserir" and devolve_insere)
                    or (m.operacao == "atualizar" and devolve_atualiza)
                    or (m.operacao == "apagar" and devolve_apaga)
                ]
                features = {
                    "adds": [_feicao_esri(m) for m in mudancas if m.operacao == "inserir"],
                    "updates": [_feicao_esri(m) for m in mudancas if m.operacao == "atualizar"],
                    "deleteIds": [m.id for m in mudancas if m.operacao == "apagar"],
                }
                if baixada.truncado:
                    features["exceededTransferLimit"] = True
                edits.append({"id": _chave_de_camada(camada["camada_id"], item_id), "features": features})
                gens_saida.append({"id": _chave_de_camada(camada["camada_id"], item_id), "serverGen": ate})
        return _json({
            "replicaID": replica_id,
            "transportType": "esriTransportTypeEmbedded",
            "responseType": "esriDataChangesResponseTypeEdits",
            "syncModel": "perLayer",
            "layerServerGens": gens_saida,
            "edits": edits,
        })
    except ErroAPI as e:
        return _erro_esri(e)


# ---------------------------------------------------------------- réplicas do serviço
def _replicas_do_servico(cur, auth, item_id: str) -> list[dict]:
    """Réplicas que contêm a camada deste serviço, visíveis ao chamador (dono; administrador vê tudo) —
    a mesma regra de visibilidade de `servico.listar`, aqui com o recorte por camada do serviço."""
    dono = "" if auth.tem("conteudo.ver_tudo") else " AND r.dono_id = %s"
    parametros: list[Any] = [item_id] if dono == "" else [item_id, auth.usuario_id]
    cur.execute(
        "SELECT r.*, ST_AsGeoJSON(r.extensao) AS extensao_geojson FROM plat.replica r "
        "JOIN plat.replica_camada rc ON rc.replica_id = r.id AND rc.camada_id = %s::uuid"
        + dono + " ORDER BY r.criada_em DESC",
        parametros,
    )
    return [dict(r) for r in cur.fetchall()]


def _status_replica(replica: dict) -> str:
    if replica["estado"] == "pronta":
        return "Completed"
    if replica["estado"] == "falhou":
        return "Failed"
    return "Pending"


@router.get(f"{SERVICO}/replicas", openapi_extra=LER, operation_id="esri_replicas")
async def listar_replicas(request: Request, item_id: str):
    try:
        auth = _autenticar(request, item_id, ESCOPO_LER)
        with db.db(auth.contexto(), somente_leitura=True) as cur:
            edicao.camada_ou_404(cur, item_id)
            replicas = _replicas_do_servico(cur, auth, item_id)
        return _json({"replicas": [
            {
                "replicaName": r["nome"],
                "replicaID": str(r["id"]),
                "owner": r["dono_id"],
                "status": _status_replica(r),
                "creationDate": _epoch(r["criada_em"]),
                "lastSyncDate": _epoch(r.get("ultima_sincronizacao")),
                "expirationDate": _epoch(r["expira_em"]),
            }
            for r in replicas
        ]})
    except ErroAPI as e:
        return _erro_esri(e)


@router.get(f"{SERVICO}/replicas/{{replica_id}}", openapi_extra=LER, operation_id="esri_replica_info")
async def replica_info(request: Request, item_id: str, replica_id: str):
    try:
        auth = _autenticar(request, item_id, ESCOPO_LER)
        replica_id = comum.uuid_ok(replica_id, "replicaid_invalido", "replicaID não é uuid")
        with db.db(auth.contexto(), somente_leitura=True) as cur:
            replica = _replica_do_servico(cur, auth, item_id, replica_id)
            camadas = servico._camadas_da_replica(cur, replica)
        return _json({
            "replicaName": replica["nome"],
            "replicaID": replica_id,
            "replicaOwner": replica["dono_id"],
            "replicaRole": "child",
            "serviceUrl": _abs(request, item_id, ""),
            "syncModel": "perLayer",
            "targetType": "client",
            "dataFormat": "sqlite",
            "transportType": "esriTransportTypeUrl",
            "status": _status_replica(replica),
            "creationDate": _epoch(replica["criada_em"]),
            "lastSyncDate": _epoch(replica.get("ultima_sincronizacao")),
            "expirationDate": _epoch(replica["expira_em"]),
            "expirada": servico.expirada(replica),
            "layerServerGens": _gens_de(camadas, item_id),
            "layers": [{"id": _chave_de_camada(c["camada_id"], item_id), "name": c["nome_gpkg"],
                        "rowCount": c["feicoes"], "serverGen": int(c["geracao_servidor"])}
                       for c in camadas],
            "politics": {"conflito": replica["politica_conflito"]},  # extensão da casa
        })
    except ErroAPI as e:
        return _erro_esri(e)


@router.get(f"{SERVICO}/replicas/{{replica_id}}/pacote", openapi_extra=LER,
            operation_id="esri_replica_pacote")
def baixar_pacote_replica(request: Request, item_id: str, replica_id: str):
    """O `URL` que o `createReplica` (esriTransportTypeUrl) devolve: o mesmo GeoPackage do pacote da
    casa (`/api/replicas/{id}/pacote`), mesmo media type, mesmo sha256 no cabeçalho."""
    try:
        auth = _autenticar(request, item_id, ESCOPO_LER)
        replica_id = comum.uuid_ok(replica_id, "replica_inexistente", "réplica inexistente")
        with db.db(auth.contexto(), somente_leitura=True) as cur:
            replica = _replica_do_servico(cur, auth, item_id, replica_id)
        if replica["estado"] != "pronta" or not replica.get("pacote_chave"):
            raise ErroAPI(409, "replica_nao_pronta",
                          f"a réplica está em {replica['estado']}; o pacote ainda não existe",
                          {"estado": replica["estado"], "erro": replica.get("erro")})
        conteudo = objetos.ler(replica["pacote_chave"])
        return Response(
            content=conteudo, media_type=servico.CONTENT_TYPE,
            headers={"content-disposition": f'attachment; filename="replica-{replica_id}.gpkg"',
                     "x-plat-sha256": replica["pacote_sha256"] or ""},
        )
    except ErroAPI as e:
        return _erro_esri(e)


@router.post(f"{SERVICO}/unRegisterReplica", openapi_extra=CAMPO, operation_id="esri_unregister_replica")
async def unregister_replica(request: Request, item_id: str):
    try:
        p = await _parametros(request)
        auth = _autenticar(request, item_id, ESCOPO_LER)
        esc.exigir_escopo(auth, "campo.coletar")
        replica_id = p.get("replicaID")
        if replica_id in (None, ""):
            raise ErroAPI(400, "replicaid_ausente", "informe replicaID")
        replica_id = comum.uuid_ok(str(replica_id), "replicaid_invalido", "replicaID não é uuid")
        with db.db(auth.contexto()) as cur:
            _replica_do_servico(cur, auth, item_id, replica_id, para_escrita=True)
            servico.apagar(cur, request, auth, replica_id)
        return _json({"success": True})
    except ErroAPI as e:
        return _erro_esri(e)


# ---------------------------------------------------------------- estado do job assíncrono
@router.get(f"{SERVICO}/jobs/{{job_id}}", openapi_extra=LER, operation_id="esri_job_status")
async def estado_job(request: Request, item_id: str, job_id: str):
    """O `statusUrl` que o `createReplica(async=true)` devolve. O estado é o da fila da casa
    (`plat.job`, L0-05); aqui só se traduz para o vocabulário esriJob*/Pending-InProgress."""
    try:
        auth = _autenticar(request, item_id, ESCOPO_LER)
        job_id = comum.uuid_ok(job_id, "job_inexistente", "job inexistente")
        with db.db(auth.contexto(), somente_leitura=True) as cur:
            cur.execute(
                "SELECT id, tipo, estado, progresso, mensagem, usuario_id, criado_em, iniciado_em, "
                "terminado_em, parametros FROM plat.job WHERE id = %s::uuid",
                (job_id,),
            )
            job = cur.fetchone()
        if job is None:
            raise ErroAPI(404, "job_inexistente", "job inexistente")
        if job["usuario_id"] != auth.usuario_id and not auth.tem("conteudo.ver_tudo"):
            raise ErroAPI(403, "job_de_outro_usuario", "este job é de outro usuário")
        estado = job["estado"]
        corpo: dict[str, Any] = {
            "jobId": str(job["id"]),
            "jobStatus": ESTADOS_JOB.get(estado, "esriJobSubmitted"),
            "status": STATUS_JOB.get(estado, "Pending"),
            "tipo": job["tipo"],
            "progresso": job["progresso"],
            "mensagem": job["mensagem"],
            "submissionTime": _epoch(job["criado_em"]),
            "lastUpdatedTime": _epoch(job["terminado_em"]) or _epoch(job["iniciado_em"]),
        }
        replica_id = (job["parametros"] or {}).get("replica_id")
        if replica_id:
            corpo["resultUrl"] = _abs(request, item_id, f"replicas/{replica_id}/pacote")
        if estado == "falhou":
            corpo["error"] = tr.corpo_erro_esri(500, job["mensagem"] or "job falhou")
        return _json(corpo)
    except ErroAPI as e:
        return _erro_esri(e)
