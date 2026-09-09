"""Rotas da ferramenta de script (item L2-16-c-script-vira-ferramenta).

Publicar = criar item `ferramenta_script` (o registro no catálogo é o próprio item: versões pela
máquina `item_versao` do L5-05, compartilhamento pela do L0-03 — nada de registro paralelo). A
validação do cabeçalho acontece ANTES de gravar (422 cabecalho_invalido) e a validação dos
valores acontece ANTES de criar o job (422 parametros_invalidos com detalhe por campo) — nada é
enfileirado com parâmetro fora do tipo.

Execução: `POST /executar` congela `versao` + `sha256` NO PEDIDO do job; o worker roda o retrato
imutável dessa versão (`app/ferramentas/script_tarefas.py`), então versão nova publicada depois
não muda execução passada nenhuma. O log de execução é a fila (`GET /execucoes`) e o resultado
é item `ferramenta_resultado` com a procedência da versão executada.
"""

import hashlib

import psycopg2
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.catalogo.comum import registrar_evento
from app.catalogo.modelos import Item
from app.erros import ErroAPI
from app.ferramentas import cabecalho
from app.jobs import servico as servico_jobs
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["ferramentas"])

PUBLICAR = {"x-auth": "S/T", "x-privilegio": "conteudo.criar"}
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EXECUTAR = {"x-auth": "S/T", "x-privilegio": "jobs.executar"}


class PublicarEntrada(BaseModel):
    codigo: str = Field(min_length=1, max_length=cabecalho.TAM_MAX_CODIGO,
                        description="texto completo do script; a docstring de módulo é o cabeçalho YAML")
    pasta_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class VersaoEntrada(BaseModel):
    codigo: str = Field(min_length=1, max_length=cabecalho.TAM_MAX_CODIGO,
                        description="texto completo da versão nova (o cabeçalho é revalidado)")
    comentario: str | None = Field(default=None, max_length=500)


class ExecutarEntrada(BaseModel):
    parametros: dict = Field(default_factory=dict)
    timeout_s: int = Field(default=300, ge=5, le=900)


def _cabecalho_ou_422(codigo: str) -> dict:
    try:
        return cabecalho.parse(codigo)
    except cabecalho.ErroCabecalho as e:
        raise ErroAPI(422, "cabecalho_invalido", str(e)) from None


def _ferramenta_ou_404(cur, id: str) -> dict:
    r = comum.item_ou_404(cur, id)
    if r["tipo"] != "ferramenta_script":
        raise ErroAPI(404, "item_inexistente", "ferramenta inexistente")  # não confirma o tipo alheio
    return r


@router.post("/api/ferramentas/script", response_model=Item, status_code=201,
             openapi_extra=PUBLICAR)
def publicar(corpo: PublicarEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    """Publica um script como ferramenta do catálogo (item `ferramenta_script`, versão 1).
    O cabeçalho YAML da docstring é validado antes de gravar; cabeçalho inválido é 422 e nada
    é gravado."""
    from app.catalogo.rotas_itens import ItemEntrada, criar

    cab = _cabecalho_ou_422(corpo.codigo)
    dados = {"codigo": corpo.codigo, "sha256": hashlib.sha256(corpo.codigo.encode("utf-8")).hexdigest(),
             "cabecalho": cab, "versao": 1}
    item = criar(ItemEntrada(tipo="ferramenta_script", titulo=cab["titulo"], dados=dados,
                             pasta_id=corpo.pasta_id, tags=corpo.tags), request, auth)
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "ferramentas/script-publicado", "item", item["id"],
                         {"nome": cab["nome"], "versao": 1, "sha256": dados["sha256"]})
    return item


@router.post("/api/ferramentas/script/{id}/versao", response_model=Item, openapi_extra=PUBLICAR)
def publicar_versao(id: str, corpo: VersaoEntrada, request: Request,
                    auth: Auth = autenticado("conteudo.criar")):
    """Publica uma versão NOVA do script: cria o retrato imutável `versao + 1` em
    `plat.item_versao` (a mesma máquina de versões de qualquer item, L5-05). Execuções passadas
    continuam apontando a versão delas — a procedência é gravada por execução."""
    from app.catalogo.comum import item_json
    from app.catalogo.rotas_itens import editar_item

    cab = _cabecalho_ou_422(corpo.codigo)
    try:
        with db.db(auth.contexto()) as cur:
            atual = _ferramenta_ou_404(cur, id)
            versao_antiga = int((atual["dados"] or {}).get("versao") or 1)
            dados = {"codigo": corpo.codigo,
                     "sha256": hashlib.sha256(corpo.codigo.encode("utf-8")).hexdigest(),
                     "cabecalho": cab, "versao": versao_antiga + 1}
            editado = editar_item(cur, request, auth, str(atual["id"]),
                                  {"titulo": cab["titulo"], "dados": dados},
                                  rotulo="edicao", comentario=corpo.comentario)
            registrar_evento(cur, request, "ferramentas/script-publicado", "item", str(atual["id"]),
                             {"nome": cab["nome"], "versao": dados["versao"], "sha256": dados["sha256"]})
            return item_json(editado, auth)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/ferramentas/script/{id}/formulario", openapi_extra=LER)
def formulario(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Formulário da ferramenta, gerado SÓ do cabeçalho: rótulos, exigência, padrões, mínimos e
    máximos, e JSON Schema por parâmetro. O corpo do script não sai por aqui."""
    with db.db(auth.contexto()) as cur:
        r = _ferramenta_ou_404(cur, id)
    dados = r["dados"] or {}
    ficha = cabecalho.formulario(dados.get("cabecalho") or {})
    ficha.update({"ferramenta_id": str(r["id"]), "versao": dados.get("versao", 1),
                  "sha256": dados.get("sha256"), "titulo_item": r["titulo"]})
    return ficha


@router.post("/api/ferramentas/script/{id}/executar", status_code=202, openapi_extra=EXECUTAR)
def executar(id: str, corpo: ExecutarEntrada, request: Request,
             auth: Auth = autenticado("jobs.executar", escopo_token="jobs:executar")):
    """Executa a ferramenta como job (`ferramentas.executar_script`). Parâmetro fora do tipo/da
    faixa ou entrada `item` inexistente é 422 ANTES de qualquer coisa ser enfileirada. O pedido
    do job congela a versão e o sha256 do script: o worker roda o retrato imutável da versão."""
    with db.db(auth.contexto()) as cur:
        r = _ferramenta_ou_404(cur, id)
    dados = r["dados"] or {}
    cab = _cabecalho_ou_422(dados.get("codigo") or "")
    try:
        valores = cabecalho.validar_valores(cab, corpo.parametros)
    except cabecalho.ErroValor as e:
        # mesma forma do 422 dados_invalidos do catálogo: detalhe É a lista de {campo, erro}
        raise ErroAPI(422, "parametros_invalidos", str(e),
                      [{"campo": e.campo, "erro": e.mensagem}]) from None
    faltando = []
    por_nome = {p["nome"]: p for p in cab["parametros"]}
    with db.db(auth.contexto()) as cur:
        for nome, valor in valores.items():
            if por_nome[nome]["tipo"] != "item":
                continue
            cur.execute("SELECT 1 FROM plat.item WHERE id = %s::uuid", (valor,))
            if cur.fetchone() is None:
                faltando.append({"campo": nome, "erro": f"item {valor} não existe neste inquilino"})
    if faltando:
        raise ErroAPI(422, "parametros_invalidos", "entrada do tipo item não encontrada", faltando)
    job = servico_jobs.criar(
        sessao_de(auth), "ferramentas.executar_script",
        {"ferramenta_id": str(r["id"]), "versao": dados.get("versao", 1), "sha256": dados.get("sha256"),
         "parametros": valores, "timeout_s": corpo.timeout_s},
    )
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "ferramentas/script-execucao-pedida", "item", str(r["id"]),
                         {"job_id": str(job["id"]), "versao": dados.get("versao", 1)})
    return {"job_id": str(job["id"]), "ferramenta_id": str(r["id"]),
            "versao": dados.get("versao", 1), "estado": job["estado"]}


@router.get("/api/ferramentas/script/{id}/execucoes", openapi_extra=LER)
def execucoes(id: str, auth: Auth = autenticado("jobs.ver", escopo_token="jobs:executar")):
    """Log de execução da ferramenta: jobs `ferramentas.executar_script` deste inquilino que
    pediram esta ferramenta, a versão e o sha256 que cada uma congelou e onde terminou."""
    with db.db(auth.contexto()) as cur:
        _ferramenta_ou_404(cur, id)
        cur.execute(
            "SELECT j.id, j.estado, j.criado_em, j.iniciado_em, j.terminado_em, j.erro, "
            "j.parametros->>'versao' AS versao, j.parametros->>'sha256' AS sha256 "
            "FROM plat.job j WHERE j.tipo = 'ferramentas.executar_script' "
            "AND j.parametros->>'ferramenta_id' = %s ORDER BY j.criado_em DESC LIMIT 50",
            (str(id),),
        )
        linhas = cur.fetchall()
    return {"ferramenta_id": str(id), "total": len(linhas), "execucoes": [
        {"job_id": str(linha["id"]), "estado": linha["estado"], "criado_em": linha["criado_em"],
         "iniciado_em": linha["iniciado_em"], "terminado_em": linha["terminado_em"],
         "erro": linha["erro"],
         "versao": int(linha["versao"]) if linha["versao"] else None, "sha256": linha["sha256"]}
        for linha in linhas
    ]}
