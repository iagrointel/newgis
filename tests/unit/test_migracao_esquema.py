"""Item L2-08-b: leitura do esquema de uma camada hospedada da Esri sobre a gravação PÚBLICA registrada com URL e
data (`tests/migracao/respostas/publicas/servico_publico.json`): tipos, alias, nulabilidade, domínios codificados,
subtipos com padrões, relacionamento com cardinalidade/chave/papel, anexos, CRS 102100 -> 3857; mais os casos da
refutação: `Shape__Area` e reservados descartados, geometria Z, data antes de 1970 e domínio de 5 mil códigos."""

import json
from pathlib import Path

from app.migracao import esquema

PUBLICO = json.loads(
    (Path(__file__).resolve().parents[1] / "migracao" / "respostas" / "publicas" / "servico_publico.json").read_text(
        encoding="utf-8"
    )
)


def test_gravacao_publica_tem_url_e_data():
    assert PUBLICO["url"].startswith("https://") and PUBLICO["gravado_em"].endswith("Z")


def test_camada_publica_campos_dominios_subtipos_relacionamento_anexos():
    e = esquema.esquema_de(PUBLICO["camadas"]["0"])
    nomes = {c["nome"]: c for c in e["campos"]}
    assert "objectid" not in nomes and "globalid" not in nomes and e["campo_oid"] == "objectid"
    assert e["campo_globalid"] == "globalid"
    assert nomes["requesttype"]["tipo"] == "text" and nomes["requesttype"]["alias"]
    assert any(c["tipo"] == "timestamptz" for c in nomes.values())  # datas (ms Esri) viram timestamptz
    assert e["geometria"] == "Point" and e["srid"] == 3857 and e["e_tabela"] is False
    doms = {f["name"]: f["domain"]["type"] for f in e["dominios"]["fields"]}
    assert doms == {"requesttype": "codedValue", "status": "codedValue"}
    # os `types` deste serviço têm id texto ("Unassigned"...): não são subtipos, ficam fora com aviso
    assert e["dominios"]["types"] == [] and any("tipos de feição" in a for a in e["avisos"])
    assert e["tem_anexos"] is True
    (rel,) = e["relacionamentos"]
    assert rel["camada_relacionada"] == 1 and rel["cardinalidade"] == "1:N" and rel["papel"] == "origem"
    assert rel["chave"] == "requestid" and rel["composto"] is True


def test_tabela_publica_e_tabela_sem_geometria():
    e = esquema.esquema_de(PUBLICO["camadas"]["1"])
    assert e["e_tabela"] is True and e["geometria"] is None
    assert e["relacionamentos"][0]["papel"] == "destino" and e["relacionamentos"][0]["camada_relacionada"] == 0


def _descritor(**extra):
    base = {
        "id": 7,
        "name": "Teste",
        "geometryType": "esriGeometryPolyline",
        "objectIdField": "OBJECTID",
        "globalIdField": "GlobalID",
        "hasZ": True,
        "hasAttachments": False,
        "sourceSpatialReference": {"wkid": 31982},
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "GlobalID", "type": "esriFieldTypeGlobalID"},
            {"name": "Shape__Area", "type": "esriFieldTypeDouble"},
            {"name": "Shape__Length", "type": "esriFieldTypeDouble"},
            {"name": "Nome Do Trecho", "type": "esriFieldTypeString", "length": 80, "alias": "Nome", "nullable": False},
            {"name": "select", "type": "esriFieldTypeInteger"},
            {"name": "data_obra", "type": "esriFieldTypeDate"},
            {"name": "created_user", "type": "esriFieldTypeString"},
        ],
        "editFieldsInfo": {"creatorField": "created_user"},
        "editingInfo": {"lastEditDate": 1700000000000},
    }
    base.update(extra)
    return base


def test_reservados_z_data_negativa_e_nomes_saneados():
    e = esquema.esquema_de(_descritor())
    nomes = [c["nome"] for c in e["campos"]]
    assert nomes == ["nome_do_trecho", "select_", "data_obra", "origem_created_user"]
    assert any("Shape__Area" in a for a in e["avisos"])
    assert e["geometria"] == "MultiLineStringZ" and e["srid"] == 31982 and e["edit_date"] == 1700000000000
    assert e["mapa_nomes"]["Nome Do Trecho"] == "nome_do_trecho"
    campo = next(c for c in e["campos"] if c["nome"] == "data_obra")
    assert esquema.valor_para_coluna(campo, -86400000 * 366) == "1968-12-31T00:00:00+00:00"  # antes de 1970
    assert esquema.valor_para_coluna(next(c for c in e["campos"] if c["nome"] == "nome_do_trecho"), 12) == "12"


def test_subtipos_inteiros_com_padroes_e_dominio_por_subtipo():
    d = _descritor(
        typeIdField="select",
        types=[
            {
                "id": 1,
                "name": "Um",
                "domains": {"data_obra": {"type": "inherited"}},
                "templates": [{"prototype": {"attributes": {"Nome Do Trecho": "padrão 1"}}}],
            },
            {
                "id": 2,
                "name": "Dois",
                "domains": {
                    "Nome Do Trecho": {"type": "codedValue", "name": "n2", "codedValues": [{"code": "x", "name": "X"}]}
                },
            },
        ],
    )
    e = esquema.esquema_de(d)
    tipos = e["dominios"]["types"]
    assert [t["id"] for t in tipos] == [1, 2] and tipos[0]["campo_subtipo"] == "select_"
    assert tipos[0]["templates"][0]["prototype"]["attributes"] == {"nome_do_trecho": "padrão 1"}
    assert "nome_do_trecho" in tipos[1]["domains"]


def test_dominio_de_cinco_mil_codigos_vai_inteiro():
    valores = [{"code": i, "name": f"c{i}"} for i in range(5000)]
    d = _descritor(
        fields=[
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {
                "name": "classe",
                "type": "esriFieldTypeInteger",
                "domain": {"type": "codedValue", "name": "classe_grande", "codedValues": valores},
            },
        ]
    )
    e = esquema.esquema_de(d)
    assert len(e["dominios"]["fields"][0]["domain"]["codedValues"]) == 5000
