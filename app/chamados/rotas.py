"""Rotas de chamados de suporte (item L7-13-a-chamados; migração 20260908T2230_chamados_suporte.sql).

Lado do CLIENTE (`/api/chamados*`, contexto de inquilino + RLS em plat.chamado*): abrir com captura de tela e
contexto automático, comentar, anexar arquivo, fechar, banner de "o suporte respondeu" e download de anexo. A
captura e os anexos entram por JSON+base64 — o CSRF sob cookie de sessão exige application/json em todo verbo
de escrita (ADR 0002 seção 5.3; mesmo truque da miniatura e do logotipo) — e passam pela prova tipo × conteúdo
do pipeline de upload (`app/uploads/tipos.py::verificar_conteudo`) e pela varredura de cabeçalho
(`app/varredura_conteudo.py::escanear_cabecalho`). A chave do objeto no Garage NUNCA sai de dentro do banco: o
download só existe pela rota desta API, com sessão e RLS — a refutação do item ("ler anexo de chamado alheio
pela URL do objeto") encontra 404 nas duas camadas.

Lado do OPERADOR (`/api/plataforma/chamados*`, só superadmin por sessão): fila de todos os inquilinos, leitura
e resposta por funções SECURITY DEFINER que provam o superadmin pelo hash da sessão (mesmo padrão de
`plat.tenant_listar`, 003) — a RLS por inquilino fica de pé, e o operador passa por cima dela com identidade
provada dentro da função, nunca por GUC. Responder grava a 1ª resposta (base do SLA exibido) e enfileira o
e-mail ao cliente no idioma dele (`app/chamados/correio.py`)."""

from __future__ import annotations

import base64
import binascii
import datetime
import io
import json
import re
import uuid

import psycopg2
from fastapi import APIRouter, Request, Response
from PIL import Image
from pydantic import Field

from app import db, limites, objetos
from app.auth.comum import erro_do_banco, registrar_evento
from app.auth.modelos import Modelo
from app.auth.sessao import Auth, autenticado, iso
from app.chamados import correio
from app.erros import ErroAPI
from app.uploads import tipos as tipos_upload

router = APIRouter(tags=["chamados"])
router_operador = APIRouter(prefix="/api/plataforma/chamados", tags=["chamados"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}
SUPER = {"x-auth": "S", "x-privilegio": "superadmin"}
UTC = datetime.UTC

# transições de estado (hipótese do item: aberto, em análise, aguardando cliente, resolvido, fechado). O cliente
# fecha quando quiser (rota própria); o operador segue este mapa. "resolvido -> em_analise" é a reabertura.
TRANSICOES: dict[str, set[str]] = {
    "aberto": {"em_analise", "aguardando_cliente", "resolvido"},
    "em_analise": {"aguardando_cliente", "resolvido"},
    "aguardando_cliente": {"em_analise", "resolvido"},
    "resolvido": {"fechado", "em_analise"},
    "fechado": set(),
}

ERROS_DO_BANCO = {
    "chamado_inexistente": (404, "chamado inexistente"),
    "anexo_inexistente": (404, "anexo inexistente"),
    "chamado_fechado": (409, "o chamado está fechado"),
}

_SEVERIDADES = "|".join(limites.CHAMADO_SEVERIDADES)
_REQ_ID = re.compile(r"^[0-9a-f]{16}$")
_DATA_URL_PNG = re.compile(r"^data:image/png;base64,([A-Za-z0-9+/=\r\n]+)$")
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"

# anexos aceitos num chamado: os dois tipos de imagem verificados aqui por assinatura e os tipos que o pipeline
# de upload (app/uploads/tipos.py) já prova por conteúdo (zip seguro, cabeçalho, cauda). Um tipo fora desta
# lista é recusado na entrada (422 tipo_desconhecido), nunca "aceito e ignorado".
TIPOS_ANEXO = {"png", "jpeg"} | set(tipos_upload.TIPOS)


def _erro_banco(e: Exception) -> ErroAPI:
    if isinstance(e, psycopg2.errors.RaiseException):
        codigo = (e.diag.message_primary or "").strip()
        if codigo in ERROS_DO_BANCO:
            status, mensagem = ERROS_DO_BANCO[codigo]
            return ErroAPI(status, codigo, mensagem)
    return erro_do_banco(e)


# ---------------------------------------------------------------- modelos
class ChamadoCriar(Modelo):
    titulo: str = Field(min_length=3, max_length=limites.CHAMADO_TITULO_MAX)
    descricao: str = Field(min_length=1, max_length=limites.CHAMADO_DESCRICAO_MAX)
    severidade: str = Field(pattern=f"^({_SEVERIDADES})$")
    contexto: dict = Field(default_factory=dict)
    captura: str | None = Field(default=None, max_length=limites.CHAMADO_CAPTURA_BYTES_MAX * 2)


class ComentarioCriar(Modelo):
    texto: str = Field(min_length=1, max_length=limites.CHAMADO_COMENTARIO_MAX)


class AnexoCriar(Modelo):
    nome: str = Field(min_length=1, max_length=limites.UPLOAD_NOME_MAX)
    tipo: str = Field(min_length=1, max_length=40)
    conteudo: str = Field(min_length=1, max_length=limites.CHAMADO_ANEXO_BYTES_MAX * 2)


class EstadoCriar(Modelo):
    estado: str


# ---------------------------------------------------------------- sanitização do contexto
_CAMPOS_TEXTO = (("tela", 200), ("versao", 40), ("navegador", 300), ("idioma", 10))


def contexto_limpo(ctx: dict) -> dict:
    """O contexto vem do navegador e nunca é confiado: campos conhecidos cortados por teto, req_ids filtrados
    pelo formato real (16 hex, app/log.py::req_id) e a estrutura do DOM reduzida a tag + texto curto. Nada de
    valor de campo de formulário entra aqui (o front não envia; o servidor também descartaria por teto)."""
    if not isinstance(ctx, dict):
        return {}
    saida: dict = {}
    for campo, teto in _CAMPOS_TEXTO:
        v = ctx.get(campo)
        if isinstance(v, str) and v:
            saida[campo] = v[:teto]
    reqs = ctx.get("req_ids")
    if isinstance(reqs, list):
        saida["req_ids"] = [
            r for r in reqs if isinstance(r, str) and _REQ_ID.match(r)
        ][: limites.CHAMADO_REQ_IDS_MAX]
    dom = ctx.get("dom")
    if isinstance(dom, list):
        estrutura = []
        for e in dom[: limites.CHAMADO_DOM_ENTRADAS_MAX]:
            if not isinstance(e, dict):
                continue
            estrutura.append({
                "tag": str(e.get("tag", ""))[:20],
                "texto": str(e.get("texto", ""))[: limites.CHAMADO_DOM_TEXTO_MAX],
            })
        saida["dom"] = estrutura
    while len(json.dumps(saida).encode()) > limites.CHAMADO_CONTEXTO_BYTES_MAX and saida:
        # estourou o teto inteiro: corta a parte maior (dom) primeiro, depois req_ids; o essencial (tela,
        # versão, idioma) sobra por último
        maior = max(saida, key=lambda c: len(json.dumps(saida[c])))
        del saida[maior]
    return saida


def _captura_bytes(captura: str) -> bytes:
    m = _DATA_URL_PNG.match(captura or "")
    if not m:
        raise ErroAPI(422, "captura_invalida", "a captura deve ser um data URL de PNG (data:image/png;base64,…)")
    try:
        dados = base64.b64decode(m.group(1), validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "captura_invalida", "base64 da captura inválido") from e
    if len(dados) > limites.CHAMADO_CAPTURA_BYTES_MAX:
        raise ErroAPI(
            413, "captura_grande",
            f"captura acima do teto desta instalação ({limites.CHAMADO_CAPTURA_BYTES_MAX} bytes)",
        )
    if not dados.startswith(_PNG):
        raise ErroAPI(422, "captura_invalida", "os bytes não provam um PNG (assinatura ausente)")
    # re-encode pelo Pillow (mesma defesa do logotipo e da miniatura): a saída é um PNG novo, sem EXIF/ICC,
    # nunca os bytes originais do cliente
    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
        buffer = io.BytesIO()
        im.convert("RGBA").save(buffer, "PNG")
    except Exception as e:  # noqa: BLE001 — qualquer falha do decodificador é captura inválida
        raise ErroAPI(422, "captura_invalida", "o PNG da captura não decodifica") from e
    return buffer.getvalue()


def _content_type_de(tipo: str) -> str:
    if tipo == "png":
        return "image/png"
    if tipo == "jpeg":
        return "image/jpeg"
    return tipos_upload.TIPOS[tipo].content_type_garagem


def _verificar_anexo(tipo: str, dados: bytes) -> None:
    if tipo not in TIPOS_ANEXO:
        raise ErroAPI(422, "tipo_desconhecido", f"tipo {tipo!r} não aceito em anexo de chamado",
                      {"aceitos": sorted(TIPOS_ANEXO)})
    try:
        # ACHADO L7-13-a (adversário, turno 9): esta chamada entregava só `dados[:65536]` enquanto o teto do
        # anexo é `limites.CHAMADO_ANEXO_BYTES_MAX` (8 MB) — um PNG estruturalmente válido cujo `IEND` termina
        # exatamente no byte 65536 preenche a fatia inteira (a checagem 4, "byte depois do fim do formato",
        # nada vê) e a carga colada depois nunca era examinada por checagem nenhuma. A varredura só enxerga o
        # que o chamador entrega (docstring de app/varredura_conteudo.py): aqui o chamador já tem o corpo
        # inteiro em memória — o teto de 8 MB é conferido em `anexar` antes de chegar aqui —, então entrega o
        # corpo inteiro. A checagem 3 (carga executável) passa a cobrir o anexo todo.
        objetos.escanear_cabecalho(dados, _content_type_de(tipo))
    except objetos.ConteudoRecusado as e:
        raise ErroAPI(415, "conteudo_recusado", f"conteúdo recusado pela varredura: {e.resultado.motivo}") from e
    if tipo == "png" and not dados.startswith(_PNG):
        raise ErroAPI(422, "conteudo_nao_corresponde", "os bytes não provam um PNG")
    if tipo == "jpeg" and not dados.startswith(_JPEG):
        raise ErroAPI(422, "conteudo_nao_corresponde", "os bytes não provam um JPEG")


def _anexo_guardar(cur, auth: Auth, chamado_id: str, corpo: AnexoCriar, dados: bytes) -> tuple[dict, str]:
    """Grava o objeto no Garage e registra a linha do anexo. A PROVA DE TIPO (`tipos_upload.verificar_conteudo`)
    NÃO acontece aqui: ela lê o objeto de volta por outra conexão (`objetos.ler_intervalo` resolve o bucket por
    conta própria) e o bucket que `objetos.guardar` acabou de criar no `cur` só é visível depois do COMMIT —
    quem chama faz a prova fora da transação (rota anexar) e limpa tudo se a prova recusar."""
    resultado = objetos.guardar(cur, "chamado_anexo", dados, _content_type_de(corpo.tipo),
                                usuario_id=auth.usuario_id)
    cur.execute(
        "INSERT INTO plat.chamado_anexo(tenant_id, chamado_id, nome, tipo, bytes, sha256, chave, enviado_por) "
        "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s) RETURNING id",
        (auth.tenant_id, chamado_id, corpo.nome.strip()[:200], corpo.tipo, len(dados), resultado["sha256"],
         resultado["chave"], auth.usuario_id),
    )
    anexo = {"id": str(cur.fetchone()["id"]), "nome": corpo.nome.strip()[:200], "tipo": corpo.tipo,
             "bytes": len(dados), "sha256": resultado["sha256"]}
    return anexo, resultado["chave"]


def _sla(linha: dict) -> dict:
    """Tempo de primeira resposta MEDIDO (aberto_em -> primeira_resposta_em) e o SLA declarado por severidade;
    os dois vão juntos em toda leitura — o número sozinho não diz se está dentro ou fora. L7-22 é quem deve
    tornar o SLA dado medido; enquanto isso o valor declarado viaja com a etiqueta 'declarado'."""
    horas = limites.CHAMADO_SLA_PRIMEIRA_RESPOSTA_HORAS[linha["severidade"]]
    aberto = linha["aberto_em"]
    pr = linha["primeira_resposta_em"]
    fim = pr or datetime.datetime.now(UTC)
    return {
        "primeira_resposta_em": iso(pr) if pr else None,
        "primeira_resposta_horas": round((fim - aberto).total_seconds() / 3600, 2) if pr else None,
        "sla_primeira_resposta_horas": horas,
        "sla_origem": "declarado",
        "sla_dentro": None if pr is None else pr <= aberto + datetime.timedelta(hours=horas),
    }


def _chamado_json(linha: dict, comentarios: int | None = None) -> dict:
    saida = {
        "id": str(linha["id"]), "numero": linha["numero"], "titulo": linha["titulo"],
        "severidade": linha["severidade"], "estado": linha["estado"],
        "aberto_em": iso(linha["aberto_em"]), "atualizado_em": iso(linha["atualizado_em"]),
        **_sla(linha),
    }
    if comentarios is not None:
        saida["comentarios"] = comentarios
    return saida


def _comentario_json(linha: dict) -> dict:
    return {"id": str(linha["id"]), "autor": linha["autor"], "origem": linha["origem"],
            "texto": linha["texto"], "criado_em": iso(linha["criado_em"])}


def _comentario_json_operador(linha: dict) -> dict:
    """As funções SECURITY DEFINER do operador devolvem colunas com prefixo s_ (padrão 003)."""
    return {"id": str(linha["s_id"]), "autor": linha["s_autor"], "origem": linha["s_origem"],
            "texto": linha["s_texto"], "criado_em": iso(linha["s_criado_em"])}


def _anexo_json_operador(linha: dict) -> dict:
    return {"id": str(linha["s_id"]), "nome": linha["s_nome"], "tipo": linha["s_tipo"],
            "bytes": linha["s_bytes"], "sha256": linha["s_sha256"], "criado_em": iso(linha["s_criado_em"])}


def _anexo_json(linha: dict) -> dict:
    return {"id": str(linha["id"]), "nome": linha["nome"], "tipo": linha["tipo"], "bytes": linha["bytes"],
            "sha256": linha["sha256"], "criado_em": iso(linha["criado_em"])}


# ---------------------------------------------------------------- cliente: abertura
@router.get("/api/chamados", openapi_extra=X)
def listar(estado: str | None = None, auth: Auth = autenticado()):
    if estado is not None and estado not in limites.CHAMADO_ESTADOS:
        raise ErroAPI(422, "estado_invalido", "estado fora do vocabulário", {"aceitos": limites.CHAMADO_ESTADOS})
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT c.*, (SELECT count(*) FROM plat.chamado_comentario k WHERE k.chamado_id = c.id) AS comentarios "
            "FROM plat.chamado c WHERE (%s::text IS NULL OR c.estado = %s::text) ORDER BY c.aberto_em DESC LIMIT 200",
            (estado, estado),
        )
        return [_chamado_json(r, r["comentarios"]) for r in cur.fetchall()]


@router.post("/api/chamados", status_code=201, openapi_extra=X)
def abrir(corpo: ChamadoCriar, request: Request, auth: Auth = autenticado()):
    captura = _captura_bytes(corpo.captura) if corpo.captura else None
    contexto = contexto_limpo(corpo.contexto)
    with db.db(auth.contexto()) as cur:
        # a MESMA linha travada serializa duas aberturas concorrentes: o numero é sequencial POR inquilino
        cur.execute("SELECT cota_bytes FROM plat.tenant WHERE id = %s FOR UPDATE", (auth.tenant_id,))
        cur.execute("SELECT coalesce(max(numero), 0) + 1 AS n FROM plat.chamado WHERE tenant_id = %s",
                    (auth.tenant_id,))
        numero = int(cur.fetchone()["n"])
        cur.execute(
            "INSERT INTO plat.chamado(tenant_id, numero, titulo, descricao, severidade, contexto, aberto_por) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING *",
            (auth.tenant_id, numero, corpo.titulo.strip(), corpo.descricao.strip(), corpo.severidade,
             json.dumps(contexto), auth.usuario_id),
        )
        linha = cur.fetchone()
        anexos: list[dict] = []
        if captura is not None:
            resultado = objetos.guardar(cur, "chamado_captura", captura, "image/png", usuario_id=auth.usuario_id)
            cur.execute(
                "INSERT INTO plat.chamado_anexo(tenant_id, chamado_id, nome, tipo, bytes, sha256, chave, "
                "enviado_por) VALUES (%s, %s::uuid, 'captura.png', 'png', %s, %s, %s, %s) RETURNING id",
                (auth.tenant_id, linha["id"], len(captura), resultado["sha256"], resultado["chave"],
                 auth.usuario_id),
            )
            anexos.append({"id": str(cur.fetchone()["id"]), "nome": "captura.png", "tipo": "png",
                           "bytes": len(captura), "sha256": resultado["sha256"]})
        registrar_evento(cur, request, "chamado/abrir", "chamado", linha["id"],
                         {"numero": numero, "severidade": corpo.severidade, "tela": contexto.get("tela"),
                          "com_captura": captura is not None})
    return {**_chamado_json(linha, 0), "descricao": linha["descricao"], "anexos": anexos}


def _chamado_do_inquilino(cur, auth: Auth, id: str, travar: bool = False) -> dict:
    try:
        uid = str(uuid.UUID(str(id)))
    except ValueError:
        raise ErroAPI(404, "chamado_inexistente", "chamado inexistente") from None
    cur.execute(f"SELECT * FROM plat.chamado WHERE id = %s::uuid {'FOR UPDATE' if travar else ''}", (uid,))
    linha = cur.fetchone()
    # RLS deixa passar só linha do inquilino; a linha ausente NUNCA revela que existe em outro inquilino
    if linha is None:
        raise ErroAPI(404, "chamado_inexistente", "chamado inexistente")
    return linha


# ---------------------------------------------------------------- cliente: leitura e participação
@router.get("/api/chamados/banner", openapi_extra=X)
def banner(auth: Auth = autenticado()):
    """Chamados com novidade do suporte desde a última leitura do cliente: resposta nova ou resolvido. É o
    segundo lado da notificação — quem não tem e-mail continua avisado dentro do produto. A rota vem ANTES de
    /api/chamados/{id}: "banner" não pode ser capturado como id."""
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT c.id, c.numero, c.titulo, CASE WHEN EXISTS ("
            "  SELECT 1 FROM plat.chamado_comentario k WHERE k.chamado_id = c.id AND k.origem = 'operador' "
            "  AND k.criado_em > coalesce(c.visto_cliente_em, c.aberto_em)) THEN 'resposta' ELSE 'resolvido' "
            "END AS motivo "
            "FROM plat.chamado c WHERE c.estado <> 'fechado' AND ("
            "  EXISTS (SELECT 1 FROM plat.chamado_comentario k WHERE k.chamado_id = c.id AND k.origem = 'operador' "
            "          AND k.criado_em > coalesce(c.visto_cliente_em, c.aberto_em)) "
            "  OR (c.estado = 'resolvido' AND c.resolvido_em > coalesce(c.visto_cliente_em, c.aberto_em))) "
            "ORDER BY c.atualizado_em DESC LIMIT 20",
        )
        return [{"id": str(r["id"]), "numero": r["numero"], "titulo": r["titulo"], "motivo": r["motivo"]}
                for r in cur.fetchall()]


@router.get("/api/chamados/{id}", openapi_extra=X)
def ver(id: str, auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        linha = _chamado_do_inquilino(cur, auth, id)
        cur.execute(
            "SELECT k.*, u.login AS autor FROM plat.chamado_comentario k JOIN plat.usuario u ON u.id = k.autor_id "
            "WHERE k.chamado_id = %s::uuid ORDER BY k.criado_em",
            (linha["id"],),
        )
        comentarios = [_comentario_json(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM plat.chamado_anexo WHERE chamado_id = %s::uuid ORDER BY criado_em",
                    (linha["id"],))
        anexos = [_anexo_json(r) for r in cur.fetchall()]
        # abrir o chamado é ver o que o suporte postou: zera o banner (visto_cliente_em)
        cur.execute("UPDATE plat.chamado SET visto_cliente_em = now() WHERE id = %s::uuid", (linha["id"],))
    contexto = linha["contexto"] if isinstance(linha["contexto"], dict) else {}
    return {
        **_chamado_json(linha, len(comentarios)), "descricao": linha["descricao"], "contexto": contexto,
        "comentarios_lista": comentarios, "anexos": anexos,
    }


@router.post("/api/chamados/{id}/comentarios", status_code=201, openapi_extra=X)
def comentar(id: str, corpo: ComentarioCriar, request: Request, auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        linha = _chamado_do_inquilino(cur, auth, id, travar=True)
        if linha["estado"] == "fechado":
            raise ErroAPI(409, "chamado_fechado", "o chamado está fechado")
        cur.execute(
            "INSERT INTO plat.chamado_comentario(tenant_id, chamado_id, autor_id, origem, texto) "
            "VALUES (%s, %s::uuid, %s, 'cliente', %s) RETURNING *",
            (auth.tenant_id, linha["id"], auth.usuario_id, corpo.texto.strip()),
        )
        novo = cur.fetchone()
        cur.execute("UPDATE plat.chamado SET atualizado_em = now() WHERE id = %s::uuid", (linha["id"],))
        registrar_evento(cur, request, "chamado/comentar", "chamado", linha["id"], {"numero": linha["numero"]})
    return _comentario_json({**novo, "autor": auth.login})


@router.post("/api/chamados/{id}/anexos", status_code=201, openapi_extra=X)
def anexar(id: str, corpo: AnexoCriar, request: Request, auth: Auth = autenticado()):
    try:
        dados = base64.b64decode(corpo.conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "conteudo_invalido", "base64 do anexo inválido") from e
    if len(dados) > limites.CHAMADO_ANEXO_BYTES_MAX:
        raise ErroAPI(413, "arquivo_grande",
                      f"anexo acima do teto ({limites.CHAMADO_ANEXO_BYTES_MAX} bytes); use o upload retomável")
    _verificar_anexo(corpo.tipo, dados)
    with db.db(auth.contexto()) as cur:
        linha = _chamado_do_inquilino(cur, auth, id, travar=True)
        if linha["estado"] == "fechado":
            raise ErroAPI(409, "chamado_fechado", "o chamado está fechado")
        anexo, chave = _anexo_guardar(cur, auth, linha["id"], corpo, dados)
        cur.execute("UPDATE plat.chamado SET atualizado_em = now() WHERE id = %s::uuid", (linha["id"],))
    # prova de tipo FORA da transação: o bucket e o objeto só são visíveis a outra conexão depois do commit
    try:
        if corpo.tipo not in ("png", "jpeg"):
            tipos_upload.verificar_conteudo(corpo.tipo, chave, len(dados))
    except tipos_upload.ConteudoNaoCorresponde as e:
        with db.db(auth.contexto()) as cur:
            cur.execute("DELETE FROM plat.chamado_anexo WHERE id = %s::uuid AND tenant_id = %s",
                        (anexo["id"], auth.tenant_id))
        objetos.apagar(chave)
        raise ErroAPI(422, "conteudo_nao_corresponde", str(e)) from e
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "chamado/anexar", "chamado", linha["id"],
                         {"numero": linha["numero"], "tipo": corpo.tipo, "bytes": len(dados)})
    return anexo


@router.get("/api/chamados/{id}/anexos/{anexo_id}", openapi_extra=X)
def baixar_anexo(id: str, anexo_id: str, auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        _chamado_do_inquilino(cur, auth, id)
        try:
            aid = str(uuid.UUID(str(anexo_id)))
        except ValueError:
            raise ErroAPI(404, "anexo_inexistente", "anexo inexistente") from None
        cur.execute("SELECT * FROM plat.chamado_anexo WHERE id = %s::uuid AND chamado_id = %s::uuid",
                    (aid, id))
        anexo = cur.fetchone()
        if anexo is None:
            raise ErroAPI(404, "anexo_inexistente", "anexo inexistente")
        chave = anexo["chave"]  # nunca sai daqui para o cliente; só os bytes lidos por cima dela
    try:
        dados = objetos.ler(chave)
    except objetos.ErroGarage as e:
        raise ErroAPI(502, "garage_falhou", f"o armazenamento não devolveu o anexo: {e}") from e
    return Response(
        dados, media_type=_content_type_de(anexo["tipo"]),
        headers={"Content-Disposition": f'inline; filename="{anexo["nome"]}"'},
    )


@router.post("/api/chamados/{id}/fechar", openapi_extra=X)
def fechar(id: str, request: Request, auth: Auth = autenticado()):
    """O cliente fecha o chamado dele, em qualquer estado aberto (o suporte resolve, o cliente decide encerrar).
    Idempotente: fechar duas vezes devolve o chamado fechado, não um erro."""
    with db.db(auth.contexto()) as cur:
        linha = _chamado_do_inquilino(cur, auth, id, travar=True)
        if linha["estado"] != "fechado":
            cur.execute(
                "UPDATE plat.chamado SET estado = 'fechado', fechado_em = now(), fechado_por = %s, "
                "atualizado_em = now() WHERE id = %s::uuid",
                (auth.usuario_id, linha["id"]),
            )
            registrar_evento(cur, request, "chamado/fechar", "chamado", linha["id"],
                             {"numero": linha["numero"]})
    return {"id": str(linha["id"]), "numero": linha["numero"], "estado": "fechado"}


# ---------------------------------------------------------------- operador (superadmin)
@router_operador.get("", openapi_extra=SUPER)
def fila(estado: str | None = None, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    if estado is not None and estado not in limites.CHAMADO_ESTADOS:
        raise ErroAPI(422, "estado_invalido", "estado fora do vocabulário", {"aceitos": limites.CHAMADO_ESTADOS})
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.chamado_fila_operador(%s, %s::text)", (auth.sessao_hash, estado))
            return [{"id": str(r["s_id"]), "tenant_id": r["s_tenant_id"], "tenant_slug": r["s_tenant_slug"],
                     "numero": r["s_numero"], "titulo": r["s_titulo"], "severidade": r["s_severidade"],
                     "estado": r["s_estado"], "aberto_por": r["s_aberto_por"], "aberto_em": iso(r["s_aberto_em"]),
                     **_sla({"severidade": r["s_severidade"], "aberto_em": r["s_aberto_em"],
                             "primeira_resposta_em": r["s_primeira_resposta_em"]}),
                     "atualizado_em": iso(r["s_atualizado_em"])} for r in cur.fetchall()]
    except psycopg2.Error as e:
        raise _erro_banco(e) from e


def _operador_ver(auth: Auth, id: str) -> tuple[dict, list[dict], list[dict]]:
    try:
        uid = str(uuid.UUID(str(id)))
    except ValueError:
        raise ErroAPI(404, "chamado_inexistente", "chamado inexistente") from None
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.chamado_operador_ver(%s, %s::uuid)", (auth.sessao_hash, uid))
            linha = cur.fetchone()
            if linha is None:
                raise ErroAPI(404, "chamado_inexistente", "chamado inexistente")
            cur.execute("SELECT * FROM plat.chamado_operador_comentarios(%s, %s::uuid)",
                        (auth.sessao_hash, uid))
            comentarios = [_comentario_json_operador(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM plat.chamado_operador_anexos(%s, %s::uuid)", (auth.sessao_hash, uid))
            anexos = [_anexo_json_operador(r) for r in cur.fetchall()]
    except psycopg2.Error as e:
        raise _erro_banco(e) from e
    return linha, comentarios, anexos


@router_operador.get("/{id}", openapi_extra=SUPER)
def operador_ver(id: str, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    linha, comentarios, anexos = _operador_ver(auth, id)
    contexto = linha["s_contexto"] if isinstance(linha["s_contexto"], dict) else {}
    return {
        "id": str(linha["s_id"]), "tenant_id": linha["s_tenant_id"], "tenant_slug": linha["s_tenant_slug"],
        "numero": linha["s_numero"], "titulo": linha["s_titulo"], "descricao": linha["s_descricao"],
        "severidade": linha["s_severidade"], "estado": linha["s_estado"], "contexto": contexto,
        "aberto_por": linha["s_aberto_por"], "aberto_por_email": linha["s_aberto_por_email"],
        "aberto_em": iso(linha["s_aberto_em"]),
        **_sla({"severidade": linha["s_severidade"], "aberto_em": linha["s_aberto_em"],
                "primeira_resposta_em": linha["s_primeira_resposta_em"]}),
        "resolvido_em": iso(linha["s_resolvido_em"]) if linha["s_resolvido_em"] else None,
        "fechado_em": iso(linha["s_fechado_em"]) if linha["s_fechado_em"] else None,
        "atualizado_em": iso(linha["s_atualizado_em"]),
        "comentarios_lista": comentarios, "anexos": anexos,
    }


@router_operador.get("/{id}/anexos/{anexo_id}", openapi_extra=SUPER)
def operador_baixar_anexo(id: str, anexo_id: str, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    linha, _com, anexos = _operador_ver(auth, id)
    try:
        aid = str(uuid.UUID(str(anexo_id)))
    except ValueError:
        raise ErroAPI(404, "anexo_inexistente", "anexo inexistente") from None
    if aid not in {a["id"] for a in anexos}:
        raise ErroAPI(404, "anexo_inexistente", "anexo inexistente")
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.chamado_operador_anexo_chave(%s, %s::uuid)",
                        (auth.sessao_hash, aid))
            r = cur.fetchone()
    except psycopg2.Error as e:
        raise _erro_banco(e) from e
    try:
        dados = objetos.ler(r["s_chave"])
    except objetos.ErroGarage as e:
        raise ErroAPI(502, "garage_falhou", f"o armazenamento não devolveu o anexo: {e}") from e
    return Response(dados, media_type=_content_type_de(r["s_tipo"]),
                    headers={"Content-Disposition": f'inline; filename="{r["s_nome"]}"'})


@router_operador.post("/{id}/comentarios", status_code=201, openapi_extra=SUPER)
def operador_responder(id: str, corpo: ComentarioCriar, request: Request,
                       auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    try:
        str(uuid.UUID(str(id)))
    except ValueError:
        raise ErroAPI(404, "chamado_inexistente", "chamado inexistente") from None
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.chamado_operador_responder(%s, %s::uuid, %s, %s)",
                        (auth.sessao_hash, id, corpo.texto.strip(), auth.usuario_id))
            r = cur.fetchone()
    except psycopg2.Error as e:
        raise _erro_banco(e) from e
    correio.notifica_cliente(r["s_tenant_id"], "resposta", r["s_numero"], r["s_titulo"],
                             r["s_aberto_por_email"], r["s_aberto_por_idioma"])
    with db.db(db.Contexto(r["s_tenant_id"], auth.usuario_id, auth.login)) as cur:
        registrar_evento(cur, request, "chamado/responder", "chamado", id, {"numero": r["s_numero"]})
    return {"id": str(id), "numero": r["s_numero"], "estado": r["s_estado"],
            "primeira_resposta_em": iso(r["s_primeira_resposta_em"]) if r["s_primeira_resposta_em"] else None}


@router_operador.post("/{id}/estado", openapi_extra=SUPER)
def operador_estado(id: str, corpo: EstadoCriar, request: Request,
                    auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    if corpo.estado not in limites.CHAMADO_ESTADOS:
        raise ErroAPI(422, "estado_invalido", "estado fora do vocabulário", {"aceitos": limites.CHAMADO_ESTADOS})
    try:
        str(uuid.UUID(str(id)))
    except ValueError:
        raise ErroAPI(404, "chamado_inexistente", "chamado inexistente") from None
    linha, _com, _anx = _operador_ver(auth, id)
    atual = linha["s_estado"]
    if corpo.estado not in TRANSICOES.get(atual, set()):
        raise ErroAPI(409, "transicao_invalida", f"não se passa de {atual!r} para {corpo.estado!r}",
                      {"de": atual, "para": corpo.estado})
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.chamado_operador_estado(%s, %s::uuid, %s::text, %s)",
                        (auth.sessao_hash, id, corpo.estado, auth.usuario_id))
            r = cur.fetchone()
    except psycopg2.Error as e:
        raise _erro_banco(e) from e
    if corpo.estado == "resolvido":
        correio.notifica_cliente(r["s_tenant_id"], "resolvido", r["s_numero"], r["s_titulo"],
                                 r["s_aberto_por_email"], r["s_aberto_por_idioma"])
    with db.db(db.Contexto(r["s_tenant_id"], auth.usuario_id, auth.login)) as cur:
        registrar_evento(cur, request, "chamado/estado", "chamado", id,
                         {"numero": r["s_numero"], "estado": corpo.estado})
    return {"id": str(id), "numero": r["s_numero"], "estado": r["s_estado"],
            "primeira_resposta_em": iso(r["s_primeira_resposta_em"]) if r["s_primeira_resposta_em"] else None}
