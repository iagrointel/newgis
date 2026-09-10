"""Ficha de procedência automática de uma camada publicada a partir de `plat.conexao` (item
L6-05-proveniencia-camada-externa). Regra da casa: "procedência errada é pior que nenhuma" — todo campo aqui
vem OU do que o próprio serviço declarou (lido agora, ao publicar) OU é `None` (a tela mostra "não registrado";
nunca um valor padrão inventado). O formato do dicionário é o mesmo `dados.procedencia` que `app/catalogo/
metadado.py` já lê para o `dataQualityInfo`/lineage do ISO 19139 e que `app/ingestao/carregar.py` já preenche
para `camada_vetorial` (fonte, url, licenca, data_do_dado, data_de_acesso, metodo, confianca, frescor) — aqui
somados sha256/comando_reexecucao (ADR 0012 "comando de reexecução" do acervo, mesma ideia aplicada à conexão).

Só lê o que o protocolo padroniza (WMS/WMTS/WFS: AccessConstraints/Title do GetCapabilities; ArcGIS REST:
`copyrightText`/`serviceDescription` de `?f=json`; STAC/OGC API: `license`/link `rel=license`); protocolos sem
metadado padronizado (postgres_fdw, s3, http, geoparquet, pmtiles) nunca são sondados — ficam `None` por
inteiro, nunca um palpite. A sondagem usa `seguranca.buscar_seguro` (o mesmo caminho auditado contra SSRF do
teste de saúde, nunca um cliente HTTP à parte) com `guardar_corpo=True` e o mesmo teto de bytes/tempo."""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError  # só o TIPO da exceção; o parse em si é sempre via defusedxml, abaixo

import defusedxml.ElementTree as ET_seguro

from app import limites
from app.conexao import seguranca

TIMEOUT_SONDA_S = 5.0
_PROTOCOLOS_XML = ("wms", "wmts", "wfs")
_PROTOCOLOS_JSON = ("esri_rest", "stac", "ogc_api")


@dataclass(frozen=True)
class Descoberta:
    procedencia: dict
    atribuicao: str | None  # vira `creditos` do item — o mais próximo de "legenda" que existe hoje (L6-02-b
    # ainda não desenha a camada no mapa; o crédito aparece na ficha do item, que é o que existe)


def _local(tag: str) -> str:
    """remove o namespace de uma tag `{ns}Nome` -> `Nome` (WMS 1.1.1 sem ns, 1.3.0 com ns — os dois casam)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _primeiro_texto(raiz, nome: str) -> str | None:
    for el in raiz.iter():
        if _local(el.tag) == nome and el.text and el.text.strip():
            return " ".join(el.text.split())
    return None


def _url_capacidades(url: str, protocolo: str) -> str:
    """anexa `SERVICE=<...>&REQUEST=GetCapabilities` só quando a URL ainda não parece uma (o usuário pode já
    ter colado a URL de capacidades inteira, com querystring)."""
    if "getcapabilities" in url.lower():
        return url
    servico = {"wms": "WMS", "wmts": "WMTS", "wfs": "WFS"}[protocolo]
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}SERVICE={servico}&REQUEST=GetCapabilities"


def _sondar_xml(url: str, protocolo: str) -> tuple[dict, str | None, str, bytes]:
    alvo = _url_capacidades(url, protocolo)
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=TIMEOUT_SONDA_S,
        max_bytes=limites.CONEXAO_RESPOSTA_MAX_BYTES, guardar_corpo=True,
    )
    if not r.ok or not r.corpo:
        return {"licenca": None, "fonte": None}, None, alvo, b""
    try:
        raiz = ET_seguro.fromstring(r.corpo)  # nunca resolve entidade externa (defusedxml)
    except (ParseError, ValueError):
        return {"licenca": None, "fonte": None}, None, alvo, r.corpo
    licenca = _primeiro_texto(raiz, "AccessConstraints")
    if licenca and licenca.lower() in ("none", "nenhuma", "n/a", "no conditions apply"):
        licenca = None  # o próprio serviço diz "sem restrição declarada" — não é uma licença, é a ausência dela
    fees = _primeiro_texto(raiz, "Fees")
    titulo = _primeiro_texto(raiz, "Title")
    return {"licenca": licenca, "fonte": titulo, "fees": fees}, titulo, alvo, r.corpo


def _sondar_json(url: str, protocolo: str) -> tuple[dict, str | None, str, bytes]:
    alvo = url
    if protocolo == "esri_rest" and "f=json" not in url.lower():
        separador = "&" if "?" in url else "?"
        alvo = f"{url}{separador}f=json"
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=TIMEOUT_SONDA_S,
        max_bytes=limites.CONEXAO_RESPOSTA_MAX_BYTES, guardar_corpo=True,
    )
    if not r.ok or not r.corpo:
        return {"licenca": None, "fonte": None}, None, alvo, b""
    try:
        doc = json.loads(r.corpo.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"licenca": None, "fonte": None}, None, alvo, r.corpo
    if not isinstance(doc, dict):
        return {"licenca": None, "fonte": None}, None, alvo, r.corpo
    if protocolo == "esri_rest":
        licenca = doc.get("copyrightText") or None
        fonte = doc.get("serviceDescription") or doc.get("description") or doc.get("name") or None
        return {"licenca": licenca or None, "fonte": fonte}, licenca or fonte, alvo, r.corpo
    if protocolo == "stac":
        licenca = doc.get("license") or None
        fonte = doc.get("title") or doc.get("id") or None
        return {"licenca": licenca, "fonte": fonte}, licenca, alvo, r.corpo
    # ogc_api: license pode vir solto ou como link rel=license (Part 1 do OGC API - Records/Features)
    licenca = doc.get("license") or None
    if not licenca:
        for link in doc.get("links") or []:
            if isinstance(link, dict) and link.get("rel") == "license":
                licenca = link.get("title") or link.get("href")
                break
    fonte = doc.get("title") or doc.get("id") or None
    return {"licenca": licenca, "fonte": fonte}, licenca, alvo, r.corpo


def descobrir(conexao: dict) -> Descoberta:
    """`conexao` é a linha de `plat.conexao` (precisa de `tipo`, `url`, `saude`, `saude_verificada_em`).
    Nunca levanta: qualquer falha de rede/parse vira campo `None`, documentada em `limites` da procedência —
    a publicação da camada NUNCA fica bloqueada por o serviço externo estar fora do ar ou não declarar nada."""
    tipo, url = conexao["tipo"], conexao["url"]
    achados: dict = {"licenca": None, "fonte": None}
    atribuicao: str | None = None
    url_sondada: str | None = None
    corpo = b""
    avisos: list[str] = []
    if tipo in _PROTOCOLOS_XML:
        achados, atribuicao, url_sondada, corpo = _sondar_xml(url, tipo)
    elif tipo in _PROTOCOLOS_JSON:
        achados, atribuicao, url_sondada, corpo = _sondar_json(url, tipo)
    else:
        avisos.append(
            f"protocolo {tipo!r} não tem metadado padronizado sondável; ficha só com o que a conexão já guarda"
        )

    if url_sondada and not corpo:
        avisos.append(f"{url_sondada}: o serviço não respondeu (ou respondeu vazio) no momento da publicação")
    elif url_sondada and achados.get("licenca") is None:
        avisos.append(f"{url_sondada}: o serviço respondeu mas não declara licença/AccessConstraints/copyrightText")

    saude = conexao.get("saude")
    verificada_em = conexao.get("saude_verificada_em")
    if saude == "ok":
        frescor = f"conexão referenciada; saúde ok na última verificação ({verificada_em})" if verificada_em else \
            "conexão referenciada; ainda sem teste de saúde registrado"
    elif saude == "erro":
        frescor = (
            f"conexão referenciada; ÚLTIMA VERIFICAÇÃO DE SAÚDE FALHOU ({verificada_em}) — "
            "a camada pode estar servindo dado velho ou fora do ar"
        )
    else:
        frescor = "conexão referenciada; nunca testada"

    procedencia = {
        "fonte": achados.get("fonte"),
        "url": url,
        "licenca": achados.get("licenca"),
        "data_do_dado": None,        # camada REFERENCIADA (nunca copiada): não há "data do dado", é ao vivo
        "data_de_acesso": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "metodo": f"sondagem automática do protocolo {tipo} ao publicar (GetCapabilities/f=json/license)"
                  if url_sondada else "sem sondagem automática para este protocolo",
        "confianca": "declarado" if achados.get("licenca") or achados.get("fonte") else None,
        "frescor": frescor,
        "sha256": hashlib.sha256(corpo).hexdigest() if corpo else None,
        "comando_reexecucao": f"GET {url_sondada}" if url_sondada else None,
        "limites": avisos or None,
        "responsavel": None,
    }
    # Conexão criada por catálogo CSW (item L6-06): o registro ISO 19139 lido na criação fica em
    # `config.procedencia`. O que o serviço VIVO declara agora vence; o que ele não declara (licença, data do
    # dado, responsável, frescor...) vem do registro — nunca de um padrão. O `metodo` diz de onde veio cada parte.
    iso = (conexao.get("config") or {}).get("procedencia") if isinstance(conexao.get("config"), dict) else None
    if isinstance(iso, dict):
        preenchidos = []
        for chave, valor in iso.items():
            if chave == "limites" or valor in (None, "", [], {}):
                continue
            if procedencia.get(chave) is None:
                procedencia[chave] = valor
                preenchidos.append(chave)
        if preenchidos:
            procedencia["metodo"] = (
                f"{procedencia['metodo']}; campos {', '.join(preenchidos)} preenchidos do registro ISO 19139 "
                f"do catálogo CSW ({(iso.get('catalogo') or {}).get('url') or 'origem não registrada'})"
            )
        if iso.get("limites"):
            procedencia["limites"] = (procedencia.get("limites") or []) + [f"registro ISO: {a}" for a in iso["limites"]]
        if atribuicao is None:
            atribuicao = iso.get("responsavel") or iso.get("fonte")
    return Descoberta(procedencia=procedencia, atribuicao=atribuicao)
