"""Rotas do upload retomável (item L0-04-a-upload-arquivo; ADR 0005 seção 3): `POST /api/uploads` reserva cota
e abre o multipart no Garage; `PUT /api/uploads/{id}/partes/{n}` recebe uma parte (fora de ordem, reenviável);
`POST /api/uploads/{id}/concluir` fecha o multipart, confere sha256/tamanho/tipo×conteúdo e registra o item
`arquivo` no catálogo; `DELETE /api/uploads/{id}` aborta; `GET /api/uploads/{id}` devolve o estado (para a barra
de progresso reconciliar depois de recarregar a página); `GET /api/uploads/tipos` lista o vocabulário aceito.

Só sob TOKEN de serviço (nunca cookie de sessão), na mesma razão de `app.rotas_arquivos`: o corpo de
`PUT .../partes/{n}` é o BYTE CRU da parte, e o CSRF sob cookie (ADR 0002 seção 5.3) exige `application/json`
em todo verbo de escrita — um cliente de navegador troca a sessão por um token de escopo restrito (`POST
/api/tokens`, essa sim sob cookie) antes de começar o envio.

Diferença assumida em relação à hipótese de cota do ADR 0005 seção 3.1 (documentada em detalhe no handoff do
item, seção "cota"): a reserva não usa `tenant.uso_reservado_bytes` (aquela coluna já é o contador de
armazenamento de TABELA da 029_ingestao_vetor.sql, "independente da cota do bucket Garage" — usá-la aqui
colidiria com o significado já em produção); a reserva é a soma de `plat.upload.bytes_declarado` em
estado='iniciado' do inquilino (`plat.upload_reservado_bytes`), somada sob o MESMO `SELECT ... FOR UPDATE` da
linha do tenant que serializa duas reservas concorrentes."""

from __future__ import annotations

import datetime
import hashlib
import uuid

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo import tipos as tipos_item
from app.catalogo.comum import jsonb, registrar_evento
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.uploads import tipos as tipos_upload

router = APIRouter(tags=["uploads"])
X = {"x-auth": "T", "x-privilegio": "conteudo.criar"}
UTC = datetime.UTC


def _exige_token(auth: Auth) -> None:
    if auth.modo != "token":
        raise ErroAPI(
            403,
            "exige_token",
            "envio por partes exige token de serviço (Authorization: Bearer): sob cookie de sessão o corpo só "
            "pode ser application/json (proteção contra CSRF)",
        )


class UploadCriar(Modelo):
    nome: str = Field(min_length=1, max_length=limites.UPLOAD_NOME_MAX)
    bytes: int = Field(gt=0)
    tipo_declarado: str = Field(min_length=1, max_length=40)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ConcluirEntrada(Modelo):
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


def _upload_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "nome": r["nome"], "bytes_declarado": r["bytes_declarado"],
        "tipo_declarado": r["tipo_declarado"], "sha256_declarado": r["sha256_declarado"],
        "parte_bytes": r["parte_bytes"], "partes_total": r["partes_total"], "estado": r["estado"],
        "arquivo_id": str(r["arquivo_id"]) if r["arquivo_id"] else None,
        "criado_em": iso(r["criado_em"]), "atualizado_em": iso(r["atualizado_em"]),
        "expira_em": iso(r["expira_em"]), "concluido_em": iso(r["concluido_em"]),
    }


def _carregar(cur, auth: Auth, upload_id: str) -> dict:
    try:
        uid = str(uuid.UUID(str(upload_id)))
    except ValueError:
        raise ErroAPI(404, "upload_inexistente", "upload inexistente") from None
    cur.execute("SELECT * FROM plat.upload WHERE id = %s::uuid", (uid,))
    r = cur.fetchone()
    # mesma regra dos itens (ADR 0004): upload de outro usuário do MESMO inquilino nunca revela que existe
    if r is None or r["usuario_id"] != auth.usuario_id:
        raise ErroAPI(404, "upload_inexistente", "upload inexistente")
    return r


def _criar_item_arquivo(cur, auth: Auth, nome_original: str, resultado: dict) -> str:
    """INSERT mínimo de `plat.item` tipo `arquivo` (ADR 0004; o mesmo schema que `POST /api/itens` valida) —
    sem os campos de organização (pasta/categorias/cota_itens) daquela rota genérica: o arquivo recém-chegado
    nasce na raiz do inquilino, como qualquer objeto de `POST /api/arquivos` + `POST /api/itens` faria hoje em
    dois passos; aqui os dois passos viram um."""
    dados = {
        "chave": resultado["chave"], "sha256": resultado["sha256"], "bytes": resultado["bytes"],
        "content_type": resultado["content_type"], "nome_original": nome_original[:255],
    }
    tipos_item.validar("arquivo", dados)
    iid = str(uuid.uuid4())
    titulo = nome_original.strip()[:250] or "arquivo"
    cur.execute(
        "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
        "modificado_por) VALUES (%s::uuid, %s, 'arquivo', %s, %s, %s, %s, %s, %s)",
        (iid, auth.tenant_id, titulo, auth.usuario_id, jsonb(dados), resultado["bytes"], auth.usuario_id,
         auth.usuario_id),
    )
    return iid


@router.get("/api/uploads/tipos", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def tipos_aceitos():
    return [{"tipo": t.nome, "extensoes": list(t.extensoes), "rotulo": t.rotulo} for t in tipos_upload.TIPOS.values()]


@router.post("/api/uploads", status_code=201, openapi_extra=X)
def iniciar(corpo: UploadCriar, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if corpo.bytes > limites.UPLOAD_BYTES_MAX:
        raise ErroAPI(
            413, "arquivo_grande",
            f"tamanho declarado ({corpo.bytes} bytes) acima do máximo desta instalação "
            f"({limites.UPLOAD_BYTES_MAX} bytes)",
            {"maximo_bytes": limites.UPLOAD_BYTES_MAX},
        )
    tipo = tipos_upload.TIPOS.get(corpo.tipo_declarado)
    if tipo is None:
        raise ErroAPI(
            422, "tipo_desconhecido", f"tipo declarado {corpo.tipo_declarado!r} não reconhecido nesta instalação",
            {"aceitos": sorted(tipos_upload.TIPOS)},
        )
    partes_total = -(-corpo.bytes // limites.UPLOAD_PARTE_BYTES)  # ceil
    expira_em = datetime.datetime.now(UTC) + datetime.timedelta(hours=limites.UPLOAD_EXPIRA_HORAS)
    with db.db(auth.contexto()) as cur:
        # a MESMA linha travada serializa duas reservas concorrentes do mesmo inquilino (refutação "duas sessões
        # subindo o mesmo uploadId" começa aqui: a 2ª reserva só lê depois da 1ª commitar ou desistir)
        cur.execute("SELECT cota_bytes FROM plat.tenant WHERE id = %s FOR UPDATE", (auth.tenant_id,))
        linha_tenant = cur.fetchone()
        if linha_tenant is None:  # pragma: no cover — defensivo; auth já garante tenant existente
            raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
        cota = int(linha_tenant["cota_bytes"])
        usado = objetos.uso(auth.tenant_slug)
        cur.execute("SELECT plat.upload_reservado_bytes(%s) AS r", (auth.tenant_id,))
        reservado = int(cur.fetchone()["r"])
        if usado + reservado + corpo.bytes > cota:
            raise ErroAPI(
                413, "cota",
                f"cota de {cota} bytes: {usado} usados + {reservado} reservados + {corpo.bytes} do upload passa "
                "do limite",
                {"cota_bytes": cota, "usado_bytes": usado, "reservado_bytes": reservado},
            )
        r = objetos.parte_iniciar(cur, "arquivo", tipo.content_type_garagem, item_id=None)
        cur.execute(
            "INSERT INTO plat.upload(tenant_id, usuario_id, nome, bytes_declarado, tipo_declarado, "
            "sha256_declarado, upload_s3_id, chave_temp, parte_bytes, partes_total, expira_em) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (auth.tenant_id, auth.usuario_id, corpo.nome, corpo.bytes, corpo.tipo_declarado, corpo.sha256,
             r["upload_id"], r["chave_temp"], limites.UPLOAD_PARTE_BYTES, partes_total, expira_em),
        )
        upload_id = str(cur.fetchone()["id"])
        registrar_evento(cur, request, "uploads/iniciar", "upload", upload_id,
                          {"nome": corpo.nome, "bytes": corpo.bytes, "tipo_declarado": corpo.tipo_declarado})
    return {
        "id": upload_id, "parte_bytes": limites.UPLOAD_PARTE_BYTES, "partes": partes_total,
        "expira_em": iso(expira_em),
    }


@router.get("/api/uploads/{id}", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def ver(id: str, auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        up = _carregar(cur, auth, id)
        cur.execute("SELECT n FROM plat.upload_parte WHERE upload_id = %s::uuid ORDER BY n", (up["id"],))
        recebidas = {r["n"] for r in cur.fetchall()}
    saida = _upload_json(up)
    saida["recebidas"] = sorted(recebidas)
    saida["faltam"] = [i for i in range(1, up["partes_total"] + 1) if i not in recebidas]
    return saida


@router.put("/api/uploads/{id}/partes/{n}", openapi_extra=X)
async def enviar_parte(id: str, n: int, request: Request, auth: Auth = autenticado()):
    _exige_token(auth)
    if n < 1:
        raise ErroAPI(422, "parte_invalida", "número de parte deve ser >= 1", {"n": n})
    with db.db(auth.contexto()) as cur:
        up = _carregar(cur, auth, id)
    if up["estado"] != "iniciado":
        raise ErroAPI(409, "estado_invalido", f"upload em estado {up['estado']!r}; esperava 'iniciado'")
    if n > up["partes_total"]:
        raise ErroAPI(422, "parte_invalida", f"parte {n} além do total ({up['partes_total']})", {"n": n})
    esperado = (
        up["parte_bytes"] if n < up["partes_total"]
        else up["bytes_declarado"] - up["parte_bytes"] * (up["partes_total"] - 1)
    )
    content_length = request.headers.get("content-length")
    if content_length is None:
        raise ErroAPI(411, "content_length_obrigatorio", "Content-Length é obrigatório em PUT .../partes/{n}")
    try:
        declarado = int(content_length)
    except ValueError:
        raise ErroAPI(422, "content_length_invalido", "Content-Length não é um inteiro") from None
    if declarado != esperado:
        raise ErroAPI(
            422, "tamanho_parte_invalido",
            f"parte {n}: Content-Length {declarado} diferente do esperado ({esperado} bytes)",
            {"esperado": esperado, "recebido": declarado},
        )
    dados = bytearray()
    async for pedaco in request.stream():
        dados += pedaco
        if len(dados) > esperado:
            raise ErroAPI(
                422, "tamanho_parte_invalido", f"parte {n}: corpo maior que o Content-Length declarado",
                {"esperado": esperado},
            )
    if len(dados) != esperado:
        raise ErroAPI(
            422, "tamanho_parte_invalido", f"parte {n}: recebido {len(dados)} bytes, esperado {esperado}",
            {"esperado": esperado, "recebido": len(dados)},
        )
    sha_calculado = hashlib.sha256(dados).hexdigest()
    sha_header = (request.headers.get("x-parte-sha256") or "").strip().lower()
    if sha_header and sha_header != sha_calculado:
        raise ErroAPI(
            422, "parte_sha256_divergente", f"parte {n}: X-Parte-SHA256 não bate com o conteúdo recebido",
        )
    with db.db(auth.contexto()) as cur:
        # relê sob a MESMA conexão: o estado pode ter mudado entre a checagem acima e o corpo ter terminado de
        # chegar (upload grande, corpo lento) — nunca grava parte de upload já concluído/abortado
        up = _carregar(cur, auth, id)
        if up["estado"] != "iniciado":
            raise ErroAPI(409, "estado_invalido", f"upload em estado {up['estado']!r}; esperava 'iniciado'")
        etag = objetos.parte_enviar(cur, up["upload_s3_id"], n, bytes(dados))
        cur.execute(
            "INSERT INTO plat.upload_parte(upload_id, n, bytes, etag, sha256) VALUES (%s::uuid,%s,%s,%s,%s) "
            "ON CONFLICT (upload_id, n) DO UPDATE SET bytes = EXCLUDED.bytes, etag = EXCLUDED.etag, "
            "sha256 = EXCLUDED.sha256, recebida_em = now()",
            (id, n, len(dados), etag, sha_calculado),
        )
        cur.execute("UPDATE plat.upload SET atualizado_em = now() WHERE id = %s::uuid", (id,))
        cur.execute("SELECT n FROM plat.upload_parte WHERE upload_id = %s::uuid", (id,))
        recebidas = {r["n"] for r in cur.fetchall()}
    faltam = [i for i in range(1, up["partes_total"] + 1) if i not in recebidas]
    return {"n": n, "recebidas": len(recebidas), "faltam": faltam}


@router.post("/api/uploads/{id}/concluir", status_code=202, openapi_extra=X)
def concluir(id: str, corpo: ConcluirEntrada, request: Request, auth: Auth = autenticado()):
    _exige_token(auth)
    with db.db(auth.contexto()) as cur:
        try:
            uid = str(uuid.UUID(str(id)))
        except ValueError:
            raise ErroAPI(404, "upload_inexistente", "upload inexistente") from None
        # FOR UPDATE serializa dois `concluir` concorrentes do mesmo upload_id (refutação do item): o 2º só lê
        # depois do 1º ter fechado a transação (estado já 'concluido' ou 'abortado')
        cur.execute("SELECT * FROM plat.upload WHERE id = %s::uuid FOR UPDATE", (uid,))
        up = cur.fetchone()
        if up is None or up["usuario_id"] != auth.usuario_id:
            raise ErroAPI(404, "upload_inexistente", "upload inexistente")
        if up["estado"] == "concluido":
            raise ErroAPI(
                409, "ja_concluido", "upload já concluído", {"arquivo_id": str(up["arquivo_id"])},
            )
        if up["estado"] != "iniciado":
            raise ErroAPI(409, "estado_invalido", f"upload em estado {up['estado']!r}; esperava 'iniciado'")

        cur.execute("SELECT n, etag FROM plat.upload_parte WHERE upload_id = %s::uuid ORDER BY n", (uid,))
        partes = cur.fetchall()
        recebidas = {p["n"] for p in partes}
        faltam = [i for i in range(1, up["partes_total"] + 1) if i not in recebidas]
        if faltam:
            raise ErroAPI(409, "partes_faltando", "há partes que ainda não chegaram", {"faltam": faltam})

        try:
            resultado = objetos.parte_concluir(cur, up["upload_s3_id"], [(p["n"], p["etag"]) for p in partes])
        except objetos.ErroGarage as e:
            raise ErroAPI(502, "garage_falhou", f"o armazenamento não fechou o upload: {e}") from e

        sha_declarado = corpo.sha256 or up["sha256_declarado"]
        try:
            if sha_declarado and resultado["sha256"] != sha_declarado:
                raise ErroAPI(
                    422, "sha256_divergente",
                    f"sha256 do objeto ({resultado['sha256']}) diferente do declarado ({sha_declarado})",
                )
            if resultado["bytes"] != up["bytes_declarado"]:
                raise ErroAPI(
                    422, "tamanho_divergente",
                    f"tamanho real ({resultado['bytes']} bytes) diferente do declarado ({up['bytes_declarado']} "
                    "bytes)",
                )
            try:
                tipos_upload.verificar_conteudo(up["tipo_declarado"], resultado["chave"], resultado["bytes"])
            except tipos_upload.ConteudoNaoCorresponde as e:
                raise ErroAPI(422, "conteudo_nao_corresponde", str(e)) from e
        except ErroAPI:
            objetos.apagar(resultado["chave"])
            raise

        item_id = _criar_item_arquivo(cur, auth, up["nome"], resultado)
        cur.execute(
            "UPDATE plat.upload SET estado = 'concluido', arquivo_id = %s::uuid, concluido_em = now(), "
            "atualizado_em = now() WHERE id = %s::uuid",
            (item_id, uid),
        )
        registrar_evento(cur, request, "uploads/concluir", "item", item_id,
                          {"upload_id": uid, "bytes": resultado["bytes"], "sha256": resultado["sha256"]})
    return {
        "arquivo_id": item_id, "sha256": resultado["sha256"], "bytes": resultado["bytes"],
        "content_type": resultado["content_type"],
    }


@router.delete("/api/uploads/{id}", status_code=204, response_class=Response, openapi_extra=X)
def abortar(id: str, request: Request, auth: Auth = autenticado()):
    _exige_token(auth)
    with db.db(auth.contexto()) as cur:
        up = _carregar(cur, auth, id)
        if up["estado"] not in ("iniciado",):
            return Response(status_code=204)  # idempotente: já concluído/abortado/expirado não é erro
        try:
            objetos.parte_abortar(cur, up["upload_s3_id"])
        except objetos.UploadInexistente:
            pass
        cur.execute(
            "UPDATE plat.upload SET estado = 'abortado', atualizado_em = now() WHERE id = %s::uuid "
            "AND estado = 'iniciado'",
            (id,),
        )
        registrar_evento(cur, request, "uploads/abortar", "upload", id, {})
    return Response(status_code=204)
