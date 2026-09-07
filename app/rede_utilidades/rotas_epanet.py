"""Rotas EPANET .inp da rede de água (item L4-05-d-epanet-inp; ADR 20260907T1629).

`POST /api/rede/{rede_id}/epanet` recebe o `.inp` cru no corpo (como `.../pacote`), guarda numa fila
(`plat.rede_importacao_epanet`) e enfileira o job `rede.epanet_importar` (pesado; a rede real desta casa tem
11.119 nós e 14.756 trechos — não roda no laço de eventos). `GET .../epanet/{importacao_id}` devolve o estado e
as contagens. `GET .../epanet` reconstrói o `.inp` DAS TABELAS (nunca de um arquivo guardado — mesma regra do
pacote de ativos, `rotas.py`) e devolve como texto; roda no threadpool porque reconstruir 14 mil trechos com um
`SELECT` por grupo não é instantâneo."""

import hashlib
import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de
from app.rede_utilidades import epanet_inp
from app.rede_utilidades.epanet_importar import TAMANHO_MAX_BYTES
from app.rede_utilidades.modelos import EpanetImportacao, EpanetImportacaoAceita

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — EPANET"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}


def _uuid_ok(valor: str, codigo: str = "rede_inexistente", mensagem: str = "rede inexistente") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, codigo, mensagem) from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _importacao_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "rede_id": str(r["rede_id"]), "estado": r["estado"],
        "nome_arquivo": r["nome_arquivo"], "crs_epsg": r["crs_epsg"], "arquivo_sha256": r["arquivo_sha256"],
        "arquivo_bytes_tamanho": r["arquivo_bytes_tamanho"], "job_id": str(r["job_id"]) if r["job_id"] else None,
        "contagens": r["contagens"], "avisos": r["avisos"], "erro": r["erro"],
        "criado_em": iso(r["criado_em"]), "atualizado_em": iso(r["atualizado_em"]),
    }


def _importar_sincrono(rid: str, bruto: bytes, crs_epsg: int | None, nome_arquivo: str | None,
                        auth: Auth, request: Request) -> dict:
    if len(bruto) > TAMANHO_MAX_BYTES:
        raise ErroAPI(413, "arquivo_grande_demais", f"o .inp passa de {TAMANHO_MAX_BYTES} bytes ({len(bruto)})")
    if not bruto.strip():
        raise ErroAPI(422, "arquivo_vazio", "o corpo do pedido está vazio")
    sha = hashlib.sha256(bruto).hexdigest()
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            cur.execute(
                "INSERT INTO plat.rede_importacao_epanet"
                "(tenant_id, rede_id, nome_arquivo, crs_epsg, arquivo_bytes, arquivo_sha256, "
                " arquivo_bytes_tamanho, criado_por) "
                "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s) RETURNING id",
                (auth.tenant_id, rid, nome_arquivo, crs_epsg, bruto, sha, len(bruto), auth.usuario_id),
            )
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        importacao_id = str(cur.fetchone()["id"])
    job = servico.criar(sessao_de(auth), "rede.epanet_importar", {"importacao_id": importacao_id})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.rede_importacao_epanet SET job_id = %s::uuid WHERE id = %s::uuid",
                     (job["id"], importacao_id))
        registrar_evento(cur, request, "redes/epanet_importar", "rede", rid,
                         {"importacao_id": importacao_id, "job_id": job["id"], "bytes": len(bruto),
                          "sha256": sha, "crs_epsg": crs_epsg})
    return {"importacao_id": importacao_id, "job_id": job["id"]}


@router.post("/{rede_id}/epanet", response_model=EpanetImportacaoAceita, status_code=202, openapi_extra=EDITAR)
async def importar_epanet(rede_id: str, request: Request, crs_epsg: int | None = Query(default=None),
                           nome_arquivo: str | None = Query(default=None),
                           auth: Auth = autenticado("rede.editar")):
    """Enfileira a importação do `.inp` recebido no corpo. `crs_epsg` é obrigatório quando as coordenadas do
    arquivo não são WGS84 (faixa -180..180/-90..90) — o job recusa sem adivinhar a projeção."""
    rid = _uuid_ok(rede_id)
    bruto = await request.body()
    return await run_in_threadpool(_importar_sincrono, rid, bruto, crs_epsg, nome_arquivo, auth, request)


@router.get("/{rede_id}/epanet/{importacao_id}", response_model=EpanetImportacao, openapi_extra=LER)
def ver_importacao_epanet(rede_id: str, importacao_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    iid = _uuid_ok(importacao_id, "importacao_inexistente", "importação inexistente")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute("SELECT * FROM plat.rede_importacao_epanet WHERE id = %s::uuid AND rede_id = %s::uuid",
                     (iid, rid))
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "importacao_inexistente", "importação inexistente")
        return _importacao_json(r)


def _reconstruir_doc(cur, rede_id: str) -> epanet_inp.DocumentoEpanet:
    doc = epanet_inp.DocumentoEpanet()
    doc.titulo = ["Exportado da plataforma (item L4-05-d-epanet-inp)"]

    def _grupo(codigo: str):
        cur.execute(
            "SELECT f.atributos, ST_X(f.geom) AS x, ST_Y(f.geom) AS y FROM plat.rede_feicao_ponto f "
            "JOIN plat.rede_tipo t ON t.id = f.tipo_id JOIN plat.rede_grupo g ON g.id = t.grupo_id "
            "WHERE f.rede_id = %s::uuid AND g.codigo = %s ORDER BY f.criado_em", (rede_id, codigo),
        )
        return cur.fetchall()

    for r in _grupo("no"):
        a = r["atributos"]
        nid = a.get("no_id")
        if nid is None:
            continue
        doc.junctions.append({"id": nid, "elev": a.get("no_elevacao") or 0.0, "demand": a.get("no_demanda") or 0.0,
                               "pattern": a.get("no_padrao_de_demanda")})
        x, y = a.get("no_x"), a.get("no_y")
        if x is not None and y is not None:
            doc.coordinates[nid] = (x, y)
        elif r["x"] is not None and r["y"] is not None:
            doc.coordinates[nid] = (r["x"], r["y"])
    for r in _grupo("reservatorio_de_nivel_fixo"):
        a = r["atributos"]
        nid = a.get("reservatorio_fixo_id")
        if nid is None:
            continue
        doc.reservoirs.append({"id": nid, "head": a.get("reservatorio_fixo_carga") or 0.0,
                                "pattern": a.get("reservatorio_fixo_padrao_de_carga")})
        x, y = a.get("_x"), a.get("_y")
        if x is not None and y is not None:
            doc.coordinates[nid] = (x, y)
        elif r["x"] is not None and r["y"] is not None:
            doc.coordinates[nid] = (r["x"], r["y"])
    for r in _grupo("reservatorio_de_nivel_variavel"):
        a = r["atributos"]
        nid = a.get("reservatorio_variavel_id")
        if nid is None:
            continue
        doc.tanks.append({
            "id": nid, "elevation": a.get("reservatorio_variavel_cota_de_fundo") or 0.0,
            "init_level": a.get("reservatorio_variavel_nivel_inicial") or 0.0,
            "min_level": a.get("reservatorio_variavel_nivel_minimo") or 0.0,
            "max_level": a.get("reservatorio_variavel_nivel_maximo") or 0.0,
            "diameter": a.get("reservatorio_variavel_diametro") or 0.0,
            "min_vol": a.get("reservatorio_variavel_volume_minimo") or 0.0,
            "vol_curve": a.get("reservatorio_variavel_curva_de_volume"),
            "overflow": a.get("reservatorio_variavel_extravasa"),
        })
        x, y = a.get("_x"), a.get("_y")
        if x is not None and y is not None:
            doc.coordinates[nid] = (x, y)
        elif r["x"] is not None and r["y"] is not None:
            doc.coordinates[nid] = (r["x"], r["y"])
    for r in _grupo("bomba"):
        a = r["atributos"]
        bid = a.get("bomba_id")
        if bid is None:
            continue
        doc.pumps.append({"id": bid, "node1": a.get("bomba_no_1"), "node2": a.get("bomba_no_2"),
                           "head_curve": a.get("bomba_curva"), "power": a.get("bomba_potencia"),
                           "pattern": a.get("bomba_padrao_de_operacao"), "speed": a.get("bomba_rotacao_relativa")})
    for r in _grupo("valvula"):
        a = r["atributos"]
        vid = a.get("valvula_id")
        if vid is None:
            continue
        cur.execute("SELECT tp.codigo FROM plat.rede_feicao_ponto f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
                    "JOIN plat.rede_grupo g ON g.id = tp.grupo_id WHERE g.codigo = 'valvula' AND "
                    "f.atributos->>'valvula_id' = %s AND f.rede_id = %s::uuid LIMIT 1", (vid, rede_id))
        tr = cur.fetchone()
        tipo_codigo = tr["codigo"] if tr else 1
        doc.valves.append({"id": vid, "node1": a.get("valvula_no_1"), "node2": a.get("valvula_no_2"),
                            "diameter": a.get("valvula_diametro") or 0.0,
                            "type": epanet_inp.CODIGO_VALVULA.get(tipo_codigo, "PRV"),
                            "setting": a.get("valvula_ajuste") or 0.0,
                            "minor_loss": a.get("valvula_perda_localizada") or 0.0})

    cur.execute(
        "SELECT f.atributos, ST_AsText(f.geom) AS wkt FROM plat.rede_feicao_linha f "
        "JOIN plat.rede_tipo t ON t.id = f.tipo_id JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "WHERE f.rede_id = %s::uuid AND g.codigo = 'tubulacao' ORDER BY f.criado_em", (rede_id,),
    )
    for r in cur.fetchall():
        a = r["atributos"]
        pid = a.get("tubulacao_id")
        if pid is None:
            continue
        doc.pipes.append({
            "id": pid, "node1": a.get("tubulacao_no_1"), "node2": a.get("tubulacao_no_2"),
            "length": a.get("tubulacao_comprimento") or 0.0, "diameter": a.get("tubulacao_diametro") or 0.0,
            "roughness": a.get("tubulacao_rugosidade") or 0.0,
            "minor_loss": a.get("tubulacao_perda_localizada") or 0.0,
            "status": a.get("tubulacao_situacao") or "Open",
        })
        wkt = r["wkt"]
        if wkt and wkt.upper().startswith("LINESTRING"):
            pontos = _pontos_de_wkt(wkt)
            if len(pontos) > 2:
                doc.vertices[pid] = pontos[1:-1]

    cur.execute("SELECT curva_id, pontos FROM plat.rede_epanet_curva WHERE rede_id = %s::uuid", (rede_id,))
    for r in cur.fetchall():
        doc.curves[r["curva_id"]] = [tuple(p) for p in r["pontos"]]
    cur.execute("SELECT padrao_id, multiplicadores FROM plat.rede_epanet_padrao WHERE rede_id = %s::uuid",
                (rede_id,))
    for r in cur.fetchall():
        doc.patterns[r["padrao_id"]] = list(r["multiplicadores"])
    return doc


def _pontos_de_wkt(wkt: str) -> list[tuple[float, float]]:
    miolo = wkt[wkt.index("(") + 1: wkt.rindex(")")]
    pontos = []
    for par in miolo.split(","):
        x_s, y_s = par.split()
        pontos.append((float(x_s), float(y_s)))
    return pontos


def _exportar_sincrono(rid: str, auth: Auth) -> str:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        doc = _reconstruir_doc(cur, rid)
    return epanet_inp.escrever_inp(doc)


@router.get("/{rede_id}/epanet", openapi_extra=LER, response_class=Response)
async def exportar_epanet(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O `.inp` reconstruído das feições atuais da rede (nunca um arquivo guardado)."""
    rid = _uuid_ok(rede_id)
    texto = await run_in_threadpool(_exportar_sincrono, rid, auth)
    bruto = texto.encode("utf-8")
    return Response(
        content=bruto, media_type="text/plain; charset=utf-8",
        headers={"ETag": '"' + hashlib.sha256(bruto).hexdigest() + '"', "Cache-Control": "no-store",
                 "Content-Disposition": "attachment; filename=rede.inp"},
    )
