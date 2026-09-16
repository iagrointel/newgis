"""Rotas do modelo genérico de conexão externa (item L6-02-a-modelo-conexao-e-seguranca; ADR 0012).

`GET /api/conexoes` lista as do inquilino (RLS); `POST /api/conexoes` cria (privilégio
`conteudo.registrar_fonte`, mesmo da rota de acervo) — a URL passa por `app.conexao.seguranca.validar_url`
ANTES do INSERT (recusa SSRF na entrada, não só no teste); `GET/PATCH/DELETE /api/conexoes/{id}` seguem
dono-ou-`conteudo.editar_tudo`, como pasta. `POST /api/conexoes/{id}/testar` é o teste de saúde: chama
`app.conexao.seguranca.buscar_seguro` com timeout curto e grava `saude`/`saude_mensagem`/
`saude_verificada_em`/`saude_latencia_ms`. Nenhuma rota devolve `credencial_cifrada` nem grava a credencial em
log (a credencial NUNCA aparece em `request`/`response` deste módulo depois de decifrada; só existe dentro do
corpo de `_testar`, e some do escopo ao final da função)."""

import json
import uuid

import psycopg2
from fastapi import APIRouter, Request

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo import comum as catalogo_comum
from app.catalogo import documento as catalogo_documento
from app.catalogo import tipos as catalogo_tipos
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import Item as ItemSaida
from app.catalogo.modelos import JobCriado
from app.conexao import cache as cache_conexao
from app.conexao import copia as copia_mod
from app.conexao import credencial as credencial_mod
from app.conexao import descoberta as descoberta_mod  # `publicar_camada` já usa a variável local `descoberta`
from app.conexao import google_sheets, ladrilhos, proveniencia, seguranca, vetor_externo
from app.conexao.modelos import (
    ArquivoUrlEntrada,
    ArquivoUrlEstado,
    CamadasPagina,
    CamposSaida,
    ColecoesPagina,
    Conexao,
    ConexaoEditar,
    ConexaoEntrada,
    ConexaoPagina,
    ConexaoTeste,
    DescobrirResultado,
    FeicoesSaida,
    PublicarCamadaEntrada,
    SaudeHistoricoPagina,
)
from app.erros import ErroAPI
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

router = APIRouter(prefix="/api/conexoes", tags=["conexoes"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}
HISTORICO_LIMITE_PADRAO = 10
HISTORICO_LIMITE_MAX = 30  # o mesmo teto de guarda de plat.conexao_saude_historico (036)

# nunca inclui credencial_cifrada
CAMPOS = (
    "c.id, c.tipo, c.modo, c.nome, c.url, c.config, (c.credencial_cifrada IS NOT NULL) AS tem_credencial, "
    "c.saude, c.saude_mensagem, c.saude_latencia_ms, c.saude_verificada_em, c.criado_em, c.atualizado_em, "
    "c.dono_id, u.login AS dono_login, u.nome AS dono_nome, "
    "v.estado_saude, v.disponibilidade_30d_pct, v.disponibilidade_30d_total"
)
# LEFT JOIN (nunca INNER): a view sempre tem 1 linha por conexão (FROM plat.conexao), mas o LEFT deixa explícito
# que a ausência de histórico não pode sumir com a conexão da listagem (item L6-02-l-saude).
SQL_BASE = (
    f"SELECT {CAMPOS} FROM plat.conexao c JOIN plat.usuario u ON u.id = c.dono_id "  # noqa: S608
    "LEFT JOIN plat.v_conexao_saude v ON v.conexao_id = c.id"
)


def _json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "tipo": r["tipo"],
        "modo": r["modo"],
        "nome": r["nome"],
        "url": r["url"],
        "config": r["config"] or {},
        "tem_credencial": bool(r["tem_credencial"]),
        "saude": r["saude"],
        "saude_mensagem": r["saude_mensagem"],
        "saude_latencia_ms": r["saude_latencia_ms"],
        "saude_verificada_em": iso(r["saude_verificada_em"]),
        "estado_saude": r.get("estado_saude") or "nunca_testada",
        "disponibilidade_30d_pct": (
            float(r["disponibilidade_30d_pct"]) if r.get("disponibilidade_30d_pct") is not None else None
        ),
        "disponibilidade_30d_total": r.get("disponibilidade_30d_total") or 0,
        "dono": {"id": r["dono_id"], "login": r["dono_login"], "nome": r["dono_nome"]},
        "criado_em": iso(r["criado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


def _carregar(cur, cid: str) -> dict:
    cur.execute(SQL_BASE + " WHERE c.id = %s::uuid", (cid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "conexao_inexistente", "conexão inexistente")
    return r


def _pode_editar(r: dict, auth: Auth) -> None:
    if r["dono_id"] != auth.usuario_id and not auth.tem("conteudo.editar_tudo"):
        raise ErroAPI(403, "sem_permissao", "só o dono da conexão ou conteudo.editar_tudo")


def _config_ok(config: dict) -> None:
    tamanho = len(json.dumps(config, ensure_ascii=False).encode("utf-8"))
    if tamanho > limites.CONEXAO_CONFIG_MAX_BYTES:
        raise ErroAPI(
            422, "config_grande_demais",
            f"config passa de {limites.CONEXAO_CONFIG_MAX_BYTES} bytes ({tamanho})",
        )


def _url_ok(url: str) -> None:
    """Recusa SSRF já na entrada (criar/editar), não só no teste de saúde: uma conexão nunca fica registrada
    com URL que o proxy jamais poderia buscar."""
    try:
        seguranca.validar_url(url)
    except seguranca.ErroURLInsegura as e:
        raise ErroAPI(422, "url_insegura", f"URL recusada: {e.motivo}", {"motivo": e.motivo}) from e


def _config_tiles_ok(tipo: str, url: str, config: dict) -> dict:
    """PMTiles/XYZ (item L6-02-g-pmtiles-xyz-tilejson): `config.atribuicao`/`zoom_min`/`zoom_max` obrigatórios
    (e `formato`/marcadores `{z}{x}{y}` para xyz) — ver `app.conexao.ladrilhos.validar_config`. Devolve o
    `config` já normalizado; para qualquer outro tipo devolve o `config` recebido, sem tocar."""
    try:
        return ladrilhos.validar_config(tipo, url, config)
    except ladrilhos.ErroConfigTiles as e:
        raise ErroAPI(422, e.codigo, str(e), {"campo": e.campo}) from e


def _range_pmtiles_ok(url: str) -> None:
    """PMTiles (item L6-02-g-pmtiles-xyz-tilejson): recusa a conexão ANTES de gravar se o servidor não honrar
    `Range`/206 — ver `app.conexao.ladrilhos.verificar_range_pmtiles` (a refutação do item: adversário que
    devolve 200 ignorando o Range)."""
    resultado = ladrilhos.verificar_range_pmtiles(url)
    if not resultado.ok:
        raise ErroAPI(
            422, "pmtiles_sem_range",
            f"o servidor não confirmou suporte a Range/206 para PMTiles: {resultado.motivo}",
            {"motivo": resultado.motivo, "status": resultado.status},
        )


def _url_de_planilha(tipo: str, url: str) -> str:
    """Item L6-02-i: conexão `google_sheets` só registra URL de planilha do Google, e já na forma CANÔNICA de
    exportação CSV (`/export?format=csv`), com o gid da aba preservado — o que fica gravado é o endereço que
    a sincronização vai baixar, não a página de edição que o usuário colou. Qualquer outra URL vira 422."""
    if tipo != "google_sheets":
        return url
    try:
        return google_sheets.url_exportacao_csv(url)
    except google_sheets.ErroGoogleSheets as e:
        raise ErroAPI(422, e.motivo, e.detalhe, {"motivo": e.motivo}) from e


def _credencial_de_planilha_ok(tipo: str, credencial: str | None) -> None:
    """A credencial de `google_sheets` é o JSON da conta de serviço: confere na ENTRADA (422 se inválido),
    sem nunca ecoar o conteúdo na resposta — a exceção carrega só o nome do campo problemático."""
    if tipo != "google_sheets" or credencial is None:
        return
    try:
        google_sheets.validar_conta_servico(credencial)
    except google_sheets.ErroGoogleSheets as e:
        raise ErroAPI(422, e.motivo, e.detalhe, {"motivo": e.motivo}) from e


def _conector(cur, cid: str, auth: Auth) -> tuple[vetor_externo.Conector, dict]:
    """Monta o conector a partir da linha (RLS já aplicada por `_carregar`), decifrando a credencial só aqui."""
    r = _carregar(cur, cid)
    if r["tipo"] not in vetor_externo.TIPOS_SUPORTADOS:
        raise ErroAPI(
            422, "tipo_sem_conector",
            f"conexão do tipo {r['tipo']!r}; este conector atende {vetor_externo.TIPOS_SUPORTADOS}",
            {"tipo": r["tipo"], "suportados": list(vetor_externo.TIPOS_SUPORTADOS)},
        )
    cabecalhos = None
    if r["tem_credencial"]:
        cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
        bruta = cur.fetchone()["credencial_cifrada"]
        try:
            token = decifrar_com_rotacao(
                credencial_mod.decifrar, bruta, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR
            )
            cabecalhos = {"Authorization": f"Bearer {token}"}
        except Exception:  # noqa: BLE001 — mesma decisão do teste de saúde: nunca quebra a rota
            cabecalhos = None
    return vetor_externo.Conector(tipo=r["tipo"], url=r["url"], cabecalhos=cabecalhos), r


def _erro_do_conector(e: vetor_externo.ErroConector) -> ErroAPI:
    """Falha do serviço de terceiro NUNCA vira 500 nosso: vira 502 com o motivo nomeado (o usuário precisa
    distinguir "o serviço deles está fora" de "a plataforma quebrou")."""
    if e.motivo == "colecao_inexistente":
        return ErroAPI(404, "colecao_inexistente", f"a conexão não publica a coleção {e.detalhe!r}")
    return ErroAPI(502, "servico_externo", f"o serviço externo não atendeu: {e.motivo}",
                   {"motivo": e.motivo, "detalhe": e.detalhe[:400]})


@router.get("", response_model=ConexaoPagina, openapi_extra=LER)
def listar(tipo: str | None = None, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    onde, params = ["true"], []
    if tipo:
        onde.append("c.tipo = %s")
        params.append(tipo)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.conexao c WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(f"{SQL_BASE} WHERE {filtro} ORDER BY lower(c.nome)", params)  # noqa: S608
        itens = [_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/{id}", response_model=Conexao, openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        return _json(_carregar(cur, cid))


@router.get("/{id}/tilejson", openapi_extra=LER)
def tilejson(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """TileJSON 3.0.0 de uma conexão `xyz` (item L6-02-g-pmtiles-xyz-tilejson) — só monta o que a conexão já
    guarda (`app.conexao.ladrilhos.tilejson`), nunca sonda o serviço de novo."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _json(_carregar(cur, cid))
    if r["tipo"] != "xyz":
        raise ErroAPI(
            422, "tipo_sem_tilejson", "TileJSON só existe para conexões do tipo xyz", {"tipo": r["tipo"]}
        )
    return ladrilhos.tilejson(r)


@router.get("/{id}/colecoes", response_model=ColecoesPagina, openapi_extra=LER)
def listar_colecoes(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Coleções que o serviço publica: `wfs:FeatureTypeList` do GetCapabilities (WFS 2.0) ou `GET /collections`
    (OGC API - Features). Resposta em cache curto por (inquilino, conexão)."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    chave = (auth.tenant_id, cid, "colecoes")
    guardado = cache_conexao.obter(chave)
    if guardado is not None:
        return {**guardado, "do_cache": True}
    with db.db(auth.contexto()) as cur:
        conector, _ = _conector(cur, cid, auth)
    try:
        cols = vetor_externo.listar_colecoes(conector)
    except vetor_externo.ErroConector as e:
        raise _erro_do_conector(e) from e
    corpo = {"total": len(cols), "itens": [
        {"nome": c.nome, "titulo": c.titulo, "crs_nativo": c.crs_nativo, "srid_nativo": c.srid_nativo,
         "srid_entregue": c.srid_entregue, "extent_4326": c.extent_4326, "formatos": list(c.formatos)}
        for c in cols
    ]}
    cache_conexao.guardar(chave, corpo)
    return {**corpo, "do_cache": False}


@router.get("/{id}/colecoes/{colecao}/campos", response_model=CamposSaida, openapi_extra=LER)
def campos_da_colecao(id: str, colecao: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Atributos e o tipo que o SERVIÇO declara (`DescribeFeatureType` no WFS, `/queryables` no OGC API). Quando
    o serviço não declara nada, os tipos vêm de uma amostra de uma feição e `origem_do_tipo` diz `amostra` —
    inferido nunca é apresentado como declarado."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    chave = (auth.tenant_id, cid, "campos", colecao)
    guardado = cache_conexao.obter(chave)
    if guardado is not None:
        return {**guardado, "do_cache": True}
    with db.db(auth.contexto()) as cur:
        conector, _ = _conector(cur, cid, auth)
    try:
        col = vetor_externo.colecao_ou_erro(conector, colecao)
        campos, _ = vetor_externo.descrever_campos(conector, col)
    except vetor_externo.ErroConector as e:
        raise _erro_do_conector(e) from e
    normalizados = copia_mod._normalizar_campos(campos)
    corpo = {"colecao": col.nome, "itens": [
        {"nome": c["nome"], "origem": c["origem"], "tipo": c["tipo"], "tipo_declarado": c["tipo_declarado"],
         "origem_do_tipo": c["origem_do_tipo"]}
        for c in normalizados
    ]}
    cache_conexao.guardar(chave, corpo)
    return {**corpo, "do_cache": False}


@router.get("/{id}/colecoes/{colecao}/feicoes", response_model=FeicoesSaida, openapi_extra=LER)
def feicoes_da_colecao(
    id: str, colecao: str, bbox: str | None = None, datahora: str | None = None,
    limite: int = limites.CONEXAO_VETOR_PREVIA_MAX,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Feições ao vivo (modo referenciado), no máximo `CONEXAO_VETOR_PREVIA_MAX` por chamada. `bbox` é
    `minx,miny,maxx,maxy` em graus (CRS84) e `datahora` é o `datetime` do OGC API (instante ou intervalo).
    A resposta traz `numberMatched` (o total que o serviço declara) ao lado de `numberReturned` — sem os dois
    não dá para saber se a página é a coleção inteira."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    limite = max(1, min(limite, limites.CONEXAO_VETOR_PREVIA_MAX))
    caixa = None
    if bbox:
        try:
            caixa = [float(v) for v in bbox.split(",")]
        except ValueError as e:
            raise ErroAPI(422, "bbox_invalido", "bbox deve ser minx,miny,maxx,maxy em graus") from e
        if len(caixa) != 4:
            raise ErroAPI(422, "bbox_invalido", "bbox deve ter exatamente 4 números")
    chave = (auth.tenant_id, cid, "feicoes", colecao, bbox, datahora, limite)
    guardado = cache_conexao.obter(chave)
    if guardado is not None:
        return {**guardado, "do_cache": True}
    with db.db(auth.contexto()) as cur:
        conector, _ = _conector(cur, cid, auth)
    try:
        col = vetor_externo.colecao_ou_erro(conector, colecao)
        formato = vetor_externo._formato_json_wfs(col) if conector.tipo == "wfs" else "application/geo+json"
        if conector.tipo == "wfs" and not formato:
            raise ErroAPI(
                422, "formato_json_indisponivel",
                "este WFS não anuncia nenhum outputFormat JSON; use o modo copiado (job conexao.copiar_vetor), "
                "que converte o GML localmente",
                {"formatos": list(col.formatos)},
            )
        pag = vetor_externo.Paginador(conector, col, bbox=caixa, datahora=datahora,
                                      tam_pagina=limite, limite=limite, formato_json=formato)
        feicoes: list[dict] = []
        for lote in pag.paginas_json():
            feicoes.extend(lote)
    except vetor_externo.ErroConector as e:
        raise _erro_do_conector(e) from e
    corpo = {
        "type": "FeatureCollection", "features": feicoes, "numberReturned": len(feicoes),
        "numberMatched": pag.relatorio.numero_matched, "colecao": col.nome,
        "srid_entregue": col.srid_entregue, "avisos": pag.relatorio.avisos,
    }
    cache_conexao.guardar(chave, corpo)
    return {**corpo, "do_cache": False}


@router.post("", response_model=Conexao, status_code=201, openapi_extra=CRIAR)
def criar(corpo: ConexaoEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    corpo.url = _url_de_planilha(corpo.tipo, corpo.url)
    _url_ok(corpo.url)
    _credencial_de_planilha_ok(corpo.tipo, corpo.credencial)
    _config_ok(corpo.config)
    corpo.config = _config_tiles_ok(corpo.tipo, corpo.url, corpo.config)
    if corpo.tipo == "pmtiles":
        _range_pmtiles_ok(corpo.url)
    credencial_cifrada = credencial_mod.cifrar(corpo.credencial, settings.PLAT_SECRET) if corpo.credencial else None
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.conexao(tenant_id, tipo, modo, nome, url, config, credencial_cifrada, dono_id) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s) RETURNING id",
                (
                    auth.tenant_id, corpo.tipo, corpo.modo, " ".join(corpo.nome.split()), corpo.url,
                    json.dumps(corpo.config, ensure_ascii=False), credencial_cifrada, auth.usuario_id,
                ),
            )
            cid = str(cur.fetchone()["id"])
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe uma conexão com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(
            cur, request, "conexoes/criar", "conexao", cid, {"tipo": corpo.tipo, "nome": corpo.nome, "modo": corpo.modo}
        )
        return _json(_carregar(cur, cid))


@router.patch("/{id}", response_model=Conexao, openapi_extra=EDITAR)
def editar(id: str, corpo: ConexaoEditar, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        campos, params = [], []
        if corpo.nome is not None:
            campos.append("nome = %s")
            params.append(" ".join(corpo.nome.split()))
        url_nova = corpo.url if corpo.url is not None else r["url"]
        if corpo.url is not None:
            corpo.url = _url_de_planilha(r["tipo"], corpo.url)
            url_nova = corpo.url
            _url_ok(corpo.url)
            campos.append("url = %s")
            params.append(corpo.url)
            campos.append("saude = 'nunca_testada'")  # URL mudou: a saúde anterior não vale mais para a nova
        if corpo.modo is not None:
            campos.append("modo = %s")
            params.append(corpo.modo)
        if corpo.config is not None:
            _config_ok(corpo.config)
            config_nova = _config_tiles_ok(r["tipo"], url_nova, corpo.config)
            campos.append("config = %s::jsonb")
            params.append(json.dumps(config_nova, ensure_ascii=False))
        elif corpo.url is not None and r["tipo"] in ("pmtiles", "xyz"):
            # a URL mudou mas o config não veio nesta edição: revalida contra o config já gravado (o
            # `atribuicao`/zoom continuam obrigatórios, e xyz precisa dos marcadores {z}{x}{y} na URL NOVA)
            _config_tiles_ok(r["tipo"], url_nova, r["config"] or {})
        if corpo.url is not None and r["tipo"] == "pmtiles":
            _range_pmtiles_ok(corpo.url)
        if corpo.remover_credencial:
            campos.append("credencial_cifrada = NULL")
        elif corpo.credencial is not None:
            _credencial_de_planilha_ok(r["tipo"], corpo.credencial)
            campos.append("credencial_cifrada = %s")
            params.append(credencial_mod.cifrar(corpo.credencial, settings.PLAT_SECRET))
        if campos:
            try:
                cur.execute(f"UPDATE plat.conexao SET {', '.join(campos)} WHERE id = %s::uuid", (*params, cid))  # noqa: S608
            except psycopg2.errors.UniqueViolation as e:
                raise ErroAPI(409, "nome_existente", "já existe uma conexão com esse nome") from e
            except psycopg2.Error as e:
                raise auth_comum.erro_do_banco(e) from e
            campos_alterados = [c.split(" =")[0] for c in campos]
            # servir a resposta da URL/coleção antiga depois da edição seria mentira, não cache (item L6-02-c)
            cache_conexao.esquecer((auth.tenant_id, cid))
            registrar_evento(cur, request, "conexoes/editar", "conexao", cid, {"campos": campos_alterados})
        return _json(_carregar(cur, cid))


@router.delete("/{id}", status_code=204, openapi_extra=EDITAR)
def apagar(id: str, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        cur.execute("DELETE FROM plat.conexao WHERE id = %s::uuid", (cid,))
        cache_conexao.esquecer((auth.tenant_id, cid))
        registrar_evento(cur, request, "conexoes/apagar", "conexao", cid, {"nome": r["nome"]})


@router.post("/{id}/testar", response_model=ConexaoTeste, openapi_extra=EDITAR)
def testar(id: str, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        url = r["url"]

    # decifra a credencial só em memória, só aqui, e só para autenticar o teste — nunca volta na resposta.
    # google_sheets: a credencial é o JSON da conta de serviço e a autenticação é a troca por access token
    # (item L6-02-i); conta recusada pelo Google vira teste com erro e mensagem em português, nunca exceção.
    cabecalhos = None
    falha_credencial: str | None = None
    if r["tem_credencial"]:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
            bruta = cur.fetchone()["credencial_cifrada"]
        try:
            em_claro = decifrar_com_rotacao(
                credencial_mod.decifrar, bruta, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR
            )
        except Exception:  # noqa: BLE001 — PLAT_SECRET (e ANTERIOR) trocados ou dado corrompido: testa sem
            # credencial, nunca quebra a rota (InvalidTag do AEAD não é ValueError — abrangido de propósito)
            em_claro = None
        try:
            cabecalhos = google_sheets.cabecalhos_auth(r["tipo"], em_claro)
        except google_sheets.ErroGoogleSheets as e:
            falha_credencial = e.detalhe

    if falha_credencial is not None:
        resultado = seguranca.ResultadoBusca(
            ok=False, status=None, mensagem=falha_credencial, url_final=url,
            latencia_ms=0, saltos=0,
        )
    else:
        resultado = seguranca.buscar_seguro(
            url, metodo="GET", timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S,
            timeout_ler=limites.CONEXAO_LER_TIMEOUT_S, cabecalhos=cabecalhos,
        )
    saude = "ok" if resultado.ok else "erro"
    with db.db(auth.contexto()) as cur:
        # plat.conexao_saude_registrar (036) grava saude/saude_mensagem/... E o histórico (item L6-02-l-saude)
        # numa função só, com a poda de 30 linhas — o UPDATE direto de antes nunca alimentava o histórico.
        cur.execute(
            "SELECT plat.conexao_saude_registrar(%s::uuid, %s, %s, %s, %s)",
            (cid, resultado.ok, resultado.status, resultado.mensagem, resultado.latencia_ms),
        )
        cur.execute("SELECT saude_verificada_em FROM plat.conexao WHERE id = %s::uuid", (cid,))
        verificada_em = cur.fetchone()["saude_verificada_em"]
        registrar_evento(
            cur, request, "conexoes/testar", "conexao", cid,
            {"ok": resultado.ok, "status": resultado.status, "mensagem": resultado.mensagem},
        )
    return {
        "ok": resultado.ok, "status": resultado.status, "mensagem": resultado.mensagem,
        "latencia_ms": resultado.latencia_ms, "saude": saude, "saude_verificada_em": iso(verificada_em),
    }


@router.get("/{id}/saude-historico", response_model=SaudeHistoricoPagina, openapi_extra=LER)
def saude_historico(
    id: str, limite: int = HISTORICO_LIMITE_PADRAO, auth: Auth = autenticado(escopo_token="catalogo:ler")
):
    """Últimos testes de saúde da conexão (item L6-02-l-saude), mais recente primeiro; `limite` (padrão 10, teto
    30 — o mesmo teto de guarda de `plat.conexao_saude_historico`) evita que a tela peça mais do que existe."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    limite = max(1, min(limite, HISTORICO_LIMITE_MAX))
    with db.db(auth.contexto()) as cur:
        _carregar(cur, cid)  # 404 se a conexão não existe ou não é visível a este inquilino (RLS)
        cur.execute(
            "SELECT verificada_em, ok, status, mensagem, latencia_ms FROM plat.conexao_saude_historico "
            "WHERE conexao_id = %s::uuid ORDER BY verificada_em DESC LIMIT %s",
            (cid, limite),
        )
        itens = [
            {
                "verificada_em": iso(row["verificada_em"]), "ok": row["ok"], "status": row["status"],
                "mensagem": row["mensagem"], "latencia_ms": row["latencia_ms"],
            }
            for row in cur.fetchall()
        ]
    return {"itens": itens}


@router.post("/{id}/publicar", response_model=ItemSaida, status_code=201, openapi_extra=CRIAR)
def publicar_camada(
    id: str, request: Request, corpo: PublicarCamadaEntrada | None = None,
    auth: Auth = autenticado("conteudo.criar"),
):
    """Cria um item de catálogo (tipo `conexao`, `dados.parametros.conexao_id` apontando para esta linha) com a
    ficha de procedência preenchida do que o SERVIÇO EXTERNO declara agora (item L6-05-proveniencia-camada-
    externa) — nunca um valor padrão; campo que o serviço não declara fica `None` (a tela mostra "não
    registrado"). `creditos` do item recebe a atribuição lida (o mais perto de "legenda" que existe hoje: o
    L6-02-b, que desenha a camada no mapa de verdade, ainda não foi construído)."""
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)

    descoberta = proveniencia.descobrir(r)  # I/O de rede FORA da transação (mesma regra de ContextoJob)
    dados_item = {
        "protocolo": r["tipo"], "url": r["url"], "parametros": {"conexao_id": cid},
        "procedencia": descoberta.procedencia,
    }
    catalogo_tipos.validar("conexao", dados_item)
    catalogo_documento.validar_grafo("conexao", dados_item)
    titulo = ((corpo.titulo if corpo else None) or r["nome"]).strip()[:250]
    atribuicao = (descoberta.atribuicao or "")[:2048] or None
    iid = str(uuid.uuid4())
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT plat.cota_itens(%s) AS cota, (SELECT count(*) FROM plat.item WHERE tenant_id = %s) AS n",
            (auth.tenant_id, auth.tenant_id),
        )
        rc = cur.fetchone()
        if rc["n"] >= rc["cota"]:
            raise ErroAPI(
                413, "cota_itens", f"cota de itens do inquilino esgotada ({rc['cota']})", {"cota": rc["cota"]}
            )
        try:
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, creditos, dono_id, dados, origem, url, "
                "criado_por, modificado_por) "
                "VALUES (%s::uuid, %s, 'conexao', %s, %s, %s, %s, 'referenciado', %s, %s, %s)",
                (
                    iid, auth.tenant_id, titulo, atribuicao, auth.usuario_id, catalogo_comum.jsonb(dados_item),
                    r["url"], auth.usuario_id, auth.usuario_id,
                ),
            )
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(
            cur, request, "conexoes/publicar_camada", "item", iid,
            {"conexao_id": cid, "tipo": r["tipo"], "licenca_declarada": bool(descoberta.procedencia.get("licenca"))},
        )
        return catalogo_comum.item_json(catalogo_comum.item_ou_404(cur, iid), auth)


# ------------------------------------------------------------------ arquivo por URL (item L6-02-h)
def _arquivo_json(r: dict) -> dict:
    return {
        "conexao_id": str(r["conexao_id"]), "formato": r["formato"], "etag": r["etag"],
        "last_modified": r["last_modified"], "sha256": r["sha256"], "bytes": r["bytes"],
        "item_id": str(r["item_id"]) if r["item_id"] else None,
        "importacao_id": str(r["importacao_id"]) if r["importacao_id"] else None,
        "intervalo_s": r["intervalo_s"], "agendado": r["agendado"], "proximo_em": iso(r["proximo_em"]),
        "ultimo_em": iso(r["ultimo_em"]), "ultimo_resultado": r["ultimo_resultado"],
        "ultimo_detalhe": r["ultimo_detalhe"], "sincronizacoes": r["sincronizacoes"], "recargas": r["recargas"],
    }


def _arquivo_estado(cur, cid: str) -> dict:
    cur.execute("SELECT * FROM plat.conexao_arquivo WHERE conexao_id = %s::uuid", (cid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(
            404, "arquivo_nao_configurado",
            "a conexão não está configurada como arquivo por URL; use POST /api/conexoes/{id}/arquivo",
        )
    return r


@router.put("/{id}/arquivo", response_model=ArquivoUrlEstado, openapi_extra=EDITAR)
def arquivo_configurar(id: str, corpo: ArquivoUrlEntrada, request: Request,
                       auth: Auth = autenticado("conteudo.publicar_camada")):
    """Marca a conexão como fonte de arquivo por URL e define o intervalo da atualização agendada (item
    L6-02-h; `google_sheets` entra pelo item L6-02-i — a planilha vira o MESMO CSV por URL). Só faz sentido
    em conexão no modo `copiada`: `referenciada` significa que o dado FICA no serviço de origem, e este
    item copia o arquivo para dentro da plataforma."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        if r["tipo"] not in ("http", "google_sheets") or r["modo"] != "copiada":
            raise ErroAPI(
                422, "conexao_incompativel",
                f"arquivo por URL exige conexão 'http' ou 'google_sheets' no modo 'copiada'; "
                f"esta é {r['tipo']!r}/{r['modo']!r}",
                {"tipo": r["tipo"], "modo": r["modo"]},
            )
        cur.execute("SELECT plat.conexao_arquivo_configurar(%s::uuid, %s, %s)",
                    (cid, corpo.intervalo_s, corpo.agendado))
        registrar_evento(cur, request, "conexoes/sincronizar_arquivo", "conexao", cid,
                         {"acao": "configurar", "intervalo_s": corpo.intervalo_s, "agendado": corpo.agendado})
        return _arquivo_json(_arquivo_estado(cur, cid))


@router.get("/{id}/arquivo", response_model=ArquivoUrlEstado, openapi_extra=LER)
def arquivo_ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Estado da sincronização: formato reconhecido, ETag/Last-Modified guardados, camada gerada, e os dois
    contadores que separam CONFERIR a URL de RECARREGAR o dado (`sincronizacoes` x `recargas`)."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar(cur, cid)
        return _arquivo_json(_arquivo_estado(cur, cid))


@router.post("/{id}/arquivo/sincronizar", response_model=JobCriado, status_code=202, openapi_extra=EDITAR)
def arquivo_sincronizar(id: str, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    """Enfileira uma passagem de sincronização agora. O job é `somente_sistema` de propósito: o privilégio é
    gasto AQUI (o usuário precisa de `conteudo.publicar_camada` e a conexão precisa ser deste inquilino), nunca
    em `POST /api/jobs` com uma URL qualquer no parâmetro."""
    from app.jobs import sistema

    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar(cur, cid)
        _arquivo_estado(cur, cid)
    job_id = sistema.enfileirar(auth.tenant_id, "conexoes.arquivo_sincronizar", {"conexao_id": cid},
                                usuario_id=auth.usuario_id)
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "conexoes/sincronizar_arquivo", "conexao", cid,
                         {"acao": "sincronizar", "job_id": job_id})
    return {"job_id": job_id}


# ------------------------------------------------------------------ conectores vivos (item L6-02-conectores-vivos)
def _camada_json(r: dict) -> dict:
    return {
        "nome": r["nome"], "titulo": r["titulo"], "crs": r["crs"] or [], "extensao": r["extensao"],
        "descoberta_em": iso(r["descoberta_em"]),
    }


@router.post("/{id}/descobrir", response_model=DescobrirResultado, openapi_extra=EDITAR)
def descobrir(id: str, request: Request, auth: Auth = autenticado()):
    """Sonda o serviço agora (`GetCapabilities`/`/collections`/`f=json`, conforme o tipo) e SUBSTITUI a lista
    guardada de camadas (item L6-02-conectores-vivos): a lista de hoje reflete o que o serviço declara HOJE,
    nunca uma mistura com uma descoberta antiga que uma camada tenha sumido do serviço. Sem rede fora de
    `app.conexao.seguranca.buscar_seguro` (mesmo caminho auditado contra SSRF do teste de saúde)."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        conexao = {"tipo": r["tipo"], "url": r["url"]}

    # I/O de rede FORA da transação (mesma regra de `publicar_camada`, mais abaixo neste arquivo)
    resultado = descoberta_mod.descobrir_camadas(conexao)

    if not resultado.ok:
        # protocolo sem descoberta automática (postgres_fdw/s3/http/stac/geoparquet/pmtiles) é erro de
        # PEDIDO (422); serviço fora do ar ou documento ilegível é erro do SERVIÇO EXTERNO (502) — nunca o
        # mesmo código para os dois, senão a tela não sabe se deve reoferecer "tentar de novo".
        codigo = 422 if resultado.mensagem.startswith("protocolo ") else 502
        raise ErroAPI(
            codigo, "descoberta_falhou", resultado.mensagem,
            {"url_sondada": resultado.url_sondada, "protocolo": conexao["tipo"]},
        )

    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)  # relê: a conexão pode ter sido apagada/editada durante a sondagem de rede
        _pode_editar(r, auth)
        cur.execute("DELETE FROM plat.conexao_camada WHERE conexao_id = %s::uuid", (cid,))
        for camada in resultado.camadas:
            cur.execute(
                "INSERT INTO plat.conexao_camada(conexao_id, tenant_id, nome, titulo, crs, extensao) "
                "VALUES (%s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb) "
                "ON CONFLICT (conexao_id, nome) DO UPDATE SET "
                "titulo = EXCLUDED.titulo, crs = EXCLUDED.crs, extensao = EXCLUDED.extensao, descoberta_em = now()",
                (
                    cid, auth.tenant_id, camada.nome, camada.titulo,
                    json.dumps(camada.crs, ensure_ascii=False),
                    json.dumps(camada.extensao, ensure_ascii=False) if camada.extensao is not None else None,
                ),
            )
        registrar_evento(
            cur, request, "conexoes/descobrir", "conexao", cid,
            {"tipo": r["tipo"], "total": len(resultado.camadas), "url_sondada": resultado.url_sondada},
        )
        cur.execute(
            "SELECT nome, titulo, crs, extensao, descoberta_em FROM plat.conexao_camada "
            "WHERE conexao_id = %s::uuid ORDER BY nome", (cid,),
        )
        itens = [_camada_json(row) for row in cur.fetchall()]
    return {
        "ok": True, "mensagem": resultado.mensagem, "url_sondada": resultado.url_sondada,
        "total": len(itens), "itens": itens,
    }


@router.get("/{id}/camadas", response_model=CamadasPagina, openapi_extra=LER)
def camadas(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Lista a última descoberta GUARDADA (sem sondar o serviço de novo); `POST /descobrir` é quem atualiza."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar(cur, cid)  # 404 se a conexão não existe ou não é visível a este inquilino (RLS)
        cur.execute(
            "SELECT nome, titulo, crs, extensao, descoberta_em FROM plat.conexao_camada "
            "WHERE conexao_id = %s::uuid ORDER BY nome", (cid,),
        )
        itens = [_camada_json(row) for row in cur.fetchall()]
    return {"total": len(itens), "itens": itens}
