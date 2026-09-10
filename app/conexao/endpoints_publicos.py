"""Catálogo de conectores públicos prontos para "um clique" (item L6-02-m-catalogo-endpoints-brasil; decisão B12
do L3L6_CONCEITO: "catálogo de endpoints prontos vem do registro vivo, não de lista digitada ... retestado por
semana; entrada morta some"). Duas origens, as duas RETESTADAS por HTTP pelo mesmo `testar`:

1. `registro`: `plat.acervo_endpoint` (view da migração 040 sobre `acervo.endpoint`, só fontes com licença escrita —
   regra D17), filtrando as URLs que são serviço OGC/ArcGIS REST/STAC e normalizando para o endereço BASE;
2. `curadoria`: `endpoints_publicos_semente.json` ao lado deste módulo — serviços públicos (federais, estaduais,
   municipais e catálogos STAC globais sem chave) com órgão, tipo e licença QUANDO o órgão a declara em página
   própria (senão `nao-declarada`, vocabulário da decisão B3; nunca inferida).

Semente e registro só entram na tabela `plat.endpoint_publico` pela função SECURITY DEFINER
`plat.endpoint_publico_semear(jsonb)`; o resultado de cada teste entra por `plat.endpoint_publico_registrar(...)`
(mesmo padrão de `plat.conexao_saude_registrar`, migração 036). A aplicação só LÊ a tabela.

O que é "verde": não basta HTTP 200 — a refutação do item diz que "endpoint 200 que devolve HTML de erro conta
como morto". Por isso `testar` pede o documento que o protocolo define (GetCapabilities, `?f=json`, raiz STAC) e
confere a assinatura do corpo: raiz `*Capabilities` (nunca `ExceptionReport`, nunca `<html`), JSON do ArcGIS sem
chave `error`, JSON com `stac_version`, JSON com `links`. Tudo por `seguranca.buscar_seguro` (SSRF, bytes, tempo)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app import limites
from app.conexao import seguranca

TIPOS = ("wms", "wfs", "wmts", "esri_rest", "stac", "ogc_api")
SEMENTE = Path(__file__).with_name("endpoints_publicos_semente.json")
_RE_HTML = re.compile(rb"^\s*(<!doctype\s+html|<html)", re.I)
_RE_ARCGIS = re.compile(r"/(arcgis|server|[a-z0-9_-]*gisserver|interativo)/rest/services", re.I)


@dataclass(frozen=True)
class ResultadoTeste:
    vivo: bool
    http: int | None
    content_type: str | None
    ms: int
    motivo: str  # "ok" ou a razão nomeada da morte (html_no_lugar_do_servico, exception_report, ...)


# --------------------------------------------------------------------------- URL de teste por tipo


def url_de_teste(url: str, tipo: str) -> str:
    """o documento que o protocolo define para 'está vivo': GetCapabilities (OGC), `?f=json` (ArcGIS), a raiz
    (STAC e OGC API). Uma URL que já traz querystring própria ganha os parâmetros com `&`."""
    sep = "&" if "?" in url else "?"
    if tipo in ("wms", "wfs", "wmts"):
        if "getcapabilities" in url.lower():
            return url
        return f"{url}{sep}SERVICE={tipo.upper()}&REQUEST=GetCapabilities"
    if tipo == "esri_rest":
        return url if "f=json" in url.lower() else f"{url}{sep}f=json"
    return url  # stac / ogc_api: a raiz já é o documento


def _assinatura(corpo: bytes, tipo: str, content_type: str | None) -> str:
    """'ok' ou o motivo pelo qual o corpo NÃO é o serviço que a entrada diz ser."""
    if not corpo:
        return "corpo_vazio"
    inicio = corpo[:4096]
    if _RE_HTML.search(inicio):
        return "html_no_lugar_do_servico"
    if tipo in ("wms", "wfs", "wmts"):
        if b"ExceptionReport" in inicio or b"ServiceExceptionReport" in inicio:
            return "exception_report"
        if b"Capabilities" not in corpo[:65536]:
            return "sem_capabilities"
        return "ok"
    try:
        doc = json.loads(corpo.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return "json_invalido"
    if not isinstance(doc, dict):
        return "json_nao_e_objeto"
    if tipo == "esri_rest":
        if "error" in doc:
            return "arcgis_error"
        if not any(k in doc for k in ("currentVersion", "services", "folders", "layers", "fields", "name")):
            return "json_sem_cara_de_arcgis"
        return "ok"
    if tipo == "stac":
        return "ok" if doc.get("stac_version") else "sem_stac_version"
    return "ok" if isinstance(doc.get("links"), list) else "sem_links"


def testar(url: str, tipo: str) -> ResultadoTeste:
    """GET seguro ao documento do protocolo + conferência da assinatura do corpo. Nunca levanta."""
    if tipo not in TIPOS:
        return ResultadoTeste(False, None, None, 0, f"tipo_desconhecido:{tipo}")
    alvo = url_de_teste(url, tipo)
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.ENDPOINT_PUBLICO_LER_TIMEOUT_S,
        max_bytes=limites.ENDPOINT_PUBLICO_MAX_BYTES, guardar_corpo=True,
    )
    content_type = None
    if r.ok:
        motivo = _assinatura(r.corpo, tipo, None)
    elif r.mensagem == "resposta_excede_limite_de_bytes" and tipo in ("wms", "wfs", "wmts"):
        # capabilities gigantes (a INDE passa de 1 MiB): o serviço respondeu e é XML — vivo, assinatura parcial
        motivo = "ok"
    else:
        motivo = r.mensagem
    return ResultadoTeste(
        vivo=(motivo == "ok"), http=r.status, content_type=content_type, ms=r.latencia_ms, motivo=motivo
    )


# --------------------------------------------------------------------------- candidatos


def _base(url: str) -> str:
    p = urlsplit(url.strip())
    caminho = p.path.rstrip("/")
    return urlunsplit((p.scheme, p.netloc.lower(), caminho, "", ""))


def tipos_da_url(url: str) -> list[tuple[str, str]]:
    """(tipo, url base) que uma URL do registro sugere. GeoServer `/ows` serve WMS e WFS (duas entradas);
    `/wms`, `/wfs`, `/wmts` explícitos viram uma; `rest/services` do ArcGIS vira `esri_rest` até o serviço
    (MapServer/FeatureServer/ImageServer, sem `/N/query`); `/stac` vira `stac`. URL que não é serviço -> []."""
    base = _base(url)
    baixo = base.lower()
    q = urlsplit(url).query.lower()
    m = _RE_ARCGIS.search(baixo)
    if m:
        corte = re.search(r"/(mapserver|featureserver|imageserver)(/\d+)?", baixo)
        fim = corte.end() if corte else len(baixo)
        return [("esri_rest", base[:fim].rstrip("/"))]
    if re.search(r"/stac(/v\d+)?$", baixo):
        return [("stac", base)]
    if baixo.endswith("/wmts") or "service=wmts" in q:
        return [("wmts", base)]
    if baixo.endswith("/wms") or "service=wms" in q:
        return [("wms", base)]
    if baixo.endswith("/wfs") or "service=wfs" in q:
        return [("wfs", base)]
    if baixo.endswith("/ows"):
        return [("wms", base), ("wfs", base)]
    return []


def _slug(tipo: str, url: str) -> str:
    p = urlsplit(url)
    bruto = f"{p.netloc}{p.path}".lower()
    bruto = re.sub(r"[^a-z0-9]+", "-", bruto).strip("-")
    return f"{tipo}-{bruto}"[:200]


def candidatos_do_registro(cur) -> list[dict]:
    """entradas derivadas de `plat.acervo_endpoint` (só fontes com licença escrita, D17) + `acervo.fonte`
    (órgão, nome, licença). Uma por (tipo, url base); a fonte que aparece primeiro dá o nome."""
    cur.execute(
        "SELECT e.fonte_id, e.url, f.orgao, f.nome, f.licenca FROM plat.acervo_endpoint e "
        "JOIN acervo.fonte f ON f.fonte_id = e.fonte_id WHERE e.vivo ORDER BY e.fonte_id, e.url"
    )
    vistos: dict[tuple[str, str], dict] = {}
    for r in cur.fetchall():
        for tipo, base in tipos_da_url(r["url"]):
            chave = (tipo, base)
            if chave in vistos:
                continue
            vistos[chave] = {
                "slug": _slug(tipo, base), "orgao": r["orgao"], "nome": f"{r['nome']} ({tipo.upper()})",
                "tipo": tipo, "url": base, "licenca": r["licenca"], "origem": "registro", "fonte_id": r["fonte_id"],
            }
    return list(vistos.values())


def candidatos_da_semente(caminho: Path = SEMENTE) -> list[dict]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    saida = []
    for e in dados["entradas"]:
        if e["tipo"] not in TIPOS:
            raise ValueError(f"semente: tipo desconhecido {e['tipo']!r} em {e['url']}")
        saida.append({
            "slug": _slug(e["tipo"], e["url"]), "orgao": e["orgao"], "nome": e["nome"], "tipo": e["tipo"],
            "url": _base(e["url"]) if e["tipo"] != "stac" else e["url"].rstrip("/"),
            "licenca": e.get("licenca") or "nao-declarada", "origem": e.get("origem") or "curadoria",
            "fonte_id": e.get("fonte_id"),
        })
    return saida


def candidatos(cur) -> list[dict]:
    """semente + registro, sem repetir (tipo, url); a semente vence no nome/licença porque foi curada."""
    por_chave: dict[tuple[str, str], dict] = {}
    for c in candidatos_da_semente() + candidatos_do_registro(cur):
        por_chave.setdefault((c["tipo"], c["url"]), c)
    return list(por_chave.values())


def semear(cur) -> int:
    """upsert dos candidatos em plat.endpoint_publico (função SECURITY DEFINER da migração); devolve o total."""
    lista = candidatos(cur)
    cur.execute("SELECT plat.endpoint_publico_semear(%s::jsonb) AS n", (json.dumps(lista, ensure_ascii=False),))
    return int(cur.fetchone()["n"])


def registrar(cur, endpoint_id: int, r: ResultadoTeste) -> None:
    cur.execute(
        "SELECT plat.endpoint_publico_registrar(%s, %s, %s, %s, %s, %s)",
        (endpoint_id, r.vivo, r.http, r.content_type, r.ms, r.motivo),
    )
