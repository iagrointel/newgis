"""Montagem de SQL da tabela de atributos (item L2-01-g-tabela-atributos), sem banco: o que decide se um nome
de coluna vira SQL, como o termo de busca é escapado e o que a ordenação aceita. É aqui que a defesa contra
injeção é verificada no ponto onde ela existe — o nome pedido é procurado na lista de colunas REAIS e, se não
estiver lá, vira 422 antes de qualquer concatenação."""

import pytest

from app.erros import ErroAPI
from app.tabela import consulta

COLUNAS = [
    {"nome": "fid", "udt": "int4", "tipo": "numero", "aceita_nulo": False},
    {"nome": "municipio", "udt": "text", "tipo": "texto", "aceita_nulo": True},
    {"nome": "area_ha", "udt": "float8", "tipo": "numero", "aceita_nulo": True},
    {"nome": "geom", "udt": "geometry", "tipo": "geometria", "aceita_nulo": True},
]


def test_classe_do_tipo_cobre_texto_numero_data_e_geometria():
    assert consulta.classe_do_tipo("varchar") == "texto"
    assert consulta.classe_do_tipo("numeric") == "numero"
    assert consulta.classe_do_tipo("timestamptz") == "data"
    assert consulta.classe_do_tipo("geometry") == "geometria"
    assert consulta.classe_do_tipo("bytea") == "outro"


def test_citar_dobra_aspas():
    assert consulta.citar('a"b') == '"a""b"'


@pytest.mark.parametrize("pedido", [
    "nome_que_nao_existe",
    "fid; DROP TABLE plat.item",
    "(SELECT senha_hash FROM plat.usuario LIMIT 1)",
    'fid" , (SELECT 1) AS "x',
    "1",
])
def test_ordenar_por_fora_do_catalogo_e_422(pedido):
    with pytest.raises(ErroAPI) as e:
        consulta.ordenacao(COLUNAS, "fid", pedido, "asc")
    assert e.value.status_code == 422 and e.value.erro == "coluna_invalida"


def test_ordenar_por_geometria_e_422():
    with pytest.raises(ErroAPI) as e:
        consulta.ordenacao(COLUNAS, "fid", "geom", "asc")
    assert e.value.status_code == 422


def test_ordenacao_valida_tem_desempate_pela_chave():
    sql = consulta.ordenacao(COLUNAS, "fid", "municipio", "desc")
    assert sql == ' ORDER BY "municipio" DESC NULLS LAST, "fid" ASC'
    assert consulta.ordenacao(COLUNAS, "fid", None, "desc") == ' ORDER BY "fid" DESC'
    assert consulta.ordenacao(COLUNAS, None, None, "asc") == ""


def test_busca_escapa_curinga_e_cobre_so_colunas_de_texto():
    sql, params = consulta.filtro(COLUNAS, "fid", "geom", 4674, {"busca": "100% _dado_"})
    assert sql.count("public.unaccent") == 2  # uma vez por lado, numa única coluna de texto
    assert params == ["%100\\% \\_dado\\_%"]
    assert '"area_ha"' not in sql and '"geom"' not in sql


def test_busca_em_camada_sem_coluna_de_texto_nao_devolve_tudo():
    so_numero = [c for c in COLUNAS if c["tipo"] != "texto"]
    sql, params = consulta.filtro(so_numero, "fid", "geom", 4674, {"busca": "algo"})
    assert sql == "false" and params == []


def test_busca_longa_e_422():
    with pytest.raises(ErroAPI) as e:
        consulta.filtro(COLUNAS, "fid", "geom", 4674, {"busca": "a" * 5000})
    assert e.value.status_code == 422


def test_bbox_sem_geometria_e_422():
    with pytest.raises(ErroAPI) as e:
        consulta.filtro(COLUNAS, "fid", None, 4674, {"bbox": [-47, -24, -46, -23]})
    assert e.value.status_code == 422 and e.value.erro == "camada_sem_geometria"


@pytest.mark.parametrize("bbox", [
    [-47, -24, -48, -23],      # oeste >= leste
    [-47, -22, -46, -23],      # sul >= norte
    [-999, -24, -46, -23],     # fora do intervalo
])
def test_bbox_incoerente_e_422(bbox):
    with pytest.raises(ErroAPI) as e:
        consulta.filtro(COLUNAS, "fid", "geom", 4674, {"bbox": bbox})
    assert e.value.status_code == 422 and e.value.erro == "bbox_invalida"


def test_bbox_usa_indice_e_refina():
    sql, params = consulta.filtro(COLUNAS, "fid", "geom", 31983, {"bbox": [-47, -24, -46, -23]})
    assert '"geom" && ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 31983)' in sql
    assert "ST_Intersects" in sql
    assert params == [-47.0, -24.0, -46.0, -23.0, -47.0, -24.0, -46.0, -23.0]


def test_selecao_por_fids_vira_any_com_inteiros():
    sql, params = consulta.filtro(COLUNAS, "fid", "geom", 4674, {"fids": [3, 1, 2]})
    assert sql == '"fid" = ANY(%s)' and params == [[3, 1, 2]]


def test_selecao_sem_chave_primaria_e_409():
    with pytest.raises(ErroAPI) as e:
        consulta.filtro(COLUNAS, None, "geom", 4674, {"fids": [1]})
    assert e.value.status_code == 409


def test_selecao_grande_e_422():
    with pytest.raises(ErroAPI) as e:
        consulta.filtro(COLUNAS, "fid", "geom", 4674, {"fids": list(range(10_000))})
    assert e.value.status_code == 422


def test_selecao_nao_devolve_geometria_como_atributo():
    sql = consulta.selecao(COLUNAS, "fid", "geom", incluir_geometria=False)
    assert '"geom"' not in sql and "ST_AsGeoJSON" not in sql
    com = consulta.selecao(COLUNAS, "fid", "geom", incluir_geometria=True)
    assert "ST_AsGeoJSON(ST_Transform(\"geom\", 4326), 7) AS __geometria" in com


def test_origem_de_camada_referenciada_e_409():
    with pytest.raises(ErroAPI) as e:
        consulta.origem_da_camada({"dados": {"fonte": "referenciada"}})
    assert e.value.status_code == 409 and e.value.erro == "camada_sem_tabela"
    with pytest.raises(ErroAPI):
        consulta.origem_da_camada({"dados": {"schema": "d_demo; DROP", "tabela": "c_1", "srid": 4674}})


def test_estatisticas_pedem_os_seis_agregados_do_portao():
    sql = consulta.estatisticas_sql({"nome": "area_ha"})
    for agregado in ("count(\"area_ha\")", "sum(", "avg(", "min(", "max(", "FILTER (WHERE \"area_ha\" IS NULL)"):
        assert agregado in sql
