"""Arquivos/objetos genéricos por inquilino (item L0-11-arquivos-objetos; ADR 0006): `POST /api/arquivos` (corpo
cru, `Content-Type` do arquivo, `?classe=`) grava por streaming com teto de tamanho e multipart real no Garage
quando o corpo passa de `limites.ARQUIVO_BUFFER_UNICO_BYTES`; `GET/DELETE /api/arquivos/{sha256}` leem o metadado
em `plat.arquivo` (RLS: o inquilino da sessão nunca vê o sha256 de outro) e entregam pela API — nunca uma URL do
Garage; `GET /api/arquivos` devolve uso × cota; `GET /api/arquivos/_varredura` roda a varredura de órfãos do
próprio inquilino (não confundir com a varredura de CONTEÚDO abaixo). Isento do limite de corpo padrão
(`app/limite_corpo.py`): a rota aplica o próprio teto em streaming, nunca bufferizando mais que uma parte
(`limites.ARQUIVO_PARTE_BYTES`) de RAM por vez. Item L7-03-b-antivirus-anexos: todo envio passa pela varredura
de conteúdo (`app/varredura_conteudo.py`) antes de tocar o Garage — na 1ª parte (multipart) ou dentro de
`objetos.guardar` (arquivo pequeno, 1 PUT só); 415 `conteudo_recusado` quando os bytes não batem com o
`Content-Type` declarado."""

import re

from fastapi import APIRouter, Request, Response

from app import db, limites, objetos, varredura_conteudo
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.ingestao.formatos import ZipSuspeito
from app.uploads import zip_remoto

router = APIRouter(tags=["arquivos"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}
CLASSE = re.compile(r"^[a-z0-9_]{1,40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _classe_ok(classe: str) -> str:
    if not CLASSE.match(classe):
        raise ErroAPI(422, "validacao", "classe fora do padrão ^[a-z0-9_]{1,40}$", {"campo": "classe"})
    return classe


def _sha256_ok(sha256: str) -> str:
    if not SHA256.match(sha256):
        raise ErroAPI(422, "validacao", "sha256 fora do padrão (64 hex)", {"campo": "sha256"})
    return sha256


def _recusar(
    request: Request, ctx, e: varredura_conteudo.ConteudoRecusado, classe: str, content_type: str, dados
) -> ErroAPI:
    """Registra a recusa na trilha (`arquivos/conteudo_recusado` ou `arquivos/quarentena` quando é o antivírus)
    em transação PRÓPRIA (mesmo padrão de app/acervo/rotas.py::_recusar_pii: levantar dentro do `with` faria
    rollback do evento) e devolve o 415 para o chamador levantar. Nunca grava o conteúdo: a quarentena É o
    registro (sha256 + assinatura + quem/quando/de onde)."""
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
def uso(auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT cota_bytes FROM plat.tenant WHERE id = %s", (auth.tenant_id,))
        cota = cur.fetchone()["cota_bytes"]
    return {"bytes_usados": objetos.uso(auth.tenant_slug), "cota_bytes": cota}


@router.post("/api/arquivos", status_code=201, openapi_extra={"x-auth": "T", "x-privilegio": "proprio"})
async def enviar(request: Request, classe: str = "objeto", auth: Auth = autenticado(escopo_token="admin:inquilino")):
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
    except varredura_conteudo.ConteudoRecusado as e:
        raise _recusar(request, ctx, e, classe, content_type, None) from None
    tamanho_parte = limites.ARQUIVO_PARTE_BYTES
    limite = pol.max_bytes
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > limite:
        # 1 byte acima do plano = 413 sem ler o corpo (o cliente que mente no Content-Length cai no contador abaixo)
        raise ErroAPI(
            413, "arquivo_grande", f"Content-Length {declarado} acima do limite de {limite} bytes da classe {pol.nome}",
            {"maximo_bytes": limite, "classe": pol.nome},
        )
    buffer = bytearray()
    total = 0
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
            if upload_id is None:
                # 1ª parte antes de abrir o multipart: varredura de conteúdo (item L7-03-b) aqui, nunca depois —
                # um arquivo grande recusado não chega a gastar upload multipart no Garage
                try:
                    objetos.escanear_cabecalho(bytes(buffer), content_type)
                except objetos.ConteudoRecusado as e:
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
                with db.db(ctx) as cur:
                    etag = objetos.parte_enviar(cur, upload_id, numero, bytes(buffer))
                partes.append((numero, etag))
            with db.db(ctx) as cur:
                resultado = objetos.parte_concluir(cur, upload_id, partes)
            if content_type in ("application/zip", "application/vnd.google-earth.kmz"):
                # zip acima do buffer único: as MESMAS regras de zip-bomba, lendo só o diretório central por
                # intervalo (app/uploads/zip_remoto); zip suspeito é apagado do Garage e recusado
                try:
                    zip_remoto.inspecionar_zip_remoto(
                        lambda a, b: objetos.ler_intervalo(resultado["chave"], a, b), int(resultado["bytes"])
                    )
                except ZipSuspeito as e:
                    objetos.apagar(resultado["chave"])
                    rec = varredura_conteudo.ConteudoRecusado(
                        varredura_conteudo.Resultado(False, f"zip suspeito: {e}", "application/zip", "zip_bomba")
                    )
                    raise _recusar(request, ctx, rec, classe, content_type, None) from None
    except objetos.CotaExcedida as e:
        abortar_se_aberto()
        raise ErroAPI(413, "cota_excedida", str(e)) from e
    except objetos.ConteudoRecusado as e:
        # só o caminho de 1 PUT (upload_id is None) chega aqui vindo de escanear/pos_processar: o caminho
        # multipart já escaneou a 1ª parte acima, antes de abrir o upload
        abortar_se_aberto()
        raise _recusar(request, ctx, e, classe, content_type, bytes(buffer)) from None
    except Exception:
        abortar_se_aberto()
        raise
    return resultado


@router.get(
    "/api/arquivos/{sha256}", openapi_extra=X, responses={200: {"content": {"application/octet-stream": {}}}}
)
def ler(sha256: str, classe: str = "objeto", auth: Auth = autenticado()):
    classe, sha256 = _classe_ok(classe), _sha256_ok(sha256)
    with db.db(auth.contexto()) as cur:
        r = _linha(cur, auth.tenant_id, classe, sha256)
    if r is None:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente")
    try:
        dados = objetos.ler(r["chave"])
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente") from e
    # L7-03-a: nunca `inline` para o que não é imagem; e mesmo a imagem vai com CSP `sandbox` + nosniff, então
    # um HTML/SVG servido daqui não executa nada no contexto da plataforma (anexo .html abre como download)
    ct = r["content_type"]
    ext = objetos.EXTENSOES.get(ct, "bin")
    disposicao = "inline" if ct in varredura_conteudo.politica(classe).inline else "attachment"
    return Response(
        dados,
        media_type=ct,
        headers={
            "Cache-Control": "private, max-age=60",
            "X-Robots-Tag": "noindex, nofollow",
            "ETag": f'"{sha256}"',
            "Content-Disposition": f'{disposicao}; filename="{sha256}.{ext}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'",
        },
    )


@router.delete("/api/arquivos/{sha256}", status_code=204, response_class=Response, openapi_extra=X)
def apagar(sha256: str, classe: str = "objeto", auth: Auth = autenticado()):
    classe, sha256 = _classe_ok(classe), _sha256_ok(sha256)
    with db.db(auth.contexto()) as cur:
        r = _linha(cur, auth.tenant_id, classe, sha256)
    if r is None:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente")
    objetos.apagar(r["chave"])
    return Response(status_code=204)
