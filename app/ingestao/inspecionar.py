"""Job `ingestao.inspecionar` (ADR 0005 seção 4, L0-04-b), reduzido aos 4 formatos desta passagem (shapefile.zip,
gpkg, geojson, csv): baixa o objeto, roda `ogrinfo -ro -json -so`, resolve geometria/CRS/codificação/campos,
amostra a validade (shapely, sem depender de dialeto SQLite do GDAL) e grava a PROPOSTA editável em
`plat.importacao.proposta` (estado `proposta`). Nunca cria tabela: só a confirmação do usuário dispara a carga."""

from __future__ import annotations

import json
import uuid

import psycopg2.extras
import pyproj
from pydantic import BaseModel
from shapely.geometry import shape
from shapely.validation import explain_validity

from app import limites, objetos
from app.ingestao import csv_normalizar, formatos, geometria, nomes, tipos_campo
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


def _ogrinfo_json(ctx, caminho: str, layer: str | None, oo: list[str]) -> dict:
    argv = ["ogrinfo", "-ro", "-json", "-so"]
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


def _tipos_por_varredura(ctx, caminho: str, layer: str, oo: list[str]) -> dict[str, int]:
    argv = ["ogrinfo", "-ro", "-json"]
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


def _amostra_validade(ctx, caminho: str, layer: str | None, oo: list[str]) -> tuple[int, int, str | None]:
    """(amostra, invalidas, exemplo) lendo até AMOSTRA_VALIDADE feições como GeoJSON e checando com shapely
    (evita depender do dialeto SQLite/SpatiaLite do GDAL)."""
    argv = ["ogr2ogr", "-f", "GeoJSON", "/vsistdout/"]
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


PREPARADORES = {
    "shapefile.zip": lambda ctx, dados, enc: _preparar_shapefile(ctx, dados, enc),
    "gpkg": lambda ctx, dados, enc: _preparar_gpkg(ctx, dados),
    "geojson": lambda ctx, dados, enc: _preparar_geojson(ctx, dados),
    "csv": lambda ctx, dados, enc: _preparar_csv(ctx, dados),
}


def _marcar_falha(ctx, importacao_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.importacao SET estado = 'falhou', erro = %s, atualizado_em = now() "
            "WHERE id = %s::uuid AND estado NOT IN ('concluida','falhou','cancelada','expirada')",
            (erro[:2000], importacao_id),
        )


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

        ctx.progresso(35, "ogrinfo")
        info = _ogrinfo_json(ctx, prep["caminho"], prep["layer"], prep["oo"])
        camadas = info.get("layers") or []
        if not camadas:
            raise FalhaDefinitiva("o arquivo não contém camada vetorial")
        camada = camadas[0]
        nome_camada_origem = camada.get("name") or prep["titulo_origem"] or "camada"
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
        elif geom_fields:
            ctx.progresso(45, "varrendo o tipo real de geometria")
            tipos_contagem = _tipos_por_varredura(ctx, prep["caminho"], nome_camada_origem, prep["oo"])
            resolvido = geometria.resolver(tipos_contagem or {"NULL": feicoes})
        else:
            resolvido = {"tipos": {}, "escolhida": None, "perguntar": False, "opcoes": [], "z": False,
                         "sem_geometria": feicoes}

        # ------------------------------------------------------------ CRS
        crs = prep["crs"]
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
            avisos = [motivo] if motivo else []
            campos.append({
                "origem": csv_colunas_origem.get(nome_origem_bruto, nome_origem_bruto), "nome": nome,
                "tipo_origem": f.get("type", "String"), "tipo": tipo_pg, "opcoes_tipo": tipos_campo.opcoes_de(tipo_pg),
                "largura": f.get("width"), "avisos": avisos,
            })

        # ------------------------------------------------------------ validade (amostra)
        ctx.progresso(70, "amostrando validade")
        amostra, invalidas, exemplo = (0, 0, None)
        if resolvido.get("escolhida"):
            amostra, invalidas, exemplo = _amostra_validade(ctx, prep["caminho"], nome_camada_origem, prep["oo"])

        perguntas = []
        if crs.get("perguntar"):
            perguntas.append("crs")
        if prep["codificacao"].get("perguntar"):
            perguntas.append("codificacao")
        if resolvido.get("perguntar"):
            perguntas.append("geometria")

        avisos_gerais = []
        if crs.get("aviso"):
            avisos_gerais.append(crs.pop("aviso"))
        if resolvido.get("sem_geometria"):
            avisos_gerais.append(f"{resolvido['sem_geometria']} feições sem geometria")

        item_id = imp["item_id"]
        proposta = {
            "importacao_id": iid, "arquivo_id": imp["arquivo_id"], "formato": formato, "driver": prep["driver"],
            "camada_origem": nome_camada_origem,
            "titulo": nomes.normalizar_titulo(prep["titulo_origem"] or nome_camada_origem),
            "nome_tabela": tabela_de(item_id),
            "feicoes": feicoes, "feicoes_exatas": feicoes >= 0,
            "geometria": resolvido, "crs": crs, "codificacao": prep["codificacao"], "csv": prep["csv"],
            "campos": campos,
            "validade": {"amostra": amostra, "invalidas": invalidas, "exemplo": exemplo,
                         "acao": "corrigir" if invalidas else None},
            "avisos": avisos_gerais, "perguntas": perguntas,
        }
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
