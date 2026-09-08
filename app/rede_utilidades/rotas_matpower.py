"""Rota de importação de caso MATPOWER (item L4-05-c-pandapower-e-matpower).

`POST /api/rede/{rede_id}/matpower` recebe o `.m` cru no corpo (como `.../pacote`), lê o caseformat 2 e
grava as barras e os ramos no grafo da rede — objetos NÃO ESPACIAIS, porque o caso do MATPOWER não tem
coordenada nenhuma (ver `matpower_importar`). Síncrona de propósito: um caso público de transmissão tem
dezenas ou centenas de barras (o `case9` tem 9, o `case30` tem 30), e o teto de tamanho abaixo mantém
assim; enfileirar um job para isso seria maquinaria sem trabalho para fazer. A leitura e a gravação vão
para o threadpool, como no importador de pacote, para não segurar o laço de eventos.

A exportação para MATPOWER é a outra ponta e mora na rota que já existe:
`GET /api/rede/{id}/subrede/{nome}/exportar?formato=matpower`."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import matpower, matpower_importar

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — MATPOWER"])
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
# um caso de transmissão em caseformat 2 é texto de matriz: o `case30` público tem 3 KiB. O teto deixa
# folga de três ordens de grandeza e ainda impede que a rota vire porta de entrada de arquivo grande.
CASO_MAX_BYTES = 4 * 1024 * 1024
PREFIXO_MAX = 32


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _importar_sincrono(rid: str, bruto: bytes, prefixo: str, auth: Auth, request: Request) -> dict:
    # A REDE PRIMEIRO, o corpo depois: quem não pode ver esta rede recebe 404 sem que o corpo diga nada
    # sobre ela (mesma ordem de `rotas.importar_pacote`, exigida pela varredura cruzada A→B).
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    if len(bruto) > CASO_MAX_BYTES:
        raise ErroAPI(413, "caso_grande_demais",
                      f"o caso passa de {CASO_MAX_BYTES} bytes ({len(bruto)})")
    if not bruto.strip():
        raise ErroAPI(422, "caso_vazio", "o corpo do pedido está vazio")
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ErroAPI(422, "caso_nao_e_texto", "o caso tem de ser texto UTF-8") from e
    try:
        caso = matpower.ler_caso(texto)
    except matpower.ErroMatpower as e:
        raise ErroAPI(422, e.codigo, e.mensagem,
                      [{"linha": e.linha, "erro": e.codigo, "mensagem": e.mensagem}]) from e
    with db.db(auth.contexto()) as cur:
        try:
            contagens = matpower_importar.importar(cur, auth.tenant_id, rid, caso, prefixo)
        except matpower_importar.ErroImportacaoMatpower as e:
            raise ErroAPI(422, e.codigo, e.mensagem) from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/importar_matpower", "rede", rid,
                         {"prefixo": prefixo, "contagens": contagens})
    return {"rede_id": rid, "prefixo": prefixo, "versao_do_caseformat": caso["versao"],
            "contagens": contagens}


@router.post("/{rede_id}/matpower", status_code=201, openapi_extra=EDITAR)
async def importar_matpower(rede_id: str, request: Request,
                            prefixo: str = Query("", max_length=PREFIXO_MAX,
                                                 pattern="^[A-Za-z0-9_-]*$"),
                            auth: Auth = autenticado("rede.editar")):
    """Importa um caso MATPOWER (caseformat 2) para o grafo da rede. A rede precisa ter o pacote de
    ativos `transmissao-matpower` importado antes. `prefixo` entra no código externo de cada objeto e
    permite mais de um caso na mesma rede. As barras entram SEM geometria: o caseformat não tem
    coordenada, e a plataforma não inventa uma."""
    rid = _uuid_ok(rede_id)
    bruto = await request.body()
    return await run_in_threadpool(_importar_sincrono, rid, bruto, prefixo, auth, request)
