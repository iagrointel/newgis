"""Arquivo por URL pública (item L6-02-h-csv-url-geojson-kml): baixa CSV, GeoJSON, KML, KMZ, GeoRSS ou GPX de
um endereço de terceiro e entrega ao pipeline de ingestão vetorial do L0-04, que já sabe virar camada.

Divisão de trabalho, para não duplicar nada:
  - a REDE é sempre `app.conexao.seguranca.buscar_seguro` (item L6-02-a). Este módulo nunca abre socket, nunca
    chama httpx/urllib direto. Endereço interno, redirecionamento para endereço interno e nome de DNS que
    resolve para a rede local são recusados lá, antes de qualquer byte ser lido.
  - o FORMATO é decidido pelos BYTES (nunca pela extensão da URL nem só pelo Content-Type, que servidor de
    arquivo estático erra o tempo todo).
  - a CONVERSÃO de KML/KMZ/GeoRSS/GPX para GeoJSON é `ogr2ogr` rodando como neto do job (o mesmo
    `ctx.subprocesso` da ingestão, com RLIMIT/timeout do worker) — nunca dentro do processo da API.
  - a CARGA é `app.ingestao.inspecionar`/`app.ingestao.carregar` sem alteração: depois da conversão, o que
    chega lá é um `geojson` ou um `csv`, dois dos 4 formatos que aquele item já entrega.

Atualização agendada sem recarregar igual: `condicionais()` monta `If-None-Match`/`If-Modified-Since` a partir
do que foi guardado na sincronização anterior; `HTTP 304` devolve `nao_modificado=True` e nada é recarregado.
Servidor que ignora o condicional e responde 200 com o mesmo conteúdo também não recarrega: o sha256 do corpo
é comparado com o da carga anterior (segunda linha de defesa, medida no teste).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field

from app import limites
from app.conexao import seguranca
from app.ingestao import csv_normalizar

# formato -> (precisa de conversão para GeoJSON?, driver GDAL, extensão do arquivo temporário)
CONVERSAO = {
    "csv": (False, "CSV", ".csv"),
    "geojson": (False, "GeoJSON", ".geojson"),
    "kml": (True, "LIBKML", ".kml"),
    "kmz": (True, "LIBKML", ".kmz"),
    "georss": (True, "GeoRSS", ".xml"),
    "gpx": (True, "GPX", ".gpx"),
}
# formatos que o GDAL lê carregando o documento XML inteiro na memória (medição em app/limites.py)
FORMATOS_XML = ("kml", "kmz", "georss", "gpx")


class ArquivoRecusado(ValueError):
    """Conteúdo que não vira camada: formato desconhecido, tamanho acima do teto, coordenada fora de faixa.
    A mensagem é o motivo em português, já pronto para o `erro` da importação e para a tela."""


@dataclass
class Baixado:
    ok: bool
    nao_modificado: bool
    status: int | None
    mensagem: str
    dados: bytes = b""
    sha256: str = ""
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None
    url_final: str = ""
    latencia_ms: int = 0


@dataclass
class Analise:
    formato: str
    precisa_converter: bool
    driver: str
    extensao: str
    avisos: list[str] = field(default_factory=list)


def condicionais(etag: str | None, last_modified: str | None) -> dict[str, str]:
    """Cabeçalhos condicionais da RFC 9110 §13: `If-None-Match` tem precedência sobre `If-Modified-Since` no
    servidor, e mandar os dois é o que um navegador faz. Sem nenhum dos dois guardados, devolve {} (a primeira
    sincronização sempre baixa)."""
    saida: dict[str, str] = {}
    if etag:
        saida["If-None-Match"] = etag
    if last_modified:
        saida["If-Modified-Since"] = last_modified
    return saida


def baixar(url: str, *, etag: str | None = None, last_modified: str | None = None,
           credencial: str | None = None, max_bytes: int = limites.CONEXAO_ARQUIVO_MAX_BYTES) -> Baixado:
    """Um GET condicional por `buscar_seguro`. Nunca levanta: recusa de segurança vira `ok=False` com o motivo
    em `mensagem` (`url_insegura:...`), do mesmo jeito que o teste de saúde do L6-02-a."""
    import hashlib

    cabecalhos = condicionais(etag, last_modified)
    if credencial:
        cabecalhos["Authorization"] = f"Bearer {credencial}"
    r = seguranca.buscar_seguro(
        url, metodo="GET", timeout_ler=limites.CONEXAO_ARQUIVO_LER_TIMEOUT_S, max_bytes=max_bytes,
        cabecalhos=cabecalhos, guardar_corpo=True,
    )
    if r.status == 304:
        return Baixado(ok=True, nao_modificado=True, status=304, mensagem="nao_modificado",
                       etag=etag, last_modified=last_modified, url_final=r.url_final, latencia_ms=r.latencia_ms)
    if not r.ok:
        return Baixado(ok=False, nao_modificado=False, status=r.status, mensagem=r.mensagem,
                       url_final=r.url_final, latencia_ms=r.latencia_ms)
    return Baixado(
        ok=True, nao_modificado=False, status=r.status, mensagem=r.mensagem, dados=r.corpo,
        sha256=hashlib.sha256(r.corpo).hexdigest(),
        etag=r.cabecalhos.get("etag"), last_modified=r.cabecalhos.get("last-modified"),
        content_type=(r.cabecalhos.get("content-type") or "").split(";")[0].strip() or None,
        url_final=r.url_final, latencia_ms=r.latencia_ms,
    )


def _e_xml_com_raiz(amostra: bytes, raizes: tuple[str, ...]) -> bool:
    texto = amostra[:8192].decode("utf-8", errors="replace").lower()
    if "<" not in texto:
        return False
    for raiz in raizes:
        if f"<{raiz}" in texto or f":{raiz} " in texto or f":{raiz}>" in texto:
            return True
    return False


def detectar_formato(dados: bytes, content_type: str | None = None, url: str = "") -> str:
    """Formato pelos BYTES. `content_type` e `url` só desempatam CSV de texto qualquer (último caso), nunca
    contradizem o conteúdo. Levanta `ArquivoRecusado` quando nada casa."""
    if not dados:
        raise ArquivoRecusado("o endereço respondeu com corpo vazio")
    amostra = dados[:65536]
    if dados[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(dados)) as zf:
                nomes = [n.lower() for n in zf.namelist()]
        except zipfile.BadZipFile as e:
            raise ArquivoRecusado(f"o endereço respondeu com um zip ilegível: {e}") from e
        if any(n.endswith(".kml") for n in nomes):
            return "kmz"
        raise ArquivoRecusado("o zip baixado não tem nenhum .kml dentro (KMZ é a única forma zipada aceita aqui)")
    inicio = amostra.lstrip()
    if inicio[:1] in (b"{", b"["):
        try:
            doc = json.loads(dados.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ArquivoRecusado(f"o endereço respondeu com JSON inválido: {e}") from e
        if isinstance(doc, dict) and doc.get("type") in (
            "FeatureCollection", "Feature", "Point", "LineString", "Polygon", "MultiPoint", "MultiLineString",
            "MultiPolygon", "GeometryCollection",
        ):
            return "geojson"
        raise ArquivoRecusado("o JSON baixado não é GeoJSON (falta o campo 'type' de GeoJSON na raiz)")
    if _e_xml_com_raiz(amostra, ("kml",)):
        return "kml"
    if _e_xml_com_raiz(amostra, ("gpx",)):
        return "gpx"
    if _e_xml_com_raiz(amostra, ("rss", "feed")):
        texto = amostra.decode("utf-8", errors="replace").lower()
        if "georss" in texto or "geo:lat" in texto or "geo/wgs84_pos" in texto:
            return "georss"
        raise ArquivoRecusado(
            "o endereço respondeu um RSS/Atom sem geometria GeoRSS (sem georss:point/georss:where nem geo:lat)"
        )
    if b"\x00" in amostra:
        raise ArquivoRecusado("o endereço respondeu um arquivo binário que não é KMZ")
    # texto sem estrutura conhecida: só vale como CSV se tiver cabeçalho e ao menos um separador
    texto = amostra.decode("utf-8", errors="replace")
    primeira = texto.splitlines()[0] if texto.splitlines() else ""
    if any(sep in primeira for sep in csv_normalizar.SEPARADORES):
        return "csv"
    raise ArquivoRecusado(
        "não foi possível reconhecer o formato do arquivo baixado; aceitos: "
        + ", ".join(limites.CONEXAO_ARQUIVO_FORMATOS)
    )


def analisar(dados: bytes, content_type: str | None = None, url: str = "") -> Analise:
    """Formato + o que fazer com ele + o teto de tamanho que vale para ESTE formato (o teto dos formatos XML é
    menor porque o driver do GDAL lê o documento inteiro na memória — ver a medição em `app/limites.py`)."""
    formato = detectar_formato(dados, content_type, url)
    precisa, driver, extensao = CONVERSAO[formato]
    if formato in FORMATOS_XML and len(dados) > limites.CONEXAO_ARQUIVO_XML_MAX_BYTES:
        raise ArquivoRecusado(
            f"arquivo {formato} de {len(dados) // (1024 * 1024)} MB acima do teto de "
            f"{limites.CONEXAO_ARQUIVO_XML_MAX_BYTES // (1024 * 1024)} MB para formatos XML "
            "(o GDAL lê o documento inteiro na memória; teto medido contra o limite de memória do job)"
        )
    return Analise(formato=formato, precisa_converter=precisa, driver=driver, extensao=extensao)


def conferir_faixa_coordenada(dados: bytes) -> None:
    """CSV com latitude e longitude TROCADAS (a refutação do item). O normalizador do L0-04 acha as colunas
    pelo NOME; se a coluna chamada `lat` tem valor 145, o pipeline criaria alegremente um ponto em latitude 145.
    Aqui a faixa é conferida e o arquivo é RECUSADO — nunca trocado sozinho: trocar por conta própria inventaria
    um dado que ninguém pediu, e um arquivo com as duas colunas dentro da faixa (por exemplo lat 10, lon 20,
    trocadas de verdade) é indistinguível de um arquivo correto, então o silêncio seria mentira.
    Só roda em CSV; nos outros formatos a coordenada vem do próprio esquema do arquivo."""
    resultado = csv_normalizar.normalizar_bytes(dados)
    if not resultado.coordenadas:
        return
    nome_x = resultado.coordenadas["x"]
    nome_y = resultado.coordenadas["y"]
    leitor = csv.DictReader(io.StringIO(resultado.texto))
    fora_lat: list[str] = []
    fora_lon: list[str] = []
    linhas = 0
    for linha in leitor:
        linhas += 1
        for nome, teto, fora in ((nome_y, limites.CONEXAO_ARQUIVO_LAT_MAX, fora_lat),
                                 (nome_x, limites.CONEXAO_ARQUIVO_LON_MAX, fora_lon)):
            bruto = (linha.get(nome) or "").strip()
            if not bruto:
                continue
            try:
                valor = float(bruto)
            except ValueError:
                continue
            if abs(valor) > teto and len(fora) < 5:
                fora.append(bruto)
    if fora_lat:
        troca = (
            " Os valores da coluna de latitude caberiam numa longitude: confira se as duas colunas estão "
            "trocadas no arquivo de origem. A plataforma não troca as colunas sozinha."
        ) if all(abs(float(v)) <= limites.CONEXAO_ARQUIVO_LON_MAX for v in fora_lat) else ""
        raise ArquivoRecusado(
            f"a coluna de latitude {nome_y!r} tem valor fora da faixa -90..90 (exemplos: {', '.join(fora_lat)}) "
            f"em {linhas} linhas lidas.{troca}"
        )
    if fora_lon:
        raise ArquivoRecusado(
            f"a coluna de longitude {nome_x!r} tem valor fora da faixa -180..180 "
            f"(exemplos: {', '.join(fora_lon)}) em {linhas} linhas lidas."
        )


def converter_para_geojson(ctx, dados: bytes, analise: Analise) -> bytes:
    """`ogr2ogr` como neto do job (`ctx.subprocesso`: RLIMIT de memória e timeout do worker já aplicados).
    Devolve os bytes do GeoJSON. Levanta `ArquivoRecusado` quando o GDAL não abre o arquivo."""
    origem = ctx.dir_trabalho / f"origem{analise.extensao}"
    origem.write_bytes(dados)
    destino = ctx.dir_trabalho / "convertido.geojson"
    argv = [
        "ogr2ogr", "-f", "GeoJSON", str(destino), str(origem),
        # -skipfailures: um Placemark sem geometria num KML de 200 mil não pode derrubar a camada inteira
        "-skipfailures",
    ]
    r = ctx.subprocesso(argv)
    if r.returncode != 0 or not destino.exists():
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        detalhe = (linhas[-1] if linhas else "sem detalhe")[:300]
        raise ArquivoRecusado(f"o GDAL não converteu o arquivo {analise.formato} para GeoJSON: {detalhe}")
    saida = destino.read_bytes()
    if not saida.strip():
        raise ArquivoRecusado(f"a conversão do arquivo {analise.formato} devolveu um GeoJSON vazio")
    return saida
