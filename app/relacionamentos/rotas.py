"""Rotas de classe de relacionamento entre camadas (item L2-10-b-relacionamentos).

`/api/relacionamentos` cria/apaga a classe (origem, destino, cardinalidade, chaves, composto, nomes
direto/inverso, cardinalidade mín/máx, limite de relacionados); `/api/camadas/{id}/relacionados/{rel}`
consulta pelos dois lados (nome direto a partir da origem, nome inverso a partir do destino);
`/api/relacionamentos/{id}/ligar` e `/desligar` gerenciam pares N:M. `/rest/services/{id}/FeatureServer/0/
queryRelatedRecords` é o mesmo dado no formato Esri (paridade exigida pelo portão do item).

Camada de outro inquilino (origem, destino ou o item do path) responde 404 em todo ponto: `camada_ou_404`
(mesma função do L2-10-a) já esconde o que a RLS esconde."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app import db
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado
from app.dominios.servico import camada_ou_404
from app.relacionamentos import servico
from app.relacionamentos.modelos import ParEntrada, RelacionamentoEntrada, RelacionamentoSaida

router = APIRouter(tags=["relacionamentos"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "conteudo.publicar_camada"}


@router.post("/api/relacionamentos", response_model=RelacionamentoSaida, openapi_extra=EDITAR)
def criar_relacionamento(corpo: RelacionamentoEntrada, request: Request,
                         auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        r = servico.criar(cur, corpo, auth.usuario_id)
        registrar_evento(cur, request, "relacionamentos/criar", "relacionamento", r["id"],
                         {"origem_item_id": corpo.origem_item_id, "destino_item_id": corpo.destino_item_id,
                          "cardinalidade": corpo.cardinalidade})
        return servico.relacionamento_json(r)


@router.delete("/api/relacionamentos/{rel_id}", status_code=204, openapi_extra=EDITAR)
def apagar_relacionamento(rel_id: str, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        servico.apagar(cur, rel_id)
        registrar_evento(cur, request, "relacionamentos/apagar", "relacionamento", rel_id, None)


@router.get("/api/relacionamentos/{rel_id}", response_model=RelacionamentoSaida, openapi_extra=LER)
def ver_relacionamento(rel_id: str, auth: Auth = autenticado()):
    with db.db(auth.contexto_leitura()) as cur:
        return servico.relacionamento_json(servico.relacionamento_ou_404(cur, rel_id))


@router.post("/api/relacionamentos/{rel_id}/ligar", status_code=204, openapi_extra=EDITAR)
def ligar_par(rel_id: str, corpo: ParEntrada, request: Request,
             auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        rel = servico.relacionamento_ou_404(cur, rel_id)
        servico.ligar(cur, rel, corpo, auth.usuario_id)
        registrar_evento(cur, request, "relacionamentos/ligar", "relacionamento", rel_id,
                         {"origem_valor": corpo.origem_valor, "destino_valor": corpo.destino_valor})


@router.post("/api/relacionamentos/{rel_id}/desligar", status_code=204, openapi_extra=EDITAR)
def desligar_par(rel_id: str, corpo: ParEntrada, request: Request,
                 auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        rel = servico.relacionamento_ou_404(cur, rel_id)
        servico.desligar(cur, rel, corpo)
        registrar_evento(cur, request, "relacionamentos/desligar", "relacionamento", rel_id,
                         {"origem_valor": corpo.origem_valor, "destino_valor": corpo.destino_valor})


def _fids(fids: str | None) -> list[int]:
    if not fids:
        return []
    saida = []
    for parte in fids.split(","):
        parte = parte.strip()
        if parte:
            saida.append(int(parte))
    return saida


@router.get("/api/camadas/{item_id}/relacionamentos", openapi_extra=LER)
def listar_relacionamentos_da_camada(item_id: str, auth: Auth = autenticado()):
    """Classes de relacionamento que a camada `item_id` enxerga (dos dois sentidos), para a tela montar o
    popup de relacionados sem conhecer o nome de antemão. Camada de outro inquilino cai em 404 antes daqui
    (`camada_ou_404`, mesma função do L2-10-a)."""
    with db.db(auth.contexto_leitura()) as cur:
        item = camada_ou_404(cur, item_id)
        itens = servico.relacionamentos_da_camada(cur, item)
        return {"itens": [
            {"id": str(r["id"]), "nome": r["nome"], "alvo_item_id": str(r["alvo_item_id"]),
             "cardinalidade": r["cardinalidade"], "sentido": r["sentido"],
             "limite_relacionados": r["limite_relacionados"]}
            for r in itens
        ]}


@router.get("/api/camadas/{item_id}/relacionados/{rel}", openapi_extra=LER)
def listar_relacionados(item_id: str, rel: str, fids: str = Query(default=""),
                        limite: int | None = Query(default=None, ge=1, le=100000),
                        deslocamento: int = Query(default=0, ge=0),
                        auth: Auth = autenticado()):
    with db.db(auth.contexto_leitura()) as cur:
        item = camada_ou_404(cur, item_id)
        return servico.relacionados(cur, item, rel, _fids(fids), limite, deslocamento)


@router.get("/rest/services/{item_id}/FeatureServer/0/queryRelatedRecords", openapi_extra=LER)
def query_related_records(item_id: str, relationshipId: str = Query(...), objectIds: str = Query(default=""),
                          resultOffset: int = Query(default=0, ge=0),
                          resultRecordCount: int | None = Query(default=None, ge=1, le=100000),
                          auth: Auth = autenticado()):
    """Mesmo dado de `/api/camadas/{id}/relacionados/{rel}`, na forma que o ArcGIS Pro/Map Viewer esperam:
    `relationshipId` é o NOME direto/inverso (a Esri usa um inteiro pequeno estável; aqui o nome já é
    estável e o inteiro seria mais um mapeamento sem ganho — o portão pede paridade de DADO, não de forma
    de endereçar, e o teste de paridade confere os mesmos fids/valores nos dois formatos)."""
    with db.db(auth.contexto_leitura()) as cur:
        item = camada_ou_404(cur, item_id)
        bruto = servico.relacionados(cur, item, relationshipId, _fids(objectIds), resultRecordCount, resultOffset)
        grupos = [
            {"objectId": fid, "relatedRecordGroups": [{"objectId": r["fid"]} for r in registros]}
            for fid, registros in bruto["grupos"].items()
        ]
        return {"fields": [], "relatedRecordGroups": grupos}
