"""Servidor OGC local para o teste do item L6-02-c-wfs-ogcapi: um WFS 2.0 e um OGC API - Features de verdade,
no loopback, servindo um conjunto sintético de N feições com atributos de tipo declarado.

Por que local: a regra do laço é que a suíte NUNCA dependa de serviço de terceiro para passar. Um WFS público
fora do ar (ou lento, ou com o nosso endereço bloqueado) reprovaria um código correto — e um teste que
reprova por motivo alheio deixa de ser prova. Os serviços públicos reais entram como MEDIDA registrada
(`tests/medidas/L6-02-c-wfs-ogcapi.json`), não como condição do verde.

O que ele implementa, com fidelidade suficiente para o conector:
  WFS 2.0 (`/wfs`)   GetCapabilities (FeatureTypeList + outputFormat do GetFeature), DescribeFeatureType (XSD
                     com os tipos declarados), GetFeature com COUNT/STARTINDEX/BBOX, RESULTTYPE=hits
                     (`numberMatched`), saída em `application/json` e em GML 3.2.
  OGC API (`/ogc`)   `/collections`, `/collections/{id}/queryables` (JSON Schema), `/collections/{id}/items`
                     com `limit`, `bbox`, `datetime`, `numberMatched`/`numberReturned` e link `rel=next`.

Modos de má-fé (a refutação do item):
  `ignora_paginacao=True`  o servidor devolve SEMPRE as mesmas `pagina_forcada` feições, qualquer que sejam
                           COUNT/STARTINDEX/limit, e declara `numberMatched` = `matched_declarado`
                           (5.000.000 no teste). É o WFS que o adversário aponta.

CRS: o WFS entrega em EPSG:31983 (SIRGAS 2000 / UTM 23S — coordenadas em metros), justamente para que a
reprojeção para 4326 feita pela cópia seja verificável (um erro de CRS põe a camada no meio do Atlântico).
O OGC API entrega em CRS84, como manda a Parte 1 do padrão.
"""

from __future__ import annotations

import datetime
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

COLECAO = "pontos"
SRID_WFS = 31983
X0, Y0, PASSO = 300000.0, 7400000.0, 50.0     # UTM 23S, dentro de São Paulo
LON0, LAT0, PASSO_GRAU = -47.9, -15.8, 0.001  # CRS84, dentro do Distrito Federal
COLUNAS = 200

# tipos DECLARADOS (é isso que o conector tem de preservar na tabela)
CAMPOS_XSD = [("nome", "xsd:string"), ("quantia", "xsd:int"), ("medida", "xsd:double"),
              ("ativo", "xsd:boolean"), ("dia", "xsd:date")]
CAMPOS_JSON = [("nome", {"type": "string"}), ("quantia", {"type": "integer"}),
               ("medida", {"type": "number"}), ("ativo", {"type": "boolean"}),
               ("dia", {"type": "string", "format": "date"})]


def atributos(i: int) -> dict:
    dia = datetime.date(2026, 1, 1) + datetime.timedelta(days=i % 365)
    return {"nome": f"ponto {i}", "quantia": i % 1000, "medida": round(i * 0.5, 2),
            "ativo": i % 2 == 0, "dia": dia.isoformat()}


def xy_utm(i: int) -> tuple[float, float]:
    return X0 + (i % COLUNAS) * PASSO, Y0 + (i // COLUNAS) * PASSO


def lonlat(i: int) -> tuple[float, float]:
    return round(LON0 + (i % COLUNAS) * PASSO_GRAU, 6), round(LAT0 + (i // COLUNAS) * PASSO_GRAU, 6)


class ServidorOGC:
    """Sobe numa porta livre do loopback; `parar()` no fim do teste. `pedidos` guarda o que o conector pediu —
    é assim que o teste prova que a paginação usou STARTINDEX/COUNT de verdade, e não uma chamada só."""

    def __init__(self, total: int = 1000, *, ignora_paginacao: bool = False,
                 matched_declarado: int | None = None, pagina_forcada: int = 0,
                 declara_json: bool = True, porta: int = 0):
        self.total = total
        self.ignora_paginacao = ignora_paginacao
        self.matched_declarado = matched_declarado
        self.pagina_forcada = pagina_forcada or min(total, 50)
        self.declara_json = declara_json
        self.pedidos: list[tuple[str, dict]] = []
        self._trava = threading.Lock()
        servidor_self = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_a):  # o servidor de teste não polui a saída do pytest
                return

            def do_GET(self):  # noqa: N802 — nome exigido por BaseHTTPRequestHandler
                partes = urlsplit(self.path)
                q = {k.lower(): v[0] for k, v in parse_qs(partes.query).items()}
                with servidor_self._trava:
                    servidor_self.pedidos.append((partes.path, q))
                try:
                    corpo, tipo = servidor_self.responder(partes.path, q)
                except ValueError as e:
                    corpo, tipo = str(e).encode("utf-8"), "text/plain; charset=utf-8"
                    self.send_response(404)
                    self.send_header("Content-Type", tipo)
                    self.send_header("Content-Length", str(len(corpo)))
                    self.end_headers()
                    self.wfile.write(corpo)
                    return
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

        # `porta` vem de um lote reservado no início do módulo de teste (ver a fixture `portas_ogc`): a
        # válvula `PLAT_TESTE_CONEXAO_ALVOS` precisa listar o par host:porta ANTES de o worker subir, e o
        # worker herda o ambiente uma vez só. Com porta 0 (efêmera) cada servidor exigiria um worker novo.
        self.http = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
        self.porta = self.http.server_address[1]
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    # ------------------------------------------------------------------ endereços
    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    @property
    def url_wfs(self) -> str:
        return f"{self.base}/wfs"

    @property
    def url_ogc(self) -> str:
        return f"{self.base}/ogc"

    @property
    def alvo(self) -> str:
        return f"127.0.0.1:{self.porta}"

    def parar(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)

    # ------------------------------------------------------------------ despacho
    def responder(self, caminho: str, q: dict) -> tuple[bytes, str]:
        if caminho.rstrip("/") == "/wfs":
            return self._wfs(q)
        if caminho.rstrip("/") == "/ogc":
            return self._json({"title": "OGC API de teste", "links": []})
        if caminho.rstrip("/") == "/ogc/collections":
            return self._json({"collections": [self._colecao_ogc()], "links": []})
        if caminho.rstrip("/") == f"/ogc/collections/{COLECAO}":
            return self._json(self._colecao_ogc())
        if caminho.rstrip("/") == f"/ogc/collections/{COLECAO}/queryables":
            return self._json({
                "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
                "properties": dict(CAMPOS_JSON),
            })
        if caminho.rstrip("/") == f"/ogc/collections/{COLECAO}/items":
            return self._itens_ogc(q)
        raise ValueError(f"caminho desconhecido: {caminho}")

    def _json(self, doc: dict) -> tuple[bytes, str]:
        return json.dumps(doc, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"

    def _matched(self) -> int:
        return self.matched_declarado if self.matched_declarado is not None else self.total

    # ------------------------------------------------------------------ OGC API - Features
    def _colecao_ogc(self) -> dict:
        x1, y1 = lonlat(max(self.total - 1, 0))
        return {
            "id": COLECAO, "title": "Pontos de teste",
            "extent": {"spatial": {"bbox": [[LON0, LAT0, x1, y1]], "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
            "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
            "storageCrs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            "links": [{"rel": "items", "type": "application/geo+json",
                       "href": f"{self.url_ogc}/collections/{COLECAO}/items"}],
        }

    def _itens_ogc(self, q: dict) -> tuple[bytes, str]:
        limite = int(q.get("limit") or 10)
        deslocamento = int(q.get("offset") or 0)
        indices = self._indices(limite, deslocamento, q.get("bbox"), q.get("datetime"), grau=True)
        feicoes = []
        for i in indices:
            lon, lat = lonlat(i)
            feicoes.append({"type": "Feature", "id": f"{COLECAO}.{i + 1}",
                            "geometry": {"type": "Point", "coordinates": [lon, lat]},
                            "properties": atributos(i)})
        doc = {"type": "FeatureCollection", "features": feicoes,
               "numberMatched": self._matched(), "numberReturned": len(feicoes), "links": []}
        proximo = deslocamento + len(feicoes)
        # em `ignora_paginacao` o link `rel=next` vem SEMPRE: é assim que o serviço de má-fé faz o cliente
        # ingênuo girar para sempre devolvendo o mesmo bloco. A trava de repetição do Paginador é o que corta.
        if self.ignora_paginacao or proximo < self._universo(q.get("bbox"), q.get("datetime"), grau=True):
            consulta = f"limit={limite}&offset={proximo}"
            if q.get("bbox"):
                consulta += f"&bbox={q['bbox']}"
            if q.get("datetime"):
                consulta += f"&datetime={q['datetime']}"
            doc["links"].append({"rel": "next", "type": "application/geo+json",
                                 "href": f"{self.url_ogc}/collections/{COLECAO}/items?{consulta}"})
        return self._json(doc)

    # ------------------------------------------------------------------ WFS 2.0
    def _wfs(self, q: dict) -> tuple[bytes, str]:
        pedido = (q.get("request") or "").lower()
        if pedido == "getcapabilities":
            return self._capacidades(), "text/xml; charset=utf-8"
        if pedido == "describefeaturetype":
            return self._xsd(), "text/xml; charset=utf-8"
        if pedido == "getfeature":
            if (q.get("resulttype") or "results").lower() == "hits":
                corpo = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
                    f'timeStamp="{datetime.datetime.now(datetime.UTC).isoformat()}" '
                    f'numberMatched="{self._matched()}" numberReturned="0"/>'
                )
                return corpo.encode("utf-8"), "text/xml; charset=utf-8"
            formato = (q.get("outputformat") or "").lower()
            if formato in ("application/json", "application/geo+json", "json", "geojson"):
                return self._getfeature_json(q)
            return self._getfeature_gml(q)
        raise ValueError(f"REQUEST desconhecido: {pedido}")

    def _capacidades(self) -> bytes:
        formatos = ["application/gml+xml; version=3.2"]
        if self.declara_json:
            formatos.insert(0, "application/json")
        valores = "".join(f"<ows:Value>{f}</ows:Value>" for f in formatos)
        x1, y1 = lonlat(max(self.total - 1, 0))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            'xmlns:ows="http://www.opengis.net/ows/1.1" xmlns:t="http://plat.teste/ogc">'
            '<ows:OperationsMetadata>'
            '<ows:Operation name="GetFeature">'
            f'<ows:Parameter name="outputFormat"><ows:AllowedValues>{valores}</ows:AllowedValues></ows:Parameter>'
            '</ows:Operation></ows:OperationsMetadata>'
            '<wfs:FeatureTypeList><wfs:FeatureType>'
            f'<wfs:Name>t:{COLECAO}</wfs:Name><wfs:Title>Pontos de teste</wfs:Title>'
            f'<wfs:DefaultCRS>urn:ogc:def:crs:EPSG::{SRID_WFS}</wfs:DefaultCRS>'
            f'<ows:WGS84BoundingBox><ows:LowerCorner>{LON0} {LAT0}</ows:LowerCorner>'
            f'<ows:UpperCorner>{x1} {y1}</ows:UpperCorner></ows:WGS84BoundingBox>'
            '</wfs:FeatureType></wfs:FeatureTypeList></wfs:WFS_Capabilities>'
        ).encode("utf-8")

    def _xsd(self) -> bytes:
        elementos = "".join(
            f'<xsd:element maxOccurs="1" minOccurs="0" name="{nome}" nillable="true" type="{tipo}"/>'
            for nome, tipo in CAMPOS_XSD
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:gml="http://www.opengis.net/gml/3.2" '
            'targetNamespace="http://plat.teste/ogc" elementFormDefault="qualified">'
            f'<xsd:complexType name="{COLECAO}Type"><xsd:complexContent>'
            '<xsd:extension base="gml:AbstractFeatureType"><xsd:sequence>'
            f'{elementos}'
            '<xsd:element maxOccurs="1" minOccurs="0" name="geom" nillable="true" '
            'type="gml:PointPropertyType"/>'
            '</xsd:sequence></xsd:extension></xsd:complexContent></xsd:complexType>'
            f'<xsd:element name="{COLECAO}" substitutionGroup="gml:AbstractFeature" type="{COLECAO}Type"/>'
            '</xsd:schema>'
        ).encode("utf-8")

    def _getfeature_json(self, q: dict) -> tuple[bytes, str]:
        indices, matched = self._pagina_wfs(q)
        feicoes = []
        for i in indices:
            x, y = xy_utm(i)
            feicoes.append({"type": "Feature", "id": f"{COLECAO}.{i + 1}",
                            "geometry": {"type": "Point", "coordinates": [x, y]},
                            "properties": atributos(i)})
        doc = {"type": "FeatureCollection", "features": feicoes, "numberMatched": matched,
               "numberReturned": len(feicoes),
               "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{SRID_WFS}"}}}
        return self._json(doc)

    def _getfeature_gml(self, q: dict) -> tuple[bytes, str]:
        indices, matched = self._pagina_wfs(q)
        membros = []
        for i in indices:
            x, y = xy_utm(i)
            a = atributos(i)
            membros.append(
                f'<wfs:member><t:{COLECAO} gml:id="{COLECAO}.{i + 1}">'
                f'<t:nome>{a["nome"]}</t:nome><t:quantia>{a["quantia"]}</t:quantia>'
                f'<t:medida>{a["medida"]}</t:medida><t:ativo>{"true" if a["ativo"] else "false"}</t:ativo>'
                f'<t:dia>{a["dia"]}</t:dia>'
                f'<t:geom><gml:Point srsName="urn:ogc:def:crs:EPSG::{SRID_WFS}" gml:id="g.{i + 1}">'
                f'<gml:pos>{x} {y}</gml:pos></gml:Point></t:geom>'
                f'</t:{COLECAO}></wfs:member>'
            )
        corpo = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            'xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:t="http://plat.teste/ogc" '
            f'numberMatched="{matched}" numberReturned="{len(indices)}">'
            + "".join(membros) + "</wfs:FeatureCollection>"
        )
        return corpo.encode("utf-8"), "text/xml; charset=utf-8"

    # ------------------------------------------------------------------ paginação e filtros
    def _pagina_wfs(self, q: dict) -> tuple[list[int], int]:
        count = int(q.get("count") or 10)
        start = int(q.get("startindex") or 0)
        indices = self._indices(count, start, q.get("bbox"), None, grau=False)
        return indices, self._matched()

    def _universo(self, bbox: str | None, datahora: str | None, *, grau: bool) -> int:
        return len(self._todos(bbox, datahora, grau=grau))

    def _todos(self, bbox: str | None, datahora: str | None, *, grau: bool) -> list[int]:
        indices = range(self.total)
        if bbox:
            partes = [float(v) for v in bbox.split(",")[:4]]
            if grau:
                indices = [i for i in indices
                           if partes[0] <= lonlat(i)[0] <= partes[2] and partes[1] <= lonlat(i)[1] <= partes[3]]
            else:
                # BBOX do WFS chega em CRS84 (o conector escreve o CRS na requisição); compara em graus
                indices = [i for i in indices
                           if partes[0] <= lonlat(i)[0] <= partes[2] and partes[1] <= lonlat(i)[1] <= partes[3]]
        if datahora:
            de, _, ate = datahora.partition("/")
            ate = ate or de
            indices = [i for i in indices if de[:10] <= atributos(i)["dia"] <= ate[:10]]
        return list(indices)

    def _indices(self, quantos: int, deslocamento: int, bbox: str | None, datahora: str | None,
                 *, grau: bool) -> list[int]:
        todos = self._todos(bbox, datahora, grau=grau)
        if self.ignora_paginacao:
            # má-fé do adversário: ignora quantos/deslocamento e devolve SEMPRE o mesmo bloco
            return todos[: self.pagina_forcada]
        return todos[deslocamento: deslocamento + quantos]
