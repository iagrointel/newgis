"""Rotas do acervo da casa (item L6-01-a-procedencia-acervo; ADR ver laco/decomposicao/L3L6_CONCEITO.md B1/B3/B5).

`GET /api/acervo` lista por domínio e busca (nome/órgão); `GET /api/acervo/{fonte_id}` devolve a ficha completa de
procedência (licença, frescor, sha256, comando de reexecução, nº de tabelas, registros); as duas leem só
`plat.acervo_ficha` (migração 021), que já filtra `licenca IS NOT NULL` — regra D17, fonte sem licença escrita nunca
aparece, nem na lista nem na ficha (404, não distinguível de "não existe": a casa não confirma que a fonte existe
para quem não pode vê-la). `POST /api/acervo/{fonte_id}/adicionar` cria um item do catálogo tipo `conexao`
(protocolo `acervo`) que referencia a fonte por `fonte_id` em `dados.parametros` — nunca copia dado, nunca escreve
em `acervo.*` (a casa só lê o registro do acervo; quem grava lá são os scripts próprios: registro.py/contagem2.py/
frescor.py)."""

import uuid

import psycopg2
from fastapi import APIRouter, Query, Request

from app import db
from app.acervo.modelos import AcervoFicha, AcervoPagina
from app.auth.comum import paginacao
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum, tipos
from app.catalogo.comum import item_json, item_ou_404, jsonb, registrar_evento
from app.catalogo.modelos import Item
from app.erros import ErroAPI

router = APIRouter(tags=["acervo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CAMPOS_FICHA = (
    "fonte_id, nome, orgao, dominio, url, url_http, url_conferida_em, licenca, frescor, data_dado, data_acesso, "
    "script_gerador, sha256, comando_reexecucao, metodo, confianca, limites, proxima_verificacao, numero_tabelas, "
    "registros_estimados, bytes, procedencia_campos, procedencia_campos_possiveis, procedencia_pontuacao, "
    "atualizado_em"
)


def _iso_datas(r: dict) -> dict:
    j = dict(r)
    for campo in ("url_conferida_em", "data_acesso", "proxima_verificacao"):
        if j.get(campo) is not None:
            j[campo] = j[campo].isoformat()
    if j.get("atualizado_em") is not None:
        j["atualizado_em"] = j["atualizado_em"].isoformat()
    return j


@router.get("/api/acervo", response_model=AcervoPagina, openapi_extra=LER)
def listar(
    dominio: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    lim, desl = paginacao(limite, deslocamento)
    onde, params = ["true"], []
    if dominio:
        onde.append("dominio = %s")
        params.append(dominio)
    if q:
        onde.append("(nome ILIKE %s OR orgao ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.acervo_ficha WHERE {filtro}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT fonte_id, nome, orgao, dominio, licenca, frescor, numero_tabelas, registros_estimados, "
            f"procedencia_pontuacao, proxima_verificacao FROM plat.acervo_ficha WHERE {filtro} "
            f"ORDER BY dominio, nome LIMIT %s OFFSET %s",
            [*params, lim, desl],
        )
        itens = [_iso_datas(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/api/acervo/{fonte_id}", response_model=AcervoFicha, openapi_extra=LER)
def ver(fonte_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT {CAMPOS_FICHA} FROM plat.acervo_ficha WHERE fonte_id = %s", (fonte_id,))
        r = cur.fetchone()
    if r is None:
        # não distingue "fonte inexistente" de "fonte sem licença escrita" (regra D17): as duas somem da API.
        raise ErroAPI(404, "fonte_inexistente", "fonte do acervo inexistente")
    return _iso_datas(r)


@router.post(
    "/api/acervo/{fonte_id}/adicionar",
    response_model=Item,
    status_code=201,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.criar|conteudo.registrar_fonte"},
)
def adicionar(fonte_id: str, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403,
            "sem_privilegio",
            "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT {CAMPOS_FICHA} FROM plat.acervo_ficha WHERE fonte_id = %s", (fonte_id,))
        f = cur.fetchone()
        if f is None:
            raise ErroAPI(404, "fonte_inexistente", "fonte do acervo inexistente")
        cur.execute(
            "SELECT plat.cota_itens(%s) AS cota, (SELECT count(*) FROM plat.item WHERE tenant_id = %s) AS n",
            (auth.tenant_id, auth.tenant_id),
        )
        cota = cur.fetchone()
        if cota["n"] >= cota["cota"]:
            raise ErroAPI(
                413, "cota_itens", f"cota de itens do inquilino esgotada ({cota['cota']})", {"cota": cota["cota"]}
            )
        dados = {
            "protocolo": "acervo",
            "url": f["url_http"] or f["url"] or f"acervo:{f['fonte_id']}",
            "parametros": {
                "fonte_id": f["fonte_id"],
                "dominio": f["dominio"],
                "licenca": f["licenca"],
                "frescor": f["frescor"],
                "numero_tabelas": f["numero_tabelas"],
                "registros_estimados": f["registros_estimados"],
                "sha256": f["sha256"],
                "comando_reexecucao": f["comando_reexecucao"],
                "modo": "referenciada",
            },
        }
        tipos.validar("conexao", dados)
        iid = str(uuid.uuid4())
        titulo = f"Acervo — {f['nome']}"[:250]
        resumo = (
            f"{f['dominio']} · {f['numero_tabelas']} tabela(s) · "
            f"{f['registros_estimados']} registro(s) (estimativa)"
        )[:2048]
        try:
            cur.execute(
                """
                INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, creditos, termos_de_uso, dono_id,
                                       dados, origem, criado_por, modificado_por)
                VALUES (%s::uuid, %s, 'conexao', %s, %s, %s, %s, %s, %s, 'referenciado', %s, %s)
                """,
                (
                    iid,
                    auth.tenant_id,
                    titulo,
                    resumo,
                    f["orgao"],
                    f["licenca"],
                    auth.usuario_id,
                    jsonb(dados),
                    auth.usuario_id,
                    auth.usuario_id,
                ),
            )
            registrar_evento(
                cur,
                request,
                "itens/adicionar",
                "item",
                iid,
                {"tipo": "conexao", "fonte_id": f["fonte_id"], "titulo": titulo},
            )
            return item_json(item_ou_404(cur, iid), auth)
        except psycopg2.Error as e:
            raise comum.erro_do_banco(e) from e
