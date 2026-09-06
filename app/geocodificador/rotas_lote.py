"""API da geocodificação de tabela (item L2-11-a-geocodificacao-csv). Sete rotas, na ordem em que a tela usa:

    POST   /api/geocodificacoes/colunas          -> colunas do arquivo + mapeamento PROPOSTO (nada é gravado)
    POST   /api/geocodificacoes                  -> cria o lote com o mapeamento confirmado e enfileira o job
    GET    /api/geocodificacoes                  -> lista os lotes do usuário
    GET    /api/geocodificacoes/{id}             -> estado, contagens, resumo e ficha da base de endereços
    GET    /api/geocodificacoes/{id}/linhas      -> linhas para a tela de revisão (filtro por estado)
    PUT    /api/geocodificacoes/{id}/linhas/{n}  -> grava a coordenada arrastada no mapa (origem 'manual')
    POST   /api/geocodificacoes/{id}/regeocodificar -> refaz SÓ as pendentes

Duas decisões que valem registrar:

1. **O teto de tamanho é conferido em bytes REAIS**, na criação (`plat.item.dados.bytes` do arquivo já
   gravado) e outra vez dentro do job (comprimento do objeto lido do armazenamento). Confiar só no que o
   navegador declara deixaria passar um arquivo de qualquer tamanho — o item pede a prova do teto.
2. **O arrasto no mapa grava na linha E na camada, na mesma transação.** Se gravasse só na linha, o mapa
   continuaria mostrando o ponto errado até a próxima re-geocodificação; se gravasse só na camada, a linha
   voltaria a ser sobrescrita na re-geocodificação seguinte.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from pydantic import Field

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import UUID_PADRAO, Modelo
from app.erros import ErroAPI
from app.geocodificador import tabela
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["geocodificacao"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
PUBLICAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}
ESTADOS_LINHA = ("resolvida", "pendente", "malformada")


class ArquivoEntrada(Modelo):
    arquivo_id: str = Field(pattern=UUID_PADRAO)


class LoteEntrada(Modelo):
    arquivo_id: str = Field(pattern=UUID_PADRAO)
    titulo: str = Field(min_length=1, max_length=250)
    mapeamento: dict = Field(default_factory=dict)


class PontoManual(Modelo):
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)


def _bytes_do_arquivo(cur, arquivo_id: str) -> dict:
    cur.execute("SELECT id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'", (arquivo_id,))
    arq = cur.fetchone()
    if arq is None:
        raise ErroAPI(404, "item_inexistente", "item de arquivo inexistente")
    return arq["dados"] or {}


def _ler_conferindo_teto(dados_item: dict) -> bytes:
    """Teto conferido DUAS vezes: no tamanho gravado no item (barato, antes de trazer o objeto) e no
    comprimento real do objeto lido (o que vale)."""
    declarado = int(dados_item.get("bytes") or 0)
    try:
        tabela.conferir_tamanho(declarado)
    except tabela.ArquivoGrandeDemais as e:
        raise ErroAPI(413, "arquivo_grande_demais", str(e),
                       {"bytes": declarado, "teto_bytes": limites.GEOCOD_ARQUIVO_BYTES_MAX}) from e
    try:
        conteudo = objetos.ler(dados_item["chave"])
    except (FileNotFoundError, KeyError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "o objeto do arquivo não existe mais no armazenamento") from e
    try:
        tabela.conferir_tamanho(len(conteudo))
    except tabela.ArquivoGrandeDemais as e:
        raise ErroAPI(413, "arquivo_grande_demais", str(e),
                       {"bytes": len(conteudo), "teto_bytes": limites.GEOCOD_ARQUIVO_BYTES_MAX}) from e
    return conteudo


def _lote(cur, auth: Auth, geocodificacao_id: str) -> dict:
    gid = uuid_ok(geocodificacao_id, "geocodificacao_inexistente", "geocodificação inexistente")
    cur.execute("SELECT * FROM plat.geocodificacao WHERE id = %s::uuid", (gid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "geocodificacao_inexistente", "geocodificação inexistente")
    if r["usuario_id"] not in (None, auth.usuario_id) and not auth.tem("jobs.gerir_todos"):
        raise ErroAPI(404, "geocodificacao_inexistente", "geocodificação inexistente")
    return r


def _lote_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "arquivo_id": str(r["arquivo_id"]),
        "item_id": str(r["item_id"]) if r["item_id"] else None,
        "titulo": r["titulo"], "mapeamento": r["mapeamento"], "estado": r["estado"],
        "linhas_total": r["linhas_total"], "resolvidas": r["resolvidas"], "pendentes": r["pendentes"],
        "malformadas": r["malformadas"], "manuais": r["manuais"], "resumo": r["resumo"],
        "base_enderecos": r["base_enderecos"], "job_id": str(r["job_id"]) if r["job_id"] else None,
        "erro": r["erro"], "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
        "atualizado_em": r["atualizado_em"].isoformat() if r["atualizado_em"] else None,
    }


@router.post("/api/geocodificacoes/colunas", openapi_extra=PUBLICAR)
def colunas(corpo: ArquivoEntrada, auth: Auth = autenticado("conteudo.publicar_camada")):
    """Lê só o cabeçalho e devolve as colunas + o mapeamento proposto. Não grava nada."""
    with db.db(auth.contexto()) as cur:
        dados_item = _bytes_do_arquivo(cur, uuid_ok(corpo.arquivo_id))
    conteudo = _ler_conferindo_teto(dados_item)
    try:
        saida = tabela.colunas(conteudo)
    except tabela.ArquivoIlegivel as e:
        raise ErroAPI(422, "arquivo_ilegivel", str(e)) from e
    saida["campos_aceitos"] = list(limites.GEOCOD_CAMPOS)
    return saida


@router.post("/api/geocodificacoes", status_code=202, openapi_extra=PUBLICAR)
def criar(corpo: LoteEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    arquivo_id = uuid_ok(corpo.arquivo_id)
    with db.db(auth.contexto()) as cur:
        dados_item = _bytes_do_arquivo(cur, arquivo_id)
    conteudo = _ler_conferindo_teto(dados_item)
    try:
        cabecalho = tabela.colunas(conteudo)["colunas"]
    except tabela.ArquivoIlegivel as e:
        raise ErroAPI(422, "arquivo_ilegivel", str(e)) from e
    mapeamento = corpo.mapeamento or tabela.colunas(conteudo)["mapeamento_proposto"]
    try:
        tabela.conferir_mapeamento(mapeamento, cabecalho)
    except ValueError as e:
        raise ErroAPI(422, "mapeamento_invalido", str(e), {"colunas": cabecalho}) from e

    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.geocodificacao(tenant_id, usuario_id, arquivo_id, titulo, mapeamento) "
            "VALUES (%s, %s, %s::uuid, %s, %s::jsonb) RETURNING id",
            (auth.tenant_id, auth.usuario_id, arquivo_id, corpo.titulo,
             json.dumps(mapeamento, ensure_ascii=False)),
        )
        gid = str(cur.fetchone()["id"])
        registrar_evento(cur, request, "geocodificacoes/criar", "item", arquivo_id,
                          {"geocodificacao_id": gid, "mapeamento": mapeamento})
    job = servico.criar(sessao_de(auth), "geocodificacao.lote",
                         {"geocodificacao_id": gid, "so_pendentes": False})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.geocodificacao SET job_id = %s::uuid WHERE id = %s::uuid", (job["id"], gid))
    return {"geocodificacao_id": gid, "job_id": job["id"], "mapeamento": mapeamento}


@router.get("/api/geocodificacoes", openapi_extra=LER)
def listar(limite: int = Query(50, ge=1, le=200), deslocamento: int = Query(0, ge=0),
           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        if auth.tem("jobs.gerir_todos"):
            cur.execute("SELECT * FROM plat.geocodificacao ORDER BY criado_em DESC LIMIT %s OFFSET %s",
                         (limite, deslocamento))
        else:
            cur.execute("SELECT * FROM plat.geocodificacao WHERE usuario_id = %s ORDER BY criado_em DESC "
                         "LIMIT %s OFFSET %s", (auth.usuario_id, limite, deslocamento))
        linhas = [_lote_json(r) for r in cur.fetchall()]
    return {"geocodificacoes": linhas, "total": len(linhas)}


@router.get("/api/geocodificacoes/{geocodificacao_id}", openapi_extra=LER)
def detalhar(geocodificacao_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return _lote_json(_lote(cur, auth, geocodificacao_id))


@router.get("/api/geocodificacoes/{geocodificacao_id}/linhas", openapi_extra=LER)
def linhas(geocodificacao_id: str, estado: str | None = Query(None), limite: int = Query(100, ge=1),
           deslocamento: int = Query(0, ge=0), auth: Auth = autenticado(escopo_token="catalogo:ler")):
    if estado is not None and estado not in ESTADOS_LINHA:
        raise ErroAPI(422, "estado_invalido", f"estado {estado!r} inválido; aceitos: {list(ESTADOS_LINHA)}")
    limite = min(limite, limites.GEOCOD_LINHAS_PAGINA_MAX)
    with db.db(auth.contexto()) as cur:
        lote = _lote(cur, auth, geocodificacao_id)
        gid = str(lote["id"])
        cur.execute(
            "SELECT count(*) AS n FROM plat.geocodificacao_linha WHERE geocodificacao_id = %s::uuid "
            "AND (%s::text IS NULL OR estado = %s)", (gid, estado, estado))
        total = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT n, entrada, endereco, lon, lat, score, tipo_acerto, origem, estado, motivo, avisos, "
            "  cod_municipio, municipio, uf FROM plat.geocodificacao_linha "
            "WHERE geocodificacao_id = %s::uuid AND (%s::text IS NULL OR estado = %s) "
            "ORDER BY n LIMIT %s OFFSET %s", (gid, estado, estado, limite, deslocamento))
        saida = [dict(r) for r in cur.fetchall()]
    return {"linhas": saida, "total": total, "limite": limite, "deslocamento": deslocamento}


@router.put("/api/geocodificacoes/{geocodificacao_id}/linhas/{n}", openapi_extra=PUBLICAR)
def ponto_manual(geocodificacao_id: str, n: int, corpo: PontoManual, request: Request,
                  auth: Auth = autenticado("conteudo.publicar_camada")):
    """Coordenada arrastada no mapa. Grava na linha (origem 'manual') e no ponto da camada, juntas."""
    with db.db(auth.contexto()) as cur:
        lote = _lote(cur, auth, geocodificacao_id)
        gid = str(lote["id"])
        cur.execute(
            "UPDATE plat.geocodificacao_linha SET lon = %s, lat = %s, origem = 'manual', "
            "  estado = 'resolvida', score = NULL, tipo_acerto = 'manual', "
            "  motivo = NULL, atualizado_em = now() "
            "WHERE geocodificacao_id = %s::uuid AND n = %s RETURNING n, estado, origem, tipo_acerto",
            (corpo.lon, corpo.lat, gid, n))
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "linha_inexistente", f"a linha {n} não existe nesta geocodificação")
        if lote["item_id"]:
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (lote["item_id"],))
            item = cur.fetchone()
            if item is not None:
                d = item["dados"] or {}
                schema, nome_tabela = d.get("schema"), d.get("tabela")
                if schema and nome_tabela:
                    cur.execute(
                        f'UPDATE "{schema}"."{nome_tabela}" SET geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326), '
                        f"geo_origem = 'manual', geo_tipo_acerto = 'manual', geo_score = NULL "
                        f"WHERE linha = %s", (corpo.lon, corpo.lat, n))
                    if cur.rowcount == 0:
                        # a linha era pendente/malformada: não havia ponto na camada, agora há
                        cur.execute(
                            f'INSERT INTO "{schema}"."{nome_tabela}" '
                            f'  (linha, endereco_entrada, geo_origem, geo_tipo_acerto, geom) '
                            "SELECT l.n, coalesce(l.entrada->>'endereco', concat_ws(', ', "
                            "  l.entrada->>'logradouro', l.entrada->>'numero', l.entrada->>'bairro', "
                            "  l.entrada->>'municipio', l.entrada->>'uf')), 'manual', 'manual', "
                            "  ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326) "
                            "FROM plat.geocodificacao_linha l "
                            "WHERE l.geocodificacao_id = %s::uuid AND l.n = %s", (gid, n))
        cur.execute(
            "UPDATE plat.geocodificacao SET "
            "  resolvidas = (SELECT count(*) FROM plat.geocodificacao_linha "
            "                WHERE geocodificacao_id = %(g)s::uuid AND estado = 'resolvida'), "
            "  pendentes = (SELECT count(*) FROM plat.geocodificacao_linha "
            "               WHERE geocodificacao_id = %(g)s::uuid AND estado = 'pendente'), "
            "  malformadas = (SELECT count(*) FROM plat.geocodificacao_linha "
            "                 WHERE geocodificacao_id = %(g)s::uuid AND estado = 'malformada'), "
            "  manuais = (SELECT count(*) FROM plat.geocodificacao_linha "
            "             WHERE geocodificacao_id = %(g)s::uuid AND origem = 'manual'), "
            "  atualizado_em = now() WHERE id = %(g)s::uuid", {"g": gid})
        registrar_evento(cur, request, "geocodificacoes/ponto_manual", "item", str(lote["arquivo_id"]),
                          {"geocodificacao_id": gid, "linha": n, "lon": corpo.lon, "lat": corpo.lat})
    return {"linha": n, "lon": corpo.lon, "lat": corpo.lat, "origem": "manual", "estado": "resolvida",
            "tipo_acerto": "manual"}


@router.post("/api/geocodificacoes/{geocodificacao_id}/regeocodificar", status_code=202,
              openapi_extra=PUBLICAR)
def regeocodificar(geocodificacao_id: str, request: Request,
                    auth: Auth = autenticado("conteudo.publicar_camada")):
    """Refaz só as linhas que não estão resolvidas (e nunca as de origem manual). Serve para depois de
    instalar uma UF nova da base de endereços, ou de corrigir o arquivo de origem."""
    with db.db(auth.contexto()) as cur:
        lote = _lote(cur, auth, geocodificacao_id)
        gid = str(lote["id"])
        if lote["estado"] in ("na_fila", "rodando"):
            raise ErroAPI(409, "geocodificacao_em_andamento",
                           "esta geocodificação ainda está na fila ou rodando")
        cur.execute(
            "SELECT count(*) AS n FROM plat.geocodificacao_linha WHERE geocodificacao_id = %s::uuid "
            "AND estado <> 'resolvida' AND origem IS DISTINCT FROM 'manual'", (gid,))
        pendentes = int(cur.fetchone()["n"])
        if pendentes == 0:
            raise ErroAPI(409, "sem_pendentes", "não há linha pendente para refazer nesta geocodificação")
        cur.execute("UPDATE plat.geocodificacao SET estado = 'na_fila', erro = NULL, atualizado_em = now() "
                     "WHERE id = %s::uuid", (gid,))
        registrar_evento(cur, request, "geocodificacoes/regeocodificar", "item", str(lote["arquivo_id"]),
                          {"geocodificacao_id": gid, "pendentes": pendentes})
    job = servico.criar(sessao_de(auth), "geocodificacao.lote",
                         {"geocodificacao_id": gid, "so_pendentes": True})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.geocodificacao SET job_id = %s::uuid WHERE id = %s::uuid", (job["id"], gid))
    return {"geocodificacao_id": gid, "job_id": job["id"], "pendentes": pendentes}
