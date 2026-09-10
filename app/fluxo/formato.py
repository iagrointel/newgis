"""Corpo recebido → lista de registros (item L2-14-a-ingestao-de-fluxos).

Formatos: `json` (objeto ou lista), `ndjson` (um objeto por linha), `csv` (cabeçalho na primeira linha),
`geojson` (Feature ou FeatureCollection: as propriedades viram o registro e a geometria entra sob a chave
`geometry`, para o mapeamento de geometria poder apontar para ela), `gpx` (trkpt/wpt do GPS de frota) e
`esri_json` (resposta de FeatureServer/`f=json` da sondagem: `features[].attributes` + `.geometry`).

Nada aqui olha o mapeamento: a decodificação é só de FORMATO. Todo limite de tamanho é conferido ANTES de
decodificar o corpo inteiro (o corpo já vem cortado pelo receptor) e o número de registros tem teto próprio.
"""

from __future__ import annotations

import csv
import io
import json
from xml.etree import ElementTree

from app import limites

FORMATOS = ("json", "ndjson", "csv", "geojson", "gpx", "esri_json")


class ErroFormato(ValueError):
    def __init__(self, motivo: str, detalhe: str = ""):
        super().__init__(detalhe or motivo)
        self.motivo = motivo
        self.detalhe = detalhe or motivo


def _texto(corpo: bytes) -> str:
    try:
        return corpo.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ErroFormato("corpo_nao_utf8", "o corpo tem de ser UTF-8") from e


def _carregar_json(texto: str):
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, RecursionError) as e:
        raise ErroFormato("json_invalido", f"JSON inválido: {str(e)[:120]}") from e


def _lista(registros: list) -> list:
    if len(registros) > limites.FLUXO_LOTE_MAX:
        raise ErroFormato("lote_grande_demais",
                          f"o lote passa de {limites.FLUXO_LOTE_MAX} eventos ({len(registros)})")
    return registros


def _de_geojson(dados) -> list:
    if not isinstance(dados, dict):
        raise ErroFormato("geojson_invalido", "GeoJSON tem de ser objeto")
    tipo = dados.get("type")
    if tipo == "FeatureCollection":
        feicoes = dados.get("features")
        if not isinstance(feicoes, list):
            raise ErroFormato("geojson_invalido", "FeatureCollection sem features")
    elif tipo == "Feature":
        feicoes = [dados]
    else:
        raise ErroFormato("geojson_invalido", "GeoJSON tem de ser Feature ou FeatureCollection")
    saida = []
    for f in feicoes:
        if not isinstance(f, dict):
            raise ErroFormato("geojson_invalido", "feature tem de ser objeto")
        props = f.get("properties")
        registro = dict(props) if isinstance(props, dict) else {}
        registro["geometry"] = f.get("geometry")
        if f.get("id") is not None:
            registro.setdefault("id", f["id"])
        saida.append(registro)
    return saida


def _de_esri_json(dados) -> list:
    if not isinstance(dados, dict) or not isinstance(dados.get("features"), list):
        raise ErroFormato("esri_json_invalido", "resposta sem a lista features")
    saida = []
    for f in dados["features"]:
        if not isinstance(f, dict):
            raise ErroFormato("esri_json_invalido", "feature tem de ser objeto")
        atributos = f.get("attributes")
        registro = dict(atributos) if isinstance(atributos, dict) else {}
        g = f.get("geometry")
        if isinstance(g, dict) and "x" in g and "y" in g:
            registro["geometry"] = {"type": "Point", "coordinates": [g["x"], g["y"]]}
            registro.setdefault("x", g["x"])
            registro.setdefault("y", g["y"])
        saida.append(registro)
    return saida


def _de_gpx(texto: str) -> list:
    """trkpt e wpt do GPX 1.1 (GPS de frota). Namespace declarado ou não — o nome local é o que decide."""
    try:
        raiz = ElementTree.fromstring(texto)  # noqa: S314 — XML de fonte declarada; sem entidade externa
    except ElementTree.ParseError as e:
        raise ErroFormato("gpx_invalido", f"GPX inválido: {str(e)[:120]}") from e
    saida = []
    for elemento in raiz.iter():
        local = elemento.tag.rsplit("}", 1)[-1]
        if local not in ("trkpt", "wpt", "rtept"):
            continue
        registro = {"lat": elemento.get("lat"), "lon": elemento.get("lon")}
        for filho in elemento:
            nome = filho.tag.rsplit("}", 1)[-1]
            if filho.text is not None and not len(filho):
                registro[nome] = filho.text.strip()
        saida.append(registro)
    return saida


def _de_csv(texto: str) -> list:
    leitor = csv.DictReader(io.StringIO(texto))
    if leitor.fieldnames is None:
        raise ErroFormato("csv_sem_cabecalho", "o CSV tem de ter uma linha de cabeçalho")
    if len(leitor.fieldnames) > limites.FLUXO_CAMPOS_MAX:
        raise ErroFormato("csv_colunas_demais", f"o CSV passa de {limites.FLUXO_CAMPOS_MAX} colunas")
    saida = []
    for linha in leitor:
        if len(saida) > limites.FLUXO_LOTE_MAX:
            break
        saida.append({k: v for k, v in linha.items() if k is not None})
    return saida


def decodificar(corpo: bytes, formato: str) -> list:
    """Corpo bruto → lista de registros. Levanta ErroFormato com motivo estável."""
    if formato not in FORMATOS:
        raise ErroFormato("formato_nao_suportado", f"formato tem de ser um de {', '.join(FORMATOS)}")
    if len(corpo) > limites.FLUXO_CORPO_MAX_BYTES:
        raise ErroFormato("corpo_grande_demais",
                          f"o corpo passa de {limites.FLUXO_CORPO_MAX_BYTES} bytes ({len(corpo)})")
    texto = _texto(corpo)
    if formato == "json":
        dados = _carregar_json(texto)
        if isinstance(dados, dict):
            dados = [dados]
        if not isinstance(dados, list):
            raise ErroFormato("json_invalido", "o corpo tem de ser um objeto ou uma lista de objetos")
        return _lista(dados)
    if formato == "ndjson":
        return _lista([_carregar_json(linha) for linha in texto.splitlines() if linha.strip()])
    if formato == "csv":
        return _lista(_de_csv(texto))
    if formato == "geojson":
        return _lista(_de_geojson(_carregar_json(texto)))
    if formato == "esri_json":
        return _lista(_de_esri_json(_carregar_json(texto)))
    return _lista(_de_gpx(texto))
