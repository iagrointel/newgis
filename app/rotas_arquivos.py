"""Arquivos/objetos genéricos por inquilino (item L0-11-arquivos-objetos; ADR 0006): `POST /api/arquivos` (corpo
cru, `Content-Type` do arquivo, `?classe=`) grava por streaming com teto de tamanho e multipart real no Garage
quando o corpo passa de `limites.ARQUIVO_BUFFER_UNICO_BYTES`; `GET/DELETE /api/arquivos/{sha256}` leem o metadado
em `plat.arquivo` (RLS: o inquilino da sessão nunca vê o sha256 de outro) e entregam pela API — nunca uma URL do
Garage; `GET /api/arquivos` devolve uso × cota; `GET /api/arquivos/_varredura` roda a varredura de órfãos do
próprio inquilino (não confundir com a varredura de CONTEÚDO abaixo). Isento do limite de corpo padrão
(`app/limite_corpo.py`): a rota aplica o próprio teto em streaming, nunca bufferizando mais que uma parte
(`limites.ARQUIVO_PARTE_BYTES`) de RAM por vez.

Item L7-03-b-antivirus-anexos: todo envio passa pela varredura de conteúdo (`app/varredura_conteudo.py`) antes
de tocar o Garage — na 1ª parte (multipart) ou dentro do buffer único (arquivo pequeno, 1 PUT só); 415
`conteudo_recusado` quando os bytes não batem com o `Content-Type` declarado; no caminho multipart cada parte
SEGUINTE também é varrida (busca de carga executável, com emenda entre blocos), então carga colada depois do
cabeçalho não escapa. `GET /api/arquivos/{sha256}` devolve o conteúdo como ANEXO (`Content-Disposition:
attachment`, `X-Content-Type-Options: nosniff`) e com tipo de mídia da lista fechada da instalação: byte
enviado por cliente nunca volta como `text/html`, `image/svg+xml` ou JavaScript (`app/entrega_conteudo.py`).

Item L7-03-a-antivirus-upload (pipeline único; docs/SEGURANCA.md §9): a `classe` do upload decide, ANTES de ler
um byte do corpo, quais `Content-Type` são aceitos e o teto de tamanho (`app/varredura_conteudo.POLITICAS`) — um
`Content-Type` fora da lista da classe recusa com 415 `politica_de_rota` sem gastar leitura de corpo. Com o
arquivo inteiro em mãos (buffer único), SVG sai sanitizado e zip/kmz passam pela regra de zip-bomba
(`varredura_conteudo.pos_processar`); acima do buffer único, a mesma regra de zip-bomba roda no que já foi
gravado, por intervalo (`app/uploads/zip_remoto.py`), e zip suspeito é apagado do Garage. Recusa por este
pipeline vira evento na trilha (`arquivos/conteudo_recusado`, ou `arquivos/quarentena` quando é o antivírus
`clamd` — nunca o conteúdo, só sha256/assinatura/motivo).

Achado do adversário (mesma causa raiz de L0-04-a, handoffs/T4/ADVERSARIO-L0.md): o escopo de token exigido
aqui NÃO é `admin:inquilino` — enviar/baixar/apagar o PRÓPRIO arquivo e ver a própria cota são operações de
conteúdo comuns, cobertas pelo escopo `conteudo:criar` (teto por PRIVILÉGIO `conteudo.criar`, vocabulário em
`app/auth/escopos.py`), não por perfil. `admin:inquilino` só perfil admin consegue emitir
(`app/auth/rotas_tokens.py`), o que deixava upload/download/apagar por token inacessíveis a um editor comum.
`POST /api/arquivos` também cobra `conteudo.criar` na dependência (é criação); `GET /api/arquivos/{sha256}`,
`DELETE /api/arquivos/{sha256}` e `GET /api/arquivos` (uso × cota) não cobram privilégio de sessão — o teto ali
é o mesmo de sempre (RLS por inquilino, `X = {"x-privilegio": "proprio"}`), só o escopo de TOKEN mudou."""

import datetime
import re

from fastapi import APIRouter, Request, Response

from app import db, entrega_conteudo, limites, objetos, objetos_raster, varredura_conteudo
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado, ip_de, sha256_hex
from app.erros import ErroAPI
from app.ingestao.formatos import ZipSuspeito
from app.uploads import zip_remoto

router = APIRouter(tags=["arquivos"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}
CLASSE = re.compile(r"^[a-z0-9_]{1,40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# mesma forma do `location ~ ^/svc/.../cog/...` de deploy/nginx.conf: se as duas divergirem, o nginx entrega
# um caminho que esta rota não sabe autorizar (403) — nunca o contrário (a rota é a mais restritiva das duas)
COG_URI = re.compile(
    r"^/svc/(?P<token>plat_[A-Za-z0-9_-]{20,128})/cog/(?P<slug>[a-z0-9][a-z0-9-]{1,38})/"
    r"(?P<objeto>[0-9A-Za-z][0-9A-Za-z_-]{0,63}/[a-z][a-z0-9_]{0,39}_[0-9a-f]{8}\.[a-z0-9]{1,8})$"
)


def _classe_ok(classe: str) -> str:
    if not CLASSE.match(classe):
        raise ErroAPI(422, "validacao", "classe fora do padrão ^[a-z0-9_]{1,40}$", {"campo": "classe"})
    return classe


def _sha256_ok(sha256: str) -> str:
    if not SHA256.match(sha256):
        raise ErroAPI(422, "validacao", "sha256 fora do padrão (64 hex)", {"campo": "sha256"})
    return sha256


def _recusar(
    request: Request, ctx, e: objetos.ConteudoRecusado, classe: str, content_type: str, dados: bytes | None
) -> ErroAPI:
    """Registra a recusa na trilha (`arquivos/conteudo_recusado`, ou `arquivos/quarentena` quando é o
    antivírus) em transação PRÓPRIA — levantar dentro do `with` do envio faria rollback do evento — e devolve
    o 415 para o chamador levantar. Nunca grava o conteúdo: a quarentena É o registro (sha256 + assinatura +
    quem/quando/de onde, nunca os bytes)."""
    props = varredura_conteudo.propriedades_da_recusa(e, classe, content_type, dados)
    with db.db(ctx) as cur:
        registrar_evento(cur, request, varredura_conteudo.tipo_do_evento(e), "arquivo", props.get("sha256"), props)
    detalhe = {"tipo_detectado": e.resultado.tipo_detectado, "motor": e.resultado.motor}
    if e.resultado.virus:
        detalhe["assinatura"] = e.resultado.virus
    return ErroAPI(415, "conteudo_recusado", str(e), detalhe)


def _linha(cur, tenant_id: int, classe: str, sha256: str) -> dict | None:
    cur.execute(
        "SELECT chave, content_type, bytes FROM plat.arquivo WHERE tenant_id=%s AND classe=%s AND "
        "referencia IS NULL AND sha256=%s AND apagado_em IS NULL",
        (tenant_id, classe, sha256),
    )
    return cur.fetchone()


# ---------------------------------------------------------------- rotas literais ANTES de /{sha256} (ordem de
# registro do FastAPI: um path param casaria com "_varredura" também)
@router.get("/api/arquivos/_varredura", openapi_extra=X)
def varredura(auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        return objetos.varrer_orfaos(cur, auth.tenant_slug)


@router.get("/api/arquivos", openapi_extra=X)
def uso(auth: Auth = autenticado(escopo_token="conteudo:criar")):
    """Uso × cota do balde do inquilino, lido do PRÓPRIO Garage (GetBucketInfo), nas DUAS dimensões que o balde
    tem desde o item L1-01-d: bytes e número de objetos. `cota_bytes` continua no corpo com o mesmo nome e o
    mesmo significado de antes (item L0-11); `objetos_usados`/`cota_objetos` são os campos novos."""
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT cota_bytes, cota_objetos FROM plat.tenant WHERE id = %s", (auth.tenant_id,))
        t = cur.fetchone()
    u = objetos.uso_detalhado(auth.tenant_slug)
    return {
        "bytes_usados": u["bytes_usados"],
        "cota_bytes": t["cota_bytes"],
        "objetos_usados": u["objetos_usados"],
        "cota_objetos": t["cota_objetos"],
    }


@router.get("/api/arquivos/_chave-leitura", openapi_extra={"x-auth": "S", "x-privilegio": "org.integracoes"})
def chave_leitura(auth: Auth = autenticado("org.integracoes", so_sessao=True)):
    """A chave S3 SÓ-LEITURA do balde do inquilino: é o que a conexão S3 do ArcGIS Pro (`Create Cloud Storage
    Connection File`, provedor S3 compatível, endereçamento por caminho) e o TiTiler (`/vsis3`) precisam para ler
    o COG direto do Garage, sem passar byte por esta API. Nunca a chave de escrita — essa só existe dentro do
    processo da API e do worker (ADR 20260908T1255 seção 4). Só sob sessão e com `org.integracoes`: um token de serviço
    não troca a si mesmo por uma credencial de armazenamento."""
    with db.db(auth.contexto()) as cur:
        return objetos_raster.credenciais_leitura(cur)


@router.get(
    "/api/arquivos/_cog/autorizar",
    status_code=204,
    response_class=Response,
    # x-auth "-" é o valor do vocabulário para rota sem credencial nenhuma (app/portal/openapi.py); estava
    # escrito "publico" por engano (confundindo com o valor de x-plat-escopo) e isso fazia
    # tests/unit/test_contrato_guarda.py achar que a rota exigia credencial sem ter Depends(autenticado(...))
    # — ela é pública DE PROPÓSITO (ver docstring abaixo), a autenticação real é o token no X-Original-URI.
    openapi_extra={"x-auth": "-", "x-privilegio": "publico"},
)
def cog_autorizar(request: Request):
    """Subrequisição `auth_request` do bloco `/svc/<token>/cog/<slug>/...` do nginx (deploy/nginx.conf). Recebe o
    caminho original em `X-Original-URI` e responde 204 (o nginx serve a fatia do Garage) ou 403 (não serve).
    Autoriza quando: o caminho está na forma esperada, o token existe, não está revogado nem expirado, e o
    inquilino do token é o dono do `<slug>` do caminho. Nunca diz QUAL das condições falhou — a resposta é a
    mesma 403 para token inexistente e para token de outro inquilino, senão a rota vira oráculo de token.
    É rota pública de propósito: a subrequisição do nginx não carrega cookie nem `Authorization`."""
    uri = (request.headers.get("x-original-uri") or "").split("?")[0]
    m = COG_URI.match(uri)
    if m is None:
        raise ErroAPI(403, "cog_negado", "caminho de COG não autorizado")
    valor = m.group("token")
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.auth_token(%s, %s)", (sha256_hex(valor), ip_de(request)))
        r = cur.fetchone()
    agora = datetime.datetime.now(datetime.UTC)
    if (
        r is None
        or r["revogado_em"] is not None
        or (r["expira_em"] is not None and r["expira_em"] <= agora)
        or r["tenant_slug"] != m.group("slug")
    ):
        raise ErroAPI(403, "cog_negado", "caminho de COG não autorizado")
    # Item de imagem EXCLUÍDO (L1-01-i): nega mesmo quando o nginx já tem a fatia em cache. A auth_request
    # roda a cada pedido (cache ou não), então o 403 aqui barra a fatia sem precisar de PURGE; quando o item
    # volta pela restauração (estado 'ativo' ou linha que não existe mais), o acesso volta do mesmo jeito.
    with db.db() as cur:
        cur.execute(
            "SELECT plat.raster_item_estado_por_item(%s, %s) AS estado",
            (m.group("slug"), m.group("objeto").split("/")[0]),  # objeto = <item_id>/<asset>_<sha8>.<ext>
        )
        estado = cur.fetchone()["estado"]
    if estado == "excluido":
        raise ErroAPI(403, "cog_negado", "caminho de COG não autorizado")
    return Response(status_code=204)


@router.post("/api/arquivos", status_code=201, openapi_extra={"x-auth": "T", "x-privilegio": "conteudo.criar"})
async def enviar(
    request: Request, classe: str = "objeto",
    auth: Auth = autenticado("conteudo.criar", escopo_token="conteudo:criar"),
):
    """Corpo cru (não multipart/form-data: o corpo INTEIRO é o arquivo). Streaming com teto de tamanho; acima de
    `limites.ARQUIVO_BUFFER_UNICO_BYTES` abre multipart real no Garage (contrato `objetos.parte_*`, ADR 0005).
    Só token de serviço (`Authorization: Bearer`), nunca cookie de sessão: o CSRF sob cookie (ADR 0002 seção 5.3)
    exige `application/json` em todo verbo de escrita, e o corpo aqui é o arquivo cru — a mesma razão que já fez
    a miniatura entrar em base64 (`app/catalogo/rotas_miniatura.py`). Um cliente de navegador troca a sessão por
    um token de escopo restrito antes de enviar (rota `POST /api/tokens`, JSON, essa sim sob cookie)."""
    if auth.modo != "token":
        raise ErroAPI(
            403,
            "exige_token",
            "envio de arquivo exige token de serviço (Authorization: Bearer): sob cookie de sessão o corpo "
            "só pode ser application/json (proteção contra CSRF)",
        )
    classe = _classe_ok(classe)
    content_type = (request.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
    ctx = auth.contexto()
    # pipeline único (item L7-03-a): lista de tipos e teto por CLASSE, decididos ANTES de ler um byte do corpo
    try:
        pol = varredura_conteudo.conferir_tipo_na_rota(classe, content_type)
    except objetos.ConteudoRecusado as e:
        raise _recusar(request, ctx, e, classe, content_type, None) from None
    tamanho_parte = limites.ARQUIVO_PARTE_BYTES
    limite = pol.max_bytes
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > limite:
        # 1 byte acima do plano = 413 SEM ler o corpo (o cliente que mente no Content-Length cai no contador
        # abaixo, que para de ler assim que passa do teto — nunca o corpo inteiro)
        raise ErroAPI(
            413, "arquivo_grande",
            f"Content-Length {declarado} acima do limite de {limite} bytes da classe {pol.nome}",
            {"maximo_bytes": limite, "classe": pol.nome},
        )
    buffer = bytearray()
    total = 0
    cauda = b""  # emenda entre partes: um padrão de carga partido na costura entre blocos não escapa
    upload_id: str | None = None
    partes: list[tuple[int, str]] = []
    numero = 1

    def abortar_se_aberto() -> None:
        if upload_id is not None:
            with db.db(ctx) as cur:
                objetos.parte_abortar(cur, upload_id)

    async for pedaco in request.stream():
        if not pedaco:
            continue
        total += len(pedaco)
        if total > limite:
            abortar_se_aberto()
            raise ErroAPI(
                413, "arquivo_grande", f"corpo acima do limite de {limite} bytes da classe {pol.nome}",
                {"maximo_bytes": limite, "classe": pol.nome},
            )
        buffer += pedaco
        if len(buffer) >= tamanho_parte:
            try:
                if upload_id is None:
                    # 1ª parte antes de abrir o multipart: varredura de conteúdo (item L7-03-b) aqui, nunca
                    # depois — um arquivo grande recusado não chega a gastar upload multipart no Garage
                    objetos.escanear_cabecalho(bytes(buffer), content_type)
                    cauda = varredura_conteudo.cauda(bytes(buffer))
                else:
                    # partes SEGUINTES: carga executável colada depois do cabeçalho também recusa o envio
                    cauda = objetos.escanear_continuacao(bytes(buffer), cauda)
            except objetos.ConteudoRecusado as e:
                abortar_se_aberto()
                raise _recusar(request, ctx, e, classe, content_type, bytes(buffer)) from None
            try:
                with db.db(ctx) as cur:
                    if upload_id is None:
                        r = objetos.parte_iniciar(cur, classe, content_type)
                        upload_id = r["upload_id"]
                    etag = objetos.parte_enviar(cur, upload_id, numero, bytes(buffer))
            except Exception:
                abortar_se_aberto()
                raise
            partes.append((numero, etag))
            numero += 1
            buffer.clear()

    if total == 0:
        raise ErroAPI(422, "arquivo_vazio", "corpo vazio")

    try:
        if upload_id is None:
            # nunca abriu multipart: cabe tudo numa parte só, 1 PUT direto (contrato objetos.guardar). A
            # varredura de conteúdo (item L7-03-b) roda AQUI, na borda onde o byte cru do cliente entra —
            # objetos.guardar() não varre (é adaptador de armazenamento genérico, ver seu próprio docstring)
            objetos.escanear_cabecalho(bytes(buffer), content_type)
            # arquivo inteiro em mãos: SVG sai sanitizado, zip/kmz passam pela regra de zip-bomba (L7-03-a)
            dados = varredura_conteudo.pos_processar(bytes(buffer), content_type)
            with db.db(ctx) as cur:
                resultado = objetos.guardar(cur, classe, dados, content_type, usuario_id=auth.usuario_id)
        else:
            if buffer:
                objetos.escanear_continuacao(bytes(buffer), cauda)
                with db.db(ctx) as cur:
                    etag = objetos.parte_enviar(cur, upload_id, numero, bytes(buffer))
                partes.append((numero, etag))
            with db.db(ctx) as cur:
                resultado = objetos.parte_concluir(cur, upload_id, partes)
            if content_type in ("application/zip", "application/vnd.google-earth.kmz"):
                # zip acima do buffer único: as MESMAS regras de zip-bomba, lendo só o diretório central por
                # intervalo (app/uploads/zip_remoto.py); zip suspeito é apagado do Garage e recusado
                try:
                    zip_remoto.inspecionar_zip_remoto(
                        lambda a, b: objetos.ler_intervalo(resultado["chave"], a, b), int(resultado["bytes"])
                    )
                except ZipSuspeito as e:
                    objetos.apagar(resultado["chave"])
                    rec = objetos.ConteudoRecusado(
                        varredura_conteudo.Resultado(False, f"zip suspeito: {e}", "application/zip", "zip_bomba")
                    )
                    raise _recusar(request, ctx, rec, classe, content_type, None) from None
    except objetos.CotaExcedida as e:
        abortar_se_aberto()
        raise ErroAPI(413, "cota_excedida", str(e)) from e
    except objetos.ConteudoRecusado as e:
        # dois caminhos chegam aqui: o de 1 PUT (upload_id is None, varredura do corpo inteiro/pós-processo) e
        # o resto final do multipart (busca de carga executável no último bloco, emendado com a cauda anterior)
        abortar_se_aberto()
        detalhe_dados = bytes(buffer) if upload_id is None else None
        raise _recusar(request, ctx, e, classe, content_type, detalhe_dados) from None
    except Exception:
        abortar_se_aberto()
        raise
    return resultado


@router.get(
    "/api/arquivos/{sha256}", openapi_extra=X, responses={200: {"content": {"application/octet-stream": {}}}}
)
def ler(sha256: str, classe: str = "objeto", auth: Auth = autenticado(escopo_token="conteudo:criar")):
    classe, sha256 = _classe_ok(classe), _sha256_ok(sha256)
    with db.db(auth.contexto()) as cur:
        r = _linha(cur, auth.tenant_id, classe, sha256)
    if r is None:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente")
    try:
        dados = objetos.ler(r["chave"])
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente") from e
    nome = entrega_conteudo.nome_saneado(f"{classe}-{sha256[:16]}", objetos.EXTENSOES.get(r["content_type"], "bin"))
    return Response(
        dados,
        media_type=entrega_conteudo.tipo_de_entrega(r["content_type"]),
        headers=entrega_conteudo.cabecalhos_de_anexo(
            nome,
            {
                "Cache-Control": "private, max-age=60",
                "X-Robots-Tag": "noindex, nofollow",
                "ETag": f'"{sha256}"',
            },
        ),
    )


@router.delete("/api/arquivos/{sha256}", status_code=204, response_class=Response, openapi_extra=X)
def apagar(sha256: str, classe: str = "objeto", auth: Auth = autenticado(escopo_token="conteudo:criar")):
    classe, sha256 = _classe_ok(classe), _sha256_ok(sha256)
    with db.db(auth.contexto()) as cur:
        r = _linha(cur, auth.tenant_id, classe, sha256)
    if r is None:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente")
    objetos.apagar(r["chave"])
    return Response(status_code=204)
