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
from app.conexao import credencial as credencial_mod
from app.conexao import pgfdw as pgfdw_mod
from app.conexao import proveniencia, seguranca
from app.conexao.modelos import (
    CamadaDaConexaoSaida,
    Conexao,
    ConexaoEditar,
    ConexaoEntrada,
    ConexaoPagina,
    ConexaoTeste,
    PublicarCamadaEntrada,
    PublicarEmMassaEntrada,
    PublicarEmMassaSaida,
    SaudeHistoricoPagina,
    TabelasExternasSaida,
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


def _url_ok(url: str, tipo: str = "") -> None:
    """Recusa SSRF já na entrada (criar/editar), não só no teste de saúde: uma conexão nunca fica registrada
    com URL que o proxy jamais poderia buscar. `postgres_fdw` (item L0-04-i-fonte-registrada) não é HTTP: a
    URL é `postgres://host:porta/banco` e passa por `pgfdw.validar_alvo` (lista explícita de banco proibido +
    IP em categoria bloqueada), nunca por `seguranca.validar_url` (que recusaria qualquer coisa fora de
    http/https já no esquema)."""
    if tipo == "postgres_fdw":
        try:
            host, porta, banco = pgfdw_mod.alvo_da_url(url)
            pgfdw_mod.validar_alvo(host, porta, banco)
        except (pgfdw_mod.ErroAlvoProibido, ValueError) as e:
            motivo = e.motivo if isinstance(e, pgfdw_mod.ErroAlvoProibido) else "url_malformada"
            raise ErroAPI(422, "url_insegura", f"URL recusada: {motivo}", {"motivo": motivo}) from e
        return
    try:
        seguranca.validar_url(url)
    except seguranca.ErroURLInsegura as e:
        raise ErroAPI(422, "url_insegura", f"URL recusada: {e.motivo}", {"motivo": e.motivo}) from e


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


@router.post("", response_model=Conexao, status_code=201, openapi_extra=CRIAR)
def criar(corpo: ConexaoEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    _url_ok(corpo.url, corpo.tipo)
    _config_ok(corpo.config)
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
        if corpo.url is not None:
            _url_ok(corpo.url, r["tipo"])
            campos.append("url = %s")
            params.append(corpo.url)
            campos.append("saude = 'nunca_testada'")  # URL mudou: a saúde anterior não vale mais para a nova
        if corpo.modo is not None:
            campos.append("modo = %s")
            params.append(corpo.modo)
        if corpo.config is not None:
            _config_ok(corpo.config)
            campos.append("config = %s::jsonb")
            params.append(json.dumps(corpo.config, ensure_ascii=False))
        if corpo.remover_credencial:
            campos.append("credencial_cifrada = NULL")
        elif corpo.credencial is not None:
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
            registrar_evento(cur, request, "conexoes/editar", "conexao", cid, {"campos": campos_alterados})
        return _json(_carregar(cur, cid))


@router.delete("/{id}", status_code=204, openapi_extra=EDITAR)
def apagar(id: str, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        cur.execute("DELETE FROM plat.conexao WHERE id = %s::uuid", (cid,))
        registrar_evento(cur, request, "conexoes/apagar", "conexao", cid, {"nome": r["nome"]})


@router.post("/{id}/testar", response_model=ConexaoTeste, openapi_extra=EDITAR)
def testar(id: str, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        url = r["url"]

    # decifra a credencial só em memória, só aqui, e só para autenticar o teste — nunca volta na resposta
    senha_ou_token = None
    if r["tem_credencial"]:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
            bruta = cur.fetchone()["credencial_cifrada"]
        try:
            # dupla-chave de 24 h da rotação de PLAT_SECRET (item L7-19): a credencial cifrada antes da troca
            # ainda decifra com o valor anterior.
            senha_ou_token = decifrar_com_rotacao(
                credencial_mod.decifrar, bruta, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR
            )
        except Exception:  # noqa: BLE001 — PLAT_SECRET (e ANTERIOR) trocados ou dado corrompido: testa sem
            # credencial, nunca quebra a rota (InvalidTag do AEAD não é ValueError — abrangido de propósito)
            senha_ou_token = None

    if r["tipo"] == "postgres_fdw":
        host, porta, banco = pgfdw_mod.alvo_da_url(url)
        alvo = pgfdw_mod.AlvoPg(
            host=host, porta=porta, banco=banco, usuario=(r["config"] or {}).get("usuario", ""),
            schema_remoto=(r["config"] or {}).get("schema_remoto", "public"),
        )
        resultado = pgfdw_mod.testar_e_medir(alvo, senha_ou_token or "")
    else:
        cabecalhos = {"Authorization": f"Bearer {senha_ou_token}"} if senha_ou_token else None
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


# ---------------------------------------------------------------------------------------------------------
# item L0-04-i-fonte-registrada: conector postgres_fdw ("fonte de dado registrada" — o "data store item" da
# Esri 11.4 / o "store" do GeoServer, restrito ao Postgres/PostGIS externo). As três rotas abaixo só existem
# para `tipo == "postgres_fdw"`; qualquer outro tipo devolve 422 `tipo_nao_suportado`.


def _alvo_pg(r: dict, schema_remoto: str) -> "pgfdw_mod.AlvoPg":
    if r["tipo"] != "postgres_fdw":
        raise ErroAPI(422, "tipo_nao_suportado", "esta operação só existe para conexões do tipo postgres_fdw")
    host, porta, banco = pgfdw_mod.alvo_da_url(r["url"])
    return pgfdw_mod.AlvoPg(
        host=host, porta=porta, banco=banco, usuario=(r["config"] or {}).get("usuario", ""),
        schema_remoto=schema_remoto,
    )


def _decifrar_senha(cur, cid: str) -> str:
    cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
    bruta = cur.fetchone()["credencial_cifrada"]
    if not bruta:
        return ""
    try:
        return credencial_mod.decifrar(bruta, settings.PLAT_SECRET)
    except ValueError:
        return ""  # PLAT_SECRET trocado ou dado corrompido: tenta sem credencial, nunca quebra a rota


def _marcar_saude(cur, cid: str, ok: bool, mensagem: str) -> None:
    """Mesma função SECURITY DEFINER de L6-02-l (036) — o teste postgres_fdw grava saúde/histórico igual ao
    teste HTTP; é essa gravação que faz `GET /{id}/camadas` (abaixo) mostrar "fonte_indisponivel" depois de
    uma queda, sem apagar nada do catálogo."""
    cur.execute("SELECT plat.conexao_saude_registrar(%s::uuid, %s, %s, %s, %s)", (cid, ok, None, mensagem, None))


@router.get("/{id}/tabelas", response_model=TabelasExternasSaida, openapi_extra=LER)
def tabelas_externas(id: str, schema_remoto: str = "public", auth: Auth = autenticado()):
    """Lista as tabelas base do schema `schema_remoto` do Postgres do cliente (via `pg_catalog`, nunca
    copiando dado). Conexão fora do ar vira 503 `fonte_indisponivel` (a conexão em si continua registrada;
    nada é apagado)."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        senha = _decifrar_senha(cur, cid)
    if not pgfdw_mod.identificador_ok(schema_remoto):
        raise ErroAPI(422, "schema_invalido", "nome de schema remoto inválido")
    alvo = _alvo_pg(r, schema_remoto)
    try:
        itens = pgfdw_mod.listar_tabelas(alvo, senha)
    except pgfdw_mod.ErroFonteIndisponivel as e:
        with db.db(auth.contexto()) as cur:
            _marcar_saude(cur, cid, False, e.motivo)
        raise ErroAPI(503, "fonte_indisponivel", f"não foi possível conectar à fonte: {e.motivo}") from e
    except pgfdw_mod.ErroAlvoProibido as e:
        raise ErroAPI(422, "alvo_proibido", f"alvo recusado: {e.motivo}", {"motivo": e.motivo}) from e
    with db.db(auth.contexto()) as cur:
        _marcar_saude(cur, cid, True, f"{len(itens)} tabelas listadas")
    return {"schema_remoto": schema_remoto, "itens": itens}


@router.post("/{id}/publicar-em-massa", response_model=PublicarEmMassaSaida, status_code=201, openapi_extra=CRIAR)
def publicar_em_massa(
    id: str, corpo: PublicarEmMassaEntrada, request: Request, auth: Auth = autenticado("conteudo.criar"),
):
    """"Bulk publish" (Esri) / criar N "stores" (GeoServer) de uma vez: uma camada `camada_vetorial`
    REFERENCIADA por tabela pedida, sem copiar dado — cada uma vira `FOREIGN TABLE` + `VIEW` (com
    `tenant_id`/predicado equivalente a RLS; `plat.conexao_fdw_publicar`, migração 20260907T0148) e um item de
    catálogo. Nome de tabela é validado por identificador ANTES de qualquer SQL (o adversário do item injeta
    no nome da tabela); se a fonte cair NO MEIO do lote, as tabelas já publicadas ficam no catálogo e as
    restantes voltam com `erro: "fonte_indisponivel:..."` no item da lista — a chamada inteira nunca vira 503
    sozinha quando pelo menos uma tabela já foi confirmada (o 503 do portão é para quando a fonte já está fora
    do ar ANTES de qualquer publicação, ver `tabelas_externas` acima e o teste `test_pgfdw.py`)."""
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        senha = _decifrar_senha(cur, cid)
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (auth.tenant_id,))
        slug = cur.fetchone()["slug"]
    if not pgfdw_mod.identificador_ok(corpo.schema_remoto):
        raise ErroAPI(422, "schema_invalido", "nome de schema remoto inválido")
    alvo = _alvo_pg(r, corpo.schema_remoto)

    # geometria de todas as tabelas do schema, numa única leitura (evita 1 round-trip extra por tabela); se a
    # fonte já está fora do ar aqui, NENHUMA tabela foi tocada ainda: 503 limpo, catálogo intocado (portão).
    try:
        geometria_por_tabela = {t["tabela"]: t for t in pgfdw_mod.listar_tabelas(alvo, senha)}
    except pgfdw_mod.ErroFonteIndisponivel as e:
        with db.db(auth.contexto()) as cur:
            _marcar_saude(cur, cid, False, e.motivo)
        raise ErroAPI(503, "fonte_indisponivel", f"não foi possível conectar à fonte: {e.motivo}") from e
    except pgfdw_mod.ErroAlvoProibido as e:
        raise ErroAPI(422, "alvo_proibido", f"alvo recusado: {e.motivo}", {"motivo": e.motivo}) from e

    resultados: list[dict] = []
    fonte_caiu_no_meio = False
    for nome_tabela in corpo.tabelas:
        if fonte_caiu_no_meio:
            resultados.append({"tabela": nome_tabela, "ok": False, "erro": "fonte_indisponivel:conexao_caiu_no_lote"})
            continue
        if not pgfdw_mod.identificador_ok(nome_tabela):
            resultados.append({"tabela": nome_tabela, "ok": False, "erro": "nome_de_tabela_invalido"})
            continue
        try:
            colunas = pgfdw_mod.colunas_da_tabela(alvo, senha, nome_tabela)
        except pgfdw_mod.ErroFonteIndisponivel as e:
            fonte_caiu_no_meio = True
            with db.db(auth.contexto()) as cur:
                _marcar_saude(cur, cid, False, e.motivo)
            resultados.append({"tabela": nome_tabela, "ok": False, "erro": f"fonte_indisponivel:{e.motivo}"})
            continue
        except pgfdw_mod.ErroAlvoProibido as e:
            resultados.append({"tabela": nome_tabela, "ok": False, "erro": e.motivo})
            continue

        info_geom = geometria_por_tabela.get(nome_tabela)
        geometria = pgfdw_mod.geometria_enum(info_geom["geometria_tipo"] if info_geom else None)
        srid = int(info_geom["srid"]) if info_geom and info_geom.get("srid") else 4326  # schema exige srid>=1
                                                                                           # mesmo sem geometria
        campos_schema = [{"nome": c["nome"], "tipo": (c["tipo_pg"] or "")[:64]} for c in colunas]
        dados_item = {
            "schema": f"d_{slug}", "tabela": "",  # preenchidos com o nome REAL logo abaixo (linha_fdw)
            "geometria": geometria, "srid": srid, "campos": campos_schema, "fonte": "referenciada",
            "procedencia": {
                "conexao_id": cid, "protocolo": "postgres_fdw", "banco_remoto": alvo.banco,
                "schema_remoto": corpo.schema_remoto, "tabela_remota": nome_tabela,
                "metodo": "postgres_fdw (foreign table + view sobre tenant_id), sem copiar dado",
            },
        }
        try:
            with db.db(auth.contexto()) as cur:
                cur.execute(
                    "SELECT schema_local, tabela_local FROM plat.conexao_fdw_publicar("
                    "%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
                    (
                        cid, slug, alvo.host, alvo.porta, alvo.banco, alvo.usuario, senha, corpo.schema_remoto,
                        nome_tabela, catalogo_comum.jsonb(colunas), auth.tenant_id,
                    ),
                )
                linha_fdw = cur.fetchone()
        except psycopg2.Error as e:
            erro_bd = auth_comum.erro_do_banco(e).erro
            resultados.append({"tabela": nome_tabela, "ok": False, "erro": f"erro_ao_publicar:{erro_bd}"})
            continue
        dados_item["schema"] = linha_fdw["schema_local"]
        dados_item["tabela"] = linha_fdw["tabela_local"]
        try:
            catalogo_tipos.validar("camada_vetorial", dados_item)
            catalogo_documento.validar_grafo("camada_vetorial", dados_item)
        except ErroAPI as e:
            resultados.append({"tabela": nome_tabela, "ok": False, "erro": f"dados_invalidos:{e.erro}"})
            continue

        iid = str(uuid.uuid4())
        with db.db(auth.contexto()) as cur:
            cur.execute(
                "SELECT plat.cota_itens(%s) AS cota, (SELECT count(*) FROM plat.item WHERE tenant_id = %s) AS n",
                (auth.tenant_id, auth.tenant_id),
            )
            rc = cur.fetchone()
            if rc["n"] >= rc["cota"]:
                resultados.append({"tabela": nome_tabela, "ok": False, "erro": "cota_itens"})
                continue
            try:
                cur.execute(
                    "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, origem, url, "
                    "criado_por, modificado_por) "
                    "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, 'referenciado', NULL, %s, %s)",
                    (
                        # url fica NULL: `plat.item.url` exige http(s) (item_url_check) — a origem real
                        # (postgres://host:porta/banco) já está em `dados.procedencia`, que é onde a tela
                        # de procedência olha (mesmo padrão de proveniencia.py para os outros protocolos)
                        iid, auth.tenant_id, nome_tabela[:250], auth.usuario_id, catalogo_comum.jsonb(dados_item),
                        auth.usuario_id, auth.usuario_id,
                    ),
                )
            except psycopg2.Error as e:
                erro_bd = auth_comum.erro_do_banco(e).erro
                resultados.append({"tabela": nome_tabela, "ok": False, "erro": f"erro_ao_gravar:{erro_bd}"})
                continue
            registrar_evento(
                cur, request, "camadas/importar", "item", iid,
                {"conexao_id": cid, "tabela_remota": nome_tabela, "fonte": "postgres_fdw"},
            )
        resultados.append({"tabela": nome_tabela, "ok": True, "item_id": iid, "erro": None})

    with db.db(auth.contexto()) as cur:
        if not fonte_caiu_no_meio:
            _marcar_saude(cur, cid, True, f"{sum(1 for x in resultados if x['ok'])}/{len(resultados)} publicadas")
        registrar_evento(
            cur, request, "conexoes/publicar_em_massa", "conexao", cid,
            {"tabelas": len(corpo.tabelas), "ok": sum(1 for x in resultados if x["ok"])},
        )
    return {"itens": resultados}


@router.get("/{id}/camadas", response_model=CamadaDaConexaoSaida, openapi_extra=LER)
def camadas_da_conexao(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Camadas de catálogo publicadas a partir desta conexão, com o estado da FONTE (não do item) calculado
    da última verificação de saúde — a camada em si NUNCA some daqui: "fonte_indisponivel" é o estado, não um
    apagamento (portão: "a camada continua no catálogo com estado 'fonte indisponível'")."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        cur.execute(
            "SELECT id, titulo, dados FROM plat.item "
            "WHERE tenant_id = %s AND tipo = 'camada_vetorial' AND dados->'procedencia'->>'conexao_id' = %s "
            "ORDER BY lower(titulo)",
            (auth.tenant_id, cid),
        )
        linhas = cur.fetchall()
    estado_fonte = "fonte_indisponivel" if r["saude"] == "erro" else ("ok" if r["saude"] == "ok" else "nunca_testada")
    itens = [
        {
            "id": str(linha["id"]), "titulo": linha["titulo"], "schema_tabela": linha["dados"]["schema"],
            "tabela": linha["dados"]["tabela"], "estado_fonte": estado_fonte,
        }
        for linha in linhas
    ]
    return {"itens": itens}
