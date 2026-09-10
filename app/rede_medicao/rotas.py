"""Rotas do módulo rede_medicao (item L4-13-integracao-telemetria): publicar leitura, cadastrar a placa do
ativo, última leitura + série de 7 dias (ficha do ativo) e agregação a jusante pela topologia.

`ativo` nunca precisa existir em nenhuma tabela de feição (mesma decisão do módulo campo): é só o uuid que o
publicador e o leitor concordam em chamar de "este trafo" — por isso as rotas de leitura/publicação não
levam `rede_id` no caminho. Só a agregação a jusante leva `rede_id` (query): ela anda pela topologia de UMA
rede."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Request

from app import db, limites
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import uuid_ok
from app.erros import ErroAPI
from app.rede_medicao import servico
from app.rede_medicao.modelos import AtivoConfigEntrada, LeiturasLote

router = APIRouter(prefix="/api/rede/medicao", tags=["rede_medicao"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "rede.medir"}


def _leitura_json(r: dict) -> dict:
    return {"grandeza": r["grandeza"], "valor": r["valor"], "unidade": r["unidade"], "ts": iso(r["ts"]),
            "fonte": r["fonte"], "recebido_em": iso(r.get("recebido_em"))}


@router.post("/leituras", status_code=201, openapi_extra=ESCREVER)
def publicar_leituras(corpo: LeiturasLote, request: Request, auth: Auth = autenticado("rede.medir")):
    """Lote de leituras de sensor. Idempotente por (ativo, grandeza, ts): reenviar não duplica. Recusa item a
    item (nunca o lote inteiro) por ts futuro, grandeza/unidade desconhecida — resposta sempre 201, com o
    detalhe de quem foi aceito/duplicado/rejeitado. Depois de gravar, roda o motor de alarme (carregamento >
    100% por 30 min) para cada ativo tocado que já tem placa cadastrada — é o que deixa a ficha do ativo e o
    alarme quase em tempo real, sem depender de um job periódico."""
    with db.db(auth.contexto()) as cur:
        r = servico.publicar_leituras(cur, auth, corpo.leituras)
        alarmes = []
        for ativo in r["ativos_tocados"]:
            a = servico.avaliar_alarme_carregamento(cur, auth, request, ativo)
            if a is not None:
                alarmes.append({"ativo": ativo, **a})
    return {"aceitas": r["aceitas"], "duplicadas": r["duplicadas"], "rejeitadas": r["rejeitadas"],
            "alarmes": alarmes}


@router.put("/ativos/{ativo}", openapi_extra=ESCREVER)
def configurar_ativo(ativo: str, corpo: AtivoConfigEntrada, request: Request,
                     auth: Auth = autenticado("rede.medir")):
    """Placa do ativo (kVA/tensão nominal): sem ela o motor de alarme não calcula carregamento — não é erro
    (nem todo ativo tem placa cadastrada ainda), só fica sem essa leitura derivada."""
    aid = uuid_ok(ativo, "ativo_invalido", "ativo inválido")
    with db.db(auth.contexto()) as cur:
        r = servico.ativo_config_upsert(cur, auth, request, aid, corpo)
    return {"ativo": str(r["ativo"]), "cod_id": r["cod_id"], "kva_nominal": r["kva_nominal"],
            "tensao_nominal_v": r["tensao_nominal_v"], "atualizado_em": iso(r["atualizado_em"])}


@router.get("/ativos/{ativo}", openapi_extra=LER)
def ver_ativo(ativo: str, auth: Auth = autenticado()) -> dict:
    aid = uuid_ok(ativo, "ativo_invalido", "ativo inválido")
    with db.db(auth.contexto()) as cur:
        r = servico.ativo_config_obter(cur, aid)
    if r is None:
        return {"ativo": aid, "cod_id": None, "kva_nominal": None, "tensao_nominal_v": None,
                "atualizado_em": None, "placa_cadastrada": False}
    return {"ativo": str(r["ativo"]), "cod_id": r["cod_id"], "kva_nominal": r["kva_nominal"],
            "tensao_nominal_v": r["tensao_nominal_v"], "atualizado_em": iso(r["atualizado_em"]),
            "placa_cadastrada": True}


@router.get("/ativos/{ativo}/ultimas", openapi_extra=LER)
def ultimas_leituras(ativo: str, auth: Auth = autenticado()) -> dict:
    """Última leitura de cada grandeza publicada para este ativo — o que a ficha do ativo mostra no topo."""
    aid = uuid_ok(ativo, "ativo_invalido", "ativo inválido")
    with db.db(auth.contexto()) as cur:
        linhas = servico.ultima_leitura(cur, aid)
    return {"ativo": aid, "leituras": [_leitura_json(r) for r in linhas]}


@router.get("/ativos/{ativo}/serie", openapi_extra=LER)
def serie(ativo: str, grandeza: str, dias: int = limites.REDE_MEDICAO_SERIE_DIAS_PADRAO,
         auth: Auth = autenticado()) -> dict:
    """Série de `grandeza` nos últimos `dias` dias (padrão 7 — o gráfico da ficha do ativo)."""
    aid = uuid_ok(ativo, "ativo_invalido", "ativo inválido")
    dias = max(1, min(dias, limites.REDE_MEDICAO_SERIE_DIAS_MAX))
    with db.db(auth.contexto()) as cur:
        catalogo = servico.grandezas_catalogo(cur)
        if grandeza not in catalogo:
            raise ErroAPI(422, "grandeza_desconhecida", f"grandeza {grandeza!r} não está no catálogo")
        ate = datetime.datetime.now(datetime.UTC)
        desde = ate - datetime.timedelta(days=dias)
        linhas = servico.serie(cur, aid, grandeza, desde, ate, limites.REDE_MEDICAO_SERIE_PONTOS_MAX)
    return {"ativo": aid, "grandeza": grandeza, "unidade": catalogo[grandeza]["unidade"], "dias": dias,
            "n": len(linhas), "pontos": [{"ts": iso(r["ts"]), "valor": r["valor"]} for r in linhas]}


@router.get("/jusante", openapi_extra=LER)
def agregado_jusante(rede_id: str, ativo: str, grandeza: str = "corrente_a", janela_min: int = 15,
                     terminal: int | None = None, auth: Auth = autenticado()) -> dict:
    """Soma a leitura mais recente (até `janela_min` min) de `grandeza` entre os transformadores de
    distribuição alcançados a JUSANTE de `ativo` pela topologia derivada da rede — exemplo do portão: soma
    das correntes dos trafos de um alimentador. `terminal` desambigua um dispositivo com mais de um
    terminal (ex.: um trafo tem alta=1/baixa=2; partir do lado de baixa é o normal para "o que ele
    alimenta")."""
    rid = uuid_ok(rede_id, "rede_inexistente", "rede inexistente")
    aid = uuid_ok(ativo, "ativo_invalido", "ativo inválido")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
        r = servico.agregado_jusante(cur, auth.tenant_id, rid, aid, grandeza, janela_min, terminal)
    return {"rede_id": rid, "ativo": aid, "grandeza": grandeza, "janela_min": janela_min, **r}


@router.get("/grandezas", openapi_extra=LER)
def grandezas(auth: Auth = autenticado()) -> dict:
    with db.db(auth.contexto()) as cur:
        catalogo = servico.grandezas_catalogo(cur)
    return {"grandezas": [
        {"codigo": g["codigo"], "nome": g["nome"], "unidade": g["unidade"], "tipo": g["tipo"],
         "descricao": g["descricao"]}
        for g in catalogo.values()
    ]}


__all__ = ["router"]
