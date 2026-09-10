"""Rotas de ingestão vetorial (ADR 0005 seção 16; L0-04-b/c/d reduzidos a 4 formatos nesta passagem):
`POST /api/importacoes` cria a importação a partir de um item `arquivo` já enviado por `POST /api/arquivos`
(L0-11) e dispara o job `ingestao.inspecionar`; `GET` lista/detalha; `PUT .../confirmar` valida a proposta
editada CONTRA a proposta gravada (nunca contra o arquivo de novo) e dispara `ingestao.carregar`; `DELETE`
remove importações que nunca chegaram a carregar. Diferença assumida em relação ao ADR 0005 seção 3: como esta
passagem reaproveita o upload genérico do L0-11 (sem o campo `tipo_declarado` do envio em partes), o par
`{arquivo_id, formato}` de `POST /api/importacoes` é onde o tipo é declarado e conferido contra os bytes
(`app.ingestao.formatos.verificar_conteudo`) — documentado no handoff do item."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app import db, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import UUID_PADRAO, JobCriado, Modelo
from app.erros import ErroAPI
from app.ingestao.formatos import FORMATOS, ConteudoNaoCorresponde
from app.ingestao.formatos import verificar_conteudo as _verificar_conteudo
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["ingestao"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
PUBLICAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}

ESTADOS_APAGAVEIS = ("proposta", "falhou", "cancelada", "expirada")


class ImportacaoEntrada(Modelo):
    arquivo_id: str = Field(pattern=UUID_PADRAO)
    formato: str = Field(min_length=1, max_length=40)


class ConfirmarEntrada(Modelo):
    """O corpo é a proposta EDITADA (ADR 0005 seção 5): só os campos que a tela deixa mudar. Cada um é validado
    contra a proposta gravada dentro da rota (nunca um esquema fixo — a proposta é que dá as opções válidas)."""

    titulo: str | None = Field(default=None, min_length=1, max_length=250)
    crs: dict | None = None
    codificacao: dict | None = None
    geometria: dict | None = None
    campos: list[dict] | None = None
    validade: dict | None = None


def _importacao_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "arquivo_id": str(r["arquivo_id"]), "item_id": str(r["item_id"]),
        "formato": r["formato"], "estado": r["estado"], "proposta": r["proposta"], "confirmacao": r["confirmacao"],
        "relatorio": r["relatorio"], "job_inspecao": str(r["job_inspecao"]) if r["job_inspecao"] else None,
        "job_carga": str(r["job_carga"]) if r["job_carga"] else None, "erro": r["erro"],
        "lote_id": str(r["lote_id"]) if r.get("lote_id") else None,
        "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
    }


importacao_json = _importacao_json  # nome público: reusado por app.intercambio.lote_importar (L6-02-o)


def carregar_importacao(cur, auth: Auth, importacao_id: str) -> dict:
    """Lê uma linha de `plat.importacao` sob RLS + a mesma regra de dono/`jobs.gerir_todos` das rotas deste
    módulo. Nome público (sem `_`) porque o item L6-02-o (importação em lote) reusa esta função em vez de
    reescrever a checagem de posse."""
    iid = uuid_ok(importacao_id, "importacao_inexistente", "importação inexistente")
    cur.execute("SELECT * FROM plat.importacao WHERE id = %s::uuid", (iid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "importacao_inexistente", "importação inexistente")
    if r["usuario_id"] not in (None, auth.usuario_id) and not auth.tem("jobs.gerir_todos"):
        raise ErroAPI(404, "importacao_inexistente", "importação inexistente")
    return r


_carregar = carregar_importacao  # compatibilidade com o resto do módulo


def preparar_importacao(cur, request: Request, auth: Auth, arquivo_id: str, formato: str) -> str:
    """Núcleo de `POST /api/importacoes`, sem o job: confere o formato, lê o objeto, prova o conteúdo e
    insere a linha em `plat.importacao`. Devolve o `importacao_id`. Extraído para o item L6-02-o (importação
    em LOTE) chamar em loop sem duplicar a prova de conteúdo — quem chama abre a transação e cria o job."""
    if formato not in FORMATOS:
        raise ErroAPI(
            422, "formato_nao_suportado",
            f"formato {formato!r} não suportado nesta instalação; aceitos: {sorted(FORMATOS)}",
            {"aceitos": sorted(FORMATOS)},
        )
    arquivo_id = uuid_ok(arquivo_id)
    cur.execute("SELECT id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'", (arquivo_id,))
    arq = cur.fetchone()
    if arq is None:
        raise ErroAPI(404, "item_inexistente", "item de arquivo inexistente")
    chave = arq["dados"]["chave"]
    try:
        dados = objetos.ler(chave)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "o objeto do arquivo não existe mais no armazenamento") from e
    try:
        _verificar_conteudo(formato, dados)
    except ConteudoNaoCorresponde as e:
        raise ErroAPI(422, "conteudo_nao_corresponde", str(e)) from e

    item_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO plat.importacao(tenant_id, usuario_id, arquivo_id, item_id, formato) "
        "VALUES (%s, %s, %s::uuid, %s::uuid, %s) RETURNING id",
        (auth.tenant_id, auth.usuario_id, arquivo_id, item_id, formato),
    )
    importacao_id = str(cur.fetchone()["id"])
    registrar_evento(cur, request, "importacoes/criar", "item", arquivo_id,
                      {"importacao_id": importacao_id, "formato": formato})
    return importacao_id


@router.post("/api/importacoes", status_code=202, openapi_extra=PUBLICAR)
def criar(corpo: ImportacaoEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        importacao_id = preparar_importacao(cur, request, auth, corpo.arquivo_id, corpo.formato)
    job = servico.criar(sessao_de(auth), "ingestao.inspecionar", {"importacao_id": importacao_id})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.importacao SET job_inspecao = %s::uuid WHERE id = %s::uuid",
                     (job["id"], importacao_id))
    return {"importacao_id": importacao_id, "job_id": job["id"]}


@router.get("/api/importacoes", openapi_extra=LER)
def listar(limite: int = 50, deslocamento: int = 0, lote_id: str | None = None,
           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    limite = max(1, min(200, limite))
    deslocamento = max(0, deslocamento)
    condicoes: list[str] = []
    params: list = []
    if not auth.tem("jobs.gerir_todos"):
        condicoes.append("usuario_id = %s")
        params.append(auth.usuario_id)
    if lote_id:  # L6-02-o: filtro do lote de importação (agrupamento, sem mudar o funil de 1 arquivo)
        condicoes.append("lote_id = %s::uuid")
        params.append(uuid_ok(lote_id))
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.importacao{onde}", params)
        total = int(cur.fetchone()["n"])
        cur.execute(
            f"SELECT * FROM plat.importacao{onde} ORDER BY criado_em DESC LIMIT %s OFFSET %s",
            [*params, limite, deslocamento],
        )
        linhas = cur.fetchall()
    return {"itens": [_importacao_json(r) for r in linhas], "total": total}


@router.get("/api/importacoes/{id}", openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
    return _importacao_json(r)


def preparar_confirmacao(cur, request: Request, r: dict, corpo: ConfirmarEntrada) -> None:
    """Núcleo de `PUT /api/importacoes/{id}/confirmar`, sem o job: valida a proposta editada CONTRA a
    proposta gravada e grava `estado='confirmada'`. Extraído para o item L6-02-o (importação em LOTE)
    aplicar a mesma validação a N importações sem duplicar a regra — quem chama cria o job em seguida."""
    if r["estado"] != "proposta":
        raise ErroAPI(409, "estado_invalido", f"importação em estado {r['estado']!r}; esperava 'proposta'")
    proposta = r["proposta"] or {}

    confirmacao: dict = {}
    perguntas_pendentes = list(proposta.get("perguntas") or [])

    if corpo.crs is not None:
        srid = corpo.crs.get("srid")
        if srid is not None:
            cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (int(srid),))
            if cur.fetchone() is None:
                raise ErroAPI(422, "srid_inexistente", f"SRID {srid} não existe em spatial_ref_sys")
            confirmacao["crs"] = {"srid": int(srid)}
            if "crs" in perguntas_pendentes:
                perguntas_pendentes.remove("crs")
    if corpo.codificacao is not None and corpo.codificacao.get("valor"):
        confirmacao["codificacao"] = {"valor": corpo.codificacao["valor"]}
        if "codificacao" in perguntas_pendentes:
            perguntas_pendentes.remove("codificacao")
    if corpo.geometria is not None and corpo.geometria.get("escolhida"):
        opcoes_geom = proposta.get("geometria", {}).get("opcoes") or []
        escolhida = corpo.geometria["escolhida"]
        if opcoes_geom and escolhida not in opcoes_geom and escolhida != "Geometry":
            raise ErroAPI(422, "geometria_nao_permitida", f"opções válidas: {opcoes_geom}", {"opcoes": opcoes_geom})
        confirmacao["geometria"] = {"escolhida": escolhida}
        if "geometria" in perguntas_pendentes:
            perguntas_pendentes.remove("geometria")
    if corpo.validade is not None:
        acao = corpo.validade.get("acao")
        if acao not in (None, "corrigir", "descartar", "recusar"):
            raise ErroAPI(422, "validacao", "validade.acao deve ser corrigir, descartar ou recusar")
        if acao:
            confirmacao["validade"] = {"acao": acao}
    if corpo.campos is not None:
        nomes_validos = {c["nome"] for c in proposta.get("campos", [])}
        campos_saida = []
        for editado in corpo.campos:
            nome = editado.get("nome")
            if nome not in nomes_validos:
                raise ErroAPI(422, "campo_desconhecido", f"campo {nome!r} não está na proposta", {"nome": nome})
            base = next(c for c in proposta["campos"] if c["nome"] == nome)
            tipo = editado.get("tipo", base["tipo"])
            if tipo not in base.get("opcoes_tipo", [base["tipo"]]):
                raise ErroAPI(422, "tipo_nao_permitido", f"tipo {tipo!r} não permitido para o campo {nome!r}",
                              {"opcoes": base.get("opcoes_tipo")})
            campos_saida.append({**base, "tipo": tipo, "importar": editado.get("importar", True)})
        # campos da proposta não mencionados no corpo mantêm o padrão (todos importados)
        mencionados = {c["nome"] for c in corpo.campos}
        for base in proposta.get("campos", []):
            if base["nome"] not in mencionados:
                campos_saida.append({**base, "importar": True})
        confirmacao["campos"] = campos_saida
    if corpo.titulo:
        confirmacao["titulo"] = corpo.titulo

    if perguntas_pendentes:
        raise ErroAPI(422, "perguntas_pendentes", "há perguntas sem resposta na proposta",
                      {"perguntas": perguntas_pendentes})

    cur.execute(
        "UPDATE plat.importacao SET estado = 'confirmada', confirmacao = %s, atualizado_em = now() "
        "WHERE id = %s::uuid",
        (jsonb(confirmacao), r["id"]),
    )
    registrar_evento(cur, request, "importacoes/confirmar", "item", str(r["item_id"]),
                     {"importacao_id": str(r["id"])})


@router.put("/api/importacoes/{id}/confirmar", response_model=JobCriado, status_code=202, openapi_extra=PUBLICAR)
def confirmar(id: str, corpo: ConfirmarEntrada, request: Request,
              auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        preparar_confirmacao(cur, request, r, corpo)
    job = servico.criar(sessao_de(auth), "ingestao.carregar", {"importacao_id": str(r["id"])})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.importacao SET job_carga = %s::uuid WHERE id = %s::uuid", (job["id"], r["id"]))
    return {"job_id": job["id"]}


@router.delete("/api/importacoes/{id}", status_code=204, response_class=Response, openapi_extra=PUBLICAR)
def apagar(id: str, auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        if r["estado"] not in ESTADOS_APAGAVEIS:
            raise ErroAPI(409, "estado_invalido", f"importação em estado {r['estado']!r} não pode ser apagada")
        cur.execute("DELETE FROM plat.importacao WHERE id = %s::uuid", (r["id"],))
    return Response(status_code=204)


@router.get("/api/importacoes/formatos", openapi_extra=LER)
def formatos_aceitos():
    return [{"tipo": f.nome, "extensoes": list(f.extensoes), "rotulo": f.rotulo} for f in FORMATOS.values()]
