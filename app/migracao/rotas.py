"""Rotas do inventário de Portal/AGOL (item L2-08-a-leitor-portal-inventario).

`POST /api/migracao/inventarios` enfileira o job de leitura sobre uma conexão do tipo `esri_rest` já
registrada (item L6-02-a — a URL passou pela defesa de SSRF antes de virar linha no banco). Quando o corpo
traz `usuario`/`senha`, o backend chama `generateToken` NO PORTAL, guarda só o token cifrado na conexão e
descarta a senha; a senha nunca é gravada e nunca volta em resposta.

`GET .../{id}` traz o retrato com resumo por tipo e por classificação; `GET .../{id}/itens` pagina a lista;
`GET .../{id}/relatorio.csv` devolve o CSV. Nenhuma rota devolve token, credencial cifrada ou dado pessoal:
o único campo de pessoa que existe no inventário é o LOGIN."""

import psycopg2
from fastapi import APIRouter, Request
from fastapi.responses import Response

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento, uuid_ok
from app.conexao import credencial as credencial_mod
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de
from app.jobs.registro import ordem_perfil
from app.migracao import relatorio
from app.migracao.classificacao import CLASSES
from app.migracao.modelos import (
    CloneCartao,
    CloneEntrada,
    ClonePagina,
    InventarioDetalhe,
    InventarioEntrada,
    InventarioPagina,
    ItemPagina,
)
from app.migracao.portal import ClientePortal, ErroPortal
from app.settings import settings

router = APIRouter(prefix="/api/migracao", tags=["migracao"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CRIAR = {"x-auth": "S", "x-privilegio": "conteudo.registrar_fonte"}
ITENS_LIMITE_MAX = 500
CAMPOS_ITEM = (
    "item_esri_id, tipo, titulo, dono_login, url, tamanho_bytes, criado_esri_em, modificado_esri_em, "
    "ultimo_acesso_em, num_visualizacoes, classificacao, classificacao_motivo, contagem_total, camadas, "
    "dependencias, recursos, relacionados"
)


def _cartao(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "conexao_id": str(r["conexao_id"]),
        "estado": r["estado"],
        "portal_url": r["portal_url"],
        "portal_nome": r["portal_nome"],
        "portal_versao": r["portal_versao"],
        "totais": r["totais"] or {},
        "job_id": str(r["job_id"]) if r["job_id"] else None,
        "mensagem": r["mensagem"],
        "criado_em": iso(r["criado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


def _carregar(cur, inventario_id: str) -> dict:
    cur.execute("SELECT * FROM plat.migracao_inventario WHERE id = %s::uuid", (inventario_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "inventario_inexistente", "inventário inexistente")
    return r


def _linhas_de_item(cur, inventario_id: str, limite: int, deslocamento: int, tipo=None, classe=None):
    onde, params = ["inventario_id = %s::uuid"], [inventario_id]
    if tipo:
        onde.append("tipo = %s")
        params.append(tipo)
    if classe:
        onde.append("classificacao = %s")
        params.append(classe)
    filtro = " AND ".join(onde)
    cur.execute(f"SELECT count(*) AS n FROM plat.migracao_item WHERE {filtro}", params)  # noqa: S608
    total = int(cur.fetchone()["n"])
    cur.execute(  # noqa: S608
        f"SELECT {CAMPOS_ITEM} FROM plat.migracao_item WHERE {filtro} "
        "ORDER BY tipo, lower(coalesce(titulo, '')) LIMIT %s OFFSET %s",
        [*params, limite, deslocamento],
    )
    return total, [dict(r) for r in cur.fetchall()]


@router.get("/inventarios", response_model=InventarioPagina, openapi_extra=LER)
def listar(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.migracao_inventario")
        total = int(cur.fetchone()["n"])
        cur.execute("SELECT * FROM plat.migracao_inventario ORDER BY criado_em DESC LIMIT 100")
        return {"total": total, "itens": [_cartao(r) for r in cur.fetchall()]}


@router.get("/inventarios/{id}", response_model=InventarioDetalhe, openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    inv = uuid_ok(id, "inventario_inexistente", "inventário inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, inv)
        cur.execute(
            "SELECT tipo, classificacao, contagem_total, tamanho_bytes FROM plat.migracao_item "
            "WHERE inventario_id = %s::uuid",
            (inv,),
        )
        linhas = [dict(x) for x in cur.fetchall()]
        cur.execute("SELECT count(*) AS n FROM plat.migracao_grupo WHERE inventario_id = %s::uuid", (inv,))
        grupos = int(cur.fetchone()["n"])
        cur.execute("SELECT count(*) AS n FROM plat.migracao_usuario WHERE inventario_id = %s::uuid", (inv,))
        usuarios = int(cur.fetchone()["n"])
    por_classe = dict.fromkeys(CLASSES, 0)
    for linha in linhas:
        chave = linha["classificacao"] if linha["classificacao"] in por_classe else "desconhecido"
        por_classe[chave] += 1
    return {
        **_cartao(r),
        "portal_id": r["portal_id"],
        "retomada": r["retomada"] or {},
        "por_tipo": relatorio.resumo_por_tipo(linhas),
        "por_classificacao": por_classe,
        "grupos": grupos,
        "usuarios": usuarios,
    }


@router.get("/inventarios/{id}/itens", response_model=ItemPagina, openapi_extra=LER)
def itens(
    id: str,
    tipo: str | None = None,
    classificacao: str | None = None,
    limite: int = 100,
    deslocamento: int = 0,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    inv = uuid_ok(id, "inventario_inexistente", "inventário inexistente")
    if not 1 <= limite <= ITENS_LIMITE_MAX:
        raise ErroAPI(422, "limite_invalido", f"limite deve estar entre 1 e {ITENS_LIMITE_MAX}")
    with db.db(auth.contexto()) as cur:
        _carregar(cur, inv)
        total, linhas = _linhas_de_item(cur, inv, limite, max(0, deslocamento), tipo, classificacao)
    for linha in linhas:
        for campo in ("criado_esri_em", "modificado_esri_em", "ultimo_acesso_em"):
            linha[campo] = iso(linha[campo]) if linha[campo] else None
    return {"total": total, "itens": linhas}


@router.get("/inventarios/{id}/relatorio.csv", openapi_extra=LER)
def relatorio_csv(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    inv = uuid_ok(id, "inventario_inexistente", "inventário inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar(cur, inv)
        cur.execute(  # noqa: S608
            f"SELECT {CAMPOS_ITEM} FROM plat.migracao_item WHERE inventario_id = %s::uuid "
            "ORDER BY tipo, lower(coalesce(titulo, ''))",
            (inv,),
        )
        linhas = [dict(r) for r in cur.fetchall()]
    corpo = relatorio.csv_de_itens(linhas)
    return Response(
        content=corpo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="inventario-{inv}.csv"'},
    )


@router.post("/inventarios", status_code=201, openapi_extra=CRIAR)
def criar(corpo: InventarioEntrada, request: Request, auth: Auth = autenticado("conteudo.registrar_fonte")):
    # achado B7: `conteudo.registrar_fonte` (perfil editor) não é suficiente para o JOB
    # `migracao.inventariar` (perfil_minimo="admin"); conferir ANTES de gravar qualquer linha, senão
    # sobra inventário órfão (job_id NULL, nunca vai rodar) depois do 403 do serviço de job.
    tipo_job = servico.tipo_registrado("migracao.inventariar")
    if not auth.superadmin and ordem_perfil(auth.perfil) < ordem_perfil(tipo_job.perfil_minimo):
        raise ErroAPI(
            403,
            "perfil_insuficiente",
            f"criar inventário exige perfil {tipo_job.perfil_minimo} ou superior (o seu é {auth.perfil})",
        )
    cid = uuid_ok(corpo.conexao_id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT id, tipo, url, credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
        conexao = cur.fetchone()
        if conexao is None:
            raise ErroAPI(404, "conexao_inexistente", "conexão inexistente")
        if conexao["tipo"] != "esri_rest":
            raise ErroAPI(
                422,
                "conexao_nao_e_portal",
                "o inventário só roda sobre conexão do tipo esri_rest (Portal/AGOL)",
                {"tipo": conexao["tipo"]},
            )

    if corpo.usuario or corpo.senha:
        if not (corpo.usuario and corpo.senha):
            raise ErroAPI(422, "credencial_incompleta", "usuário e senha vêm juntos ou nenhum dos dois")
        try:
            token = ClientePortal.gerar_token(
                conexao["url"],
                corpo.usuario,
                corpo.senha,
                referer=settings.PLAT_URL_PUBLICA,
            )
        except ErroPortal as e:
            raise ErroAPI(422, e.motivo, f"generateToken recusado pelo portal ({e.motivo})") from e
        cifrado = credencial_mod.cifrar(token, settings.PLAT_SECRET)
        del token
        with db.db(auth.contexto()) as cur:
            cur.execute("UPDATE plat.conexao SET credencial_cifrada = %s WHERE id = %s::uuid", (cifrado, cid))

    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.migracao_inventario(tenant_id, conexao_id, portal_url, criado_por) "
                "VALUES (%s, %s::uuid, %s, %s) RETURNING id",
                (auth.tenant_id, cid, conexao["url"], auth.usuario_id),
            )
            inv = str(cur.fetchone()["id"])
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(
            cur, request, "migracao/inventariar", "conexao", cid, {"inventario_id": inv, "portal_url": conexao["url"]}
        )

    job = servico.criar(sessao_de(auth), "migracao.inventariar", {"inventario_id": inv})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.migracao_inventario SET job_id = %s::uuid WHERE id = %s::uuid", (job["id"], inv))
        return _cartao(_carregar(cur, inv))


@router.delete("/inventarios/{id}", status_code=204, openapi_extra=CRIAR)
def apagar(id: str, request: Request, auth: Auth = autenticado("conteudo.registrar_fonte")):
    inv = uuid_ok(id, "inventario_inexistente", "inventário inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, inv)
        if r["criado_por"] != auth.usuario_id and not auth.tem("conteudo.editar_tudo"):
            raise ErroAPI(403, "sem_permissao", "só quem criou o inventário ou conteudo.editar_tudo")
        cur.execute("DELETE FROM plat.migracao_inventario WHERE id = %s::uuid", (inv,))
        registrar_evento(
            cur, request, "migracao/inventario_apagar", "conexao", str(r["conexao_id"]), {"inventario_id": inv}
        )
    return Response(status_code=204)


# ------------------------------------------------------------------ clonagem de camadas hospedadas (item L2-08-b)
def _clone_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "conexao_id": str(r["conexao_id"]),
        "url_servico": r["url_servico"],
        "estado": r["estado"],
        "camadas_pedidas": list(r["camadas_pedidas"]) if r["camadas_pedidas"] is not None else None,
        "job_id": str(r["job_id"]) if r["job_id"] else None,
        "mensagem": r["mensagem"],
        "camadas": r["camadas"] or [],
        "relatorio": r["relatorio"] or {},
        "criado_em": r["criado_em"].isoformat(),
        "atualizado_em": r["atualizado_em"].isoformat(),
    }


@router.get("/clones", response_model=ClonePagina, openapi_extra=LER)
def listar_clones(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.migracao_clone ORDER BY criado_em DESC LIMIT 200")
        itens = [_clone_json(r) for r in cur.fetchall()]
    return {"total": len(itens), "itens": itens}


@router.get("/clones/{id}", response_model=CloneCartao, openapi_extra=LER)
def ver_clone(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    cid = uuid_ok(id, "clone_inexistente", "clonagem inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.migracao_clone WHERE id = %s::uuid", (cid,))
        r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "clone_inexistente", "clonagem inexistente")
    return _clone_json(r)


@router.post("/clones", status_code=201, response_model=CloneCartao, openapi_extra=CRIAR)
def criar_clone(corpo: CloneEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    """Pede a clonagem (job `migracao.clonar`) das camadas/tabelas de um FeatureServer da conexão `esri_rest`.
    `url_servico` tem de estar sob a URL da conexão (a credencial dela nunca viaja para outro host)."""
    tipo_job = servico.tipo_registrado("migracao.clonar")
    if not auth.superadmin and ordem_perfil(auth.perfil) < ordem_perfil(tipo_job.perfil_minimo):
        raise ErroAPI(403, "perfil_insuficiente", f"clonar exige perfil {tipo_job.perfil_minimo} ou superior")
    cid = uuid_ok(corpo.conexao_id, "conexao_inexistente", "conexão inexistente")
    url = corpo.url_servico.strip().rstrip("/")
    if "/FeatureServer" not in url and "/MapServer" not in url:
        raise ErroAPI(422, "url_servico_invalida", "url_servico precisa apontar para um FeatureServer/MapServer")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT id, tipo, url FROM plat.conexao WHERE id = %s::uuid", (cid,))
        conexao = cur.fetchone()
        if conexao is None:
            raise ErroAPI(404, "conexao_inexistente", "conexão inexistente")
        if conexao["tipo"] != "esri_rest":
            raise ErroAPI(422, "conexao_nao_e_portal", "a clonagem só roda sobre conexão do tipo esri_rest")
        from app.conexao.seguranca import _mesma_origem_de_confianca

        if not _mesma_origem_de_confianca(conexao["url"], url):
            raise ErroAPI(422, "url_servico_fora_da_conexao", "url_servico fica fora da origem da conexão")
        try:
            cur.execute(
                "INSERT INTO plat.migracao_clone(tenant_id, conexao_id, url_servico, camadas_pedidas, criado_por) "
                "VALUES (%s, %s::uuid, %s, %s, %s) RETURNING *",
                (auth.tenant_id, cid, url, corpo.camadas, auth.usuario_id),
            )
            r = cur.fetchone()
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(
            cur, request, "migracao/clonar", "conexao", cid, {"clone_id": str(r["id"]), "url_servico": url}
        )
        job = servico.criar(sessao_de(auth), "migracao.clonar", {"clone_id": str(r["id"])})
        cur.execute(
            "UPDATE plat.migracao_clone SET job_id = %s::uuid WHERE id = %s::uuid RETURNING *",
            (str(job["id"]), str(r["id"])),
        )
        r = cur.fetchone()
    return _clone_json(r)


@router.delete("/clones/{id}", status_code=204, openapi_extra=CRIAR)
def apagar_clone(id: str, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    """Apaga só o registro da clonagem; as camadas clonadas continuam no catálogo (são itens comuns)."""
    cid = uuid_ok(id, "clone_inexistente", "clonagem inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("DELETE FROM plat.migracao_clone WHERE id = %s::uuid RETURNING id", (cid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "clone_inexistente", "clonagem inexistente")
        registrar_evento(cur, request, "migracao/clone_apagar", "migracao_clone", cid)
    return Response(status_code=204)
