"""Portão de pronto do item L2-01-l (exportação a partir do mapa), cláusula por cláusula.

1. "12 formatos gerados da seleção de 500 feições, cada arquivo reaberto por ogrinfo com contagem 500 e
   CRS pedido"                                → test_doze_formatos_da_selecao_de_500_com_contagem_e_crs
2. "exportação respeita campo oculto da vista"→ test_vista_esconde_campo_na_exportacao_e_no_filtro
3. "e a permissão 'exportar' do item (403 quando negada)"
                                              → test_permissao_de_exportar_negada_devolve_403
4. "pacote reimportado em outra instalação recria mapa com as mesmas camadas e estilos"
                                              → test_pacote_de_mapa_ida_e_volta_em_outro_inquilino
Refutação do item (adversário):
   - XLSX acima do teto de linhas do formato → test_xlsx_acima_do_teto_de_linhas_e_recusado_com_mensagem
   - DXF com atributos (perda declarada)      → test_dxf_declara_a_perda_de_atributos
   - o pacote não contém dado de outra camada → test_pacote_nao_leva_camada_que_o_mapa_nao_cita

As cláusulas do PNG e do e2e do botão são de tela e ficam em tests/e2e/test_exportar_mapa.py.
"""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.exportacao.formatos import FORMATOS
from tests.api.exportacao.conftest import (
    InquilinoDeExportacao,
    conexao,
    exportar,
    semear_camada,
)

FEICOES_DA_CAMADA = 2_000
SELECAO = 500
SRID_PEDIDO = 31983  # SIRGAS 2000 / UTM 23S — projetado, para o CRS lido do arquivo não ser o da tabela
# Os 12 formatos da cláusula 1: todos os que o `ogrinfo` desta máquina reabre feição a feição. Fora ficam o
# GeoParquet (sem driver Parquet neste GDAL — portão do L0-04-h), os tilados e o `pacote`, que tem cláusula
# própria mais abaixo.
DOZE = [n for n, f in FORMATOS.items() if f.reabre_com_ogrinfo and not f.tilado and n != "pacote"]


# ---------------------------------------------------------------- cenário
@pytest.fixture(scope="module")
def inquilino_mapa(sessao_plat):
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture(scope="module")
def inquilino_destino(sessao_plat):
    """A "outra instalação" do teste de ida e volta do pacote: outro inquilino, outro schema de dado."""
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture(scope="module")
def camada(env, inquilino_mapa):
    return semear_camada(env, inquilino_mapa, FEICOES_DA_CAMADA, "zt camada do mapa")


@pytest.fixture(scope="module")
def camada_nao_citada(env, inquilino_mapa):
    """Segunda camada do MESMO inquilino, que o mapa não cita: é ela que o pacote não pode levar."""
    return semear_camada(env, inquilino_mapa, 300, "zt camada fora do mapa", prefixo="FORA-DO-MAPA")


@pytest.fixture(scope="module")
def selecao_de_500(env, inquilino_mapa, camada) -> list[int]:
    """Os 500 fid que a seleção do mapa produziria (retângulo/laço/filtro dão o mesmo tipo de lista)."""
    con = conexao(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                "set_config('plat.login', 'teste-exportacao-mapa', true)",
                (str(inquilino_mapa.id), str(inquilino_mapa.admin_id)),
            )
            cur.execute(f'SELECT fid FROM "{camada["schema"]}"."{camada["tabela"]}" ORDER BY fid LIMIT %s',
                        (SELECAO,))
            fids = [int(r["fid"]) for r in cur.fetchall()]
        con.commit()
    finally:
        con.close()
    assert len(fids) == SELECAO
    return fids


def ogrinfo(caminho: Path, formato: str) -> str:
    alvo = str(caminho)
    f = FORMATOS[formato]
    if formato == "shapefile":
        alvo = f"/vsizip/{caminho}"
    elif formato == "kmz":
        alvo = f"/vsizip/{caminho}/doc.kml"
    elif f.caminho_interno:
        alvo = f"/vsizip/{caminho}/{f.caminho_interno}"
    r = subprocess.run(["ogrinfo", "-so", "-al", alvo], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"ogrinfo não reabriu {caminho.name}: {r.stderr[:400]}"
    return r.stdout


def contagem(saida: str) -> int:
    linhas = [int(li.split(":", 1)[1]) for li in saida.splitlines() if li.strip().startswith("Feature Count:")]
    assert linhas, saida[:400]
    return sum(linhas)


def epsg_declarado(saida: str) -> int | None:
    """O ÚLTIMO `ID["EPSG",n]` do WKT é o do CRS anunciado pelo arquivo; os anteriores são os do CRS de
    base (num PROJCRS o `BASEGEOGCRS` vem antes e traz o EPSG geográfico — 4674 no caso desta camada)."""
    codigos = [int(re.search(r'ID\["EPSG",\s*(\d+)', li).group(1)) for li in saida.splitlines()
               if 'ID["EPSG"' in li]
    return codigos[-1] if codigos else None


def baixar(cliente, exportacao_id: str, destino: Path) -> Path:
    r = cliente.get(f"/api/exportacoes/{exportacao_id}/baixar")
    assert r.status_code == 200, r.text
    destino.write_bytes(r.content)
    return destino


# ---------------------------------------------------------------- 1: 12 formatos da seleção de 500
def test_doze_formatos_da_selecao_de_500_com_contagem_e_crs(inquilino_mapa, camada, selecao_de_500,
                                                            worker_exportacao, medida, tmp_path):
    """Cláusula 1: "12 formatos gerados da seleção de 500 feições, cada arquivo reaberto por ogrinfo com
    contagem 500 e CRS pedido".

    O CRS pedido depende da política do formato (`app/exportacao/formatos.py`): quem tem CRS livre recebe
    EPSG:31983 e tem de devolver 31983; quem tem CRS preso pela especificação (GeoJSON, GeoJSON Sequence,
    KML/KMZ) devolve 4326 e RECUSA o 31983 com 422 — é a diferença entre um arquivo honesto e um arquivo
    com coordenada projetada sob rótulo de WGS 84."""
    cliente = inquilino_mapa.admin
    assert len(DOZE) == 12, sorted(DOZE)
    lidos: dict[str, dict] = {}
    for nome in DOZE:
        f = FORMATOS[nome]
        pedido = {"item_id": camada["item_id"], "formato": nome, "nome": f"zt-sel-{nome}",
                  "ids": selecao_de_500}
        if f.crs_saida == "livre":
            pedido["srid_saida"] = SRID_PEDIDO
        else:
            recusa = cliente.post("/api/exportacoes", json={**pedido, "srid_saida": SRID_PEDIDO})
            if f.crs_saida in ("4326", "3857"):
                assert recusa.status_code == 422, (nome, recusa.text)
                assert recusa.json()["erro"] == "crs_fixo_do_formato", recusa.text
        final = exportar(cliente, pedido, timeout=600)
        assert final["estado"] == "pronta", (nome, final["estado"], final["erro"])
        assert final["feicoes"] == SELECAO, (nome, final["feicoes"])
        caminho = baixar(cliente, final["id"], tmp_path / f"sel_{nome}{f.extensao}")
        saida = ogrinfo(caminho, nome)
        epsg = epsg_declarado(saida)
        esperado = SRID_PEDIDO if f.crs_saida == "livre" else (int(f.crs_saida)
                                                               if f.crs_saida.isdigit() else None)
        assert contagem(saida) == SELECAO, (nome, saida[:300])
        assert epsg == esperado, (nome, epsg, esperado)
        lidos[nome] = {"feicoes": contagem(saida), "epsg": epsg, "bytes": final["bytes"]}
    medida("L2-01-l-exportacao-do-mapa")(
        "formatos_da_selecao_de_500", lidos, "feições e EPSG lidos do arquivo baixado",
        "tests/api/exportacao/test_exportacao_mapa.py::test_doze_formatos_da_selecao_de_500_com_contagem_e_crs",
    )


def test_formato_tilado_sai_e_declara_que_a_contagem_nao_e_a_do_banco(inquilino_mapa, camada,
                                                                      selecao_de_500, worker_exportacao,
                                                                      tmp_path):
    """MVT e PMTiles saem da mesma seleção, mas a contagem do arquivo é por tile: o pedido devolve a perda
    declarada em vez de prometer 500."""
    cliente = inquilino_mapa.admin
    for nome in ("mvt", "pmtiles"):
        r = cliente.post("/api/exportacoes", json={"item_id": camada["item_id"], "formato": nome,
                                                   "nome": f"zt-tile-{nome}", "ids": selecao_de_500})
        assert r.status_code == 202, (nome, r.text)
        assert any("tile" in p for p in r.json()["perda_declarada"]), r.json()
        final = exportar(cliente, {"item_id": camada["item_id"], "formato": nome,
                                   "nome": f"zt-tile2-{nome}", "ids": selecao_de_500}, timeout=600)
        assert final["estado"] == "pronta", (nome, final)
        caminho = baixar(cliente, final["id"], tmp_path / f"tile_{nome}{FORMATOS[nome].extensao}")
        assert caminho.stat().st_size > 0


def test_filtro_do_construtor_exporta_so_o_que_o_filtro_diz(inquilino_mapa, camada, worker_exportacao,
                                                            tmp_path):
    """O mesmo CQL2-JSON de `POST /api/mapa/camadas/{id}/filtrar` vale como recorte da exportação."""
    cliente = inquilino_mapa.admin
    filtro = {"op": "=", "args": [{"property": "categoria"}, "mata"]}
    r = cliente.post("/api/mapa/camadas/{}/filtrar".format(camada["item_id"]), json={"filtro": filtro})
    assert r.status_code == 200, r.text
    esperado = r.json()["n"]
    assert 0 < esperado < FEICOES_DA_CAMADA
    final = exportar(cliente, {"item_id": camada["item_id"], "formato": "gpkg", "nome": "zt-filtro",
                               "filtro": filtro}, timeout=600)
    assert final["estado"] == "pronta", final
    assert final["feicoes"] == esperado, (final["feicoes"], esperado)
    caminho = baixar(cliente, final["id"], tmp_path / "filtro.gpkg")
    assert contagem(ogrinfo(caminho, "gpkg")) == esperado


def test_filtro_com_campo_fora_da_lista_branca_e_recusado(inquilino_mapa, camada):
    r = inquilino_mapa.admin.post("/api/exportacoes", json={
        "item_id": camada["item_id"], "formato": "gpkg",
        "filtro": {"op": "=", "args": [{"property": "senha_do_admin"}, "x"]}})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"]["codigo"] == "campo_nao_permitido", r.text


# ---------------------------------------------------------------- 2: campo oculto da vista
@pytest.fixture(scope="module")
def vista_com_campo_oculto(inquilino_mapa, camada) -> str:
    r = inquilino_mapa.admin.post("/api/itens", json={
        "tipo": "vista_de_camada", "titulo": "zt vista sem a coluna quantidade",
        "dados": {"camada_id": camada["item_id"], "campos_ocultos": ["quantidade"]}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_vista_esconde_campo_na_exportacao_e_no_filtro(inquilino_mapa, camada, vista_com_campo_oculto,
                                                       worker_exportacao, tmp_path):
    """Cláusula: "exportação respeita campo oculto da vista". Três provas na mesma vista: o campo não sai
    no arquivo, pedi-lo explicitamente é 422, e filtrá-lo também é 422 (esconder um campo que ainda pode
    ser usado como filtro não esconde nada: o filtro devolve a informação pela contagem)."""
    cliente = inquilino_mapa.admin
    final = exportar(cliente, {"item_id": vista_com_campo_oculto, "formato": "gpkg", "nome": "zt-vista"},
                     timeout=600)
    assert final["estado"] == "pronta", final
    caminho = baixar(cliente, final["id"], tmp_path / "vista.gpkg")
    saida = ogrinfo(caminho, "gpkg")
    assert "quantidade" not in saida, saida[:600]
    assert "categoria" in saida, saida[:600]

    r = cliente.post("/api/exportacoes", json={"item_id": vista_com_campo_oculto, "formato": "gpkg",
                                               "campos": ["nome", "quantidade"]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_oculto", r.text

    r = cliente.post("/api/exportacoes", json={
        "item_id": vista_com_campo_oculto, "formato": "gpkg",
        "filtro": {"op": ">", "args": [{"property": "quantidade"}, 50]}})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"]["codigo"] == "campo_nao_permitido", r.text


def test_selecao_salva_como_origem_exporta_os_fids_dela(inquilino_mapa, camada, selecao_de_500,
                                                        worker_exportacao, tmp_path):
    """A seleção SALVA (item `selecao` do L2-01-h) é origem de exportação como qualquer camada."""
    cliente = inquilino_mapa.admin
    r = cliente.post("/api/itens", json={
        "tipo": "selecao", "titulo": "zt selecao de 500",
        "dados": {"camada_id": camada["item_id"], "ids": selecao_de_500[:120],
                  "criterio": {"modo": "retangulo"}, "contagem": 120}})
    assert r.status_code == 201, r.text
    final = exportar(cliente, {"item_id": r.json()["id"], "formato": "gpkg", "nome": "zt-selecao"},
                     timeout=600)
    assert final["estado"] == "pronta", final
    assert final["feicoes"] == 120, final
    caminho = baixar(cliente, final["id"], tmp_path / "selecao.gpkg")
    assert contagem(ogrinfo(caminho, "gpkg")) == 120


# ---------------------------------------------------------------- 3: permissão
def test_permissao_de_exportar_negada_devolve_403(inquilino_mapa, camada, editor_sem_exportar):
    """Cláusula: "a permissão 'exportar' do item (403 quando negada)". Duas negativas diferentes: quem não
    tem o privilégio `conteudo.exportar` não passa da porta; quem tem o privilégio mas não é dono do item
    também não, enquanto o dono não ligar `dados.exportacao.permitir_outros`."""
    r = editor_sem_exportar.post("/api/exportacoes", json={"item_id": camada["item_id"], "formato": "gpkg"})
    assert r.status_code == 403, r.text

    from tests.api.conftest import Usuarios

    usuarios = Usuarios(inquilino_mapa.admin)
    try:
        outro, _u, _s = usuarios.sessao("editor")
        # item privado é 404 até dentro do mesmo inquilino (a RLS esconde o que não foi compartilhado):
        # para CHEGAR à checagem de exportação, a camada precisa antes estar visível
        assert outro.post("/api/exportacoes",
                          json={"item_id": camada["item_id"], "formato": "gpkg"}).status_code == 404
        r = inquilino_mapa.admin.put(f"/api/itens/{camada['item_id']}/compartilhamento",
                                     json={"acesso": "inquilino"})
        assert r.status_code == 200, r.text
        r = outro.post("/api/exportacoes", json={"item_id": camada["item_id"], "formato": "gpkg"})
        assert r.status_code == 403, r.text
        assert r.json()["erro"] == "exportacao_nao_permitida", r.text
    finally:
        inquilino_mapa.admin.put(f"/api/itens/{camada['item_id']}/compartilhamento",
                                 json={"acesso": "privado"})
        usuarios.limpar()


# ---------------------------------------------------------------- refutação: teto do XLSX
@pytest.mark.lento
def test_xlsx_acima_do_teto_de_linhas_e_recusado_com_mensagem(env, inquilino_mapa, worker_exportacao):
    """Refutação do adversário: "exporta camada de 1 mi de feições em XLSX (limite de linhas do formato
    deve ser recusado com mensagem, não arquivo truncado)".

    O teto do XLSX é 1.048.576 linhas COM o cabeçalho, e não 1 milhão: por isso a camada deste teste tem
    1.048.600 feições — 1 milhão passaria, e um teste que passa por baixo do limite não prova nada. A
    recusa é 422 ANTES de existir job, para o usuário não esperar minutos por um erro."""
    grande = semear_camada(env, inquilino_mapa, 1_048_600, "zt camada acima do teto do xlsx", prefixo="p")
    r = inquilino_mapa.admin.post("/api/exportacoes", json={"item_id": grande["item_id"], "formato": "xlsx"})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "formato_limite_de_linhas", corpo
    assert corpo["detalhe"]["linhas"] == 1_048_600, corpo
    assert "1048576" in corpo["mensagem"].replace(".", ""), corpo["mensagem"]
    # e a mesma camada sai em CSV, que não tem teto de linhas — a recusa é do FORMATO, não da plataforma
    r = inquilino_mapa.admin.post("/api/exportacoes", json={"item_id": grande["item_id"], "formato": "csv",
                                                            "nome": "zt-grande-csv"})
    assert r.status_code == 202, r.text
    inquilino_mapa.admin.delete(f"/api/exportacoes/{r.json()['exportacao_id']}")


def test_xlsx_abaixo_do_teto_continua_saindo(inquilino_mapa, camada, selecao_de_500, worker_exportacao,
                                             tmp_path):
    final = exportar(inquilino_mapa.admin, {"item_id": camada["item_id"], "formato": "xlsx",
                                            "nome": "zt-xlsx", "ids": selecao_de_500}, timeout=600)
    assert final["estado"] == "pronta", final
    caminho = baixar(inquilino_mapa.admin, final["id"], tmp_path / "sel.xlsx")
    assert contagem(ogrinfo(caminho, "xlsx")) == SELECAO


# ---------------------------------------------------------------- refutação: DXF sem atributo
def test_dxf_declara_a_perda_de_atributos(inquilino_mapa, camada, selecao_de_500, worker_exportacao,
                                          tmp_path):
    """Refutação do adversário: "DXF com atributos (perda declarada)". O DXF sai, com a geometria certa, e
    a resposta do pedido diz que os atributos ficam de fora — o arquivo não é truncado em silêncio."""
    cliente = inquilino_mapa.admin
    r = cliente.post("/api/exportacoes", json={"item_id": camada["item_id"], "formato": "dxf",
                                               "nome": "zt-dxf-aviso", "ids": selecao_de_500,
                                               "campos": ["nome", "categoria"]})
    assert r.status_code == 202, r.text
    perdas = r.json()["perda_declarada"]
    assert any("não guarda atributo" in p for p in perdas), perdas
    assert any("nome" in p and "categoria" in p for p in perdas), perdas
    final = exportar(cliente, {"item_id": camada["item_id"], "formato": "dxf", "nome": "zt-dxf",
                               "ids": selecao_de_500, "campos": ["nome", "categoria"]}, timeout=600)
    assert final["estado"] == "pronta", final
    caminho = baixar(cliente, final["id"], tmp_path / "sel.dxf")
    saida = ogrinfo(caminho, "dxf")
    assert contagem(saida) == SELECAO, saida[:300]
    # o driver cria os seus próprios campos (Layer, SubClasses, ...); os NOSSOS não estão lá
    assert "categoria" not in saida.lower().split("feature count")[0], saida[:600]


# ---------------------------------------------------------------- 4: pacote de mapa, ida e volta
@pytest.fixture(scope="module")
def mapa_com_uma_camada(inquilino_mapa, camada, camada_nao_citada) -> str:
    r = inquilino_mapa.admin.post("/api/itens", json={
        "tipo": "mapa", "titulo": "zt mapa do pacote", "descricao": "mapa de teste do item L2-01-l",
        "dados": {"esquema_versao": 1, "corpo": {
            "centro": [-46.54, -23.44], "zoom": 12,
            "camadas": [{"camada_id": camada["item_id"], "titulo": "zt camada do mapa", "visivel": True}]}}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def pacote_gerado(inquilino_mapa, mapa_com_uma_camada, worker_exportacao, tmp_path_factory) -> Path:
    final = exportar(inquilino_mapa.admin, {"item_id": mapa_com_uma_camada, "formato": "pacote",
                                            "nome": "zt-pacote"}, timeout=900)
    assert final["estado"] == "pronta", final
    destino = tmp_path_factory.mktemp("pacote") / "mapa.zip"
    return baixar(inquilino_mapa.admin, final["id"], destino)


def test_pacote_nao_leva_camada_que_o_mapa_nao_cita(pacote_gerado, camada_nao_citada):
    """Refutação do adversário: "confere que o pacote não contém dado de outra camada". O inquilino tem
    duas camadas; o mapa cita uma. O GeoPackage do pacote tem UMA tabela, e nenhuma feição da outra."""
    with zipfile.ZipFile(pacote_gerado) as z:
        nomes = set(z.namelist())
        man = json.loads(z.read("MANIFESTO.json").decode("utf-8"))
    assert "dados.gpkg" in nomes and "MANIFESTO.json" in nomes, nomes
    assert len(man["camadas"]) == 1, man["camadas"]
    assert man["camadas"][0]["estilo_maplibre"] in nomes and man["camadas"][0]["estilo_sld"] in nomes, nomes
    saida = subprocess.run(["ogrinfo", "-so", f"/vsizip/{pacote_gerado}/dados.gpkg"],
                           capture_output=True, text=True, timeout=300)
    assert saida.returncode == 0, saida.stderr[:400]
    tabelas = [li for li in saida.stdout.splitlines() if li.strip().startswith(("1:", "2:", "3:"))]
    assert len(tabelas) == 1, saida.stdout
    despejo = subprocess.run(["ogr2ogr", "-f", "CSV", "/vsistdout/",
                              f"/vsizip/{pacote_gerado}/dados.gpkg", "cam_1"],
                             capture_output=True, text=True, timeout=600)
    assert despejo.returncode == 0, despejo.stderr[:400]
    assert "FORA-DO-MAPA" not in despejo.stdout, "o pacote levou feição de uma camada que o mapa não cita"
    assert despejo.stdout.count("\n") - 1 == FEICOES_DA_CAMADA, despejo.stdout[:200]


def test_pacote_de_mapa_ida_e_volta_em_outro_inquilino(pacote_gerado, inquilino_destino, inquilino_mapa,
                                                       mapa_com_uma_camada):
    """Cláusula 4: "pacote reimportado recria mapa com as mesmas camadas e estilos (teste de ida e volta)".

    O destino é OUTRO inquilino — outro schema de dado, outras tabelas, outros uuid: é o que "levar a outra
    instalação" quer dizer. A prova compara o que o usuário vê: título do mapa, número e títulos de camada,
    contagem de feições e a simbologia (que é o que gera estilo e legenda, `app/mapa/simbologia.py`)."""
    destino = inquilino_destino.admin
    r = destino.post("/api/mapa/pacotes/importar", content=pacote_gerado.read_bytes(),
                     headers={"Content-Type": "application/zip"}, timeout=900)
    assert r.status_code == 201, r.text
    novo = r.json()
    assert novo["titulo"] == "zt mapa do pacote", novo
    assert len(novo["camadas"]) == 1, novo

    r = destino.get(f"/api/itens/{novo['mapa_id']}")
    assert r.status_code == 200, r.text
    corpo_novo = r.json()["dados"]["corpo"]
    assert corpo_novo["zoom"] == 12 and corpo_novo["centro"] == [-46.54, -23.44], corpo_novo
    # o de-para reescreveu o corpo: o mapa do destino aponta para a camada NOVA, não para o uuid de origem
    assert corpo_novo["camadas"][0]["camada_id"] == novo["camadas"][0]["id"], corpo_novo
    assert corpo_novo["camadas"][0]["camada_id"] != novo["camadas"][0]["id_no_pacote"], corpo_novo

    ficha = destino.get(f"/api/mapa/camadas/{novo['camadas'][0]['id']}")
    assert ficha.status_code == 200, ficha.text
    ficha = ficha.json()
    assert ficha["titulo"] == "zt camada do mapa", ficha
    assert ficha["n_feicoes"] in (None, FEICOES_DA_CAMADA), ficha["n_feicoes"]

    original = inquilino_mapa.admin.get(f"/api/mapa/camadas/{corpo_novo['camadas'][0]['camada_id']}")
    assert original.status_code == 404, "a camada do destino não pode ser visível do inquilino de origem"

    r = destino.get(f"/api/mapa/camadas/{novo['camadas'][0]['id']}/estilo?formato=maplibre")
    assert r.status_code == 200, r.text
    estilo_destino = r.json()
    with zipfile.ZipFile(pacote_gerado) as z:
        estilo_pacote = json.loads(z.read("estilos/cam_1.json").decode("utf-8"))
    cores_pacote = [c["paint"] for c in estilo_pacote["layers"]]
    cores_destino = [c["paint"] for c in estilo_destino["camadas"]]
    assert cores_pacote == cores_destino, (cores_pacote, cores_destino)


def test_pacote_invalido_e_recusado_com_a_razao(inquilino_destino, tmp_path):
    zip_ruim = tmp_path / "ruim.zip"
    with zipfile.ZipFile(zip_ruim, "w") as z:
        z.writestr("leiame.txt", "isto não é um pacote")
    r = inquilino_destino.admin.post("/api/mapa/pacotes/importar", content=zip_ruim.read_bytes(),
                                     headers={"Content-Type": "application/zip"})
    assert r.status_code == 422, r.text
    assert "MANIFESTO.json" in r.json()["mensagem"], r.text


def test_mapa_sem_camada_nao_vira_pacote(inquilino_mapa):
    r = inquilino_mapa.admin.post("/api/itens", json={
        "tipo": "mapa", "titulo": "zt mapa vazio", "dados": {"esquema_versao": 1, "corpo": {"camadas": []}}})
    assert r.status_code == 201, r.text
    r = inquilino_mapa.admin.post("/api/exportacoes", json={"item_id": r.json()["id"], "formato": "pacote"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "mapa_sem_camadas", r.text


# ---------------------------------------------------------------- cópia de feição e estilo
def test_copiar_feicao_como_geojson_e_como_wkt(inquilino_mapa, camada, selecao_de_500):
    """A feição copiada vem da TABELA (geometria inteira), não do tile — e em EPSG:4326, que é o que
    qualquer destino da área de transferência (QGIS, editor de texto, outra aplicação) espera."""
    cliente = inquilino_mapa.admin
    fid = selecao_de_500[0]
    r = cliente.get(f"/api/mapa/camadas/{camada['item_id']}/feicoes/{fid}?formato=geojson")
    assert r.status_code == 200, r.text
    feicao = json.loads(r.json()["texto"])
    assert feicao["type"] == "Feature" and feicao["geometry"]["type"] == "Point", feicao
    assert feicao["properties"]["categoria"] in ("mata", "pasto", "urbano"), feicao
    assert r.json()["crs"] == "EPSG:4326"

    r = cliente.get(f"/api/mapa/camadas/{camada['item_id']}/feicoes/{fid}?formato=wkt")
    assert r.status_code == 200, r.text
    assert r.json()["texto"].startswith("POINT("), r.json()["texto"][:60]

    assert cliente.get(f"/api/mapa/camadas/{camada['item_id']}/feicoes/999999999").status_code == 404
    assert cliente.get(f"/api/mapa/camadas/{camada['item_id']}/feicoes/{fid}?formato=dwg").status_code == 422


def test_estilo_da_camada_em_maplibre_e_em_sld(inquilino_mapa, camada):
    cliente = inquilino_mapa.admin
    r = cliente.get(f"/api/mapa/camadas/{camada['item_id']}/estilo")
    assert r.status_code == 200, r.text
    maplibre = r.json()
    assert maplibre["camadas"] and maplibre["legenda"], maplibre
    r = cliente.get(f"/api/mapa/camadas/{camada['item_id']}/estilo?formato=sld")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.ogc.sld+xml"), r.headers
    assert 'version="1.0.0"' in r.text and "StyledLayerDescriptor" in r.text, r.text[:300]
    for entrada in maplibre["legenda"]:
        assert entrada["cor"] in r.text, (entrada, r.text[:400])
