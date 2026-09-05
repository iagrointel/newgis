"""Categorias do inquilino (ADR 0004 seção 8.3): árvore de 3 níveis com teto por inquilino (tenant.config.catalogo.
categorias_max, padrão 200), PUT da árvore inteira com ids preservados (nó removido com itens = 409), importação
idempotente dos modelos ISO 19115 (19) e INSPIRE (34). Escrita exige conteudo.categorias (RLS + rota)."""

import json
from pathlib import Path

import psycopg2
from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.catalogo.comum import registrar_evento
from app.catalogo.modelos import Categorias, CategoriasEntrada, ImportadoCategorias, ImportarCategorias
from app.erros import ErroAPI

router = APIRouter(prefix="/api/categorias", tags=["categorias"])
MODELOS = Path(__file__).resolve().parent / "modelos_categorias"


def _arvore(cur) -> tuple[list[dict], int]:
    cur.execute(
        "SELECT k.*, (SELECT count(*) FROM plat.item i WHERE k.id = ANY (i.categorias) AND "
        "i.apagado_em IS NULL) AS itens "
        "FROM plat.categoria k ORDER BY k.nivel, k.posicao, lower(k.nome)"
    )
    linhas = cur.fetchall()
    nos = {
        str(r["id"]): {
            "id": str(r["id"]),
            "nome": r["nome"],
            "codigo": r["codigo"],
            "caminho": r["caminho"],
            "nivel": r["nivel"],
            "origem": r["origem"],
            "itens": r["itens"],
            "filhas": [],
        }
        for r in linhas
    }
    raiz = []
    for r in linhas:
        no = nos[str(r["id"])]
        if r["pai_id"] and str(r["pai_id"]) in nos:
            nos[str(r["pai_id"])]["filhas"].append(no)
        else:
            raiz.append(no)
    return raiz, len(linhas)


@router.get("", response_model=Categorias, openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def ver(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        arvore, total = _arvore(cur)
        cur.execute("SELECT plat.categorias_max(%s) AS m", (auth.tenant_id,))
        return {"arvore": arvore, "total": total, "maximo": cur.fetchone()["m"]}


def _contar(nos, nivel=1) -> int:
    n = 0
    for no in nos:
        if nivel > 3:
            raise ErroAPI(422, "nivel_maximo", "categorias têm no máximo 3 níveis", {"nome": no.nome})
        n += 1 + _contar(no.filhas, nivel + 1)
    return n


def _gravar(cur, auth: Auth, nos, pai_id: str | None, vistos: set, posicao_base: int = 0) -> None:
    for pos, no in enumerate(nos):
        nome = " ".join(no.nome.split())
        if no.id:
            cur.execute("SELECT id FROM plat.categoria WHERE id = %s::uuid", (no.id,))
            if cur.fetchone() is None:
                raise ErroAPI(404, "categoria_inexistente", "categoria inexistente", {"id": no.id})
            cur.execute(
                "UPDATE plat.categoria SET nome = %s, pai_id = %s::uuid, posicao = %s, codigo = coalesce(%s, codigo) "
                "WHERE id = %s::uuid",
                (nome, pai_id, posicao_base + pos, no.codigo, no.id),
            )
            cid = no.id
        else:
            cur.execute(
                "INSERT INTO plat.categoria(tenant_id, pai_id, nome, posicao, codigo) VALUES (%s, "
                "%s::uuid, %s, %s, %s) RETURNING id",
                (auth.tenant_id, pai_id, nome, posicao_base + pos, no.codigo),
            )
            cid = str(cur.fetchone()["id"])
        vistos.add(cid)
        _gravar(cur, auth, no.filhas, cid, vistos)


@router.put("", response_model=Categorias, openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.categorias"})
def definir(corpo: CategoriasEntrada, request: Request, auth: Auth = autenticado("conteudo.categorias")):
    total = _contar(corpo.arvore)
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT plat.categorias_max(%s) AS m", (auth.tenant_id,))
            maximo = cur.fetchone()["m"]
            if total > maximo:
                raise ErroAPI(
                    422,
                    "limite_categorias",
                    f"no máximo {maximo} categorias por inquilino",
                    {"total": total, "maximo": maximo},
                )
            antes, _ = _arvore(cur)
            vistos: set[str] = set()
            _gravar(cur, auth, corpo.arvore, None, vistos)
            cur.execute(
                "SELECT k.id, k.caminho, (SELECT count(*) FROM plat.item i WHERE k.id = ANY (i.categorias)) AS itens "
                "FROM plat.categoria k WHERE NOT (k.id = ANY (%s::uuid[])) ORDER BY k.nivel DESC",
                (list(vistos) or ["00000000-0000-0000-0000-000000000000"],),
            )
            removidas = cur.fetchall()
            em_uso = [
                {"id": str(r["id"]), "caminho": r["caminho"], "itens": r["itens"]} for r in removidas if r["itens"]
            ]
            if em_uso:
                raise ErroAPI(
                    409, "categoria_em_uso", "categoria com itens não se remove; tire-a dos itens antes", em_uso
                )
            for r in removidas:
                cur.execute("DELETE FROM plat.categoria WHERE id = %s::uuid", (r["id"],))
            depois, n = _arvore(cur)
            registrar_evento(cur, request, "categorias/alterar", "categoria", None, {"antes": antes, "depois": depois})
            return {"arvore": depois, "total": n, "maximo": maximo}
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "nome_existente", "duas categorias irmãs com o mesmo nome") from e
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


def _importar(cur, auth: Auth, modelo: str) -> tuple[int, int]:
    dados = json.loads((MODELOS / f"{modelo}.json").read_text(encoding="utf-8"))
    criadas = existentes = 0

    def garantir(nome: str, codigo: str, pai_id: str | None, origem: str, posicao: int) -> str:
        nonlocal criadas, existentes
        cur.execute("SELECT id FROM plat.categoria WHERE codigo = %s", (codigo,))
        r = cur.fetchone()
        if r:
            existentes += 1
            return str(r["id"])
        cur.execute(
            "INSERT INTO plat.categoria(tenant_id, pai_id, nome, posicao, origem, codigo) VALUES "
            "(%s, %s::uuid, %s, %s, %s, %s) RETURNING id",
            (auth.tenant_id, pai_id, nome, posicao, origem, codigo),
        )
        criadas += 1
        return str(cur.fetchone()["id"])

    if modelo == "iso19115":
        for i, c in enumerate(dados["categorias"]):
            garantir(c["nome"], f"iso19115:{c['codigo']}", None, "iso19115", i)
    else:
        for i, anexo in enumerate(dados["anexos"]):
            pai = garantir(anexo["nome"], f"inspire:{anexo['codigo']}", None, "inspire", i)
            for j, (cod, nome) in enumerate(anexo["temas"]):
                garantir(nome, f"inspire:{cod}", pai, "inspire", j)
    return criadas, existentes


@router.post(
    "/importar",
    response_model=ImportadoCategorias,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.categorias"},
)
def importar(corpo: ImportarCategorias, request: Request, auth: Auth = autenticado("conteudo.categorias")):
    try:
        with db.db(auth.contexto()) as cur:
            criadas, existentes = _importar(cur, auth, corpo.modelo)
            registrar_evento(
                cur, request, "categorias/importar", "categoria", None, {"modelo": corpo.modelo, "criadas": criadas}
            )
            return {"criadas": criadas, "existentes": existentes}
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
