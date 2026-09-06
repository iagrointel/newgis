"""Trilha de auditoria de negócio (item L7-20): consulta, exportação e retenção.

Diferença para `/api/log` e `/api/eventos` (app/auth/rotas_log.py):
  * `/api/log` responde "que requisição entrou" (método, rota, status, bytes, tempo);
  * `/api/eventos` responde "que ato de negócio aconteceu", mas mora numa tabela particionada por mês cujo
    expurgo derruba a partição inteira, igual para todos os inquilinos;
  * `/api/auditoria` é a trilha propriamente dita: append-only por trigger, retenção POR INQUILINO, e cobre
    também as rotas de escrita que por decisão não geram evento de domínio (linhas de `origem='cobertura'`).

A listagem e a exportação chamam a MESMA função do banco (`plat.auditoria_listar`), com o mesmo filtro e o
mesmo `plat.auditoria_contar`: é por isso que a contagem da exportação bate com a contagem em tabela, e não
por dois SQL parecidos escritos duas vezes.
"""

import csv
import io
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from app import db, limites
from app.auth.comum import paginacao, registrar_evento
from app.auth.modelos import Modelo, Pagina, Saida
from app.auth.rotas_log import janela
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["auditoria"])
PRIV_VER = {"x-auth": "S/T", "x-privilegio": "org.log_ver"}
PRIV_CONFIG = {"x-auth": "S/T", "x-privilegio": "org.configurar"}
COLUNAS = (
    "id",
    "em",
    "ator_id",
    "ator_login",
    "token_id",
    "acao",
    "recurso_tipo",
    "recurso_id",
    "antes",
    "depois",
    "req_id",
    "ip",
    "metodo",
    "rota",
    "origem",
)


class RetencaoEntrada(Modelo):
    retencao_dias: int = Field(ge=limites.AUDITORIA_RETENCAO_MIN_DIAS, le=limites.AUDITORIA_RETENCAO_MAX_DIAS)


class RetencaoSaida(Saida):
    retencao_dias: int
    minimo_dias: int
    maximo_dias: int
    padrao_dias: int
    job_expurgo: str | None


def _linha(r: dict) -> dict:
    return {
        "id": r["id"],
        "em": iso(r["em"]),
        "ator_id": r["ator_id"],
        "ator_login": r["ator_login"],
        "token_id": r["token_id"],
        "acao": r["acao"],
        "recurso_tipo": r["recurso_tipo"],
        "recurso_id": r["recurso_id"],
        "antes": r["antes"],
        "depois": r["depois"],
        "req_id": r["req_id"],
        "ip": r["ip"],
        "metodo": r["metodo"],
        "rota": r["rota"],
        "origem": r["origem"],
    }


def consultar(cur, *, ator_id, acao, recurso_tipo, origem, desde, ate, limite, deslocamento) -> dict:
    """Contagem e página saem do MESMO par de funções do banco, com os MESMOS parâmetros."""
    inicio, fim = janela(desde, ate)
    filtros = (inicio, fim, ator_id, acao, recurso_tipo, origem)
    cur.execute("SELECT plat.auditoria_contar(%s, %s, %s, %s, %s, %s) AS n", filtros)
    total = cur.fetchone()["n"]
    cur.execute("SELECT * FROM plat.auditoria_listar(%s, %s, %s, %s, %s, %s, %s, %s)",
                (*filtros, limite, deslocamento))
    return {"total": total, "itens": [_linha(r) for r in cur.fetchall()], "inicio": inicio, "fim": fim}


@router.get(
    "/auditoria",
    response_model=Pagina,
    responses={200: {"content": {"text/csv": {}}}},
    openapi_extra=PRIV_VER,
)
def auditoria_listar(
    request: Request,
    ator_id: int | None = None,
    acao: str | None = None,
    recurso_tipo: str | None = None,
    origem: str | None = None,
    desde: str | None = None,
    ate: str | None = None,
    limite: int | None = None,
    deslocamento: int | None = None,
    formato: str = "json",
    auth: Auth = autenticado("org.log_ver"),
):
    """Lista a trilha do inquilino da sessão. `formato=csv` ou `formato=json_export` exporta o período
    inteiro (até AUDITORIA_EXPORTA_MAX linhas) e registra o próprio ato de exportar na trilha."""
    if formato not in ("json", "csv", "json_export"):
        raise ErroAPI(422, "validacao", "formato aceita json, csv ou json_export", {"campo": "formato"})
    if origem is not None and origem not in ("evento", "cobertura", "aplicacao"):
        raise ErroAPI(422, "validacao", "origem aceita evento, cobertura ou aplicacao", {"campo": "origem"})
    exporta = formato in ("csv", "json_export")
    lim, desl = ((limites.AUDITORIA_EXPORTA_MAX, 0) if exporta
                 else paginacao(limite, deslocamento, limites.LOG_LIMITE_MAX))
    with db.db(auth.contexto()) as cur:
        pagina = consultar(cur, ator_id=ator_id, acao=acao or None, recurso_tipo=recurso_tipo or None,
                           origem=origem, desde=desde, ate=ate, limite=lim, deslocamento=desl)
        if exporta:
            # o ato de exportar é ele mesmo auditado, DEPOIS de o conjunto ser lido: a linha nova não entra
            # no que se exportou, senão a contagem exportada nunca bateria com a contagem do período.
            registrar_evento(cur, request, "auditoria/exportar", "auditoria", None,
                             {"formato": formato, "linhas": len(pagina["itens"]),
                              "desde": iso(pagina["inicio"]), "ate": iso(pagina["fim"])})
    itens = pagina["itens"]
    if formato == "json":
        return {"total": pagina["total"], "itens": itens}
    if formato == "json_export":
        return StreamingResponse(
            iter([json.dumps({"total": len(itens), "itens": itens}, ensure_ascii=False, default=str)]),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=auditoria.json",
                     "X-Plat-Linhas": str(len(itens))},
        )
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, fieldnames=COLUNAS)
    escritor.writeheader()
    for item in itens:
        escritor.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                           for k, v in item.items()})
    return StreamingResponse(
        iter([saida.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=auditoria.csv", "X-Plat-Linhas": str(len(itens))},
    )


def _config(cur) -> dict:
    cur.execute(
        "SELECT plat.auditoria_retencao_dias(plat.tenant_atual()) AS dias, plat.auditoria_cron_nome() AS job"
    )
    r = cur.fetchone()
    return {
        "retencao_dias": r["dias"],
        "minimo_dias": limites.AUDITORIA_RETENCAO_MIN_DIAS,
        "maximo_dias": limites.AUDITORIA_RETENCAO_MAX_DIAS,
        "padrao_dias": limites.AUDITORIA_RETENCAO_PADRAO_DIAS,
        "job_expurgo": r["job"],
    }


@router.get("/auditoria/config", response_model=RetencaoSaida, openapi_extra=PRIV_CONFIG)
def auditoria_config_ler(auth: Auth = autenticado("org.configurar")):
    with db.db(auth.contexto()) as cur:
        return _config(cur)


@router.put("/auditoria/config", response_model=RetencaoSaida, openapi_extra=PRIV_CONFIG)
def auditoria_config_gravar(
    corpo: RetencaoEntrada, request: Request, auth: Auth = autenticado("org.configurar", so_sessao=True)
):
    """Retenção por inquilino. O piso de AUDITORIA_RETENCAO_MIN_DIAS existe para que o administrador do
    inquilino não consiga encolher a própria trilha até apagá-la — e a mudança é ela mesma auditada."""
    with db.db(auth.contexto()) as cur:
        antes = _config(cur)
        cur.execute(
            "UPDATE plat.tenant SET config = config || %s::jsonb WHERE id = plat.tenant_atual()",
            (json.dumps({"auditoria_retencao_dias": corpo.retencao_dias}),),
        )
        registrar_evento(cur, request, "auditoria/retencao", "tenant", auth.tenant_id,
                         {"antes": {"retencao_dias": antes["retencao_dias"]},
                          "depois": {"retencao_dias": corpo.retencao_dias}})
        return _config(cur)
