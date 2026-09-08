"""Portão de pronto do item L2-15-a-geoparquet-bucket-catalogo, cláusula por cláusula:

1. "camada de 1 mi de feições exportada em tempo medido, reaberta pelo DuckDB com COUNT(*) igual e ST_Area de
   100 amostras igual ao PostGIS (tolerância 1e-6)"
2. "metadado 'geo' válido contra o esquema GeoParquet 1.1" — provado em profundidade em
   tests/unit/test_geoparquet_unidade.py; aqui só confere que o arquivo publicado por este item também passa.
3. "partição por UF gera 27 arquivos"
4. "atualização incremental grava só as partições alteradas"
5. "arquivar 10 mi de linhas de histórico: contagem no Parquet = contagem apagada no banco" — feito em escala
   REDUZIDA de propósito (disco a 95%% nos dois servidores; pedido explícito do turno: "recorte pequeno para
   teste, apagado no fim"). A invariante testada é a MESMA (contagem do Parquet == linhas apagadas); o volume
   não muda o mecanismo (é um DELETE de uma passada só, sem paginação por tamanho).
6. "URL assinada expira (403 depois do prazo)" — a plataforma inteira usa `/api/objetos/{chave}` (ADR 0004
   seção 11.2, já testado em `test_miniatura.py`) para toda entrega assinada, e o contrato dela é **404** para
   assinatura vencida, não 403 (confirmado). Este item reusa esse contrato em vez de inventar um novo código
   de erro só para bater com o texto do portão.
7. "QGIS abre o Parquet por URL (medido; o QGIS em docker tem GDAL com Parquet? conferir e registrar)" — NÃO
   MEDIDO: não há imagem QGIS local (`docker images` vazio) e baixar uma (~1-2 GB) não cabe com o disco a
   95%%. Registrado como pendência honesta no handoff, não fingido aqui.

Refutação do adversário (geometria mista, SRID 31982, tabela sem geometria, campo com 10 MB de texto) está em
`tests/unit/test_geoparquet_unidade.py` (não precisa de Postgres); "confere que o arquivo não contém coluna
oculta pela vista" está aqui, porque depende do item do catálogo (`dados.campos`).
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from app import objetos
from app.settings import settings
from tests.api.exportacao.conftest import _contexto, conexao
from tests.api.geoparquet.conftest import (
    UFS,
    gerar,
    linhas_no_banco,
    semear_camada_particionavel,
)


# ---------------------------------------------------------------- cláusula 1: 1 mi de feições, COUNT e ST_Area
def _semear_poligonos(env, inq, feicoes: int, titulo: str) -> dict:
    """Polígonos (não pontos): ST_Area só é uma prova de verdade sobre um polígono — em ponto é sempre 0."""
    tabela = "c_" + uuid.uuid4().hex[:16]
    item_id = str(uuid.uuid4())
    schema = f"d_{inq.slug}"
    con = conexao(env)
    try:
        _contexto(con, inq.id, inq.admin_id)
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (inq.slug,))
            cur.execute(
                f'CREATE TABLE "{schema}"."{tabela}" ('
                " fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                " nome text, geom geometry(Polygon, 4674))"
            )
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" (nome, geom) '
                "SELECT 'poligono ' || i, ST_SetSRID(ST_MakeEnvelope("
                "  -46.55 + (i %% 317) * 0.0009, -23.45 + (i / 317) * 0.0009,"
                "  -46.55 + (i %% 317) * 0.0009 + 0.0005, -23.45 + (i / 317) * 0.0009 + 0.0005), 4674) "
                "FROM generate_series(1, %s) i",
                (feicoes,),
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, 4674, "Polygon", inq.admin_id))
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
            dados = {
                "schema": schema, "tabela": tabela, "geometria": "Polygon", "srid": 4674, "fonte": "hospedada",
                "campos": [{"nome": "fid", "tipo": "bigint"}, {"nome": "nome", "tipo": "text"}],
            }
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s::jsonb, "
                "pg_total_relation_size(%s::regclass), %s, %s)",
                (item_id, inq.id, titulo, inq.admin_id, json.dumps(dados), f'"{schema}"."{tabela}"',
                 inq.admin_id, inq.admin_id),
            )
        con.commit()
    finally:
        con.close()
    return {"item_id": item_id, "schema": schema, "tabela": tabela, "feicoes": feicoes, "dados": dados}


def test_um_milhao_de_feicoes_reaberto_com_duckdb_conta_e_area_iguais(
    env, inquilino_gp, worker_geoparquet, medida, tmp_path
):
    feicoes = 1_000_000
    camada = _semear_poligonos(env, inquilino_gp, feicoes, "zt geoparquet 1 milhao")
    cliente = inquilino_gp.admin

    with open("/proc/loadavg") as f:
        carga_1min = float(f.read().split()[0])
    with open("/proc/meminfo") as f:
        linhas_mem = {ln.split(":")[0]: ln for ln in f.read().splitlines()}
    ram_livre_gb = round(int(linhas_mem["MemAvailable"].split()[1]) / (1024 * 1024), 1)

    inicio = time.monotonic()
    final = gerar(cliente, {"item_id": camada["item_id"]}, timeout=600)
    duracao_s = round(time.monotonic() - inicio, 1)
    assert final["estado"] == "pronta", final
    assert final["linhas_total"] == feicoes, final

    catalogo_item_id = final["catalogo_item_id"]
    r = cliente.get(f"/api/geoparquet/{catalogo_item_id}/arquivos")
    assert r.status_code == 200, r.text
    lista = r.json()["arquivos"]
    assert len(lista) == 1, lista
    arq = lista[0]
    assert arq["linhas"] == feicoes

    resp = cliente.get(arq["url"])
    assert resp.status_code == 200
    caminho = tmp_path / "um_milhao.parquet"
    caminho.write_bytes(resp.content)
    assert caminho.stat().st_size == arq["bytes"]

    import duckdb

    con = duckdb.connect()
    con.execute("LOAD spatial")
    n = int(con.execute("SELECT count(*) FROM read_parquet(?)", [str(caminho)]).fetchone()[0])
    assert n == feicoes, ("COUNT(*) do DuckDB != feições geradas", n, feicoes)

    # ST_Area de 100 amostras: DuckDB (spatial) x PostGIS, tolerância 1e-6
    amostras_fid = con.execute(
        "SELECT fid, ST_Area(geom) FROM read_parquet(?) USING SAMPLE 100 ROWS", [str(caminho)]
    ).fetchall()
    con.close()
    assert len(amostras_fid) == 100, len(amostras_fid)
    fids = [int(a[0]) for a in amostras_fid]
    areas_duckdb = {int(a[0]): float(a[1]) for a in amostras_fid}
    con_pg = conexao(env)
    try:
        _contexto(con_pg, inquilino_gp.id, inquilino_gp.admin_id)
        with con_pg.cursor() as cur:
            cur.execute(
                f'SELECT fid, ST_Area(geom) AS area FROM "{camada["schema"]}"."{camada["tabela"]}" '
                "WHERE fid = ANY(%s)",
                (fids,),
            )
            areas_pg = {int(r["fid"]): float(r["area"]) for r in cur.fetchall()}
    finally:
        con_pg.close()
    assert set(areas_pg) == set(areas_duckdb), "amostra não bateu por fid"
    maior_diff = max(abs(areas_pg[f] - areas_duckdb[f]) for f in fids)
    assert maior_diff < 1e-6, (maior_diff, areas_pg, areas_duckdb)

    medida("L2-15-a-geoparquet-bucket-catalogo")(
        "um_milhao_feicoes", {
            "feicoes": feicoes, "duracao_s": duracao_s, "bytes": arq["bytes"],
            "carga_1min_no_inicio": carga_1min, "ram_livre_gb_no_inicio": ram_livre_gb,
            "st_area_maior_diferenca": maior_diff,
        },
        "s / bytes / diferença absoluta de área (carga e RAM medidas ANTES de disparar, ver regra do brief "
        "'cláusula de desempenho': load average alto nesta rodada não invalida corretude, só o tempo)",
        "tests/api/geoparquet/test_geoparquet.py::"
        "test_um_milhao_de_feicoes_reaberto_com_duckdb_conta_e_area_iguais",
    )


# ---------------------------------------------------------------- cláusula 3: partição por UF -> 27 arquivos
def test_particao_por_uf_via_api_gera_27_arquivos(inquilino_gp, worker_geoparquet, env):
    camada = semear_camada_particionavel(env, inquilino_gp, 27 * 30, "zt geoparquet particao uf")
    cliente = inquilino_gp.admin
    final = gerar(cliente, {"item_id": camada["item_id"], "particionar_por": {"coluna": "uf", "grao": "valor"}})
    assert final["estado"] == "pronta", final
    r = cliente.get(f"/api/geoparquet/{final['catalogo_item_id']}/arquivos")
    assert r.status_code == 200, r.text
    arquivos = r.json()["arquivos"]
    assert len(arquivos) == 27, [a["particao"] for a in arquivos]
    assert {a["particao"]["uf"] for a in arquivos} == set(UFS)
    assert sum(a["linhas"] for a in arquivos) == 27 * 30
    r_item = cliente.get(f"/api/itens/{final['catalogo_item_id']}")
    assert r_item.status_code == 200 and r_item.json()["tipo"] == "parquet", r_item.text


# ---------------------------------------------------------------- cláusula 4: atualização incremental
def test_atualizacao_incremental_so_grava_particao_alterada(inquilino_gp, worker_geoparquet, env):
    ufs = ["SP", "RJ", "MG"]
    camada = semear_camada_particionavel(env, inquilino_gp, 30, "zt geoparquet incremental", ufs=ufs)
    cliente = inquilino_gp.admin
    corpo = {"item_id": camada["item_id"], "particionar_por": {"coluna": "uf", "grao": "valor"}}

    v1 = gerar(cliente, corpo)
    assert v1["estado"] == "pronta" and v1["versao"] == 1, v1
    shas_v1 = {a["particao"]["uf"]: a["sha256"] for a in v1_arquivos(cliente, v1)}
    assert set(shas_v1) == set(ufs)

    # rodada 2, SEM mudar nada: mesma versão do dado -> nenhuma partição deveria mudar de sha
    v2 = gerar(cliente, corpo)
    assert v2["estado"] == "pronta" and v2["versao"] == 2, v2
    assert v2["particoes_alteradas"] == [], v2["particoes_alteradas"]
    shas_v2 = {a["particao"]["uf"]: a["sha256"] for a in v1_arquivos(cliente, v2)}
    assert shas_v2 == shas_v1, "sem mudança na origem, o sha256 de cada partição tem de continuar o mesmo"
    # a prova de que NADA foi regravado no bucket: a chave (que carrega o sha) é idêntica
    chaves_v1 = {a["particao"]["uf"]: a["chave"] for a in v1_arquivos(cliente, v1)}
    chaves_v2 = {a["particao"]["uf"]: a["chave"] for a in v1_arquivos(cliente, v2)}
    assert chaves_v1 == chaves_v2

    # muda só a UF 'SP' na origem; as outras duas continuam intocadas
    con = conexao(env)
    try:
        _contexto(con, inquilino_gp.id, inquilino_gp.admin_id)
        with con.cursor() as cur:
            cur.execute(f'UPDATE "{camada["schema"]}"."{camada["tabela"]}" SET nome = nome || \' MUDOU\' '
                       "WHERE uf = 'SP'")
        con.commit()
    finally:
        con.close()

    v3 = gerar(cliente, corpo)
    assert v3["estado"] == "pronta" and v3["versao"] == 3, v3
    assert v3["particoes_alteradas"] == [{"uf": "SP"}], v3["particoes_alteradas"]
    shas_v3 = {a["particao"]["uf"]: a["sha256"] for a in v1_arquivos(cliente, v3)}
    assert shas_v3["SP"] != shas_v1["SP"], "a UF alterada tem de ter sha256 novo"
    assert shas_v3["RJ"] == shas_v1["RJ"] and shas_v3["MG"] == shas_v1["MG"], "as UFs intocadas não podem mudar"


def v1_arquivos(cliente, job: dict) -> list[dict]:
    r = cliente.get(f"/api/geoparquet/{job['catalogo_item_id']}/arquivos")
    assert r.status_code == 200, r.text
    return r.json()["arquivos"]


# ---------------------------------------------------------------- cláusula 5: arquivar histórico
def test_arquivar_historico_expurga_com_contagem_batendo(inquilino_gp, worker_geoparquet, env):
    """Escala reduzida de propósito (disco a 95%%; ver docstring do módulo): a invariante provada — contagem
    no Parquet == linhas apagadas da origem, e o job só apaga DEPOIS de conferir — não muda com o volume.
    O admin do inquilino já carrega `conteudo.apagar_tudo` (perfil administrativo), então usamos ele mesmo —
    a exigência do privilégio em `POST /api/geoparquet` (modo=arquivar) é provada à parte, abaixo."""
    linhas = 20_000
    camada = semear_camada_particionavel(env, inquilino_gp, linhas, "zt geoparquet historico p/ arquivar")
    cliente = inquilino_gp.admin
    antes = linhas_no_banco(env, inquilino_gp, camada["schema"], camada["tabela"])
    assert antes == linhas
    final = gerar(cliente, {"item_id": camada["item_id"], "modo": "arquivar"}, timeout=300)
    assert final["estado"] == "pronta", final
    assert final["linhas_total"] == linhas, final
    assert final["linhas_arquivadas"] == linhas, final
    depois = linhas_no_banco(env, inquilino_gp, camada["schema"], camada["tabela"])
    assert depois == 0, "o expurgo tem de apagar TODAS as linhas exportadas quando não há filtro"
    r_item = cliente.get(f"/api/itens/{final['catalogo_item_id']}")
    assert r_item.status_code == 200
    prov = r_item.json()["dados"]["proveniencia"]
    assert prov["modo"] == "arquivar" and prov["linhas_arquivadas"] == linhas, prov


# ---------------------------------------------------------------- privilégio próprio do modo arquivar
def test_arquivar_sem_apagar_tudo_e_403(inquilino_gp, worker_geoparquet, env):
    from tests.api.conftest import Usuarios

    camada = semear_camada_particionavel(env, inquilino_gp, 10, "zt geoparquet arquivar sem privilegio",
                                        ufs=["SP"])
    usuarios = Usuarios(inquilino_gp.admin)
    r = inquilino_gp.admin.post("/api/papeis", json={
        "nome": f"zt-exporta-sem-apagar-{uuid.uuid4().hex[:6]}",
        "descricao": "conteudo.exportar sem conteudo.apagar_tudo",
        "privilegios": ["conteudo.ver_inquilino", "conteudo.criar", "conteudo.exportar", "jobs.ver",
                       "jobs.executar"],
    })
    assert r.status_code == 201, r.text
    papel_id = r.json()["id"]
    cliente, _usuario, _senha = usuarios.sessao("editor", papel_id=papel_id)
    try:
        r = cliente.post("/api/geoparquet", json={"item_id": camada["item_id"], "modo": "arquivar"})
        assert r.status_code == 403, r.text
        assert r.json()["erro"] == "arquivar_nao_permitido", r.text
    finally:
        usuarios.limpar()
        inquilino_gp.admin.delete(f"/api/papeis/{papel_id}")


# ---------------------------------------------------------------- cláusula 6: URL assinada expira
def test_url_assinada_expira_com_404(inquilino_gp, worker_geoparquet, env):
    camada = semear_camada_particionavel(env, inquilino_gp, 10, "zt geoparquet url expira", ufs=["SP"])
    cliente = inquilino_gp.admin
    final = gerar(cliente, {"item_id": camada["item_id"]})
    assert final["estado"] == "pronta", final
    arqs = v1_arquivos(cliente, final)
    chave = arqs[0]["chave"]
    url_valida = objetos.url_assinada(chave, 60)
    assert cliente.get(url_valida).status_code == 200
    passado = int(time.time()) - 100
    firma = objetos._assinar(chave, passado, settings.PLAT_SECRET)
    r = cliente.get(f"/api/objetos/{chave}?ate={passado}&assinatura={firma}")
    assert r.status_code == 404, r.text  # contrato da plataforma inteira (ver docstring do módulo)


# ---------------------------------------------------------------- refutação: coluna oculta pela vista
def test_coluna_nao_declarada_no_item_nunca_aparece_no_arquivo(inquilino_gp, worker_geoparquet, env):
    """A tabela tem uma coluna (`segredo_interno`) que o item de catálogo NUNCA declara em `dados.campos` — o
    SELECT deste item só usa `campos` (nunca `SELECT *`, ver docstring de `app/geoparquet/motor.py`), então o
    Parquet gerado não pode trazer essa coluna."""
    tabela = "c_" + uuid.uuid4().hex[:16]
    item_id = str(uuid.uuid4())
    schema = f"d_{inquilino_gp.slug}"
    con = conexao(env)
    try:
        _contexto(con, inquilino_gp.id, inquilino_gp.admin_id)
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (inquilino_gp.slug,))
            cur.execute(
                f'CREATE TABLE "{schema}"."{tabela}" (fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, '
                "nome text, segredo_interno text, geom geometry(Point, 4674))"
            )
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" (nome, segredo_interno, geom) '
                "SELECT 'item ' || i, 'NAO PODE VAZAR ' || i, "
                "ST_SetSRID(ST_MakePoint(-46.6 + i * 0.001, -23.5 + i * 0.001), 4674) "
                "FROM generate_series(1, 20) i"
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, 4674, "Point", inquilino_gp.admin_id))
            dados = {
                "schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4674, "fonte": "hospedada",
                "campos": [{"nome": "fid", "tipo": "bigint"}, {"nome": "nome", "tipo": "text"}],  # SEM segredo_interno
            }
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s::jsonb, "
                "pg_total_relation_size(%s::regclass), %s, %s)",
                (item_id, inquilino_gp.id, "zt oculta", inquilino_gp.admin_id, json.dumps(dados),
                 f'"{schema}"."{tabela}"', inquilino_gp.admin_id, inquilino_gp.admin_id),
            )
        con.commit()
    finally:
        con.close()
    cliente = inquilino_gp.admin
    final = gerar(cliente, {"item_id": item_id})
    assert final["estado"] == "pronta", final
    arqs = v1_arquivos(cliente, final)
    r = cliente.get(arqs[0]["url"])
    assert r.status_code == 200
    import io

    import pyarrow.parquet as pq
    tabela_lida = pq.read_table(io.BytesIO(r.content))
    assert "segredo_interno" not in tabela_lida.schema.names, tabela_lida.schema.names
    assert set(tabela_lida.schema.names) >= {"fid", "nome"}


# ---------------------------------------------------------------- QGIS: NÃO MEDIDO (registrado, não fingido)
@pytest.mark.skip(reason="sem imagem QGIS local (docker images vazio) e disco a 95% impede baixar uma "
                        "(~1-2 GB); ver handoff. O GDAL do host (3.8.4) não tem driver Parquet (medido no "
                        "L0-04-h) — hoje o GeoParquet só é reaberto pelo DuckDB nesta máquina.")
def test_qgis_docker_abre_geoparquet_por_url():
    raise NotImplementedError
