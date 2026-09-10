"""Rotas do diagrama de rede (item L4-04-d-diagrama-esquematico).

  * `POST   /api/rede/{rede_id}/diagrama` — gera (ou regera, pelo mesmo nome) o diagrama a partir de uma
    subrede atualizada, de um traçado ou de uma seleção de feições, com o modelo (template) escolhido;
  * `GET    /api/rede/{rede_id}/diagramas` — a lista, com estado consistente/inconsistente;
  * `GET    /api/rede/{rede_id}/diagrama/{diagrama_id}` — o grafo inteiro (nós com x,y no espaço do diagrama
    e a âncora de volta ao mapa; arestas com as feições que cada uma representa);
  * `POST   /api/rede/{rede_id}/diagrama/{diagrama_id}/layout` — reaplica só o layout, sem refazer o recorte;
  * `GET    /api/rede/{rede_id}/diagrama/{diagrama_id}/exportar` — `json`, `svg` ou `png`;
  * `DELETE /api/rede/{rede_id}/diagrama/{diagrama_id}` — apaga;
  * `GET    /api/rede/{rede_id}/diagrama-modelos` e `PUT /api/rede/{rede_id}/diagrama-modelo/{codigo}` — os
    modelos embutidos e os do inquilino.

Mesmo padrão dos outros módulos de rede: escrita exige `rede.editar`, leitura segue a visibilidade por
inquilino (RLS), trabalho pesado vai para o threadpool."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import diagrama
from app.rede_utilidades.modelos import DiagramaEntrada, DiagramaLayoutEntrada, DiagramaModeloEntrada

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — diagrama"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
LISTA_LIMITE_MAX = 500


def _uuid_ok(valor: str, erro: str = "rede_inexistente", texto: str = "rede inexistente") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, erro, texto) from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _gerar_sincrono(rid: str, corpo: DiagramaEntrada, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            return diagrama.gerar(cur, auth.tenant_id, rid, corpo.nome, corpo.origem, corpo.modelo,
                                  corpo.layout)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e


@router.post("/{rede_id}/diagrama", status_code=201, openapi_extra=EDITAR)
async def gerar_diagrama(rede_id: str, corpo: DiagramaEntrada, request: Request,
                         auth: Auth = autenticado("rede.editar")):
    """Gera o diagrama. `origem` é um objeto com `tipo`:

      * `{"tipo": "subrede", "subrede": "<nome>", "tier": "<codigo>"}` — a subrede tem de estar atualizada
        (o diagrama é feito do que a atualização gravou, não de um traçado novo escondido dentro da chamada);
      * `{"tipo": "tracado", "tracado": "subrede|conectado", "pontos_partida": [...], "barreiras": [...]}`;
      * `{"tipo": "selecao", "feicoes": ["<uuid>", ...]}`.

    Gerar de novo com o MESMO nome substitui o desenho e devolve o diagrama a `consistente`, mantendo o
    identificador — o link que alguém guardou continua valendo."""
    rid = _uuid_ok(rede_id)
    saida = await run_in_threadpool(_gerar_sincrono, rid, corpo, auth)
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "redes/diagrama_gerar", "rede", rid,
                         {"diagrama_id": saida["id"], "nome": saida["nome"], "modelo": saida["modelo"],
                          "layout": saida["layout"], "nos": saida["resumo"]["nos"],
                          "arestas": saida["resumo"]["arestas"]})
    return saida


@router.get("/{rede_id}/diagramas", openapi_extra=LER)
def listar_diagramas(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A lista de diagramas da rede, com o estado de consistência de cada um."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = diagrama.listar(cur, rid, min(max(limite, 1), LISTA_LIMITE_MAX))
        return {"total": len(itens), "itens": itens}


@router.get("/{rede_id}/diagrama/{diagrama_id}", openapi_extra=LER)
def ler_diagrama(rede_id: str, diagrama_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O grafo do diagrama: nós (x,y do diagrama, mais `feicao_id`/`terminal`/`lon`/`lat` para a seleção
    casar com o mapa) e arestas (com a lista de feições que cada uma representa)."""
    rid = _uuid_ok(rede_id)
    did = _uuid_ok(diagrama_id, "diagrama_inexistente", "diagrama inexistente")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return diagrama.ler(cur, rid, did)


@router.post("/{rede_id}/diagrama/{diagrama_id}/layout", openapi_extra=EDITAR)
def aplicar_layout_diagrama(rede_id: str, diagrama_id: str, corpo: DiagramaLayoutEntrada, request: Request,
                            auth: Auth = autenticado("rede.editar")):
    """Reposiciona os nós com outro layout, sem refazer o recorte nem as regras. Não muda o estado de
    consistência: trocar o desenho não conserta diagrama velho."""
    rid = _uuid_ok(rede_id)
    did = _uuid_ok(diagrama_id, "diagrama_inexistente", "diagrama inexistente")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        r = diagrama.reaplicar_layout(cur, rid, did, corpo.layout)
        registrar_evento(cur, request, "redes/diagrama_layout", "rede", rid,
                         {"diagrama_id": did, "layout": corpo.layout})
        return r


@router.get("/{rede_id}/diagrama/{diagrama_id}/exportar", openapi_extra=LER)
def exportar_diagrama(rede_id: str, diagrama_id: str, formato: str = "json",
                      auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """`json` (padrão) devolve o mesmo documento da leitura; `svg` devolve o desenho vetorial e `png` a
    imagem. Os três saem do MESMO grafo gravado — a figura nunca é redesenhada por outro caminho."""
    if formato not in diagrama.FORMATOS_EXPORTACAO:
        raise ErroAPI(422, "formato_invalido", f"formato deve ser um de {diagrama.FORMATOS_EXPORTACAO}")
    rid = _uuid_ok(rede_id)
    did = _uuid_ok(diagrama_id, "diagrama_inexistente", "diagrama inexistente")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        doc = diagrama.ler(cur, rid, did)
    if formato == "json":
        return doc
    nome = doc["nome"].replace('"', "")
    if formato == "svg":
        return Response(content=diagrama.para_svg(doc), media_type="image/svg+xml",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.svg"'})
    return Response(content=diagrama.para_png(doc), media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="{nome}.png"'})


@router.delete("/{rede_id}/diagrama/{diagrama_id}", status_code=204, openapi_extra=EDITAR)
def apagar_diagrama(rede_id: str, diagrama_id: str, request: Request,
                    auth: Auth = autenticado("rede.editar")):
    """Apaga o diagrama e o desenho dele. A rede não é tocada: diagrama é derivado."""
    rid = _uuid_ok(rede_id)
    did = _uuid_ok(diagrama_id, "diagrama_inexistente", "diagrama inexistente")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        diagrama.apagar(cur, rid, did)
        registrar_evento(cur, request, "redes/diagrama_apagar", "rede", rid, {"diagrama_id": did})
    return Response(status_code=204)


@router.get("/{rede_id}/diagrama-modelos", openapi_extra=LER)
def listar_modelos_diagrama(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Os modelos embutidos (`basico`, `esquematico`, `geografico`) e os declarados nesta rede."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = diagrama.listar_modelos(cur, rid)
        return {"total": len(itens), "itens": itens, "layouts": list(diagrama.LAYOUTS),
                "regras": list(diagrama.REGRAS)}


@router.put("/{rede_id}/diagrama-modelo/{codigo}", openapi_extra=EDITAR)
def definir_modelo_diagrama(rede_id: str, codigo: str, corpo: DiagramaModeloEntrada, request: Request,
                            auth: Auth = autenticado("rede.editar")):
    """Declara um modelo do inquilino: as regras de construção, na ordem em que se aplicam, e o layout
    padrão. Código de modelo embutido é recusado — quem quer outro comportamento cria outro código."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            r = diagrama.definir_modelo(cur, auth.tenant_id, rid, codigo, corpo.nome, corpo.regras,
                                        corpo.layout)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/diagrama_modelo_definir", "rede", rid,
                         {"codigo": r["codigo"], "layout": r["layout"], "regras": r["regras"]})
        return r
