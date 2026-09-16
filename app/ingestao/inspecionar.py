"""Job `ingestao.inspecionar` (ADR 0005 seção 4, L0-04-b/d; formatos ampliados pelo L6-02-o-importacao-
exportacao-formatos): baixa o objeto, roda `ogrinfo -ro -json -so`, resolve geometria/CRS/codificação/campos por
CAMADA (nunca só a primeira — item L0-04-b "GPKG com 3 camadas"/"KMZ com 3 pastas"), amostra a validade
(shapely, sem depender de dialeto SQLite do GDAL) e grava a PROPOSTA editável em `plat.importacao.proposta`
(estado `proposta`). Nunca cria tabela: só a confirmação do usuário dispara a carga.
14 formatos de importação hoje: shapefile.zip, gpkg, geojson, csv (fundação) + geojsonseq, kml, kmz, gpx, dxf,
dwg, filegdb.zip/gdb, xlsx, gml, flatgeobuf — ver `app/ingestao/formatos.py` para o que cada um prova por
conteúdo e o driver GDAL usado. Achados da re-triagem de 16/09: (a) wt/f2fixapi2 já tinha restaurado
geojsonseq/kml/filegdb.zip/xlsx perdidos na fusão dos 198 ramos (31a35ae57); (b) esta passagem restaurou os
que faltavam do portão do L0-04-d/L0-04-b (kmz/gpx/gml/flatgeobuf) e a listagem de TODAS as camadas do arquivo
(`proposta["camadas"]`, `_analisar_camada()`), que a fusão nunca trouxe de `wt/g3fix`."""

from __future__ import annotations

import json
import uuid

import psycopg2.extras
import pyproj
from pydantic import BaseModel
from shapely.geometry import shape
from shapely.validation import explain_validity

from app import limites, objetos
from app.ingestao import cad, csv_normalizar, formatos, geometria, nomes, tipos_campo
from app.jobs.registro import FalhaDefinitiva, tarefa

AMOSTRA_VALIDADE = limites.INGESTAO_AMOSTRA_VALIDADE
BRASIL_BBOX = (-76.0, -34.5, -27.0, 6.0)  # (lonmin, latmin, lonmax, latmax) com folga
CAMPOS_MAX = limites.INGESTAO_CAMPOS_MAX


class InspecionarParametros(BaseModel):
    importacao_id: uuid.UUID


def tabela_de(item_id) -> str:
    return "c_" + uuid.UUID(str(item_id)).hex[:16]


def _extent_sugere_srid(extent: list[float] | None) -> int | None:
    if extent is None:
        return None
    xmin, ymin, xmax, ymax = extent
    if not (-180 <= xmin <= 180 and -180 <= xmax <= 180 and -90 <= ymin <= 90 and -90 <= ymax <= 90):
        return None  # provavelmente projetado (metros); a zona UTM fica para o L0-04-d completo
    lxmin, lymin, lxmax, lymax = BRASIL_BBOX
    if lxmin <= xmin and xmax <= lxmax and lymin <= ymin and ymax <= lymax:
        return 4674
    return 4326


def _cfg(config: list[str] | None) -> list[str]:
    """`--config CHAVE VALOR` repetido. O driver DXF do GDAL ignora `-oo` para DXF_INLINE_BLOCKS e
    DXF_ENCODING (MEDIDO, ADR 0020 seção 3): só a opção de configuração vale."""
    argv = []
    for par in config or []:
        chave, _, valor = par.partition("=")
        argv += ["--config", chave, valor]
    return argv


def _ogrinfo_json(ctx, caminho: str, layer: str | None, oo: list[str], config: list[str] | None = None) -> dict:
    argv = ["ogrinfo", "-ro", "-json", "-so", *_cfg(config)]
    for o in oo:
        argv += ["-oo", o]
    argv.append(caminho)
    if layer:
        argv.append(layer)
    r = ctx.subprocesso(argv)
    if r.returncode != 0:
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        raise FalhaDefinitiva(f"o GDAL não abriu o arquivo: {(linhas[-1] if linhas else 'sem detalhe')[:200]}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise FalhaDefinitiva(f"ogrinfo não devolveu JSON válido: {e}") from e


def _tipos_por_varredura(ctx, caminho: str, layer: str, oo: list[str],
                         config: list[str] | None = None) -> dict[str, int]:
    argv = ["ogrinfo", "-ro", "-json", *_cfg(config)]
    for o in oo:
        argv += ["-oo", o]
    argv += ["-dialect", "OGRSQL", "-sql", f'SELECT OGR_GEOMETRY, COUNT(*) AS n FROM "{layer}" GROUP BY OGR_GEOMETRY',
             caminho]
    r = ctx.subprocesso(argv)
    if r.returncode != 0:
        return {}
    try:
        dados = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {}
    saida: dict[str, int] = {}
    for camada in dados.get("layers", []):
        for feicao in camada.get("features", []):
            props = feicao.get("properties", {})
            tipo = props.get("OGR_GEOMETRY") or "NULL"
            saida[tipo] = saida.get(tipo, 0) + int(props.get("n", 0))
    return saida


def _amostra_validade(ctx, caminho: str, layer: str | None, oo: list[str],
                      config: list[str] | None = None) -> tuple[int, int, str | None]:
    """(amostra, invalidas, exemplo) lendo até AMOSTRA_VALIDADE feições como GeoJSON e checando com shapely
    (evita depender do dialeto SQLite/SpatiaLite do GDAL)."""
    argv = ["ogr2ogr", "-f", "GeoJSON", "/vsistdout/", *_cfg(config)]
    for o in oo:
        argv += ["-oo", o]
    argv += ["-limit", str(AMOSTRA_VALIDADE), caminho]
    if layer:
        argv.append(layer)
    r = ctx.subprocesso(argv)
    if r.returncode != 0 or not (r.stdout or "").strip():
        return 0, 0, None
    try:
        colecao = json.loads(r.stdout)
    except json.JSONDecodeError:
        return 0, 0, None
    amostra = invalidas = 0
    exemplo = None
    for feicao in colecao.get("features", []):
        geom = feicao.get("geometry")
        if geom is None:
            continue
        amostra += 1
        try:
            g = shape(geom)
        except (ValueError, TypeError):
            continue
        if not g.is_valid:
            invalidas += 1
            if exemplo is None:
                exemplo = explain_validity(g)
    return amostra, invalidas, exemplo


def _preparar_shapefile(ctx, dados: bytes, encoding_confirmada: str | None) -> dict:
    caminho_zip = ctx.dir_trabalho / "original.zip"
    caminho_zip.write_bytes(dados)
    zf = formatos.conferir_zip(dados)
    bases = formatos._shapefile_no_zip(zf)
    if not bases:
        raise FalhaDefinitiva("o zip não tem trio .shp/.shx/.dbf")
    base = bases[0]
    membros = formatos.shapefile_membros(zf, base)
    if "shx" not in membros or "dbf" not in membros:
        raise FalhaDefinitiva(f"o zip tem {base}.shp mas falta {base}.shx/.dbf")
    caminho = f"/vsizip/{caminho_zip}/{membros['shp']}"

    crs = {"origem": "nenhum", "srid": None, "perguntar": True, "wkt": None, "sugestao": None}
    if "prj" in membros:
        wkt = zf.read(membros["prj"]).decode("ascii", errors="replace")
        epsg = None
        try:
            epsg = pyproj.CRS.from_user_input(wkt).to_epsg(min_confidence=70)
        except pyproj.exceptions.CRSError:
            epsg = None
        if epsg:
            crs = {"origem": "prj", "srid": epsg, "perguntar": False, "wkt": None, "sugestao": None}
        else:
            crs = {"origem": "wkt", "srid": None, "perguntar": True, "wkt": wkt, "sugestao": None}

    codificacao = {"origem": "nenhuma", "valor": None, "perguntar": True, "sugestao": "UTF-8"}
    oo = ["ADJUST_GEOM_TYPE=ALL"]
    if "cpg" in membros:
        valor = zf.read(membros["cpg"]).decode("ascii", errors="replace").strip()
        codificacao = {"origem": "cpg", "valor": valor, "perguntar": False, "sugestao": None}
        oo.append(f"ENCODING={valor}")
    elif encoding_confirmada:
        codificacao = {"origem": "confirmada", "valor": encoding_confirmada, "perguntar": False, "sugestao": None}
        oo.append(f"ENCODING={encoding_confirmada}")
    else:
        try:
            from charset_normalizer import from_bytes

            amostra_dbf = zf.read(membros["dbf"])[:65536]
            melhor = from_bytes(amostra_dbf).best()
            if melhor is not None:
                codificacao["sugestao"] = str(melhor.encoding).upper()
        except Exception:  # noqa: BLE001 — sugestão é best-effort; nunca derruba a inspeção
            pass

    return {"caminho": caminho, "layer": base, "oo": oo, "crs": crs, "codificacao": codificacao, "csv": None,
            "titulo_origem": base, "driver": "ESRI Shapefile", "origem_e_normalizada": False}


def _preparar_gpkg(ctx, dados: bytes) -> dict:
    if dados[:16] != b"SQLite format 3\x00":
        raise FalhaDefinitiva("conteúdo não corresponde ao tipo gpkg: cabeçalho SQLite ausente")
    caminho = ctx.dir_trabalho / "original.gpkg"
    caminho.write_bytes(dados)
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": None, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "GPKG", "origem_e_normalizada": False}


def _preparar_geojson(ctx, dados: bytes) -> dict:
    caminho = ctx.dir_trabalho / "original.geojson"
    caminho.write_bytes(dados)
    inicio = dados[:4096]
    crs = {"origem": "rfc7946", "srid": 4326, "perguntar": False, "wkt": None, "sugestao": None}
    if b'"crs"' in inicio:
        import re

        m = re.search(rb"EPSG(?:::|:)(\d+)", inicio)
        if m:
            crs = {"origem": "crs_legado", "srid": int(m.group(1)), "perguntar": False, "wkt": None,
                   "sugestao": None, "aviso": "o arquivo declara crs fora da RFC 7946; será respeitado"}
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": crs, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "GeoJSON", "origem_e_normalizada": False}


def _preparar_geojsonseq(ctx, dados: bytes) -> dict:
    """GeoJSONSeq/NDJSON (item L6-02-o): mesma regra de CRS do GeoJSON comum (RFC 7946, sempre WGS84 — o formato
    não tem seção `crs` por feição nem por arquivo, então não há "crs legado" a respeitar aqui)."""
    caminho = ctx.dir_trabalho / "original.geojsonl"
    caminho.write_bytes(dados)
    crs = {"origem": "rfc7946", "srid": 4326, "perguntar": False, "wkt": None, "sugestao": None}
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": crs, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "GeoJSONSeq", "origem_e_normalizada": False}


def _preparar_kml(ctx, dados: bytes) -> dict:
    """KML (item L6-02-o, driver LIBKML): o formato é sempre lon/lat WGS84 (OGC KML 22.1 §5.3), então o CRS nunca
    é perguntado — igual ao GeoJSON. Atributos chegam como campos genéricos do LIBKML (Name/description são os
    dois primeiros; os `<ExtendedData>`/`<SimpleData>` do arquivo viram os campos de verdade)."""
    caminho = ctx.dir_trabalho / "original.kml"
    caminho.write_bytes(dados)
    crs = {"origem": "kml", "srid": 4326, "perguntar": False, "wkt": None, "sugestao": None}
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": crs, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "LIBKML", "origem_e_normalizada": False,
            "avisos": ["estilos do KML (ícones, cores, rótulos) não são importados; só geometria e atributos"]}


def _preparar_kmz(ctx, dados: bytes) -> dict:
    """KMZ (item L0-04-d, portão literal 'KMZ com 3 pastas gera 3 camadas'): o mesmo driver LIBKML lê o .kmz
    zipado direto, sem descompactar à mão — cada `<Folder>` do `doc.kml` interno vira uma camada OGR própria.
    Mesma observação de CRS do KML (WGS84 fixo, OGC KML 22.1 §5.3)."""
    caminho = ctx.dir_trabalho / "original.kmz"
    caminho.write_bytes(dados)
    crs = {"origem": "kml", "srid": 4326, "perguntar": False, "wkt": None, "sugestao": None}
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": crs, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "LIBKML", "origem_e_normalizada": False,
            "avisos": ["estilos do KML (ícones, cores, rótulos) não são importados; só geometria e atributos"]}


def _preparar_gpx(ctx, dados: bytes) -> dict:
    """GPX (item L0-04-d): o driver GPX do GDAL sempre declara as MESMAS 5 camadas fixas (waypoints, routes,
    tracks, route_points, track_points), estejam elas vazias ou não — a inspeção lista as 5 e escolhe a única
    com dado (ou pergunta, se mais de uma tiver). Formato é sempre WGS84 (RFC de facto do GPX)."""
    caminho = ctx.dir_trabalho / "original.gpx"
    caminho.write_bytes(dados)
    crs = {"origem": "gpx", "srid": 4326, "perguntar": False, "wkt": None, "sugestao": None}
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": crs, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "GPX", "origem_e_normalizada": False}


def _preparar_gml(ctx, dados: bytes) -> dict:
    """GML (item L0-04-b, 4 formatos a mais do portão): o driver GML do GDAL lê o `.gml`; sem CRS fixo (o
    arquivo pode trazer `srsName` ou nada), então `crs=None` deixa o passo de CRS do `ingestao_inspecionar` ler
    o `projjson`/perguntar como faz para o GPKG."""
    caminho = ctx.dir_trabalho / "original.gml"
    caminho.write_bytes(dados)
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": None, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "GML", "origem_e_normalizada": False}


def _preparar_flatgeobuf(ctx, dados: bytes) -> dict:
    """FlatGeobuf (item L0-04-b): formato binário com CRS embutido no cabeçalho (WKT); `crs=None` deixa o
    `ingestao_inspecionar` ler do `projjson` do `ogrinfo -json`, igual ao GPKG."""
    caminho = ctx.dir_trabalho / "original.fgb"
    caminho.write_bytes(dados)
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": str(caminho), "layer": None, "oo": [], "crs": None, "codificacao": codificacao, "csv": None,
            "titulo_origem": None, "driver": "FlatGeobuf", "origem_e_normalizada": False}


def _preparar_csv(ctx, dados: bytes) -> dict:
    resultado = csv_normalizar.normalizar_bytes(dados)
    if resultado.aspas_desbalanceadas_linha is not None:
        raise FalhaDefinitiva(
            f"aspas desbalanceadas na linha {resultado.aspas_desbalanceadas_linha} do CSV; corrija o arquivo"
        )
    caminho = ctx.dir_trabalho / "normalizado.csv"
    caminho.write_text(resultado.texto, encoding="utf-8")
    oo = ["AUTODETECT_TYPE=YES"]
    if resultado.coordenadas:
        oo.append(f"X_POSSIBLE_NAMES={resultado.coordenadas['x']}")
        oo.append(f"Y_POSSIBLE_NAMES={resultado.coordenadas['y']}")
        oo.append("KEEP_GEOM_COLUMNS=YES")
    crs = {"origem": "nenhum", "srid": None, "perguntar": bool(resultado.coordenadas), "wkt": None,
           "sugestao": 4674 if resultado.coordenadas else None}
    codificacao = {"origem": "detectado", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    csv_info = {
        "separador_origem": resultado.separador_origem, "decimal_origem": resultado.decimal_origem,
        "coordenadas": resultado.coordenadas, "linhas_lidas": resultado.linhas_lidas,
        "colunas_decimal_virgula": [c.nome for c in resultado.colunas if c.e_numero_decimal_virgula],
    }
    return {"caminho": str(caminho), "layer": None, "oo": oo, "crs": crs, "codificacao": codificacao,
            "csv": csv_info, "titulo_origem": None, "driver": "CSV", "origem_e_normalizada": True,
            "csv_colunas": resultado.colunas}


def _preparar_cad(ctx, dados: bytes, formato: str, respostas: dict | None = None) -> dict:
    """DXF/DWG: grava o envio, converte o DWG com o LibreDWG em processo ISOLADO (ADR 0015/0018) e lê camadas,
    unidade, codificação e contagens com o GDAL, também isolado. Nunca abre o arquivo do cliente no processo do
    worker."""
    extensao = ".dwg" if formato == "dwg" else ".dxf"
    caminho = ctx.dir_trabalho / f"original{extensao}"
    caminho.write_bytes(dados)
    rel = cad.inspecionar(caminho, ctx.dir_trabalho, formato=formato, respostas=respostas or {},
                          medir_isolamento=True)
    if rel.estado == "recusado":
        raise FalhaDefinitiva(rel.problemas[0] if rel.problemas else "o desenho não pôde ser lido")
    codificacao = {"origem": rel.codificacao.get("origem", "bytes"), "valor": rel.codificacao.get("valor", "UTF-8"),
                   "perguntar": bool(rel.codificacao.get("perguntar")), "sugestao": None}
    crs = {"origem": "nenhum", "srid": None, "perguntar": True, "wkt": None, "sugestao": None}
    inline = rel.totais.get("blocos_modo") == "explodido"
    config = [f"DXF_INLINE_BLOCKS={'TRUE' if inline else 'FALSE'}",
              f"DXF_ENCODING={codificacao['valor']}"]
    return {"caminho": rel.caminho_dxf, "layer": "entities", "oo": [], "config": config, "crs": crs,
            "codificacao": codificacao, "csv": None, "titulo_origem": None, "driver": "DXF",
            "origem_e_normalizada": False, "cad": rel.json(), "tipos_geometria": dict(rel.tipos_geometria)}


def _preparar_filegdb(ctx, dados: bytes) -> dict:
    """File Geodatabase zipada (item L6-02-o, driver OpenFileGDB): mesmo truque do shapefile.zip — abre a pasta
    `<nome>.gdb` de dentro do zip via `/vsizip`, sem descompactar em disco (37 GB livres, ver regra dura da
    bancada). CRS vem do próprio catálogo da FileGDB (como no GPKG): `crs=None` deixa o passo de CRS do
    `ingestao_inspecionar` ler o `projjson` do `ogrinfo -json`."""
    caminho_zip = ctx.dir_trabalho / "original_gdb.zip"
    caminho_zip.write_bytes(dados)
    zf = formatos.conferir_zip(dados)
    base = formatos._gdb_no_zip(zf)
    if not base:
        raise FalhaDefinitiva("o zip não tem uma pasta <nome>.gdb com catálogo (a*.gdbtable)")
    caminho = f"/vsizip/{caminho_zip}/{base.rstrip('/')}"
    codificacao = {"origem": "formato", "valor": "UTF-8", "perguntar": False, "sugestao": None}
    return {"caminho": caminho, "layer": None, "oo": [], "crs": None, "codificacao": codificacao, "csv": None,
            "titulo_origem": base.rstrip("/").rsplit("/", 1)[-1].removesuffix(".gdb"), "driver": "OpenFileGDB",
            "origem_e_normalizada": False}


def _slug_aba(nome: str) -> str:
    """Nome de arquivo seguro para uma aba do XLSX (`planilha_um` -> `planilha_um`; qualquer coisa fora
    [a-z0-9_-] vira `_`, sempre em minúsculo, nunca vazio)."""
    import re

    limpo = re.sub(r"[^a-z0-9_-]+", "_", nome.lower()).strip("_")
    return limpo or "aba"


def _preparar_xlsx(ctx, dados: bytes, encoding_confirmada: str | None, aba_escolhida: str | None = None) -> dict:
    """Excel/XLSX (item L6-02-o + L0-04-b 'XLSX com 2 planilhas'): o driver XLSX do GDAL NÃO tem geometria
    (`ogrinfo --format XLSX`: "No support for geometries" — MEDIDO, não é bug nosso) — é só tabela. Lista TODAS
    as abas primeiro (achado do adversário do turno 3: `abas[0]` escolhia sempre a primeira e as demais
    desapareciam sem aviso — mesma classe do bug de `camadas[0]` no resto do módulo); converte a aba ESCOLHIDA
    (`aba_escolhida`, ou a primeira por padrão) para CSV com `ogr2ogr` e entrega para `_preparar_csv`: mesmo
    caminho, mesmas regras de X/Y (`app/ingestao/csv_normalizar.py`), mesma proposta. Uma camada de
    polígono/linha ou uma aba sem coluna de coordenada chega SEM geometria automática (Excel não tem onde
    guardar um polígono) — fica registrada como aviso; o par lon/lat continua funcionando para pontos, provado
    no teste de ida e volta. `camadas_disponiveis` carrega nome+contagem de TODAS as abas (barato: uma só
    chamada de `ogrinfo` no arquivo cru, sem conversão) para `ingestao_inspecionar` montar `proposta["camadas"]`
    sem custo de converter as abas que não forem escolhidas."""
    caminho_xlsx = ctx.dir_trabalho / "original.xlsx"
    caminho_xlsx.write_bytes(dados)
    info = _ogrinfo_json(ctx, str(caminho_xlsx), None, [])
    abas = info.get("layers") or []
    if not abas:
        raise FalhaDefinitiva("o arquivo XLSX não tem nenhuma aba")
    nomes_abas = [a.get("name") for a in abas]
    aba = aba_escolhida if aba_escolhida in nomes_abas else nomes_abas[0]
    caminho_csv = ctx.dir_trabalho / f"aba_{_slug_aba(aba)}.csv"
    r = ctx.subprocesso(["ogr2ogr", "-f", "CSV", str(caminho_csv), str(caminho_xlsx), aba])
    if r.returncode != 0:
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        raise FalhaDefinitiva(f"não converteu a aba {aba!r} do XLSX para tabela: "
                              f"{(linhas[-1] if linhas else 'sem detalhe')[:200]}")
    prep = _preparar_csv(ctx, caminho_csv.read_bytes())
    prep["titulo_origem"] = aba
    prep["driver"] = "XLSX (aba convertida para CSV)"
    # `_preparar_csv` devolve `layer: None` (o CSV comum não precisa de nome — o driver assume o único que
    # existe); aqui o nome IMPORTA porque `camada_origem` (nome de EXIBIÇÃO, a aba) e o layer OGR real do CSV
    # gerado ("aba_planilha_um") são coisas diferentes, e `carregar.py` precisa do segundo para o `ogr2ogr`.
    prep["layer"] = caminho_csv.stem
    prep["camadas_disponiveis"] = [{"camada_origem": n, "feicoes": int(a.get("featureCount") or 0),
                                    "tem_geometria_declarada": bool(a.get("geometryFields"))}
                                   for n, a in zip(nomes_abas, abas, strict=True)]
    prep["camada_ativa"] = aba
    if not (prep.get("csv") or {}).get("coordenadas"):
        prep.setdefault("avisos", []).append(
            "a aba não tinha colunas de latitude/longitude reconhecidas; a camada será importada sem geometria "
            "automática (Excel não guarda polígono/linha nativamente)"
        )
    return prep


PREPARADORES = {
    "shapefile.zip": lambda ctx, dados, enc: _preparar_shapefile(ctx, dados, enc),
    "gpkg": lambda ctx, dados, enc: _preparar_gpkg(ctx, dados),
    "geojson": lambda ctx, dados, enc: _preparar_geojson(ctx, dados),
    "geojsonseq": lambda ctx, dados, enc: _preparar_geojsonseq(ctx, dados),
    "kml": lambda ctx, dados, enc: _preparar_kml(ctx, dados),
    "kmz": lambda ctx, dados, enc: _preparar_kmz(ctx, dados),
    "gpx": lambda ctx, dados, enc: _preparar_gpx(ctx, dados),
    "gml": lambda ctx, dados, enc: _preparar_gml(ctx, dados),
    "flatgeobuf": lambda ctx, dados, enc: _preparar_flatgeobuf(ctx, dados),
    "csv": lambda ctx, dados, enc: _preparar_csv(ctx, dados),
    "dxf": lambda ctx, dados, enc, respostas=None: _preparar_cad(ctx, dados, "dxf", respostas),
    "dwg": lambda ctx, dados, enc, respostas=None: _preparar_cad(ctx, dados, "dwg", respostas),
    "filegdb.zip": lambda ctx, dados, enc: _preparar_filegdb(ctx, dados),
    "gdb": lambda ctx, dados, enc: _preparar_filegdb(ctx, dados),
    "xlsx": lambda ctx, dados, enc, respostas=None: _preparar_xlsx(ctx, dados, enc,
                                                                   (respostas or {}).get("aba")),
}


def _marcar_falha(ctx, importacao_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.importacao SET estado = 'falhou', erro = %s, atualizado_em = now() "
            "WHERE id = %s::uuid AND estado NOT IN ('concluida','falhou','cancelada','expirada')",
            (erro[:2000], importacao_id),
        )


def _analisar_camada(ctx, prep: dict, camada: dict) -> dict:
    """Os cinco pedaços que a proposta grava por camada (campos, geometria, CRS, validade, avisos), extraídos
    do resumo de UMA camada que `ogrinfo -json` devolve. Isolado do laço principal (achado do adversário do
    turno 3, item L0-04-b 'GPKG com 3 camadas'/'KMZ com 3 pastas': o código antigo só chamava isto para
    `camadas[0]` e as demais desapareciam da proposta em silêncio) para rodar uma vez por camada do arquivo,
    não só na primeira — `ingestao_inspecionar` decide QUAL vira a escolhida; esta função não decide nada."""
    nome_camada_origem = camada.get("name") or prep.get("titulo_origem") or "camada"
    feicoes = int(camada.get("featureCount") or 0)

    campos_origem = camada.get("fields") or []
    if len(campos_origem) > CAMPOS_MAX:
        raise FalhaDefinitiva(f"a camada tem {len(campos_origem)} campos; o máximo é {CAMPOS_MAX}")
    if not campos_origem and not camada.get("geometryFields"):
        raise FalhaDefinitiva(f"a camada {nome_camada_origem} não tem campos nem geometria")

    # ------------------------------------------------------------ geometria
    geom_fields = camada.get("geometryFields") or []
    tipo_bruto = geom_fields[0].get("type") if geom_fields else None
    base_tipo, _ = geometria.normalizar_tipo_ogr(tipo_bruto or "")
    if base_tipo in geometria.TIPOS_CONCRETOS:
        resolvido = {"tipos": {tipo_bruto: feicoes}, "escolhida": base_tipo, "perguntar": False,
                     "opcoes": [base_tipo], "z": "Z" in (tipo_bruto or "") or "25D" in (tipo_bruto or ""),
                     "sem_geometria": 0}
    elif prep.get("tipos_geometria"):
        # DXF/DWG: os tipos já vieram contados pelo leitor de CAD, com o dialeto SQLITE (o OGR SQL não tem
        # GROUP BY e a varredura genérica devolveria vazio em silêncio). DXF/DWG têm sempre UMA camada só
        # ("entities"), então não há ambiguidade de qual resumo esta contagem descreve.
        resolvido = geometria.resolver(dict(prep["tipos_geometria"]))
    elif geom_fields and feicoes:
        ctx.progresso(45, "varrendo o tipo real de geometria")
        tipos_contagem = _tipos_por_varredura(ctx, prep["caminho"], nome_camada_origem, prep["oo"],
                                              prep.get("config"))
        resolvido = geometria.resolver(tipos_contagem or {"NULL": feicoes})
    elif geom_fields:
        resolvido = {"tipos": {}, "escolhida": None, "perguntar": False, "opcoes": [], "z": False,
                     "sem_geometria": 0}
    else:
        resolvido = {"tipos": {}, "escolhida": None, "perguntar": False, "opcoes": [], "z": False,
                     "sem_geometria": feicoes}

    # ------------------------------------------------------------ CRS
    crs = dict(prep["crs"]) if prep["crs"] is not None else None
    extent = None
    if geom_fields and geom_fields[0].get("extent"):
        extent = [float(v) for v in geom_fields[0]["extent"]]
    if crs is None:
        projjson = (geom_fields[0].get("coordinateSystem") or {}).get("projjson") if geom_fields else None
        epsg = None
        if projjson:
            ident = (projjson.get("id") or {})
            if str(ident.get("authority", "")).upper() == "EPSG":
                epsg = int(ident["code"])
        if epsg:
            crs = {"origem": "gpkg", "srid": epsg, "perguntar": False, "wkt": None, "sugestao": None}
        else:
            crs = {"origem": "nenhum", "srid": None, "perguntar": True, "wkt": None,
                   "sugestao": _extent_sugere_srid(extent)}
    elif crs.get("srid") is None and crs.get("sugestao") is None:
        crs["sugestao"] = _extent_sugere_srid(extent)
    crs["extent_origem"] = extent

    # ------------------------------------------------------------ campos
    # CSV/TXT: o ogrinfo já leu o arquivo NORMALIZADO (csv_normalizar.py normaliza o cabeçalho antes do
    # GDAL) — "origem" mostra o cabeçalho VERDADEIRO do arquivo enviado, não o nome já limpo, casado por
    # posição com `prep["csv_colunas"]` (mesma ordem: csv_normalizar preserva a ordem das colunas).
    csv_colunas_origem = {c.nome: c.origem for c in prep.get("csv_colunas", [])} if prep.get("csv_colunas") else {}
    usados: set[str] = set()
    campos = []
    for i, f in enumerate(campos_origem):
        tipo_pg = tipos_campo.pg_de(f.get("type", "String"), f.get("subType"))
        nome_origem_bruto = f.get("name", "")
        nome, motivo = nomes.normalizar(nome_origem_bruto, usados, posicao=i)
        avisos_campo = [motivo] if motivo else []
        campos.append({
            "origem": csv_colunas_origem.get(nome_origem_bruto, nome_origem_bruto), "nome": nome,
            "tipo_origem": f.get("type", "String"), "tipo": tipo_pg, "opcoes_tipo": tipos_campo.opcoes_de(tipo_pg),
            "largura": f.get("width"), "avisos": avisos_campo,
        })

    # ------------------------------------------------------------ validade (amostra)
    amostra, invalidas, exemplo = (0, 0, None)
    if resolvido.get("escolhida"):
        ctx.progresso(70, "amostrando validade")
        amostra, invalidas, exemplo = _amostra_validade(ctx, prep["caminho"], nome_camada_origem,
                                                        prep["oo"], prep.get("config"))

    # ------------------------------------------------------------ avisos desta camada
    avisos_camada = []
    if crs.get("aviso"):
        avisos_camada.append(crs.pop("aviso"))
    if feicoes == 0:
        # refutação literal do L0-04-b ("CSV com 300 colunas e 0 linhas ... silêncio ou 500 = refutado"):
        # nunca terminar sem dizer que a camada não trouxe NENHUMA linha, mesmo tendo campos de sobra.
        avisos_camada.append(
            f"a camada {nome_camada_origem!r} tem {len(campos_origem)} campos e NENHUMA linha de dado"
        )
    elif resolvido.get("sem_geometria"):
        avisos_camada.append(f"{resolvido['sem_geometria']} feições sem geometria")

    return {
        "camada_origem": nome_camada_origem, "feicoes": feicoes, "feicoes_exatas": feicoes >= 0,
        "geometria": resolvido, "crs": crs, "campos": campos,
        "validade": {"amostra": amostra, "invalidas": invalidas, "exemplo": exemplo,
                     "acao": "corrigir" if invalidas else None},
        "avisos": avisos_camada, "tem_geometria": bool(resolvido.get("escolhida")),
    }


@tarefa(
    nome="ingestao.inspecionar",
    descricao="Inspeciona um arquivo (ogrinfo -json + sondas) e grava a proposta editável de importação",
    parametros=InspecionarParametros,
    pesado=False,
    memoria_mb=768,
    timeout_s=300,
    tentativas=1,
    chave=lambda p: f"importacao:{p.get('importacao_id')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def ingestao_inspecionar(ctx, importacao_id: uuid.UUID) -> dict:
    iid = str(importacao_id)
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.importacao WHERE id = %s::uuid", (iid,))
        imp = cur.fetchone()
        if imp is None:
            raise FalhaDefinitiva("importação inexistente")
        cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'", (imp["arquivo_id"],))
        arq = cur.fetchone()
        if arq is None:
            raise FalhaDefinitiva("o arquivo de origem não existe mais")
    ctx.progresso(5, "baixando o arquivo")
    try:
        dados = objetos.ler(arq["dados"]["chave"])
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise FalhaDefinitiva(f"arquivo corrompido ou inexistente no armazenamento: {e}") from e
    import hashlib

    sha_real = hashlib.sha256(dados).hexdigest()
    if sha_real != arq["dados"]["sha256"]:
        raise FalhaDefinitiva("arquivo corrompido: sha256 divergente do gravado no upload")
    ctx.entrada(imp["arquivo_id"], sha_real, "arquivo de origem")

    formato = imp["formato"]
    preparador = PREPARADORES.get(formato)
    if preparador is None:
        raise FalhaDefinitiva(f"formato não suportado nesta instalação: {formato}")

    try:
        ctx.progresso(20, "preparando a fonte")
        prep = preparador(ctx, dados, None)

        # ------------------------------------------------------------ listagem de TODAS as camadas
        # Achado do adversário do turno 3 (item L0-04-b: "GPKG com 3 camadas", "KMZ com 3 pastas"):
        # `camadas[0]` descartava as demais em silêncio. XLSX é o único formato cuja listagem leve
        # (`camadas_disponiveis`) já veio pronta do preparador sem custo de converter cada aba; para todos
        # os outros o MESMO `ogrinfo -json` sem `layer` específico (já feito hoje) devolve TODAS as camadas
        # do arquivo de uma vez, com campos e geometria completos — só faltava não jogar fora as demais.
        if prep.get("camadas_disponiveis") is not None:
            resumo = prep["camadas_disponiveis"]
            camadas_ogr = None
        else:
            ctx.progresso(35, "ogrinfo")
            info_container = _ogrinfo_json(ctx, prep["caminho"], prep["layer"], prep["oo"], prep.get("config"))
            camadas_ogr = info_container.get("layers") or []
            if not camadas_ogr:
                raise FalhaDefinitiva("o arquivo não contém camada vetorial")
            resumo = [{"camada_origem": c.get("name") or prep.get("titulo_origem") or "camada",
                      "feicoes": int(c.get("featureCount") or 0),
                      "tem_geometria_declarada": bool(c.get("geometryFields"))} for c in camadas_ogr]

        # ------------------------------------------------------------ escolha da camada
        # Regra (item L0-04-d/L0-04-b): 1 camada só -> ela mesma, sem pergunta. Mais de uma e SÓ uma tem
        # dado -> essa entra por padrão, as vazias só avisam (cláusula do GPX: "abre na única com dado").
        # Mais de uma com dado (ou nenhuma) -> ambíguo, pergunta "camada", padrão é a 1ª (o usuário troca na
        # confirmação com `camada.escolhida`).
        nao_vazias = [i for i, c in enumerate(resumo) if c["feicoes"] > 0]
        if len(resumo) == 1:
            indice_escolhido, camada_ambigua = 0, False
        elif len(nao_vazias) == 1:
            indice_escolhido, camada_ambigua = nao_vazias[0], False
        else:
            indice_escolhido, camada_ambigua = 0, True
        camada_escolhida_nome = resumo[indice_escolhido]["camada_origem"]

        if camadas_ogr is not None:
            camada_ogr_escolhida = camadas_ogr[indice_escolhido]
        else:
            # XLSX: a aba escolhida por padrão pode não ser a 1ª (só a preparada até aqui) — reconverte só
            # ela, e SÓ ela: as abas vazias/ignoradas nunca pagam o custo de virar CSV.
            if camada_escolhida_nome != prep.get("camada_ativa"):
                prep = preparador(ctx, dados, None, {"aba": camada_escolhida_nome})
            info_aba = _ogrinfo_json(ctx, prep["caminho"], prep["layer"], prep["oo"], prep.get("config"))
            camadas_aba = info_aba.get("layers") or []
            if not camadas_aba:
                raise FalhaDefinitiva(f"a aba {camada_escolhida_nome!r} não gerou nenhuma camada")
            camada_ogr_escolhida = camadas_aba[0]

        analise = _analisar_camada(ctx, prep, camada_ogr_escolhida)
        analise["camada_origem"] = camada_escolhida_nome  # nome de EXIBIÇÃO (aba do xlsx, pasta do kmz, ...)
        feicoes = analise["feicoes"]
        resolvido = analise["geometria"]
        crs = analise["crs"]
        campos = analise["campos"]

        perguntas = []
        if camada_ambigua:
            perguntas.append("camada")
        if crs.get("perguntar"):
            perguntas.append("crs")
        if prep["codificacao"].get("perguntar"):
            perguntas.append("codificacao")
        if resolvido.get("perguntar"):
            perguntas.append("geometria")
        cad_info = prep.get("cad")
        if cad_info:
            if (cad_info.get("unidade") or {}).get("perguntar"):
                perguntas.append("unidade")
            perguntas.append("georreferencia")   # o desenho não traz projeção: EPSG ou pontos de controle

        avisos_gerais = list(prep.get("avisos") or [])
        avisos_gerais.extend(analise["avisos"])
        if cad_info:
            avisos_gerais.extend(cad_info.get("avisos") or [])
            avisos_gerais.extend(cad_info.get("pendencias") or [])
        # avisos sobre as OUTRAS camadas: nunca uma camada some do arquivo sem que a proposta diga o nome dela
        if len(resumo) > 1:
            outras = [c for i, c in enumerate(resumo) if i != indice_escolhido]
            if camada_ambigua:
                nomes_outras = ", ".join(repr(c["camada_origem"]) for c in outras)
                avisos_gerais.append(
                    f"o arquivo tem {len(resumo)} camadas; além de {camada_escolhida_nome!r} (escolhida por "
                    f"padrão) também existem {nomes_outras}, que não entram nesta importação sem escolher "
                    f"'camada' na confirmação"
                )
            else:
                for c in outras:
                    if c["feicoes"] == 0:
                        avisos_gerais.append(f"a camada {c['camada_origem']!r} está vazia")
                    else:
                        avisos_gerais.append(
                            f"a camada {c['camada_origem']!r} também tem dado e não entra nesta importação"
                        )

        item_id = imp["item_id"]
        camadas_proposta = [
            {"camada_origem": c["camada_origem"], "feicoes": c["feicoes"],
            "tem_geometria": (analise["tem_geometria"] if i == indice_escolhido
                              else bool(c.get("tem_geometria_declarada", True)))}
            for i, c in enumerate(resumo)
        ]
        proposta = {
            "importacao_id": iid, "arquivo_id": imp["arquivo_id"], "formato": formato, "driver": prep["driver"],
            "camada_origem": camada_escolhida_nome, "camada_escolhida": camada_escolhida_nome,
            "camadas": camadas_proposta,
            "titulo": nomes.normalizar_titulo(prep.get("titulo_origem") or camada_escolhida_nome),
            "nome_tabela": tabela_de(item_id),
            "feicoes": feicoes, "feicoes_exatas": analise["feicoes_exatas"],
            "geometria": resolvido, "crs": crs, "codificacao": prep["codificacao"], "csv": prep["csv"],
            "campos": campos, "validade": analise["validade"],
            "avisos": avisos_gerais, "perguntas": perguntas,
        }
        if prep.get("cad"):
            proposta["cad"] = prep["cad"]
            proposta["camadas_desenho"] = [c["nome"] for c in prep["cad"].get("camadas", [])]
        with ctx.db() as cur:
            cur.execute(
                "UPDATE plat.importacao SET estado = 'proposta', proposta = %s, atualizado_em = now() "
                "WHERE id = %s::uuid",
                (psycopg2.extras.Json(proposta, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str)), iid),
            )
        ctx.progresso(100, "proposta pronta")
        return {"importacao_id": iid, "feicoes": feicoes, "perguntas": perguntas}
    except FalhaDefinitiva as e:
        _marcar_falha(ctx, iid, str(e))
        raise
