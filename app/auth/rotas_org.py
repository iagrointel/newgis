"""Configurações da organização/inquilino (item L0-07-a-configuracoes-org; ADR 0002 seção 11): `GET/PUT /api/org`
sobre `plat.tenant` — nome (coluna), cota de armazenamento (coluna `cota_bytes`, já lida ao vivo por
`GET /api/arquivos`: mudar aqui reflete lá na próxima chamada, sem cache) e o resto em `tenant.config` — mesma
coluna jsonb que o L0-02 já usa para `config.auth`. Superfície com paridade às abas General / Home page / Map /
Gallery / Security do ArcGIS Enterprise 11.4 (fora, como o portão declara: legado, Bing e Living Atlas): cor,
logotipo, resumo (≤ 310), contato (e-mail), contatos administrativos (≥ 1, membros ativos com perfil admin do
próprio inquilino — a migração 20260918T1300 semeia o admin mais antigo nos inquilinos antigos para o PUT
full-replace não trancar a primeira gravação), idioma padrão, unidades e formato de número/data, mapa padrão
(centro, zoom, basemap, extent, SRID de exibição), página inicial em blocos (texto / links / galeria; ≤ 15
blocos, ≤ 8 links por bloco, URL só https:// ou caminho relativo), galeria em destaque (grupo), banner de aviso
e termo de acesso (textos pré-login, servidos ao /entrar por `plat.tenant_publico`), cota de usuários e a
política de senha/2FA/domínios/compartilhamento/2FA. Esta rota NUNCA reescreve `config` inteiro: grava só as
chaves que possui (merge `config || jsonb`), preservando `config.logo` (gravado por `POST/DELETE /api/org/logo`,
endpoint separado porque é a única chave binária) e qualquer chave futura de outro item.

Privilégio único `org.configurar` (já semeado na migração 003, teto só do perfil admin) para leitura e
escrita — o portão do item ("editor comum recebe 403") é a checagem padrão de `autenticado()`, a mesma que
toda rota administrativa já usa. RLS em `plat.tenant` (`id = plat.tenant_atual()`) garante que o PUT nunca
alcança outro inquilino mesmo que a rota não tivesse checagem própria (defesa em profundidade: não há `id` na
URL para adulterar, e mesmo que houvesse, o `WHERE` da política ignoraria).

`POST /api/org/logo` reaproveita o adaptador genérico de arquivo do L0-11 (`app/objetos.py::guardar`, classe
`org_logo`, sem `item_id`: um objeto por inquilino, deduplicado por sha256) e o MESMO truque de base64 sob
JSON que a miniatura de item já usa (`app/catalogo/rotas_miniatura.py`): o CSRF sob cookie de sessão exige
`application/json` em todo verbo de escrita (ADR 0002 seção 5.3), então o envio de bytes crus fica reservado
à rota de token de serviço (`POST /api/arquivos`, escopo `conteudo:criar` — achado do adversário L0-11,
ver `app/rotas_arquivos.py`). A imagem é revalidada e
REDESENHADA pelo Pillow (contain 300×300, fundo transparente, sem EXIF/ICC) antes de gravar — mesma razão do
L7-03-b (a saída é sempre um PNG novo, nunca os bytes originais do cliente), por isso não chama
`escanear_cabecalho()` de novo (o padrão já isento é o mesmo da miniatura: ver o docstring de
`objetos.guardar`)."""

import base64
import binascii
import io
import json
import re
import uuid
import warnings
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from PIL import Image, ImageOps
from pydantic import Field, field_validator

from app import db, limites, objetos
from app.auth.comum import registrar_evento
from app.auth.modelos import Modelo, Saida
from app.auth.politica import Politica, politica_de, validar_config_auth
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["org"])
PRIV = {"x-auth": "S/T", "x-privilegio": "org.configurar"}
_FORMATOS_LOGO = {"PNG", "JPEG", "GIF", "WEBP"}
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]+$")


# ---------------------------------------------------------------- modelos
class Link(Modelo):
    rotulo: str = Field(min_length=1, max_length=limites.ORG_LINK_ROTULO_MAX)
    url: str = Field(min_length=1, max_length=limites.ORG_LINK_URL_MAX)

    @field_validator("url")
    @classmethod
    def _url_segura(cls, v: str) -> str:
        """Só https absoluto ou caminho relativo da própria origem: um `javascript:`/`data:` aqui viraria
        âncora clicável na página inicial de todo membro (o HTML é montado com textContent, mas o HREF
        precisa nascer limpo — defesa em profundidade, não confiança no front)."""
        if v.startswith("https://") or (v.startswith("/") and not v.startswith("//")):
            return v
        raise ValueError("url precisa começar por https:// ou ser caminho relativo (/)")


class BlocoTexto(Modelo):
    tipo: Literal["texto"]
    titulo: str = Field(default="", max_length=limites.ORG_BLOCO_TITULO_MAX)
    texto: str = Field(min_length=1, max_length=limites.ORG_BLOCO_TEXTO_MAX)


class BlocoLinks(Modelo):
    tipo: Literal["links"]
    titulo: str = Field(default="", max_length=limites.ORG_BLOCO_TITULO_MAX)
    links: list[Link] = Field(min_length=1, max_length=limites.ORG_BLOCO_LINKS_MAX)


class BlocoGaleria(Modelo):
    """Galeria de itens: mostra os itens do grupo `galeria_destaque` (a fonte é única por inquilino, como o
    'featured content' da aba Gallery da Esri — o bloco só decide ONDE ela aparece na página inicial)."""
    tipo: Literal["galeria"]
    titulo: str = Field(default="", max_length=limites.ORG_BLOCO_TITULO_MAX)


Bloco = Annotated[BlocoTexto | BlocoLinks | BlocoGaleria, Field(discriminator="tipo")]


class OrgEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=limites.ORG_NOME_MAX)
    cor: str = Field(default=limites.ORG_COR_PADRAO, pattern=r"^#[0-9a-fA-F]{6}$")
    resumo: str | None = Field(default=None, max_length=limites.ORG_RESUMO_MAX)
    contato: str | None = Field(default=None, max_length=limites.ORG_CONTATO_MAX)
    contatos_admin: list[str] = Field(min_length=1, max_length=limites.ORG_CONTATOS_ADMIN_MAX)
    idioma_padrao: str = Field(default=limites.ORG_IDIOMAS[0], max_length=10)
    unidades: str = Field(default=limites.ORG_UNIDADES[0])
    formato_data: str = Field(default=limites.ORG_FORMATOS_DATA[0])
    formato_numero_data: str = Field(default=limites.ORG_FORMATOS_NUMERO_DATA[0])
    centro: list[float] | None = Field(default=None, min_length=2, max_length=2)
    zoom: int | None = Field(default=None, ge=0, le=limites.ORG_ZOOM_MAX)
    basemap: str | None = Field(default=None, max_length=limites.ORG_BASEMAP_MAX)
    extent: list[float] | None = Field(default=None, min_length=4, max_length=4)
    srid_padrao: int | None = Field(default=None, ge=1024, le=999999)
    pagina_inicial: list[Bloco] = Field(default_factory=list, max_length=limites.ORG_BLOCOS_MAX)
    galeria_destaque: str | None = Field(default=None)

    @field_validator("galeria_destaque")
    @classmethod
    def _galeria_uuid(cls, v: str | None) -> str | None:
        """O id vai a uma consulta `WHERE id = %s` em coluna uuid: uma string que não é uuid explodiria em
        DataError 500 — recusar aqui como 422 com o campo nomeado."""
        if v is None:
            return v
        try:
            return str(uuid.UUID(v))
        except ValueError as e:
            raise ValueError("galeria_destaque precisa ser um uuid") from e
    banner_aviso: str | None = Field(default=None, max_length=limites.ORG_BANNER_MAX)
    termo_acesso: str | None = Field(default=None, max_length=limites.ORG_TERMO_MAX)
    cota_bytes: int = Field(ge=limites.ORG_COTA_BYTES_MIN)
    cota_usuarios: int = Field(ge=limites.ORG_COTA_USUARIOS_MIN)
    anexos_remover_exif_gps: bool = Field(default=False)
    auth: dict[str, Any] = Field(default_factory=dict)


class OrgLogoEntrada(Modelo):
    conteudo: str = Field(min_length=1, max_length=limites.ORG_LOGO_BYTES_MAX * 4 // 3 + 16)


class OrgSaida(Saida):
    slug: str
    nome: str
    ativo: bool
    cor: str
    logo: str | None
    resumo: str | None
    contato: str | None
    contatos_admin: list[str]
    idioma_padrao: str
    regional: dict[str, Any]
    mapa: dict[str, Any]
    pagina_inicial: list[dict[str, Any]]
    galeria_destaque: str | None
    banner_aviso: str | None
    termo_acesso: str | None
    armazenamento: dict[str, Any]
    usuarios: dict[str, Any]
    anexos_remover_exif_gps: bool
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
        "SELECT nome, ativo, cota_bytes, cota_bytes_teto, config FROM plat.tenant WHERE id = plat.tenant_atual()"
    )
    t = cur.fetchone()
    cur.execute(
        "SELECT plat.cota_usuarios(%s) AS cota, plat.usuarios_ativos(%s) AS ativos, "
        "plat.cota_usuarios_teto(%s) AS teto",
        (auth.tenant_id, auth.tenant_id, auth.tenant_id),
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
        "resumo": config.get("resumo"),
        "contato": config.get("contato"),
        "contatos_admin": list(config.get("contatos_admin") or []),
        "idioma_padrao": config.get("idioma_padrao") or limites.ORG_IDIOMAS[0],
        "regional": {
            "unidades": config.get("unidades") or limites.ORG_UNIDADES[0],
            "formato_data": config.get("formato_data") or limites.ORG_FORMATOS_DATA[0],
            "formato_numero_data": config.get("formato_numero_data") or limites.ORG_FORMATOS_NUMERO_DATA[0],
        },
        "mapa": {
            "centro": config.get("centro"),
            "zoom": config.get("zoom"),
            "basemap": config.get("basemap"),
            "extent": config.get("extent"),
            "srid_padrao": config.get("srid_padrao"),
        },
        "pagina_inicial": list(config.get("pagina_inicial") or []),
        "galeria_destaque": config.get("galeria_destaque"),
        "banner_aviso": config.get("banner_aviso"),
        "termo_acesso": config.get("termo_acesso"),
        # cota_bytes_teto/teto (item L0-07-c-cotas-uso): teto IMPOSTO PELA PLATAFORMA (só o superadmin move,
        # plat.tenant_cotas_definir) — o inquilino edita a própria cota livremente ABAIXO do teto, nunca acima
        # (achado do adversário 06/09: sem isso o admin do inquilino elevava a própria cota sem limite).
        "armazenamento": {
            "cota_bytes": t["cota_bytes"], "cota_bytes_teto": t["cota_bytes_teto"],
            "bytes_usados": objetos.uso(auth.tenant_slug),
        },
        "usuarios": {"cota": u["cota"], "teto": u["teto"], "ativos": u["ativos"]},
        # L2-03-e (LGPD): ligado = anexo de imagem entra no Garage já sem o bloco GPS do EXIF
        "anexos_remover_exif_gps": bool(config.get("anexos_remover_exif_gps")),
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
    if corpo.unidades not in limites.ORG_UNIDADES:
        raise ErroAPI(422, "validacao", f"unidades precisa ser um de {list(limites.ORG_UNIDADES)}",
                      {"campo": "unidades"})
    if corpo.formato_data not in limites.ORG_FORMATOS_DATA:
        raise ErroAPI(422, "validacao", f"formato_data precisa ser um de {list(limites.ORG_FORMATOS_DATA)}",
                      {"campo": "formato_data"})
    if corpo.formato_numero_data not in limites.ORG_FORMATOS_NUMERO_DATA:
        raise ErroAPI(422, "validacao",
                      f"formato_numero_data precisa ser um de {list(limites.ORG_FORMATOS_NUMERO_DATA)}",
                      {"campo": "formato_numero_data"})
    if corpo.contato is not None and corpo.contato.strip() and not _EMAIL.match(corpo.contato.strip()):
        raise ErroAPI(422, "validacao", "contato precisa ser um e-mail", {"campo": "contato"})
    if corpo.centro is not None:
        lon, lat = corpo.centro
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ErroAPI(422, "validacao", "centro fora do intervalo geográfico (lon -180..180, lat -90..90)",
                          {"campo": "centro"})
    if corpo.extent is not None:
        oeste, sul, leste, norte = corpo.extent
        lon_ok = -180 <= oeste <= 180 and -180 <= leste <= 180
        lat_ok = -90 <= sul <= 90 and -90 <= norte <= 90
        if not (lon_ok and lat_ok and oeste < leste and sul < norte):
            raise ErroAPI(422, "validacao",
                          "extent precisa ser [oeste, sul, leste, norte] dentro de lon -180..180, lat -90..90, "
                          "com oeste < leste e sul < norte",
                          {"campo": "extent"})
    erros_auth = validar_config_auth(corpo.auth)
    if erros_auth:
        raise ErroAPI(422, "validacao", "política de senha/2FA/domínios inválida", erros_auth)
    # teto IMPOSTO PELA PLATAFORMA (item L0-07-c-cotas-uso, correção pós-refutação de 06/09): o admin do
    # inquilino sobe/desce a própria cota livremente, mas nunca acima do teto que só o superadmin move
    # (plat.tenant_cotas_definir) — sem esta checagem a rota só tinha piso (Field ge=...), e um adversário
    # provou que o admin elevava a própria cota_bytes/cota_usuarios sem limite algum.
    # Os contatos administrativos precisam ser membros ATIVOS com perfil admin do PRÓPRIO inquilino (RLS
    # esconde qualquer outro inquilino — um login estranho sai simplesmente como "não encontrado"), e o
    # grupo da galeria em destaque precisa existir aqui também.
    contatos = sorted({(c or "").strip().lower() for c in corpo.contatos_admin if (c or "").strip()})
    if not contatos:
        # refutação do adversário: "define contato administrativo vazio" — nunca gravar a lista zerada
        raise ErroAPI(422, "validacao", "pelo menos um contato administrativo", {"campo": "contatos_admin"})
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT cota_bytes_teto FROM plat.tenant WHERE id = plat.tenant_atual()")
        teto_bytes = cur.fetchone()["cota_bytes_teto"]
        cur.execute("SELECT plat.cota_usuarios_teto(%s) AS teto", (auth.tenant_id,))
        teto_usuarios = cur.fetchone()["teto"]
        cur.execute(
            "SELECT login FROM plat.usuario WHERE login = ANY(%s) AND ativo AND perfil = 'admin'",
            (contatos,),
        )
        encontrados = {r["login"] for r in cur.fetchall()}
        faltam = [c for c in contatos if c not in encontrados]
        if faltam:
            raise ErroAPI(
                422, "validacao",
                f"contato administrativo precisa ser um usuário ativo com perfil admin do inquilino: "
                f"{', '.join(faltam)}",
                {"campo": "contatos_admin", "logins": faltam},
            )
        if corpo.galeria_destaque is not None:
            cur.execute("SELECT 1 FROM plat.grupo WHERE id = %s", (corpo.galeria_destaque,))
            if cur.fetchone() is None:
                raise ErroAPI(422, "validacao", "grupo da galeria em destaque inexistente",
                              {"campo": "galeria_destaque"})
    if corpo.cota_bytes > teto_bytes:
        raise ErroAPI(
            422, "cota_bytes_acima_do_teto",
            f"cota_bytes não pode passar do teto de {teto_bytes} bytes definido pela plataforma "
            "(fale com o superadmin para subir o teto)",
            {"campo": "cota_bytes", "teto": teto_bytes},
        )
    if corpo.cota_usuarios > teto_usuarios:
        raise ErroAPI(
            422, "cota_usuarios_acima_do_teto",
            f"cota_usuarios não pode passar do teto de {teto_usuarios} definido pela plataforma "
            "(fale com o superadmin para subir o teto)",
            {"campo": "cota_usuarios", "teto": teto_usuarios},
        )
    def _txt(v: str | None) -> str | None:
        return (v or "").strip() or None

    merge = {
        "cor": corpo.cor,
        "resumo": _txt(corpo.resumo),
        "contato": _txt(corpo.contato),
        "contatos_admin": contatos,
        "idioma_padrao": corpo.idioma_padrao,
        "unidades": corpo.unidades,
        "formato_data": corpo.formato_data,
        "formato_numero_data": corpo.formato_numero_data,
        "centro": corpo.centro,
        "zoom": corpo.zoom,
        "basemap": _txt(corpo.basemap),
        "extent": corpo.extent,
        "srid_padrao": corpo.srid_padrao,
        "pagina_inicial": [b.model_dump() for b in corpo.pagina_inicial],
        "galeria_destaque": corpo.galeria_destaque,
        "banner_aviso": _txt(corpo.banner_aviso),
        "termo_acesso": _txt(corpo.termo_acesso),
        "cota_usuarios": corpo.cota_usuarios,
        "anexos_remover_exif_gps": bool(corpo.anexos_remover_exif_gps),
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
             "exigir_2fa": corpo.auth.get("exigir_2fa"), "contatos_admin": contatos,
             "blocos": len(corpo.pagina_inicial)},
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
