"""Rotas da exportação COMPLETA do inquilino (item L0-06-d-exportar-inquilino; ADR 0018 seção do item):

    GET    /api/inquilino/exportar/estimativa      tamanho estimado ANTES de pedir, e se a cota do dia já foi
    POST   /api/inquilino/exportar                pede o pacote (privilégio org.exportar, 1x/dia UTC — 429)
    GET    /api/inquilino/exportacoes              lista as pedidas por este inquilino
    GET    /api/inquilino/exportacoes/{id}         estado, contagens e link de download
    GET    /api/inquilino/exportacoes/{id}/baixar  o pacote, em blocos
    DELETE /api/inquilino/exportacoes/{id}         cancela a pendente ou apaga o arquivo pronto

Só quem tem `org.exportar` (perfil admin, migração 003) vê e pede — nunca um editor ou visualizador; o
inquilino inteiro (inclusive dado de outros usuários) sai no pacote, então o privilégio é o mesmo que já
guarda "exportar o inquilino, relatórios"."""

from __future__ import annotations

from fastapi import Request
from fastapi.routing import APIRouter

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.erros import ErroAPI
from app.exportacao.rotas import ESTADOS_APAGAVEIS
from app.exportacao_inquilino import motor
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["exportacao_inquilino"])
EXPORTAR = {"x-auth": "S/T", "x-privilegio": "org.exportar"}


def _json(r: dict, base_url: str = "") -> dict:
    pronta = r["estado"] == "pronta"
    return {
        "id": str(r["id"]), "estado": r["estado"], "job_id": str(r["job_id"]) if r["job_id"] else None,
        "arquivo_item_id": str(r["arquivo_item_id"]) if r["arquivo_item_id"] else None,
        "sha256": r["sha256"], "bytes": r["bytes"], "n_itens": r["n_itens"], "n_camadas": r["n_camadas"],
        "n_arquivos": r["n_arquivos"], "duracao_ms": r["duracao_ms"], "erro": r["erro"],
        "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
        "concluido_em": r["concluido_em"].isoformat() if r["concluido_em"] else None,
        "expira_em": r["expira_em"].isoformat() if r["expira_em"] else None,
        "link": f"{base_url}/api/inquilino/exportacoes/{r['id']}/baixar" if pronta else None,
        "validade_dias": limites.EXPORTACAO_VALIDADE_DIAS,
    }


def _carregar(cur, exportacao_id: str) -> dict:
    eid = uuid_ok(exportacao_id, "exportacao_inexistente", "exportação inexistente")
    cur.execute("SELECT * FROM plat.exportacao_inquilino WHERE id = %s::uuid", (eid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "exportacao_inexistente", "exportação inexistente")
    return r


def _pedidas_hoje(cur, tenant_id: int) -> int:
    cur.execute("SELECT plat.exportacao_inquilino_hoje(%s) AS n", (tenant_id,))
    return int(cur.fetchone()["n"])


@router.get("/api/inquilino/exportar/estimativa", openapi_extra=EXPORTAR)
def estimativa(auth: Auth = autenticado("org.exportar")):
    """Quanto o pacote deve pesar, lido do banco (ver `motor.estimar_bytes`), e se a cota do dia já foi gasta —
    para a tela avisar ANTES do clique, em vez de o admin descobrir com um 429 ou com um arquivo de gigabytes."""
    with db.db(auth.contexto()) as cur:
        e = motor.estimar_bytes(cur, motor.montar_catalogo(cur, auth.tenant_id))
        hoje = _pedidas_hoje(cur, auth.tenant_id)
    e["pedidas_hoje"] = hoje
    e["maximo_por_dia"] = limites.EXPORTACAO_INQUILINO_POR_DIA_MAX
    e["disponivel"] = hoje < limites.EXPORTACAO_INQUILINO_POR_DIA_MAX
    return e


@router.post("/api/inquilino/exportar", status_code=202, openapi_extra=EXPORTAR)
def pedir(request: Request, auth: Auth = autenticado("org.exportar")):
    with db.db(auth.contexto()) as cur:
        hoje = _pedidas_hoje(cur, auth.tenant_id)
        if hoje >= limites.EXPORTACAO_INQUILINO_POR_DIA_MAX:
            raise ErroAPI(
                429, "exportacao_inquilino_ja_pedida_hoje",
                f"já existe {hoje} exportação completa do inquilino pedida hoje (máximo "
                f"{limites.EXPORTACAO_INQUILINO_POR_DIA_MAX} por dia); tente de novo amanhã",
                {"hoje": hoje, "maximo": limites.EXPORTACAO_INQUILINO_POR_DIA_MAX},
            )
        e = motor.estimar_bytes(cur, motor.montar_catalogo(cur, auth.tenant_id))
        cur.execute(
            "INSERT INTO plat.exportacao_inquilino(tenant_id, usuario_id, estimativa_bytes) "
            "VALUES (%s, %s, %s) RETURNING id",
            (auth.tenant_id, auth.usuario_id, e["bytes"]),
        )
        exportacao_id = str(cur.fetchone()["id"])
        registrar_evento(cur, request, "inquilino/exportar", "inquilino", None, {"exportacao_id": exportacao_id})
    job = servico.criar(sessao_de(auth), "inquilino.exportar", {"exportacao_id": exportacao_id})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.exportacao_inquilino SET job_id = %s::uuid WHERE id = %s::uuid",
                    (job["id"], exportacao_id))
    return {"exportacao_id": exportacao_id, "job_id": job["id"], "estimativa_bytes": e["bytes"]}


@router.get("/api/inquilino/exportacoes", openapi_extra=EXPORTAR)
def listar(limite: int = 50, deslocamento: int = 0, auth: Auth = autenticado("org.exportar")):
    limite = max(1, min(200, limite))
    deslocamento = max(0, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.exportacao_inquilino")
        total = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT * FROM plat.exportacao_inquilino ORDER BY criado_em DESC LIMIT %s OFFSET %s",
            (limite, deslocamento),
        )
        itens = [_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens, "limite": limite, "deslocamento": deslocamento}


@router.get("/api/inquilino/exportacoes/{exportacao_id}", openapi_extra=EXPORTAR)
def obter(exportacao_id: str, auth: Auth = autenticado("org.exportar")):
    with db.db(auth.contexto()) as cur:
        return _json(_carregar(cur, exportacao_id))


@router.get("/api/inquilino/exportacoes/{exportacao_id}/baixar", openapi_extra=EXPORTAR,
            responses={200: {"content": {"application/zip": {}}}})
def baixar(exportacao_id: str, request: Request, auth: Auth = autenticado("org.exportar")):
    from app import objetos
    from fastapi.responses import StreamingResponse

    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, exportacao_id)
        if r["estado"] == "expirada" or (r["estado"] == "pronta" and not r["chave"]):
            raise ErroAPI(410, "exportacao_expirada",
                          f"o pacote desta exportação expirou (validade de {limites.EXPORTACAO_VALIDADE_DIAS} "
                          "dias) e foi apagado")
        if r["estado"] != "pronta":
            raise ErroAPI(409, "exportacao_nao_pronta", f"a exportação está em estado {r['estado']!r}")
        registrar_evento(cur, request, "inquilino/exportar_baixar", "inquilino", None,
                         {"exportacao_id": str(r["id"])})
        chave = r["chave"]
        tamanho = r["bytes"]
    return StreamingResponse(
        objetos.ler_stream(chave, limites.EXPORTACAO_BLOCO_LEITURA_BYTES),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="inquilino_exportado.zip"',
            "Content-Length": str(tamanho) if tamanho else "",
        },
    )


@router.delete("/api/inquilino/exportacoes/{exportacao_id}", status_code=204, openapi_extra=EXPORTAR)
def apagar(exportacao_id: str, auth: Auth = autenticado("org.exportar")):
    from app import objetos

    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, exportacao_id)
        if r["estado"] in ESTADOS_APAGAVEIS:
            servico.cancelar(sessao_de(auth), str(r["job_id"])) if r["job_id"] else None
            cur.execute("UPDATE plat.exportacao_inquilino SET estado = 'cancelada' WHERE id = %s::uuid",
                        (str(r["id"]),))
        elif r["estado"] == "pronta" and r["chave"]:
            chave = r["chave"]
            cur.execute("UPDATE plat.exportacao_inquilino SET estado = 'expirada', chave = NULL "
                        "WHERE id = %s::uuid", (str(r["id"]),))
            objetos.apagar(chave)
    return None
