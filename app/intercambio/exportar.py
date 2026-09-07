"""Jobs `intercambio.exportar_camada` e `intercambio.exportar_inquilino` (item L6-02-o).

Leitura pelo `ogr2ogr` conectando como o papel da aplicação COM o inquilino na sessão
(`options='-c plat.tenant_id=N'` — as tabelas de camada têm RLS FORCE por `plat.tenant_atual()`, ver
`plat.camada_preparar` na migração 029); a escrita é em arquivo no diretório de trabalho do job, e o
pacote final (arquivo único ou zip) vai para o Garage por `objetos.guardar` e vira item `arquivo` do
catálogo. Avisos de fidelidade (truncamento DBF, tipo que muda, quantização de tile) são calculados
ANTES de rodar — ver `avisos.py` — e gravados em `plat.intercambio_exportacao.avisos`.

Depois de escrito, o arquivo é reaberto com `ogrinfo -ro -json -so` e a contagem lida tem de bater com
a da origem (ida conferida pela própria plataforma; a volta completa — geometria e atributos — é o
teste de `tests/api/intercambio/test_exportacao.py`).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import uuid
import zipfile

import psycopg2.extensions
import psycopg2.extras
from pydantic import BaseModel

from app import limites, objetos
from app.intercambio import avisos as avisos_mod
from app.intercambio.formatos_saida import FORMATOS_SAIDA, FormatoSaida
from app.jobs.registro import Cancelado, FalhaDefinitiva, tarefa
from app.settings import settings

MEMORIA_MB = limites.INTERCAMBIO_MEMORIA_MB
TIMEOUT_S = limites.INTERCAMBIO_TIMEOUT_S


class ExportacaoParametros(BaseModel):
    exportacao_id: uuid.UUID


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _aspas(valor: str) -> str:
    """Valor entre aspas simples para a string de conexão do GDAL (escapa \\ e ')."""
    return "'" + valor.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _pg_conninfo(tenant_id: int) -> str:
    """`PG:...` de leitura com o inquilino na sessão (RLS das tabelas de camada exige plat.tenant_id)."""
    partes = psycopg2.extensions.parse_dsn(settings.PLAT_DSN)
    pares = " ".join(f"{k}={_aspas(str(v))}" for k, v in partes.items()
                     if k in ("dbname", "host", "port", "user", "password"))
    return (f"PG:{pares} application_name='plat-intercambio' "
            f"options='-c plat.tenant_id={int(tenant_id)}'")


def _ident(nome: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", nome):
        raise FalhaDefinitiva(f"identificador fora do padrão: {nome!r}")
    return '"' + nome + '"'


def _carregar_exportacao(ctx, exportacao_id) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.intercambio_exportacao WHERE id = %s::uuid", (str(exportacao_id),))
        r = cur.fetchone()
        if r is None:
            raise FalhaDefinitiva("exportação inexistente")
        if r["estado"] != "fila":
            raise FalhaDefinitiva(f"exportação em estado {r['estado']!r}; esperava 'fila'")
        cur.execute("UPDATE plat.intercambio_exportacao SET estado = 'rodando' WHERE id = %s::uuid",
                    (str(exportacao_id),))
    return r


def _camada_do_item(cur, item_id: str) -> dict:
    cur.execute(
        "SELECT id, titulo, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial' "
        "AND apagado_em IS NULL",
        (item_id,),
    )
    r = cur.fetchone()
    if r is None:
        raise FalhaDefinitiva("camada inexistente (ou de outro inquilino)")
    dados = r["dados"] or {}
    for chave in ("schema", "tabela", "srid"):
        if not dados.get(chave):
            raise FalhaDefinitiva(f"camada sem {chave} no catálogo")
    return {"id": str(r["id"]), "titulo": r["titulo"], **dados}


def _sql_select(schema: str, tabela: str, campos: list[dict], *, wkt: bool) -> str:
    colunas = ", ".join(_ident(c["nome"]) for c in campos)
    if colunas:
        colunas += ", "
    if wkt:
        return (f"SELECT {colunas}ST_AsText(geom) AS geometria_wkt "
                f"FROM {_ident(schema)}.{_ident(tabela)} ORDER BY fid")
    return f"SELECT {colunas}geom FROM {_ident(schema)}.{_ident(tabela)} ORDER BY fid"


def _avisos_da_camada(cur, fmt: FormatoSaida, campos: list[dict], schema: str, tabela: str,
                      srid_origem: int, srid_alvo: int) -> tuple[list[str], dict[str, str]]:
    avisos = list(fmt.avisos_inerentes)
    mapa_dbf: dict[str, str] = {}
    if fmt.nome == "shapefile.zip":
        textos = [c for c in campos if c.get("tipo") == "text"]
        max_len: dict[str, int] = {}
        if textos:
            soma = ", ".join(f"max(length({_ident(c['nome'])})) AS {_ident(c['nome'])}" for c in textos)
            cur.execute(f"SELECT {soma} FROM {_ident(schema)}.{_ident(tabela)}")
            max_len = {k: int(v) for k, v in cur.fetchone().items() if v is not None}
        mapa_dbf, por_campo = avisos_mod.avisos_shapefile(campos, max_len)
        avisos += por_campo
    if fmt.crs_fixo is None and srid_alvo != srid_origem:
        avisos.append(f"reprojetado de EPSG:{srid_origem} para EPSG:{srid_alvo} a pedido do usuário")
    return avisos, mapa_dbf


def _guarda_disco(ctx, estimativa_bytes: int) -> None:
    livre = shutil.disk_usage(ctx.dir_trabalho).free
    if livre < estimativa_bytes * limites.INTERCAMBIO_DISCO_FOLGA:
        raise FalhaDefinitiva(
            f"disco temporário insuficiente: livre {livre // (1024 * 1024)} MB, exigido "
            f"{estimativa_bytes * limites.INTERCAMBIO_DISCO_FOLGA // (1024 * 1024)} MB"
        )


def _argv_ogr2ogr(fmt: FormatoSaida, conninfo: str, destino: str, sql: str, nome_saida: str,
                  srid_origem: int, srid_alvo: int) -> list[str]:
    argv = ["ogr2ogr", "-f", fmt.driver, destino, conninfo,
            "-sql", sql, "-nln", nome_saida, "-a_srs", f"EPSG:{srid_origem}"]
    if srid_alvo != srid_origem:
        argv += ["-t_srs", f"EPSG:{srid_alvo}"]
    for o in fmt.opcoes_camada:
        argv += ["-lco", o]
    for o in fmt.opcoes_dataset:
        argv += ["-dsco", o]
    argv += ["--config", "PG_USE_COPY", "YES"]
    return argv


def _rodar_ogr2ogr(ctx, argv: list[str]) -> None:
    r = ctx.subprocesso(argv)
    if r.returncode != 0:
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        raise FalhaDefinitiva(f"ogr2ogr falhou: {(linhas[-1] if linhas else 'sem detalhe')[:200]}")


def _contar_na_saida(ctx, caminho: str, camada: str | None = None) -> int | None:
    """featureCount do arquivo gerado (de uma camada específica, quando dada; senão a soma). None se o
    ogrinfo não abrir — vira falha no chamador."""
    argv = ["ogrinfo", "-ro", "-json", "-so", caminho]
    if camada:
        argv.append(camada)
    r = ctx.subprocesso(argv)
    if r.returncode != 0:
        return None
    try:
        dados = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    total = 0
    for c in dados.get("layers", []):
        n = c.get("featureCount")
        if n is None or int(n) < 0:
            return None
        total += int(n)
    return total


def _empacotar(fmt: FormatoSaida, base_dir, nome_base: str) -> tuple[bytes, str]:
    """(bytes do pacote final, nome do arquivo) — zip do shapefile ou do diretório .gdb; demais: o arquivo."""
    if fmt.empacotar == "zip_shapefile":
        exts = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".fix", ".sbn", ".sbx")
        membros = sorted(p for p in base_dir.iterdir() if p.suffix.lower() in exts)
        if not any(p.suffix.lower() == ".shp" for p in membros):
            raise FalhaDefinitiva("ogr2ogr terminou sem gravar o .shp")
        pacote = base_dir.parent / f"{nome_base}.zip"
        with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in membros:
                zf.write(p, p.name)
        return pacote.read_bytes(), f"{nome_base}.zip"
    if fmt.empacotar == "zip_gdb":
        if not base_dir.is_dir() or not any(p.suffix == ".gdbtable" for p in base_dir.iterdir()):
            raise FalhaDefinitiva("ogr2ogr terminou sem gravar o diretório .gdb")
        pacote = base_dir.parent / f"{nome_base}.zip"
        with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(base_dir.rglob("*")):
                if p.is_file():
                    zf.write(p, f"{nome_base}.gdb/{p.relative_to(base_dir)}")
        return pacote.read_bytes(), f"{nome_base}.zip"
    return base_dir.read_bytes(), base_dir.name


def _gravar_resultado(ctx, exportacao_id: str, content_type: str, titulo: str, dados_pacote: bytes,
                      nome_arquivo: str, avisos: list[str], relatorio: dict) -> str:
    """Guarda o pacote no Garage, cria o item `arquivo` e fecha a exportação. Devolve o item_id do arquivo."""
    if len(dados_pacote) > limites.INTERCAMBIO_EXPORTACAO_BYTES_MAX:
        raise FalhaDefinitiva(
            f"pacote de {len(dados_pacote) // (1024 * 1024)} MB acima do máximo "
            f"{limites.INTERCAMBIO_EXPORTACAO_BYTES_MAX // (1024 * 1024 * 1024)} GiB"
        )
    sha = hashlib.sha256(dados_pacote).hexdigest()
    item_arquivo = str(uuid.uuid4())
    with ctx.db() as cur:
        obj = objetos.guardar(cur, "exportacao", dados_pacote, content_type, item_id=item_arquivo,
                              usuario_id=ctx.usuario_id)
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
            "criado_por, modificado_por) VALUES (%s::uuid, %s, 'arquivo', %s, %s, %s, %s, %s, %s)",
            (item_arquivo, ctx.tenant_id, titulo[:250], ctx.usuario_id,
             _jsonb({"chave": obj["chave"], "sha256": sha, "bytes": len(dados_pacote),
                     "content_type": content_type, "nome_original": nome_arquivo}),
             len(dados_pacote), ctx.usuario_id, ctx.usuario_id),
        )
        cur.execute(
            "UPDATE plat.intercambio_exportacao SET estado = 'concluida', item_arquivo = %s::uuid, "
            "avisos = %s, relatorio = %s WHERE id = %s::uuid",
            (item_arquivo, _jsonb(avisos), _jsonb(relatorio | {"sha256": sha, "bytes": len(dados_pacote)}),
             exportacao_id),
        )
    return item_arquivo


def _marcar_falha(ctx, exportacao_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.intercambio_exportacao SET estado = %s, erro = %s "
            "WHERE id = %s::uuid AND estado NOT IN ('concluida','falhou','cancelada')",
            ("cancelada" if "cancel" in erro.lower() else "falhou", erro[:2000], str(exportacao_id)),
        )


def _exportar_uma(ctx, conninfo: str, camada: dict, fmt: FormatoSaida, srid_alvo: int,
                  nome_saida: str, campos: list[dict] | None = None,
                  destino_compartilhado=None) -> dict:
    """Exporta UMA camada para o formato; devolve {feicoes_origem, feicoes_saida, pacote, nome_arquivo,
    srid_alvo}. Com `destino_compartilhado` (o GPKG do escrow) grava com -update -append dentro dele e
    `pacote` fica None. A contagem lida do arquivo gerado tem de bater com a da origem (ida conferida)."""
    campos = campos if campos is not None else (camada.get("campos") or [])
    srid_origem = int(camada["srid"])
    alvo = fmt.crs_fixo if fmt.crs_fixo is not None else srid_alvo
    if destino_compartilhado is not None:
        destino = destino_compartilhado
    else:
        sub = ctx.dir_trabalho / f"saida_{nome_saida}"
        sub.mkdir(exist_ok=True)
        if fmt.empacotar == "zip_shapefile":
            destino = sub / f"{nome_saida}.shp"
        elif fmt.empacotar == "zip_gdb":
            destino = sub / f"{nome_saida}.gdb"
        else:
            destino = sub / f"{nome_saida}.{fmt.extensao}"

    sql = _sql_select(camada["schema"], camada["tabela"], campos, wkt=(fmt.geometria == "wkt"))
    argv = _argv_ogr2ogr(fmt, conninfo, str(destino), sql, nome_saida, srid_origem, alvo)
    if destino_compartilhado is not None and destino.exists():
        argv += ["-update", "-append"]
    _rodar_ogr2ogr(ctx, argv)

    feicoes_saida = _contar_na_saida(ctx, str(destino),
                                     nome_saida if destino_compartilhado is not None else None)
    if feicoes_saida is None:
        raise FalhaDefinitiva("o arquivo gerado não abriu no ogrinfo")
    with ctx.db() as cur:
        cur.execute(f"SELECT count(*) AS n FROM {_ident(camada['schema'])}.{_ident(camada['tabela'])}")
        feicoes_origem = int(cur.fetchone()["n"])
    if fmt.geometria != "tile" and feicoes_saida != feicoes_origem:
        raise FalhaDefinitiva(
            f"contagem divergente: origem {feicoes_origem}, arquivo {feicoes_saida} — exportação recusada"
        )
    if destino_compartilhado is not None:
        pacote, nome_final = None, None
    elif fmt.empacotar == "zip_shapefile":
        pacote, nome_final = _empacotar(fmt, destino.parent, nome_saida)
    elif fmt.empacotar == "zip_gdb":
        pacote, nome_final = _empacotar(fmt, destino, nome_saida)
    else:
        pacote, nome_final = destino.read_bytes(), destino.name
    return {"feicoes_origem": feicoes_origem, "feicoes_saida": feicoes_saida,
            "pacote": pacote, "nome_arquivo": nome_final, "srid_alvo": alvo}


@tarefa(
    nome="intercambio.exportar_camada",
    descricao="Exporta uma camada vetorial do inquilino para arquivo no formato escolhido",
    parametros=ExportacaoParametros,
    pesado=True,
    memoria_mb=MEMORIA_MB,
    timeout_s=TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"intercambio:{p.get('exportacao_id')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def intercambio_exportar_camada(ctx, exportacao_id: uuid.UUID) -> dict:
    eid = str(exportacao_id)
    inicio = time.monotonic()
    try:
        exp = _carregar_exportacao(ctx, exportacao_id)
        fmt = FORMATOS_SAIDA.get(exp["formato"])
        if fmt is None:
            raise FalhaDefinitiva(f"formato não oferecido nesta instalação: {exp['formato']}")
        parametros = exp["parametros"] or {}
        ctx.progresso(5, "lendo a camada")
        with ctx.db() as cur:
            camada = _camada_do_item(cur, str(exp["item_origem"]))
            cur.execute('SELECT pg_total_relation_size(%s::regclass) AS b',
                        (f'"{camada["schema"]}"."{camada["tabela"]}"',))
            tamanho_tabela = int(cur.fetchone()["b"])
        _guarda_disco(ctx, max(tamanho_tabela, 1024 * 1024))

        campos_todos = camada.get("campos") or []
        escolhidos = parametros.get("campos")
        if escolhidos:
            validos = {c["nome"] for c in campos_todos}
            if not set(escolhidos) <= validos:
                raise FalhaDefinitiva("campo fora da camada no pedido de exportação")
            campos = [c for c in campos_todos if c["nome"] in set(escolhidos)]
        else:
            campos = campos_todos
        srid_alvo = int(parametros.get("srid") or camada["srid"])

        with ctx.db() as cur:
            avisos, mapa_dbf = _avisos_da_camada(cur, fmt, campos, camada["schema"], camada["tabela"],
                                                 int(camada["srid"]), srid_alvo)
        ctx.progresso(20, "ogr2ogr")
        conninfo = _pg_conninfo(ctx.tenant_id)
        nome_saida = re.sub(r"[^A-Za-z0-9_]+", "_", (parametros.get("titulo") or "camada")).strip("_")[:40] \
            or "camada"
        medidas = _exportar_uma(ctx, conninfo, camada, fmt, srid_alvo, nome_saida, campos)
        ctx.progresso(85, "guardando o pacote")
        relatorio = {"feicoes": medidas["feicoes_saida"], "srid_alvo": medidas["srid_alvo"],
                     "mapa_dbf": mapa_dbf, "segundos": round(time.monotonic() - inicio, 3),
                     "camada_saida": nome_saida, "nome_arquivo": medidas["nome_arquivo"]}
        item_arquivo = _gravar_resultado(
            ctx, eid, fmt.content_type, medidas["nome_arquivo"], medidas["pacote"],
            medidas["nome_arquivo"], avisos, relatorio,
        )
        with ctx.db() as cur:
            cur.execute(
                "SELECT plat.evento_registrar('intercambio/exportar_camada', 'item', %s, %s::jsonb, NULL, NULL)",
                (str(exp["item_origem"]),
                 json.dumps({"exportacao_id": eid, "formato": fmt.nome, "job_id": str(ctx.job_id)})),
            )
        ctx.progresso(100, "concluído")
        return {"exportacao_id": eid, "item_arquivo": item_arquivo, "feicoes": medidas["feicoes_saida"],
                "avisos": len(avisos)}
    except Cancelado:
        _marcar_falha(ctx, eid, "cancelamento solicitado")
        raise
    except FalhaDefinitiva as e:
        _marcar_falha(ctx, eid, str(e))
        raise


def _nome_camada_escrow(titulo: str, item_id: str, usados: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", (titulo or "camada").lower()).strip("_")[:40] or "camada"
    nome = f"{base}_{uuid.UUID(item_id).hex[:8]}"
    while nome in usados:  # título igual + hex igual não acontece; defesa barata
        nome += "_"
    usados.add(nome)
    return nome


@tarefa(
    nome="intercambio.exportar_inquilino",
    descricao="Escrow: todas as camadas vetoriais do inquilino num GeoPackage + manifesto JSON, num zip",
    parametros=ExportacaoParametros,
    pesado=True,
    memoria_mb=MEMORIA_MB,
    timeout_s=TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"intercambio:{p.get('exportacao_id')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def intercambio_exportar_inquilino(ctx, exportacao_id: uuid.UUID) -> dict:
    eid = str(exportacao_id)
    inicio = time.monotonic()
    try:
        _carregar_exportacao(ctx, exportacao_id)
        fmt = FORMATOS_SAIDA["gpkg"]
        ctx.progresso(5, "listando as camadas do inquilino")
        with ctx.db() as cur:
            cur.execute(
                "SELECT id, titulo, dados FROM plat.item WHERE tipo = 'camada_vetorial' "
                "AND apagado_em IS NULL ORDER BY criado_em"
            )
            itens = cur.fetchall()
            cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
            slug = cur.fetchone()["slug"]
            tamanho_total = 0
            for it in itens:
                d = it["dados"] or {}
                if d.get("schema") and d.get("tabela"):
                    cur.execute('SELECT pg_total_relation_size(%s::regclass) AS b',
                                (f'"{d["schema"]}"."{d["tabela"]}"',))
                    tamanho_total += int(cur.fetchone()["b"])
        if not itens:
            raise FalhaDefinitiva("o inquilino não tem camada vetorial para exportar")
        if len(itens) > limites.INTERCAMBIO_CAMADAS_ESCROW_MAX:
            raise FalhaDefinitiva(
                f"{len(itens)} camadas acima do máximo {limites.INTERCAMBIO_CAMADAS_ESCROW_MAX} por escrow"
            )
        _guarda_disco(ctx, max(tamanho_total, 1024 * 1024))

        conninfo = _pg_conninfo(ctx.tenant_id)
        gpkg = ctx.dir_trabalho / "escrow.gpkg"
        manifesto_camadas = []
        usados: set[str] = set()
        feicoes_total = 0
        for i, it in enumerate(itens):
            ctx.verificar()
            dados = it["dados"] or {}
            camada = {"id": str(it["id"]), "titulo": it["titulo"], **dados}
            nome = _nome_camada_escrow(it["titulo"], str(it["id"]), usados)
            ctx.progresso(10 + int(80 * i / len(itens)), f"camada {i + 1}/{len(itens)}: {nome}")
            medidas = _exportar_uma(ctx, conninfo, camada, fmt, int(dados["srid"]), nome,
                                    campos=dados.get("campos") or [], destino_compartilhado=gpkg)
            feicoes_total += medidas["feicoes_saida"]
            manifesto_camadas.append({
                "camada_gpkg": nome, "item_id": str(it["id"]), "titulo": it["titulo"],
                "srid": dados["srid"], "geometria": dados.get("geometria"),
                "campos": dados.get("campos") or [], "feicoes": medidas["feicoes_saida"],
                "extent_4326": (dados.get("estatisticas") or {}).get("extent_nativo"),
                "procedencia": dados.get("procedencia"),
            })

        sha_gpkg = hashlib.sha256(gpkg.read_bytes()).hexdigest()
        from app.versao import git_sha_curto

        manifesto = {
            "produto": "escrow do inquilino (L6-02-o)",
            "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "gerador": "plat intercambio.exportar_inquilino v1",
            "versao_plataforma": git_sha_curto(),
            "inquilino": slug,
            "camadas": manifesto_camadas,
            "feicoes_total": feicoes_total,
            "gpkg": {"arquivo": "escrow.gpkg", "sha256": sha_gpkg,
                     "bytes": gpkg.stat().st_size},
        }
        ctx.progresso(90, "montando o pacote")
        pacote_path = ctx.dir_trabalho / "escrow.zip"
        with zipfile.ZipFile(pacote_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(gpkg, "escrow.gpkg")
            zf.writestr("manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=1))
        dados_pacote = pacote_path.read_bytes()
        relatorio = {"camadas": len(manifesto_camadas), "feicoes": feicoes_total,
                     "segundos": round(time.monotonic() - inicio, 3), "nome_arquivo": "escrow.zip",
                     "sha256_gpkg": sha_gpkg}
        data_hoje = time.strftime("%Y%m%d", time.gmtime())
        item_arquivo = _gravar_resultado(
            ctx, eid, "application/zip", f"escrow_{slug}_{data_hoje}.zip", dados_pacote,
            f"escrow_{slug}_{data_hoje}.zip", [], relatorio,
        )
        with ctx.db() as cur:
            cur.execute(
                "SELECT plat.evento_registrar('intercambio/exportar_inquilino', 'tenant', %s, %s::jsonb, "
                "NULL, NULL)",
                (str(ctx.tenant_id), json.dumps({"exportacao_id": eid, "camadas": len(manifesto_camadas),
                                                 "job_id": str(ctx.job_id)})),
            )
        ctx.progresso(100, "concluído")
        return {"exportacao_id": eid, "item_arquivo": item_arquivo, "camadas": len(manifesto_camadas),
                "feicoes": feicoes_total, "segundos": relatorio["segundos"]}
    except Cancelado:
        _marcar_falha(ctx, eid, "cancelamento solicitado")
        raise
    except FalhaDefinitiva as e:
        _marcar_falha(ctx, eid, str(e))
        raise
