"""Ficha de metadado e licença da imagem (item L1-27): a ÚNICA tabela de licenças da casa e a tradução
ficha <-> propriedades STAC.

Fonte da verdade da ficha é `plat.item.dados['ficha']` (o item de catálogo do tipo `raster`), não o item
STAC: quem decide compartilhamento e exportação já carregou a linha de `plat.item` (RLS), e uma segunda
leitura do pgstac em cada checagem custaria caro e abriria espaço para as duas cópias divergirem. O item
STAC recebe a PROJEÇÃO da ficha em `properties` a cada gravação (`para_stac`), de modo que a licença e a
data da ficha, do STAC e do XML ISO são sempre o mesmo dado escrito em três formatos.

Regra D17 da casa: item com licença `sem-licenca-escrita` é AUDITÁVEL, não VENDÁVEL — a tela mostra o
aviso, `vendavel` é falso e ele nunca entra em material de canal. Licença que não autoriza redistribuição
(`comercial-eula`, e a própria ausência de licença) bloqueia link público e exportação em massa.

Extensões STAC usadas na projeção (as declaradas no item): eo, view, sat, projection, raster.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from app.erros import ErroAPI

# --------------------------------------------------------------------------- extensões STAC declaradas
EXTENSOES_STAC = (
    "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
    "https://stac-extensions.github.io/view/v1.0.0/schema.json",
    "https://stac-extensions.github.io/sat/v1.0.0/schema.json",
    "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
    "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
)


@dataclass(frozen=True)
class Licenca:
    codigo: str          # chave estável usada na ficha e na tela
    rotulo: str          # texto em português mostrado ao usuário
    stac: str            # valor do campo `license` do STAC: identificador SPDX ou "other"
    url: str | None      # endereço do texto da licença (vira link rel=license no STAC e onLine no ISO)
    redistribuicao: str  # 'livre' | 'restrita' — 'restrita' bloqueia link público e exportação em massa
    exige_atribuicao: bool
    vendavel: bool       # D17: material de canal só usa item vendável
    aviso: str | None = None


# ============================ A TABELA (uma só; nada de licença escrita em outro lugar do código) =====
LICENCAS: tuple[Licenca, ...] = (
    Licenca(
        "copernicus", "Copernicus (dados Sentinel)", "other",
        "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
        "livre", True, True,
    ),
    Licenca("cc-by-4.0", "CC BY 4.0", "CC-BY-4.0",
            "https://creativecommons.org/licenses/by/4.0/", "livre", True, True),
    Licenca("cc-by-sa-4.0", "CC BY-SA 4.0", "CC-BY-SA-4.0",
            "https://creativecommons.org/licenses/by-sa/4.0/", "livre", True, True),
    Licenca("dominio-publico", "domínio público (CC0 1.0)", "CC0-1.0",
            "https://creativecommons.org/publicdomain/zero/1.0/", "livre", False, True),
    Licenca("odbl-1.0", "ODbL 1.0", "ODbL-1.0",
            "https://opendatacommons.org/licenses/odbl/1-0/", "livre", True, True),
    Licenca(
        "comercial-eula", "comercial (contrato do fornecedor)", "other", None, "restrita", True, True,
        "o contrato do fornecedor não autoriza redistribuição: link público e exportação em massa ficam "
        "bloqueados para este item",
    ),
    Licenca(
        "sem-licenca-escrita", "sem licença escrita", "other", None, "restrita", True, False,
        "item sem licença escrita é auditável, não vendável (regra D17): não pode ser compartilhado por "
        "link público, não entra em exportação em massa e não entra em material de canal",
    ),
)
POR_CODIGO: dict[str, Licenca] = {lic.codigo: lic for lic in LICENCAS}
LICENCA_PADRAO = "sem-licenca-escrita"


def licenca(codigo: str | None) -> Licenca:
    """Licença da tabela; código ausente/desconhecido cai no padrão auditável (nunca em uma livre)."""
    return POR_CODIGO.get(codigo or "", POR_CODIGO[LICENCA_PADRAO])


def catalogo_licencas() -> list[dict]:
    """A tabela em JSON para a tela (a tela NUNCA repete a lista: lê daqui)."""
    return [
        {
            "codigo": lic.codigo, "rotulo": lic.rotulo, "stac": lic.stac, "url": lic.url,
            "redistribuicao": lic.redistribuicao, "exige_atribuicao": lic.exige_atribuicao,
            "vendavel": lic.vendavel, "aviso": lic.aviso,
        }
        for lic in LICENCAS
    ]


def permite_link_publico(codigo: str | None) -> bool:
    return licenca(codigo).redistribuicao == "livre"


def permite_exportacao_em_massa(codigo: str | None) -> bool:
    return licenca(codigo).redistribuicao == "livre"


def vendavel(codigo: str | None) -> bool:
    return licenca(codigo).vendavel


# --------------------------------------------------------------------------- validação da ficha
FONTES = ("upload", "conector")
ORBITAS = ("ascending", "descending", "geostationary")
_ID = re.compile(r"^[\w .,:/+()-]{1,120}$", re.UNICODE)
OBRIGATORIOS = ("plataforma", "instrumentos", "gsd", "data_aquisicao", "fornecedor", "licenca", "fonte")


@dataclass
class Ficha:
    plataforma: str
    instrumentos: list[str]
    gsd: float
    data_aquisicao: str                 # ISO 8601 UTC; instante único
    fornecedor: str
    licenca: str
    fonte: str                          # 'upload' | 'conector'
    constelacao: str | None = None
    data_aquisicao_fim: str | None = None   # com este campo a data vira intervalo start/end
    nuvem_pct: float | None = None
    angulo_off_nadir: float | None = None
    angulo_incidencia: float | None = None
    angulo_azimute: float | None = None
    sol_azimute: float | None = None
    sol_elevacao: float | None = None
    orbita_estado: str | None = None
    orbita_relativa: int | None = None
    orbita_absoluta: int | None = None
    atribuicao: str | None = None
    observacao: str | None = None
    campos_extra: dict = field(default_factory=dict)


def _erro(campo: str, mensagem: str):
    return ErroAPI(422, "ficha_invalida", mensagem, {"campo": campo})


def _texto(bruto: dict, campo: str, obrigatorio: bool, limite: int = 200) -> str | None:
    v = bruto.get(campo)
    if v is None or (isinstance(v, str) and not v.strip()):
        if obrigatorio:
            raise _erro(campo, f"{campo} é obrigatório")
        return None
    if not isinstance(v, str):
        raise _erro(campo, f"{campo} tem de ser texto")
    v = v.strip()
    if len(v) > limite:
        raise _erro(campo, f"{campo} passa de {limite} caracteres")
    return v


def _numero(bruto: dict, campo: str, minimo: float, maximo: float, obrigatorio: bool = False) -> float | None:
    v = bruto.get(campo)
    if v is None or v == "":
        if obrigatorio:
            raise _erro(campo, f"{campo} é obrigatório")
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _erro(campo, f"{campo} tem de ser número")
    if not (minimo <= float(v) <= maximo):
        raise _erro(campo, f"{campo} tem de ficar entre {minimo} e {maximo}")
    return float(v)


def _inteiro(bruto: dict, campo: str, minimo: int, maximo: int) -> int | None:
    v = bruto.get(campo)
    if v is None or v == "":
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise _erro(campo, f"{campo} tem de ser inteiro")
    if not (minimo <= v <= maximo):
        raise _erro(campo, f"{campo} tem de ficar entre {minimo} e {maximo}")
    return v


def _instante(bruto: dict, campo: str, obrigatorio: bool) -> str | None:
    v = bruto.get(campo)
    if v is None or (isinstance(v, str) and not v.strip()):
        if obrigatorio:
            raise _erro(campo, f"{campo} é obrigatória")
        return None
    if not isinstance(v, str):
        raise _erro(campo, f"{campo} tem de ser texto ISO 8601")
    texto = v.strip()
    try:
        quando = datetime.datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as e:
        raise _erro(campo, f"{campo} não é uma data ISO 8601 válida") from e
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=datetime.UTC)
    return quando.astimezone(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def validar(bruto: dict | None) -> Ficha:
    """Ficha crua (corpo do PUT ou `dados['ficha']` guardado) -> Ficha normalizada. 422 com o campo."""
    if bruto is None or not isinstance(bruto, dict):
        raise _erro("ficha", "ficha tem de ser um objeto")
    instrumentos = bruto.get("instrumentos")
    if isinstance(instrumentos, str):
        instrumentos = [p.strip() for p in instrumentos.split(",") if p.strip()]
    if not isinstance(instrumentos, list) or not instrumentos:
        raise _erro("instrumentos", "instrumentos é obrigatório (ao menos um)")
    if len(instrumentos) > 20:
        raise _erro("instrumentos", "instrumentos passa de 20 entradas")
    limpos = []
    for i in instrumentos:
        if not isinstance(i, str) or not _ID.match(i.strip()):
            raise _erro("instrumentos", "cada instrumento tem de ser texto de 1 a 120 caracteres")
        limpos.append(i.strip())

    codigo_licenca = _texto(bruto, "licenca", True, 60)
    if codigo_licenca not in POR_CODIGO:
        raise _erro("licenca", f"licença fora da lista da casa: {sorted(POR_CODIGO)}")
    fonte = _texto(bruto, "fonte", True, 20)
    if fonte not in FONTES:
        raise _erro("fonte", f"fonte tem de ser uma de {list(FONTES)}")
    orbita_estado = _texto(bruto, "orbita_estado", False, 20)
    if orbita_estado is not None and orbita_estado not in ORBITAS:
        raise _erro("orbita_estado", f"órbita tem de ser uma de {list(ORBITAS)}")

    inicio = _instante(bruto, "data_aquisicao", True)
    fim = _instante(bruto, "data_aquisicao_fim", False)
    if fim is not None and fim < inicio:
        raise _erro("data_aquisicao_fim", "o fim da aquisição vem antes do início")

    atribuicao = _texto(bruto, "atribuicao", False, 300)
    lic = POR_CODIGO[codigo_licenca]
    if lic.exige_atribuicao and not atribuicao:
        raise _erro("atribuicao", f"a licença {lic.rotulo} exige texto de atribuição")

    extra = bruto.get("campos_extra") or {}
    if not isinstance(extra, dict) or len(extra) > 30:
        raise _erro("campos_extra", "campos_extra tem de ser um objeto com até 30 chaves")

    return Ficha(
        plataforma=_texto(bruto, "plataforma", True, 120),
        instrumentos=limpos,
        gsd=_numero(bruto, "gsd", 0.001, 100000.0, obrigatorio=True),
        data_aquisicao=inicio,
        fornecedor=_texto(bruto, "fornecedor", True, 200),
        licenca=codigo_licenca,
        fonte=fonte,
        constelacao=_texto(bruto, "constelacao", False, 120),
        data_aquisicao_fim=fim,
        nuvem_pct=_numero(bruto, "nuvem_pct", 0.0, 100.0),
        angulo_off_nadir=_numero(bruto, "angulo_off_nadir", 0.0, 90.0),
        angulo_incidencia=_numero(bruto, "angulo_incidencia", 0.0, 90.0),
        angulo_azimute=_numero(bruto, "angulo_azimute", 0.0, 360.0),
        sol_azimute=_numero(bruto, "sol_azimute", 0.0, 360.0),
        sol_elevacao=_numero(bruto, "sol_elevacao", -90.0, 90.0),
        orbita_estado=orbita_estado,
        orbita_relativa=_inteiro(bruto, "orbita_relativa", 0, 100000),
        orbita_absoluta=_inteiro(bruto, "orbita_absoluta", 0, 100000000),
        atribuicao=atribuicao,
        observacao=_texto(bruto, "observacao", False, 1000),
        campos_extra=extra,
    )


def para_json(f: Ficha) -> dict:
    """Ficha -> objeto guardado em `plat.item.dados['ficha']` (sem chave nula: o que não foi medido não vai)."""
    bruto = {
        "plataforma": f.plataforma, "instrumentos": f.instrumentos, "gsd": f.gsd,
        "data_aquisicao": f.data_aquisicao, "data_aquisicao_fim": f.data_aquisicao_fim,
        "fornecedor": f.fornecedor, "licenca": f.licenca, "fonte": f.fonte,
        "constelacao": f.constelacao, "nuvem_pct": f.nuvem_pct,
        "angulo_off_nadir": f.angulo_off_nadir, "angulo_incidencia": f.angulo_incidencia,
        "angulo_azimute": f.angulo_azimute, "sol_azimute": f.sol_azimute, "sol_elevacao": f.sol_elevacao,
        "orbita_estado": f.orbita_estado, "orbita_relativa": f.orbita_relativa,
        "orbita_absoluta": f.orbita_absoluta, "atribuicao": f.atribuicao, "observacao": f.observacao,
    }
    saida = {k: v for k, v in bruto.items() if v is not None}
    if f.campos_extra:
        saida["campos_extra"] = f.campos_extra
    return saida


# --------------------------------------------------------------------------- projeção STAC
_PROPRIEDADES = (
    # (campo da ficha, propriedade STAC) — só as de tradução 1:1; as de nome/forma diferente vão à mão
    ("constelacao", "constellation"),
    ("gsd", "gsd"),
    ("nuvem_pct", "eo:cloud_cover"),
    ("angulo_off_nadir", "view:off_nadir"),
    ("angulo_incidencia", "view:incidence_angle"),
    ("angulo_azimute", "view:azimuth"),
    ("sol_azimute", "view:sun_azimuth"),
    ("sol_elevacao", "view:sun_elevation"),
    ("orbita_estado", "sat:orbit_state"),
    ("orbita_relativa", "sat:relative_orbit"),
    ("orbita_absoluta", "sat:absolute_orbit"),
)


def para_stac(f: Ficha) -> dict:
    """Ficha -> propriedades STAC. `datetime` sozinho quando a aquisição é um instante; quando a ficha traz
    fim, o STAC exige `datetime: null` com `start_datetime`/`end_datetime` (STAC 1.0 §Date and Time Range)."""
    props: dict = {"platform": f.plataforma, "instruments": list(f.instrumentos)}
    for campo, chave in _PROPRIEDADES:
        v = getattr(f, campo)
        if v is not None:
            props[chave] = v
    if f.data_aquisicao_fim:
        props["datetime"] = None
        props["start_datetime"] = f.data_aquisicao
        props["end_datetime"] = f.data_aquisicao_fim
    else:
        props["datetime"] = f.data_aquisicao
    lic = POR_CODIGO[f.licenca]
    props["license"] = lic.stac
    props["providers"] = [{"name": f.fornecedor, "roles": ["producer", "licensor"]}]
    props["plat:licenca"] = f.licenca
    props["plat:redistribuicao"] = lic.redistribuicao
    props["plat:vendavel"] = lic.vendavel
    props["plat:fonte_da_ficha"] = f.fonte
    if f.atribuicao:
        props["plat:atribuicao"] = f.atribuicao
    if f.observacao:
        props["plat:observacao"] = f.observacao
    return props


def links_stac(f: Ficha) -> list[dict]:
    lic = POR_CODIGO[f.licenca]
    return [{"rel": "license", "href": lic.url, "title": lic.rotulo}] if lic.url else []


def avisos(f: Ficha | None) -> list[str]:
    """Avisos mostrados na ficha e no aviso do item (D17)."""
    if f is None:
        return [
            "este item ainda não tem ficha de metadado; sem ficha ele conta como sem licença escrita: "
            "auditável, não vendável"
        ]
    lic = POR_CODIGO[f.licenca]
    saida = [lic.aviso] if lic.aviso else []
    if lic.exige_atribuicao and not f.atribuicao:
        saida.append("a licença exige atribuição e a ficha está sem o texto de atribuição")
    return saida


def do_item(dados: dict | None) -> Ficha | None:
    """`plat.item.dados` -> Ficha, ou None quando o item ainda não tem ficha. Ficha guardada inválida
    (esquema antigo, edição manual do jsonb) conta como ausente: quem não tem ficha legível é tratado
    como sem licença escrita, nunca como livre."""
    bruto = (dados or {}).get("ficha") if isinstance(dados, dict) else None
    if not bruto:
        return None
    try:
        return validar(bruto)
    except ErroAPI:
        return None


def licenca_do_item(dados: dict | None) -> str:
    f = do_item(dados)
    return f.licenca if f else LICENCA_PADRAO
