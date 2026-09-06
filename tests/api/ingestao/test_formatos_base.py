"""Formatos do portão e camadas do arquivo (itens L0-04-b-inspecao, L0-04-d-formatos-base, L0-04-ingest-vetor).

Conserto dos achados do adversário do turno 3: a instalação anunciava 4 formatos contra os 9 do portão do
L0-04-d, a rota que anuncia os formatos respondia 404, um arquivo com três camadas perdia duas sem aviso, um
CSV de 300 colunas e nenhuma linha terminava em silêncio e um zip malformado saía 500 em vez de 422."""

from __future__ import annotations

import pytest

from tests.api.ingestao.conftest import GERADOS, esperar_job
from tests.api.test_rls import contexto, ids_por_slug

pytestmark = pytest.mark.skipif(not GERADOS.exists(), reason="rode `venv/bin/python tests/dados/gerar.py` antes")

# (formato declarado, arquivo, nº de camadas que o arquivo tem)
FORMATOS_DO_PORTAO = [
    ("shapefile.zip", "cobertura_shp.zip", 1),
    ("gpkg", "cobertura.gpkg", 1),
    ("geojson", "cobertura.geojson", 1),
    ("geojsonseq", "cobertura.geojsonl", 1),
    ("csv", "lugares_pv.csv", 1),
    ("kml", "cobertura.kml", 1),
    ("kmz", "tres_pastas.kmz", 3),
    ("gpx", "lugares.gpx", 5),
    ("xlsx", "duas_planilhas.xlsx", 2),
]
FORMATOS_A_MAIS_DO_L0_04_B = [
    ("gml", "cobertura.gml", 1),
    ("flatgeobuf", "cobertura.fgb", 1),
    ("dxf", "cobertura.dxf", 1),
    ("gdb", "cobertura_gdb.zip", 1),
]


def _importar_bruto(ing, nome_arquivo: str, formato: str):
    """POST /api/importacoes sem assert: devolve a resposta crua (para provar recusa com mensagem)."""
    obj = ing.enviar_arquivo(GERADOS / nome_arquivo)
    item_id = ing.item_arquivo(obj, nome_arquivo)
    return ing.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": formato})


def _inspecionar(ing, nome_arquivo: str, formato: str) -> dict:
    r = _importar_bruto(ing, nome_arquivo, formato)
    assert r.status_code == 202, r.text
    esperar_job(ing.sessao, r.json()["job_id"], timeout=120)
    return ing.sessao.get(f"/api/importacoes/{r.json()['importacao_id']}").json()


# ------------------------------------------------------------------ a rota que anuncia os formatos
def test_a_rota_de_formatos_responde_e_cobre_os_nove_do_portao(sessao_a):
    """Portão do L0-04-d: 'teste automatizado com 1 arquivo aberto por formato (9 arquivos)'. A rota estava
    declarada depois de /api/importacoes/{id} e respondia 404 'importação inexistente'."""
    r = sessao_a.get("/api/importacoes/formatos")
    assert r.status_code == 200, r.text
    corpo = r.json()
    tipos = {f["tipo"] for f in corpo["aceitos"]}
    assert {f for f, _, _ in FORMATOS_DO_PORTAO} <= tipos, sorted(tipos)
    assert {f for f, _, _ in FORMATOS_A_MAIS_DO_L0_04_B} <= tipos, sorted(tipos)


def test_o_que_depende_de_licenca_de_terceiro_e_declarado_e_nao_escondido(sessao_a, ingestor_a):
    """DWG é o ÚNICO formato dos portões que esta instalação não traz, e não por falta de driver: depende do
    ODA File Converter (licença própria) ou do LibreDWG (GPL-3) — decisão do dono, item L0-04-e. A recusa diz
    isso, em vez de fingir que o tipo não existe."""
    corpo = sessao_a.get("/api/importacoes/formatos").json()
    nao_aceitos = {f["tipo"]: f["motivo"] for f in corpo["nao_aceitos"]}
    assert "dwg" in nao_aceitos and "licença" in nao_aceitos["dwg"], nao_aceitos

    r = _importar_bruto(ingestor_a, "cobertura.dxf", "dwg")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "formato_nao_suportado"
    assert "ODA" in r.json()["mensagem"] or "LibreDWG" in r.json()["mensagem"], r.json()["mensagem"]


# ------------------------------------------------------------------ um arquivo aberto por formato
@pytest.mark.parametrize("formato,arquivo,n_camadas", FORMATOS_DO_PORTAO + FORMATOS_A_MAIS_DO_L0_04_B)
def test_cada_formato_do_portao_e_inspecionado(ingestor_a, formato, arquivo, n_camadas):
    """Cada formato tem de chegar a uma PROPOSTA, com todas as camadas do arquivo listadas. Antes deste
    conserto, 8 dos 13 nem sequer eram aceitos (`formato_nao_suportado`)."""
    imp = _inspecionar(ingestor_a, arquivo, formato)
    assert imp["estado"] == "proposta", f"{formato}: {imp.get('erro')}"
    proposta = imp["proposta"]
    assert proposta["formato"] == formato
    assert len(proposta["camadas"]) == n_camadas, [c["camada_origem"] for c in proposta["camadas"]]


# ------------------------------------------------------------------ nenhuma camada some em silêncio
def test_gpkg_com_tres_camadas_lista_as_tres_e_pergunta_qual_entra(ingestor_a):
    """Portão literal do L0-04-b ('GPKG com 3 camadas') e do L0-04-c ('1 job por arquivo, N camadas').
    `camadas[0]` descartava duas camadas sem aviso nenhum."""
    imp = _inspecionar(ingestor_a, "tres_camadas.gpkg", "gpkg")
    proposta = imp["proposta"]
    nomes = [c["camada_origem"] for c in proposta["camadas"]]
    assert nomes == ["camada_um", "camada_dois", "camada_tres"], nomes
    assert "camada" in proposta["perguntas"], proposta["perguntas"]
    texto = " ".join(proposta["avisos"])
    assert "camada_dois" in texto and "camada_tres" in texto, texto
    # a confirmação sem responder a pergunta é recusada com a lista das perguntas
    r = ingestor_a.sessao.put(f"/api/importacoes/{imp['id']}/confirmar", json={})
    assert r.status_code == 422 and r.json()["erro"] == "perguntas_pendentes", r.text
    assert "camada" in r.json()["detalhe"]["perguntas"]


def test_as_tres_camadas_do_gpkg_importam_uma_a_uma(ingestor_a, conexao_plat_app):
    """A outra metade da cláusula: além de avisar, as três TÊM de poder entrar — uma importação por camada,
    do mesmo arquivo enviado uma vez só."""
    obj = ingestor_a.enviar_arquivo(GERADOS / "tres_camadas.gpkg")
    arquivo_id = ingestor_a.item_arquivo(obj, "tres_camadas.gpkg")
    itens = {}
    for nome in ("camada_um", "camada_dois", "camada_tres"):
        r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": arquivo_id, "formato": "gpkg"})
        assert r.status_code == 202, r.text
        esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=120)
        final = ingestor_a.confirmar(r.json()["importacao_id"], {"camada": {"escolhida": nome}}, timeout=180)
        assert final["estado"] == "concluida", (nome, final)
        assert final["relatorio"]["feicoes_carregadas"] == 80, (nome, final["relatorio"])
        itens[nome] = final["item_id"]
    assert len(set(itens.values())) == 3

    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        contexto(conexao_plat_app, ids["demo"], usuario_id=cur.fetchone()["usuario_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        for nome, item_id in itens.items():
            cur.execute("SELECT dados->>'schema' AS s, dados->>'tabela' AS t, "
                        "dados->'procedencia' AS p FROM plat.item WHERE id = %s::uuid", (item_id,))
            r = cur.fetchone()
            cur.execute(f'SELECT count(*) AS n FROM "{r["s"]}"."{r["t"]}"')
            assert cur.fetchone()["n"] == 80, nome


def test_kmz_com_tres_pastas_gera_tres_camadas(ingestor_a):
    """Cláusula literal do portão do L0-04-d: 'KMZ com 3 pastas gera 3 camadas'."""
    imp = _inspecionar(ingestor_a, "tres_pastas.kmz", "kmz")
    nomes = [c["camada_origem"] for c in imp["proposta"]["camadas"]]
    assert nomes == ["pasta_um", "pasta_dois", "pasta_tres"], nomes
    assert imp["proposta"]["crs"]["srid"] == 4326  # a especificação do KML fixa WGS 84
    assert any("estilo" in a for a in imp["proposta"]["avisos"]), imp["proposta"]["avisos"]


def test_gpx_avisa_as_camadas_vazias_em_vez_de_escolher_calado(ingestor_a):
    """O GPX declara sempre 5 camadas (waypoints, routes, tracks, route_points, track_points) e quase todas
    vêm vazias. A proposta abre na única com dado e DIZ quais estão vazias."""
    imp = _inspecionar(ingestor_a, "lugares.gpx", "gpx")
    proposta = imp["proposta"]
    assert proposta["camada_escolhida"] == "waypoints", proposta["camada_escolhida"]
    assert proposta["feicoes"] == 40
    texto = " ".join(proposta["avisos"])
    for vazia in ("routes", "tracks", "route_points", "track_points"):
        assert vazia in texto, texto


# ------------------------------------------------------------------ silêncio nunca
def test_csv_com_300_colunas_e_nenhuma_linha_diz_o_que_aconteceu(ingestor_a):
    """Refutação literal do L0-04-b: 'CSV com 300 colunas e 0 linhas ... silêncio ou 500 = refutado'."""
    imp = _inspecionar(ingestor_a, "largo_300_colunas.csv", "csv")
    assert imp["estado"] == "proposta", imp
    proposta = imp["proposta"]
    assert len(proposta["campos"]) == 300, len(proposta["campos"])
    assert proposta["feicoes"] == 0
    texto = " ".join(proposta["avisos"])
    assert "NENHUMA linha" in texto, proposta["avisos"]
    assert "300 campos" in texto, proposta["avisos"]


def test_planilha_sem_geometria_e_recusada_na_confirmacao_com_motivo(ingestor_a):
    """Uma planilha é tabela sem coluna espacial. Esta passagem não a carrega — e diz isso na confirmação,
    com 422 e mensagem, em vez de deixar o job morrer no meio da carga."""
    imp = _inspecionar(ingestor_a, "duas_planilhas.xlsx", "xlsx")
    assert imp["estado"] == "proposta", imp
    r = ingestor_a.sessao.put(f"/api/importacoes/{imp['id']}/confirmar",
                              json={"camada": {"escolhida": "planilha_um"}})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "camada_sem_geometria", r.json()
    assert "não tem geometria" in r.json()["mensagem"], r.json()["mensagem"]


@pytest.mark.parametrize("arquivo", ["zip_corrompido.zip", "zip_aninhado.zip"])
def test_zip_malformado_devolve_422_e_nunca_500(ingestor_a, arquivo):
    """Refutação do item pai: 'ou importa certo ou recusa com mensagem exata'. ZipSuspeito e
    ConteudoNaoCorresponde eram classes irmãs e a rota só capturava a segunda."""
    r = _importar_bruto(ingestor_a, arquivo, "shapefile.zip")
    assert r.status_code == 422, f"veio {r.status_code}: {r.text[:300]}"
    assert r.json()["erro"] == "zip_suspeito", r.json()
    assert r.json()["mensagem"], r.json()
