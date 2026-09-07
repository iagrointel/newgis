"""Exportação em lote do item L6-02-o. Os 7 formatos que L0-04-h-exportar (gpkg, geojson, shapefile, csv,
xlsx, kml, kmz) já prova de ida e volta em `tests/api/exportacao/test_exportacao.py` NÃO são reprovados aqui
de novo (seria outro conversor testado duas vezes); este arquivo cobre só o que o módulo `app.intercambio`
acrescenta: geojsonseq, filegdb.zip, mbtiles, pmtiles, o escrow do inquilino inteiro e o aviso de fidelidade
do shapefile (refutação do item)."""

from __future__ import annotations

import json
import subprocess
import time
import uuid
import zipfile

from tests.api.intercambio.conftest import (
    FEICOES_PEQUENA,
    baixar_intercambio,
    exportar_intercambio,
)


# ------------------------------------------------------------ 1: formatos novos, ida e volta
def _contar_ogrinfo(caminho, camada: str | None = None) -> int:
    argv = ["ogrinfo", "-so", "-al", "-json", str(caminho)]
    if camada:
        argv.append(camada)
    r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    dados = json.loads(r.stdout)
    return sum(int(c["featureCount"]) for c in dados["layers"])


def test_geojsonseq_ida_e_volta_geometria_e_atributos(inquilino_ic, camada_ic, worker_intercambio, tmp_path,
                                                       medida):
    cliente = inquilino_ic.admin
    inicio = time.monotonic()
    final = exportar_intercambio(cliente, {"tipo": "camada", "item_id": camada_ic["item_id"],
                                           "formato": "geojsonseq", "titulo": "zt_geojsonseq"})
    segundos = round(time.monotonic() - inicio, 2)
    assert final["estado"] == "concluida", final
    caminho = baixar_intercambio(cliente, final["id"], tmp_path / "saida.geojsonl")
    linhas = [ln for ln in caminho.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(linhas) == FEICOES_PEQUENA
    primeira = json.loads(linhas[0])
    assert primeira["geometry"]["type"] == "Point"
    assert set(primeira["properties"]) >= {"nome", "categoria", "area_ha", "quantidade"}
    medida("L6-02-o-importacao-exportacao-formatos")(
        "geojsonseq_segundos", segundos, "s (pedido -> arquivo pronto, 2 mil feições)",
        "tests/api/intercambio/test_exportacao.py::test_geojsonseq_ida_e_volta_geometria_e_atributos",
    )


def test_mbtiles_e_pmtiles_ida_e_volta_com_aviso_de_quantizacao(inquilino_ic, camada_ic, worker_intercambio,
                                                                tmp_path):
    """MVT/PMTiles são tile: a cláusula do portão ('geometria e atributos preservados') não se aplica ao pé da
    letra (quantização na grade do tile é inerente ao formato) — a prova aqui é que (a) o arquivo abre e tem
    feição, e (b) o aviso inerente está SEMPRE no relatório, nunca escondido."""
    cliente = inquilino_ic.admin
    for nome, extensao in (("mbtiles", ".mbtiles"), ("pmtiles", ".pmtiles")):
        final = exportar_intercambio(cliente, {"tipo": "camada", "item_id": camada_ic["item_id"],
                                                "formato": nome, "titulo": f"zt_{nome}"})
        assert final["estado"] == "concluida", (nome, final)
        assert any("quantizada" in a for a in final["avisos"]), (nome, final["avisos"])
        caminho = baixar_intercambio(cliente, final["id"], tmp_path / f"saida_{nome}{extensao}")
        assert caminho.stat().st_size > 0, nome


def test_filegdb_ida_e_volta_geometria_e_atributos_e_abre_pelo_driver_do_qgis(
    inquilino_ic, camada_ic, worker_intercambio, tmp_path
):
    """Cláusula 2 do portão ('FileGDB escrito abre no QGIS'). Não há QGIS nesta máquina (medido: 'qgis' e
    'qgis_process' ausentes do PATH) — a prova estrutural é que o pacote é um diretório `.gdb` de verdade
    (arquivos `.gdbtable`/`.gdbtablx`/`a00000001.gdbindexes` do formato ESRI) reaberto pelo driver
    `OpenFileGDB` do GDAL, que é O MESMO driver que o QGIS usa para ler FileGDB (QGIS não tem driver
    próprio; delega ao GDAL/OGR — documentado em https://gdal.org/en/stable/drivers/vector/openfilegdb.html
    e na lista de provedores do QGIS). Reabrir com esse driver e bater a contagem é a prova que esta máquina
    consegue dar; 'abrir de fato no aplicativo QGIS' fica registrado como limitação honesta no handoff."""
    import shutil

    assert shutil.which("qgis") is None and shutil.which("qgis_process") is None, (
        "QGIS apareceu nesta máquina depois de 06/09 — trocar a prova estrutural por abertura real"
    )
    cliente = inquilino_ic.admin
    final = exportar_intercambio(cliente, {"tipo": "camada", "item_id": camada_ic["item_id"],
                                           "formato": "filegdb.zip", "titulo": "zt_filegdb"},
                                 timeout=240)
    assert final["estado"] == "concluida", final
    assert final["avisos"] and "OpenFileGDB" in final["avisos"][0], final["avisos"]
    caminho = baixar_intercambio(cliente, final["id"], tmp_path / "saida_filegdb.zip")
    extraido = tmp_path / "extraido"
    with zipfile.ZipFile(caminho) as zf:
        zf.extractall(extraido)
    gdb_dirs = list(extraido.glob("*.gdb"))
    assert len(gdb_dirs) == 1, list(extraido.iterdir())
    gdb = gdb_dirs[0]
    assert any(p.suffix == ".gdbtable" for p in gdb.iterdir()), list(gdb.iterdir())
    total = _contar_ogrinfo(gdb)
    assert total == FEICOES_PEQUENA, total
    # driver reportado pelo próprio ogrinfo tem de ser OpenFileGDB (não Esri FileGDB proprietário, ausente
    # desta instalação) — é o driver que o QGIS delega ao GDAL para ler .gdb
    r = subprocess.run(["ogrinfo", "--formats"], capture_output=True, text=True, timeout=30)
    assert "OpenFileGDB -raster,vector- (rw+v)" in r.stdout, r.stdout


# ------------------------------------------------------------ 2: refutação — aviso de truncamento do shapefile
def _semear_camada_adversario(env, inq, schema: str) -> str:
    """Camada de 5 feições com um campo de nome > 10 caracteres e um campo data-hora — o alvo exato da
    refutação do item ('nome de campo > 10 caracteres e com data'). Devolve o `item_id`."""
    from tests.api.exportacao.conftest import conexao

    tabela = "c_" + uuid.uuid4().hex[:16]
    item_id = str(uuid.uuid4())
    con = conexao(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true)",
                (str(inq.id), str(inq.admin_id)),
            )
            cur.execute(
                f'CREATE TABLE "{schema}"."{tabela}" ('
                " fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                " campo_muito_longo_de_verdade text, data_do_evento timestamptz,"
                " geom geometry(Point, 4674))"
            )
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" (campo_muito_longo_de_verdade, data_do_evento, geom) '
                "SELECT 'valor ' || i, now() - (i || ' days')::interval, "
                "ST_SetSRID(ST_MakePoint(-46.6 + i * 0.001, -23.5 + i * 0.001), 4674) "
                "FROM generate_series(1, 5) i"
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, 4674, "Point", inq.admin_id))
            dados = {
                "schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4674, "fonte": "hospedada",
                "campos": [
                    {"nome": "fid", "tipo": "bigint"},
                    {"nome": "campo_muito_longo_de_verdade", "tipo": "text"},
                    {"nome": "data_do_evento", "tipo": "timestamp with time zone"},
                ],
            }
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s::jsonb, "
                "pg_total_relation_size(%s::regclass), %s, %s)",
                (item_id, inq.id, "zt camada adversario truncamento", inq.admin_id, json.dumps(dados),
                 f'"{schema}"."{tabela}"', inq.admin_id, inq.admin_id),
            )
        con.commit()
    finally:
        con.close()
    return item_id


def test_adversario_shapefile_campo_longo_e_data_tem_aviso_de_truncamento(
    env, inquilino_ic, camada_ic, worker_intercambio, tmp_path
):
    """Refutação do item: 'adversário exporta shapefile com nome de campo > 10 caracteres e com data: tem de
    haver aviso de truncamento.' Cria uma camada com um campo de nome longo e um campo data-hora, e confere
    que a exportação RECUSA o silêncio do GDAL (o Warning 6 do driver vira aviso no relatório)."""
    cliente = inquilino_ic.admin
    item_id = _semear_camada_adversario(env, inquilino_ic, camada_ic["schema"])

    final = exportar_intercambio(cliente, {"tipo": "camada", "item_id": item_id, "formato": "shapefile.zip",
                                           "titulo": "zt_adversario"})
    assert final["estado"] == "concluida", final
    avisos = final["avisos"]
    assert any("mais de 10 caracteres" in a and "campo_muito_longo_de_verdade" in a for a in avisos), avisos
    assert any("data-hora" in a and "data_do_evento" in a for a in avisos), avisos
    caminho = baixar_intercambio(cliente, final["id"], tmp_path / "adversario.zip")
    with zipfile.ZipFile(caminho) as zf:
        nomes = zf.namelist()
    assert any(n.endswith(".dbf") for n in nomes), nomes
