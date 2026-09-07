"""/api/eu: a própria conta (dados, senha, sessões, 2FA, convites, perfil). Tudo sob sessão, exceto GET /api/eu
(S/T). ADR 0002 seções 5.1, 6.3, 7.3, 14.

Item L0-02-g-perfil-usuario (auto-atendimento, distinto do L0-02-f-tela-usuarios que é o ADMIN editando OUTRO
usuário): `PUT /api/eu` ganha idioma_preferido/unidades/formato_data/visibilidade_perfil, sempre pela MESMA
whitelist de `campos_json` que já protegia nome/email — perfil, papel_id, ativo e login continuam fora dela,
então a defesa contra auto-escalada (regra da refutação do item) é o mesmo mecanismo, não um novo. `POST/DELETE
/api/eu/foto` reaproveita o adaptador genérico de arquivo do L0-11 (`app/objetos.py::guardar`, classe
`usuario_foto`) e o MESMO truque de base64 sob JSON que `POST /api/org/logo` já usa (CSRF sob cookie de sessão
exige `application/json` em todo verbo de escrita, ADR 0002 seção 5.3): a imagem é revalidada e REDESENHADA pelo
Pillow (recorte 200×200, sem EXIF/ICC) antes de gravar — nunca os bytes originais do cliente, então um SVG com
script (ou qualquer coisa que não seja PNG/JPEG/GIF/WEBP de verdade) nunca chega a ser interpretado: o Pillow
recusa abrir e a rota devolve 415 antes de qualquer gravação."""

import base64
import binascii
import io
import warnings

import psycopg2
from fastapi import APIRouter, Body, Request, Response
from PIL import Image, ImageOps
from pydantic import Field

from app import db, limites, objetos, senha
from app.auth import totp
from app.auth.comum import campos_json, erro_do_banco, eu_json, registrar_evento
from app.auth.modelos import (
    CodigoEntrada,
    CodigosRecuperacao,
    Convite,
    Eu,
    Iniciar2FA,
    Modelo,
    Saida,
    SenhaCodigoEntrada,
    SenhaEntrada,
    SenhaSoEntrada,
    Sessao,
)
from app.auth.politica import email_permitido, mensagem_da_regra, regra_da_senha
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

router = APIRouter(prefix="/api/eu", tags=["eu"])
S = {"x-auth": "S", "x-privilegio": "proprio"}
_CAMPOS_EU = {"nome", "email", "idioma_preferido", "unidades", "formato_data", "visibilidade_perfil"}
_FORMATOS_FOTO = {"PNG", "JPEG", "GIF", "WEBP"}


def _so_local(auth: Auth) -> None:
    if auth.origem != "local":
        raise ErroAPI(409, "login_externo", "esta conta entra pelo login da organização; senha e 2FA são do provedor")


def _senha_confere(cur, auth: Auth, informada: str, codigo_erro: str = "senha_atual_incorreta") -> str:
    cur.execute("SELECT senha_hash FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
    atual = cur.fetchone()["senha_hash"]
    if not senha.verificar(informada, atual or ""):
        raise ErroAPI(401, codigo_erro, "senha atual incorreta")
    return atual


@router.get(
    "", response_model=Eu, response_model_exclude_unset=True, openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"}
)
def eu(auth: Auth = autenticado(escopo_token=None, permitir_pendencia=True)):
    with db.db(auth.contexto()) as cur:
        return eu_json(cur, auth)


def _opcao_ok(campos: dict, campo: str, opcoes: tuple[str, ...]) -> str | None:
    valor = campos.get(campo)
    if valor is not None and valor not in opcoes:
        raise ErroAPI(422, "validacao", f"{campo} precisa ser um de {list(opcoes)}", {"campo": campo})
    return valor


@router.put("", response_model=Eu, response_model_exclude_unset=True, openapi_extra=S)
def editar_eu(request: Request, corpo: dict = Body(...), auth: Auth = autenticado(so_sessao=True)):
    """Whitelist `_CAMPOS_EU`: perfil, papel_id, ativo e login NUNCA entram aqui (regra da refutação do item
    L0-02-g — o próprio usuário não escala o próprio perfil de acesso nem troca o login pelo PUT de perfil)."""
    campos = campos_json(corpo, _CAMPOS_EU)
    if "email" in campos and campos["email"] is not None and not email_permitido(campos["email"], auth.politica):
        raise ErroAPI(
            422,
            "email_dominio",
            "e-mail fora dos domínios permitidos do inquilino",
            {"dominios": list(auth.politica.dominios_email)},
        )
    nome = (campos.get("nome") or auth.nome).strip()
    if not nome:
        raise ErroAPI(422, "validacao", "nome não pode ser vazio", {"campo": "nome"})
    idioma = _opcao_ok(campos, "idioma_preferido", limites.PERFIL_IDIOMAS)
    unidades = _opcao_ok(campos, "unidades", limites.PERFIL_UNIDADES)
    formato_data = _opcao_ok(campos, "formato_data", limites.PERFIL_FORMATOS_DATA)
    visibilidade = _opcao_ok(campos, "visibilidade_perfil", limites.PERFIL_VISIBILIDADES)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.usuario SET nome = %s, email = CASE WHEN %s THEN %s ELSE email END, "
            "idioma_preferido = CASE WHEN %s THEN %s ELSE idioma_preferido END, "
            "unidades = CASE WHEN %s THEN %s ELSE unidades END, "
            "formato_data = CASE WHEN %s THEN %s ELSE formato_data END, "
            "visibilidade_perfil = CASE WHEN %s THEN %s ELSE visibilidade_perfil END "
            "WHERE id = %s",
            (
                nome[:200],
                "email" in campos, campos.get("email"),
                "idioma_preferido" in campos, idioma,
                "unidades" in campos, unidades,
                "formato_data" in campos, formato_data,
                "visibilidade_perfil" in campos, visibilidade,
                auth.usuario_id,
            ),
        )
        registrar_evento(
            cur, request, "usuarios/atualizar", "usuario", auth.usuario_id, {"campos": sorted(campos), "proprio": True}
        )
        auth.nome = nome
        return eu_json(cur, auth)


# ---------------------------------------------------------------- foto de perfil (reaproveita o L0-11, mesmo
# padrão de app/auth/rotas_org.py::org_logo_enviar/remover)
class FotoEntrada(Modelo):
    conteudo: str = Field(min_length=1, max_length=limites.PERFIL_FOTO_BYTES_MAX * 4 // 3 + 16)


class FotoSaida(Saida):
    foto_url: str | None


def _decodificar_base64_foto(conteudo: str) -> bytes:
    if len(conteudo) * 3 // 4 > limites.PERFIL_FOTO_BYTES_MAX + 4:
        raise ErroAPI(413, "foto_grande", f"foto acima de {limites.PERFIL_FOTO_BYTES_MAX // 1024} KB")
    if conteudo.startswith("data:"):
        conteudo = conteudo.split(",", 1)[-1]
    try:
        dados = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "validacao", "conteudo precisa ser base64 válido", {"campo": "conteudo"}) from e
    if len(dados) > limites.PERFIL_FOTO_BYTES_MAX:
        raise ErroAPI(413, "foto_grande", f"foto acima de {limites.PERFIL_FOTO_BYTES_MAX // 1024} KB")
    return dados


def _normalizar_foto(dados: bytes) -> bytes:
    """Bytes de PNG/JPEG/GIF/WEBP → PNG 200×200 (recorte central, sem letterbox — diferente do contain do
    org_logo: um rosto fica melhor cortado que emoldurado), sem metadado. Um SVG (ou qualquer coisa que não seja
    imagem raster de verdade) nunca abre no Pillow e cai no `except Exception` abaixo → 415, ANTES de qualquer
    gravação: é a defesa contra a refutação do item ("SVG com script como foto")."""
    if len(dados) > limites.PERFIL_FOTO_BYTES_MAX:
        raise ErroAPI(413, "foto_grande", f"foto acima de {limites.PERFIL_FOTO_BYTES_MAX // 1024} KB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(dados))
            formato = (im.format or "").upper()
            if formato not in _FORMATOS_FOTO:
                raise ErroAPI(415, "formato_nao_aceito", "só PNG, JPEG, GIF ou WEBP", {"formato": formato or None})
            largura, altura = im.size
            if largura * altura > limites.PERFIL_FOTO_PIXELS_MAX:
                raise ErroAPI(422, "imagem_grande", "imagem com pixels demais",
                              {"largura": largura, "altura": altura, "maximo_px": limites.PERFIL_FOTO_PIXELS_MAX})
            im.load()
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise ErroAPI(422, "imagem_grande", "imagem com pixels demais",
                      {"maximo_px": limites.PERFIL_FOTO_PIXELS_MAX}) from e
    except ErroAPI:
        raise
    except Exception as e:  # noqa: BLE001 — Pillow não abriu: não é imagem aceita (inclusive SVG)
        raise ErroAPI(415, "formato_nao_aceito", "só PNG, JPEG, GIF ou WEBP", {"motivo": str(e)[:200]}) from e
    lado = limites.PERFIL_FOTO_LADO
    quadro = ImageOps.fit(im, (lado, lado), method=Image.Resampling.LANCZOS)
    saida = io.BytesIO()
    quadro.save(saida, format="PNG", optimize=True)
    return saida.getvalue()


@router.post("/foto", response_model=FotoSaida, openapi_extra=S)
def enviar_foto(corpo: FotoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    dados = _decodificar_base64_foto(corpo.conteudo)
    png = _normalizar_foto(dados)
    with db.db(auth.contexto()) as cur:
        o = objetos.guardar(cur, "usuario_foto", png, "image/png", usuario_id=auth.usuario_id)
        cur.execute("UPDATE plat.usuario SET foto_sha256 = %s WHERE id = %s", (o["sha256"], auth.usuario_id))
        registrar_evento(
            cur, request, "usuarios/foto_enviar", "usuario", auth.usuario_id, {"sha256": o["sha256"], "proprio": True}
        )
    return {"foto_url": f"/api/arquivos/{o['sha256']}?classe=usuario_foto"}


@router.delete("/foto", response_model=FotoSaida, openapi_extra=S)
def remover_foto(request: Request, auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.usuario SET foto_sha256 = NULL WHERE id = %s", (auth.usuario_id,))
        registrar_evento(cur, request, "usuarios/foto_remover", "usuario", auth.usuario_id, {"proprio": True})
    return {"foto_url": None}


@router.put("/senha", status_code=204, response_class=Response, openapi_extra=S)
def trocar_senha(
    corpo: SenhaEntrada, request: Request, auth: Auth = autenticado(so_sessao=True, permitir_pendencia=True)
):
    _so_local(auth)
    regra = regra_da_senha(corpo.nova, auth.politica, auth.login, auth.tenant_slug, auth.nome)
    if regra:
        raise ErroAPI(422, "senha_fraca", mensagem_da_regra(regra, auth.politica), {"regra": regra})
    try:
        with db.db(auth.contexto()) as cur:
            atual = _senha_confere(cur, auth, corpo.atual)
            n = auth.politica.senha_historico
            cur.execute(
                "SELECT senha_hash FROM plat.senha_historico WHERE usuario_id = %s ORDER BY criado_em DESC LIMIT %s",
                (auth.usuario_id, max(n - 1, 0)),
            )
            anteriores = [atual] + [r["senha_hash"] for r in cur.fetchall()] if n > 0 else []
            if any(senha.verificar(corpo.nova, h) for h in anteriores):
                raise ErroAPI(422, "senha_fraca", mensagem_da_regra("historico", auth.politica), {"regra": "historico"})
            cur.execute(
                "UPDATE plat.usuario SET senha_hash = %s, senha_alterada_em = now(), trocar_senha = false "
                "WHERE id = %s",
                (senha.gerar_hash(corpo.nova), auth.usuario_id),
            )
            if n > 0:
                cur.execute(
                    "INSERT INTO plat.senha_historico(usuario_id, senha_hash) VALUES (%s, %s)", (auth.usuario_id, atual)
                )
                cur.execute(
                    "DELETE FROM plat.senha_historico WHERE usuario_id = %s AND id NOT IN "
                    "(SELECT id FROM plat.senha_historico WHERE usuario_id = %s ORDER BY criado_em DESC LIMIT %s)",
                    (auth.usuario_id, auth.usuario_id, n),
                )
            cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, %s)", (auth.usuario_id, auth.sessao_hash))
            registrar_evento(cur, request, "usuarios/trocar_senha", "usuario", auth.usuario_id)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


@router.get("/sessoes", response_model=list[Sessao], openapi_extra=S)
def sessoes(auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT token_hash, criado_em, ultimo_uso, expira_em, ip, agente FROM plat.sessao "
            "WHERE usuario_id = %s ORDER BY criado_em DESC",
            (auth.usuario_id,),
        )
        return [
            {
                "id": r["token_hash"][:12],
                "criado_em": iso(r["criado_em"]),
                "ultimo_uso": iso(r["ultimo_uso"]),
                "expira_em": iso(r["expira_em"]),
                "ip": r["ip"],
                "agente": r["agente"],
                "atual": r["token_hash"] == auth.sessao_hash,
            }
            for r in cur.fetchall()
        ]


@router.delete("/sessoes", status_code=204, response_class=Response, openapi_extra=S)
def encerrar_outras(request: Request, outras: int = 0, auth: Auth = autenticado(so_sessao=True)):
    if outras != 1:
        raise ErroAPI(400, "pedido_invalido", "use ?outras=1 para encerrar as outras sessões")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, %s) AS n", (auth.usuario_id, auth.sessao_hash))
        n = cur.fetchone()["n"]
        registrar_evento(cur, request, "sessoes/revogar", "usuario", auth.usuario_id, {"outras": n})
    return Response(status_code=204)


@router.delete("/sessoes/{id}", status_code=204, response_class=Response, openapi_extra=S)
def encerrar_sessao(id: str, request: Request, auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "DELETE FROM plat.sessao WHERE usuario_id = %s AND left(token_hash, 12) = %s RETURNING token_hash",
            (auth.usuario_id, id[:12]),
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "sessao_inexistente", "sessão inexistente")
        registrar_evento(cur, request, "sessoes/revogar", "sessao", id[:12])
    return Response(status_code=204)


@router.post("/2fa/iniciar", response_model=Iniciar2FA, openapi_extra=S)
def iniciar_2fa(auth: Auth = autenticado(so_sessao=True, permitir_pendencia=True)):
    _so_local(auth)
    if auth.totp_ativo:
        raise ErroAPI(409, "ja_ativo", "o segundo fator já está ligado")
    segredo = totp.gerar_segredo()
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.usuario SET totp_secret = %s, totp_ativo = false, totp_ultimo_passo = NULL WHERE id = %s",
            (totp.cifrar(segredo, settings.PLAT_SECRET), auth.usuario_id),
        )
    uri = totp.uri(segredo, auth.tenant_slug, auth.login)
    return {"segredo": segredo, "uri": uri, "qr_svg": totp.qr_svg(uri)}


@router.post("/2fa/confirmar", response_model=CodigosRecuperacao, openapi_extra=S)
def confirmar_2fa(
    corpo: CodigoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True, permitir_pendencia=True)
):
    _so_local(auth)
    if auth.totp_ativo:
        raise ErroAPI(409, "ja_ativo", "o segundo fator já está ligado")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT totp_secret, totp_ultimo_passo FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
        r = cur.fetchone()
        if not r["totp_secret"]:
            raise ErroAPI(409, "nao_iniciado", "chame /api/eu/2fa/iniciar antes")
        passo = totp.verificar(
            decifrar_com_rotacao(totp.decifrar, r["totp_secret"], settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR),
            corpo.codigo,
            r["totp_ultimo_passo"],
        )
        if passo is None:
            raise ErroAPI(401, "codigo_invalido", "código inválido")
        codigos = totp.codigos_recuperacao()
        cur.execute(
            "UPDATE plat.usuario SET totp_ativo = true, totp_ultimo_passo = %s, codigos_recuperacao = %s WHERE id = %s",
            (passo, [totp.hash_recuperacao(c) for c in codigos], auth.usuario_id),
        )
        registrar_evento(cur, request, "usuarios/2fa_ligar", "usuario", auth.usuario_id)
    return {"codigos_recuperacao": codigos}


@router.post("/2fa/desativar", status_code=204, response_class=Response, openapi_extra=S)
def desativar_2fa(corpo: SenhaCodigoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    _so_local(auth)
    if auth.politica.exigir_2fa:
        raise ErroAPI(409, "2fa_obrigatorio", "o inquilino exige o segundo fator; ele não pode ser desligado")
    if not auth.totp_ativo:
        raise ErroAPI(409, "nao_ativo", "o segundo fator não está ligado")
    with db.db(auth.contexto()) as cur:
        _senha_confere(cur, auth, corpo.senha, "senha_incorreta")
        cur.execute("SELECT totp_secret, totp_ultimo_passo FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
        r = cur.fetchone()
        if (
            totp.verificar(
                decifrar_com_rotacao(
                    totp.decifrar, r["totp_secret"], settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR
                ),
                corpo.codigo,
                r["totp_ultimo_passo"],
            )
            is None
        ):
            raise ErroAPI(401, "codigo_invalido", "código inválido")
        cur.execute(
            "UPDATE plat.usuario SET totp_secret = NULL, totp_ativo = false, totp_ultimo_passo = NULL, "
            "codigos_recuperacao = NULL WHERE id = %s",
            (auth.usuario_id,),
        )
        registrar_evento(cur, request, "usuarios/2fa_desligar", "usuario", auth.usuario_id, {"proprio": True})
    return Response(status_code=204)


@router.post("/2fa/codigos", response_model=CodigosRecuperacao, openapi_extra=S)
def novos_codigos(corpo: SenhaSoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    _so_local(auth)
    if not auth.totp_ativo:
        raise ErroAPI(409, "nao_ativo", "o segundo fator não está ligado")
    codigos = totp.codigos_recuperacao(limites.CODIGOS_RECUPERACAO)
    with db.db(auth.contexto()) as cur:
        _senha_confere(cur, auth, corpo.senha, "senha_incorreta")
        cur.execute(
            "UPDATE plat.usuario SET codigos_recuperacao = %s WHERE id = %s",
            ([totp.hash_recuperacao(c) for c in codigos], auth.usuario_id),
        )
        registrar_evento(cur, request, "usuarios/2fa_codigos", "usuario", auth.usuario_id)
    return {"codigos_recuperacao": codigos}


@router.get("/convites", response_model=list[Convite], openapi_extra=S)
def convites(auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            """
            SELECT g.id, g.nome, m.papel, m.criado_em, c.id AS c_id, c.nome AS c_nome, c.login AS c_login
            FROM plat.grupo_membro m JOIN plat.grupo g ON g.id = m.grupo_id
            LEFT JOIN plat.usuario c ON c.id = m.convidado_por
            WHERE m.usuario_id = %s AND m.estado = 'convidado' ORDER BY m.criado_em DESC""",
            (auth.usuario_id,),
        )
        return [
            {
                "grupo": {"id": str(r["id"]), "nome": r["nome"]},
                "papel": r["papel"],
                "convidado_por": ({"id": r["c_id"], "nome": r["c_nome"], "login": r["c_login"]} if r["c_id"] else None),
                "criado_em": iso(r["criado_em"]),
            }
            for r in cur.fetchall()
        ]
