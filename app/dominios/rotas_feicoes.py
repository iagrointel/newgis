"""Gravação de UMA feição pelo formulário (item L2-10-a).

Fronteira declarada, para não haver dúvida de escopo: a edição de feições em lote (`applyEdits`, versão,
anexo, histórico) é da linha L2-08. O que existe aqui é o mínimo que o formulário de atributos deste item
precisa para PROVAR a cláusula "o formulário mostra a descrição e grava o código": inserir e listar feições
de uma camada hospedada, com os nomes de campo conferidos contra os campos declarados no item de catálogo.
Quando a L2-08 chegar, estas duas rotas viram um caso particular dela — o que se reaproveita é a conferência
de nome de campo e a tradução do erro do gatilho, não o roteamento.

Quem valida o valor é o banco (`plat.feicao_validar_dominio`), nunca esta rota: assim o 422 que a tela recebe
e o erro que um `psql` receberia são a MESMA regra, com a mesma frase."""

from __future__ import annotations

import json

import psycopg2
from fastapi import APIRouter, Query, Request
from pydantic import Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.catalogo.modelos import Modelo
from app.dominios import servico
from app.erros import ErroAPI

router = APIRouter(tags=["feicoes"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "feicoes.editar"}
CAMPOS_INTERNOS = ("fid", "geom", "globalid", "versao", "tenant_id", "criado_em", "atualizado_em",
                   "criado_por", "atualizado_por")


class FeicaoEntrada(Modelo):
    atributos: dict[str, object] = Field(default_factory=dict)
    geometria: dict | None = None   # GeoJSON, no SRID declarado da camada


def _tabela(item: dict) -> tuple[str, str]:
    dados = item["dados"] or {}
    esquema, tabela = dados.get("schema"), dados.get("tabela")
    if not esquema or not tabela:
        raise ErroAPI(409, "camada_sem_tabela", "esta camada não aponta para uma tabela hospedada")
    for nome in (esquema, tabela):
        if not nome.replace("_", "a").isalnum() or not nome[0].isalpha():
            raise ErroAPI(409, "camada_sem_tabela", "esta camada aponta para um nome de tabela inválido")
    return esquema, tabela


@router.post("/api/camadas/{item_id}/feicoes", status_code=201, openapi_extra=EDITAR)
def criar_feicao(item_id: str, corpo: FeicaoEntrada, request: Request,
                 auth: Auth = autenticado("feicoes.editar")):
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        esquema, tabela = _tabela(item)
        declarados = servico.campos_declarados(item)
        desconhecidos = [c for c in corpo.atributos if c not in declarados or c in CAMPOS_INTERNOS]
        if desconhecidos:
            raise ErroAPI(422, "campo_inexistente",
                          f"a camada não tem o(s) campo(s) {sorted(desconhecidos)}",
                          {"campos": sorted(declarados)[:200]})
        colunas = list(corpo.atributos)
        valores = [corpo.atributos[c] for c in colunas]
        partes = ["%s"] * len(colunas)
        if corpo.geometria is not None:
            colunas.append("geom")
            partes.append("ST_SetSRID(ST_GeomFromGeoJSON(%s), %s)")
            valores.extend([json.dumps(corpo.geometria), (item["dados"] or {}).get("srid") or 4326])
        lista = ", ".join(f'"{c}"' for c in colunas)
        try:
            cur.execute(
                f'INSERT INTO "{esquema}"."{tabela}" ({lista}) VALUES ({", ".join(partes)}) '
                f"RETURNING fid, globalid",
                valores,
            )
        except psycopg2.Error as e:
            raise servico.erro_do_banco(e) from e
        r = cur.fetchone()
        registrar_evento(cur, request, "camadas/importar", "item", item["id"],
                         {"feicao": r["fid"], "campos": sorted(corpo.atributos)})
    return {"fid": r["fid"], "globalid": str(r["globalid"])}


@router.get("/api/camadas/{item_id}/feicoes", openapi_extra=LER)
def listar_feicoes(item_id: str, limite: int = Query(default=50, ge=1, le=500),
                   auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Só os atributos declarados e o fid; sem geometria (a leitura de geometria é do serviço de camada)."""
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        esquema, tabela = _tabela(item)
        declarados = servico.campos_declarados(item)
        lista = ", ".join(['fid'] + [f'"{c}"' for c in declarados])
        cur.execute(f'SELECT {lista} FROM "{esquema}"."{tabela}" ORDER BY fid DESC LIMIT %s', (limite,))
        return {"itens": [dict(r) for r in cur.fetchall()]}
