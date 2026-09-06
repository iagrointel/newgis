"""Configurações da organização/inquilino (item L0-07-a-configuracoes-org; ADR 0002 seção 11): `GET/PUT /api/org`
sobre `plat.tenant` — nome (coluna), cota de armazenamento (coluna `cota_bytes`, já lida ao vivo por
`GET /api/arquivos`: mudar aqui reflete lá na próxima chamada, sem cache) e o resto (cor, logotipo, mapa
padrão, idioma padrão, cota de usuários, política de senha/2FA) em `tenant.config` — mesma coluna jsonb que o
L0-02 já usa para `config.auth`. Esta rota NUNCA reescreve `config` inteiro: grava só as chaves que possui
(merge `config || jsonb`), preservando `config.logo` (gravado por `POST/DELETE /api/org/logo`, endpoint
separado porque é a única chave binária) e qualquer chave futura de outro item.

Privilégio único `org.configurar` (já semeado na migração 003, teto só do perfil admin) para leitura e
escrita — o portão do item ("editor comum recebe 403") é a checagem padrão de `autenticado()`, a mesma que
toda rota administrativa já usa. RLS em `plat.tenant` (`id = plat.tenant_atual()`) garante que o PUT nunca
alcança outro inquilino mesmo que a rota não tivesse checagem própria (defesa em profundidade: não há `id` na
URL para adulterar, e mesmo que houvesse, o `WHERE` da política ignoraria).

`POST /api/org/logo` reaproveita o adaptador genérico de arquivo do L0-11 (`app/objetos.py::guardar`, classe
`org_logo`, sem `item_id`: um objeto por inquilino, deduplicado por sha256) e o MESMO truque de base64 sob
JSON que a miniatura de item já usa (`app/catalogo/rotas_miniatura.py`): o CSRF sob cookie de sessão exige
`application/json` em todo verbo de escrita (ADR 0002 seção 5.3), então o envio de bytes crus fica reservado
à rota de token de serviço (`POST /api/arquivos`, escopo `admin:inquilino`). A imagem é revalidada e
REDESENHADA pelo Pillow (contain 300×300, fundo transparente, sem EXIF/ICC) antes de gravar — mesma razão do
L7-03-b (a saída é sempre um PNG novo, nunca os bytes originais do cliente), por isso não chama
`escanear_cabecalho()` de novo (o padrão já isento é o mesmo da miniatura: ver o docstring de
`objetos.guardar`)."""

import base64
import binascii
import io
import json
import warnings
from typing import Any

from fastapi import APIRouter, Request
from PIL import Image, ImageOps
from pydantic import Field

from app import db, limites, objetos
from app.auth.comum import registrar_evento
from app.auth.modelos import Modelo, Saida
from app.auth.politica import Politica, politica_de, validar_config_auth
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["org"])
PRIV = {"x-auth": "S/T", "x-privilegio": "org.configurar"}
_FORMATOS_LOGO = {"PNG", "JPEG", "GIF", "WEBP"}


# ---------------------------------------------------------------- modelos
class OrgEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=limites.ORG_NOME_MAX)
    cor: str = Field(default=limites.ORG_COR_PADRAO, pattern=r"^#[0-9a-fA-F]{6}$")
    idioma_padrao: str = Field(default=limites.ORG_IDIOMAS[0], max_length=10)
    centro: list[float] | None = Field(default=None, min_length=2, max_length=2)
    zoom: int | None = Field(default=None, ge=0, le=limites.ORG_ZOOM_MAX)
    basemap: str | None = Field(default=None, max_length=limites.ORG_BASEMAP_MAX)
    srid_padrao: int | None = Field(default=None, ge=1024, le=999999)
    cota_bytes: int = Field(ge=limites.ORG_COTA_BYTES_MIN, le=limites.ORG_COTA_BYTES_TETO_MAX)
    cota_usuarios: int = Field(ge=limites.ORG_COTA_USUARIOS_MIN, le=limites.ORG_COTA_USUARIOS_TETO_MAX)
    auth: dict[str, Any] = Field(default_factory=dict)


class OrgLogoEntrada(Modelo):
    conteudo: str = Field(min_length=1, max_length=limites.ORG_LOGO_BYTES_MAX * 4 // 3 + 16)


class OrgSaida(Saida):
    slug: str
    nome: str
    ativo: bool
    cor: str
    logo: str | None
    idioma_padrao: str
    mapa: dict[str, Any]
    armazenamento: dict[str, Any]
    usuarios: dict[str, Any]
    auth: dict[str, Any]


class OrgLogoSaida(Saida):
    logo: str | None
    url: str | None


def _auth_completo(p: Politica) -> dict:
    """A política INTEIRA (não só `Politica.publica()`, que é o subconjunto que qualquer sessão vê em
    `GET /api/eu` para repetir a regra de senha ao vivo): quem administra o inquilino também vê e edita
    histórico, bloqueio e sessão."""
    return {
        "senha_min": p.senha_min,
        "senha_maiuscula": p.senha_maiuscula,
        "senha_minuscula": p.senha_minuscula,
        "senha_simbolo": p.senha_simbolo,
        "senha_historico": p.senha_historico,
        "senha_expira_dias": p.senha_expira_dias,
        "bloqueio_tentativas": p.bloqueio_tentativas,
        "bloqueio_minutos": p.bloqueio_minutos,
        "sessao_ociosa_horas": p.sessao_ociosa_horas,
        "sessao_max_dias": p.sessao_max_dias,
        "exigir_2fa": p.exigir_2fa,
        "token_max_dias": p.token_max_dias,
        "token_padrao_dias": p.token_padrao_dias,
        "dominios_email": list(p.dominios_email),
        "compartilhar_publico": p.compartilhar_publico,
    }


def _org_json(cur, auth: Auth) -> dict:
    cur.execute(
        "SELECT nome, ativo, cota_bytes, cota_bytes_teto, cota_usuarios_teto, config "
        "FROM plat.tenant WHERE id = plat.tenant_atual()"
    )
    t = cur.fetchone()
    cur.execute(
        "SELECT plat.cota_usuarios(%s) AS cota, plat.usuarios_ativos(%s) AS ativos", (auth.tenant_id, auth.tenant_id)
    )
    u = cur.fetchone()
    config = t["config"] or {}
    politica = politica_de(config, auth.tenant_slug)
    return {
        "slug": auth.tenant_slug,
        "nome": t["nome"],
        "ativo": t["ativo"],
        "cor": config.get("cor") or limites.ORG_COR_PADRAO,
        "logo": config.get("logo"),
        "idioma_padrao": config.get("idioma_padrao") or limites.ORG_IDIOMAS[0],
        "mapa": {
            "centro": config.get("centro"),
            "zoom": config.get("zoom"),
            "basemap": config.get("basemap"),
            "srid_padrao": config.get("srid_padrao"),
        },
        "armazenamento": {
            "cota_bytes": t["cota_bytes"],
            "cota_bytes_teto": t["cota_bytes_teto"],
            "bytes_usados": objetos.uso(auth.tenant_slug),
        },
        "usuarios": {"cota": u["cota"], "cota_teto": t["cota_usuarios_teto"], "ativos": u["ativos"]},
        "auth": _auth_completo(politica),
    }


@router.get("/org", response_model=OrgSaida, openapi_extra=PRIV)
def org_ler(auth: Auth = autenticado("org.configurar")):
    with db.db(auth.contexto()) as cur:
        return _org_json(cur, auth)


@router.put("/org", response_model=OrgSaida, openapi_extra=PRIV)
def org_gravar(corpo: OrgEntrada, request: Request, auth: Auth = autenticado("org.configurar", so_sessao=True)):
    if corpo.idioma_padrao not in limites.ORG_IDIOMAS:
        raise ErroAPI(
            422, "validacao", f"idioma_padrao precisa ser um de {list(limites.ORG_IDIOMAS)}",
            {"campo": "idioma_padrao"},
        )
    if corpo.centro is not None:
        lon, lat = corpo.centro
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ErroAPI(422, "validacao", "centro fora do intervalo geográfico (lon -180..180, lat -90..90)",
                          {"campo": "centro"})
    erros_auth = validar_config_auth(corpo.auth)
    if erros_auth:
        raise ErroAPI(422, "validacao", "política de senha/2FA/domínios inválida", erros_auth)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT cota_bytes_teto, cota_usuarios_teto FROM plat.tenant WHERE id = plat.tenant_atual()"
        )
        teto = cur.fetchone()
    # Achados G4-04 e G4-05: a rota é do admin do INQUILINO e só tinha piso. Quem escolhe o teto é a
    # plataforma (PUT /api/plataforma/inquilinos/{id}/cotas, superadmin); aqui o inquilino escolhe abaixo dele.
    # O gatilho tg_tenant_cota_guarda repete a regra no banco, para que nenhum caminho novo a contorne.
    if corpo.cota_bytes > teto["cota_bytes_teto"]:
        raise ErroAPI(
            422, "cota_acima_do_teto",
            "cota_bytes acima do teto definido pela plataforma para este inquilino",
            {"campo": "cota_bytes", "teto": teto["cota_bytes_teto"]},
        )
    if corpo.cota_usuarios > teto["cota_usuarios_teto"]:
        raise ErroAPI(
            422, "cota_acima_do_teto",
            "cota_usuarios acima do teto definido pela plataforma para este inquilino",
            {"campo": "cota_usuarios", "teto": teto["cota_usuarios_teto"]},
        )
    merge = {
        "cor": corpo.cor,
        "idioma_padrao": corpo.idioma_padrao,
        "centro": corpo.centro,
        "zoom": corpo.zoom,
        "basemap": corpo.basemap,
        "srid_padrao": corpo.srid_padrao,
        "cota_usuarios": corpo.cota_usuarios,
        "auth": corpo.auth,
    }
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.tenant SET nome = %s, cota_bytes = %s, config = config || %s::jsonb "
            "WHERE id = plat.tenant_atual()",
            (corpo.nome.strip(), corpo.cota_bytes, json.dumps(merge)),
        )
        registrar_evento(
            cur, request, "org/configurar", "tenant", auth.tenant_id,
            {"nome": corpo.nome.strip(), "cota_bytes": corpo.cota_bytes, "cota_usuarios": corpo.cota_usuarios,
             "exigir_2fa": corpo.auth.get("exigir_2fa")},
        )
        saida = _org_json(cur, auth)
    return saida


# ---------------------------------------------------------------- logotipo (reaproveita o L0-11)
def _decodificar_base64_logo(conteudo: str) -> bytes:
    """Igual a `app.catalogo.miniatura.decodificar_base64`, mas com o teto do LOGO (1 MiB), não o da
    miniatura (10 MiB) — reaproveitar aquela função deixaria passar 1-10 MiB com o erro errado ('miniatura
    acima de 10 MB' numa tela que não fala de miniatura)."""
    if len(conteudo) * 3 // 4 > limites.ORG_LOGO_BYTES_MAX + 4:
        raise ErroAPI(413, "logo_grande", f"logo acima de {limites.ORG_LOGO_BYTES_MAX // 1024} KB")
    if conteudo.startswith("data:"):
        conteudo = conteudo.split(",", 1)[-1]
    try:
        dados = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "validacao", "conteudo precisa ser base64 válido", {"campo": "conteudo"}) from e
    if len(dados) > limites.ORG_LOGO_BYTES_MAX:
        raise ErroAPI(413, "logo_grande", f"logo acima de {limites.ORG_LOGO_BYTES_MAX // 1024} KB")
    return dados


def _normalizar_logo(dados: bytes) -> bytes:
    """Bytes de PNG/JPEG/GIF/WEBP → PNG 300×300 (contido, sem corte, fundo transparente), sem metadado.
    Mesma defesa de bomba de descompressão da miniatura (ImageOps.contain nunca amplia além do original)."""
    if len(dados) > limites.ORG_LOGO_BYTES_MAX:
        raise ErroAPI(413, "logo_grande", f"logo acima de {limites.ORG_LOGO_BYTES_MAX // 1024} KB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(dados))
            formato = (im.format or "").upper()
            if formato not in _FORMATOS_LOGO:
                raise ErroAPI(415, "formato_nao_aceito", "só PNG, JPEG, GIF ou WEBP", {"formato": formato or None})
            largura, altura = im.size
            if largura * altura > limites.ORG_LOGO_PIXELS_MAX:
                raise ErroAPI(422, "imagem_grande", "imagem com pixels demais",
                              {"largura": largura, "altura": altura, "maximo_px": limites.ORG_LOGO_PIXELS_MAX})
            im.load()
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise ErroAPI(422, "imagem_grande", "imagem com pixels demais",
                      {"maximo_px": limites.ORG_LOGO_PIXELS_MAX}) from e
    except ErroAPI:
        raise
    except Exception as e:  # noqa: BLE001 — Pillow não abriu: não é imagem aceita
        raise ErroAPI(415, "formato_nao_aceito", "só PNG, JPEG, GIF ou WEBP", {"motivo": str(e)[:200]}) from e
    lado = limites.ORG_LOGO_LADO
    ajustada = ImageOps.contain(im, (lado, lado), method=Image.Resampling.LANCZOS)
    quadro = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    quadro.paste(ajustada, ((lado - ajustada.width) // 2, (lado - ajustada.height) // 2), ajustada)
    saida = io.BytesIO()
    quadro.save(saida, format="PNG", optimize=True)
    return saida.getvalue()


@router.post("/org/logo", response_model=OrgLogoSaida, openapi_extra=PRIV)
def org_logo_enviar(
    corpo: OrgLogoEntrada, request: Request, auth: Auth = autenticado("org.configurar", so_sessao=True)
):
    dados = _decodificar_base64_logo(corpo.conteudo)
    png = _normalizar_logo(dados)
    with db.db(auth.contexto()) as cur:
        o = objetos.guardar(cur, "org_logo", png, "image/png", usuario_id=auth.usuario_id)
        cur.execute(
            "UPDATE plat.tenant SET config = config || jsonb_build_object('logo', %s::text) "
            "WHERE id = plat.tenant_atual()",
            (o["sha256"],),
        )
        registrar_evento(cur, request, "org/logo_enviar", "tenant", auth.tenant_id, {"sha256": o["sha256"]})
    return {"logo": o["sha256"], "url": f"/api/arquivos/{o['sha256']}?classe=org_logo"}


@router.delete("/org/logo", response_model=OrgLogoSaida, openapi_extra=PRIV)
def org_logo_remover(request: Request, auth: Auth = autenticado("org.configurar", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.tenant SET config = config - 'logo' WHERE id = plat.tenant_atual() RETURNING config"
        )
        cur.fetchone()
        registrar_evento(cur, request, "org/logo_remover", "tenant", auth.tenant_id, {})
    return {"logo": None, "url": None}
