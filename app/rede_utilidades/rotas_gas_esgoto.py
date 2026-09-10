"""Rotas de gás e de esgoto da rede de utilidades (item L4-05-e-gas-e-esgoto).

`GET /api/rede/{rede_id}/esgoto/escoamento` confere o escoamento por gravidade dos trechos de esgoto e
drenagem; `GET /api/rede/{rede_id}/gas/pressao` confere o controle de tier de pressão da rede de gás. As duas
são de LEITURA por desenho: nomeiam o problema e não corrigem nada (ver o cabeçalho de `esgoto.py`).

`POST /api/rede/{rede_id}/teksi` recebe um GeoPackage no esquema TEKSI no corpo e grava as feições no
vocabulário do pacote `esgoto-teksi` já importado na rede. É síncrono, no threadpool, com teto de tamanho e de
feições declarado em `teksi.py`: o caso de uso é a bacia levantada em campo, não o cadastro inteiro de uma
cidade — para isso existe a fila de jobs, que este item não usa (ponytail: nada de job novo antes de haver
arquivo grande de verdade).

O GeoPackage vai no corpo com `Content-Type: application/json`, como o pacote de ativos e o `.inp` do EPANET:
a defesa de CSRF de sessão por cookie (`app/auth/sessao.py::checar_escrita_sob_cookie`) exige esse tipo em toda
escrita, e afrouxá-la para uma rota abriria o produto inteiro. O corpo é lido cru, sem passar por JSON."""

import hashlib
import tempfile
import uuid as uuid_mod
from pathlib import Path

import psycopg2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import deposito, esgoto, feicoes, gas, teksi
from app.rede_utilidades.modelos import ConferenciaEscoamento, ConferenciaPressao, TeksiImportacaoResultado

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — gás e esgoto"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _conferir_escoamento(rid: str, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return esgoto.conferir(cur, rid)


@router.get("/{rede_id}/esgoto/escoamento", response_model=ConferenciaEscoamento, openapi_extra=LER)
async def conferir_escoamento(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Confere se a ponta declarada como jusante é a mais baixa em cada trecho que escoa por gravidade.
    Nada é corrigido: `alterou_a_rede` é sempre falso e cada divergência sai como problema nomeado."""
    return await run_in_threadpool(_conferir_escoamento, _uuid_ok(rede_id), auth)


def _conferir_pressao(rid: str, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return gas.conferir(cur, rid)


@router.get("/{rede_id}/gas/pressao", response_model=ConferenciaPressao, openapi_extra=LER)
async def conferir_pressao(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Confere o controle de tier de pressão: todo regulador reduz pressão, e toda emenda entre tiers
    diferentes tem um controlador ao lado."""
    return await run_in_threadpool(_conferir_pressao, _uuid_ok(rede_id), auth)


def _importar_teksi(rid: str, bruto: bytes, auth: Auth, request: Request) -> dict:
    if len(bruto) > teksi.TAMANHO_MAX_BYTES:
        raise ErroAPI(413, "arquivo_grande_demais",
                      f"o GeoPackage passa de {teksi.TAMANHO_MAX_BYTES} bytes ({len(bruto)})")
    if not bruto:
        raise ErroAPI(422, "arquivo_vazio", "o corpo do pedido está vazio")
    sha = hashlib.sha256(bruto).hexdigest()
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        doc = deposito.exportar(cur, rid)
    if doc is None:
        raise ErroAPI(409, "pacote_ausente",
                      "esta rede ainda não recebeu um pacote de ativos; importe o pacote esgoto-teksi antes "
                      "de mandar o GeoPackage")
    with tempfile.TemporaryDirectory(prefix="plat-teksi-") as pasta:
        arquivo = Path(pasta) / "entrada.gpkg"
        arquivo.write_bytes(bruto)
        try:
            lido = teksi.ler_geopackage(arquivo, doc)
        except teksi.ErroTeksi as e:
            raise ErroAPI(422, e.codigo, e.mensagem) from e
    with db.db(auth.contexto()) as cur:
        try:
            res_ponto = feicoes.aplicar_edicoes(cur, auth.tenant_id, rid, {"adds": lido["pontos"]}, "ponto")
            res_linha = feicoes.aplicar_edicoes(cur, auth.tenant_id, rid, {"adds": lido["linhas"]}, "linha")
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        gravadas = {
            "pontos": sum(1 for r in res_ponto["addResults"] if r["success"]),
            "linhas": sum(1 for r in res_linha["addResults"] if r["success"]),
        }
        recusadas = [r for r in res_ponto["addResults"] + res_linha["addResults"] if not r["success"]]
        registrar_evento(cur, request, "redes/teksi_importar", "rede", rid,
                         {"sha256": sha, "bytes": len(bruto), "gravadas": gravadas,
                          "recusadas": len(recusadas), "contagens": lido["contagens"]})
    return {"rede_id": rid, "sha256": sha, "bytes": len(bruto), "contagens": lido["contagens"],
            "gravadas": gravadas, "recusadas": recusadas, "avisos": lido["avisos"]}


@router.post("/{rede_id}/teksi", response_model=TeksiImportacaoResultado, status_code=201,
             openapi_extra=EDITAR)
async def importar_teksi(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Importa um GeoPackage no esquema TEKSI para as feições da rede. O de-para coluna → atributo é o do
    pacote de ativos já importado nesta rede (`origem.camada`/`origem.coluna` de cada atributo)."""
    rid = _uuid_ok(rede_id)
    bruto = await request.body()
    return await run_in_threadpool(_importar_teksi, rid, bruto, auth, request)
