"""Item L0-09-c-xml-iso-validacao: `POST /api/itens/{id}/metadado.xml` — importação de metadado ISO 19139.

O que se prova aqui (o analisador em si está em tests/unit/test_metadado_iso_importacao.py): o registro real
da INDE entra no item e preenche pelo menos 15 campos; a ida e volta pela API (exportar de um item, importar
noutro) não perde campo do perfil; XML ilegível responde 422 com linha e coluna; `estrito=1` transforma o
parecer do XSD em recusa; `aplicar=false` não grava; e a leitura não atravessa inquilino."""

from pathlib import Path

INDE = Path(__file__).resolve().parents[3] / "tests" / "dados" / "inde_iso19139_carta_imagem.xml"

CAMPOS_DO_PERFIL = ("titulo", "resumo", "creditos", "termos_de_uso", "status")


def _importar(sessao, iid: str, corpo: bytes, **params):
    """O XML vai num campo de texto do corpo JSON: a defesa de CSRF sob cookie só aceita corpo JSON."""
    consulta = "&".join(f"{k}={'true' if v is True else 'false' if v is False else v}" for k, v in params.items())
    url = f"/api/itens/{iid}/metadado.xml" + (f"?{consulta}" if consulta else "")
    return sessao.post(url, json={"xml": corpo.decode("utf-8", "replace")})


def test_registro_da_inde_preenche_ao_menos_quinze_campos_do_item(sessao_a, itens_a):
    it = itens_a.criar("camada_vetorial")
    r = _importar(sessao_a, it["id"], INDE.read_bytes())
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["preenchidos"]) >= 15, j["preenchidos"]
    assert j["aplicado"] is True
    assert j["identificador_estrangeiro"] is True  # o XML é do IBGE, não deste item
    depois = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert depois["titulo"].startswith("CARTA IMAGEM")
    assert depois["resumo"].startswith("As Cartas Imagens")
    assert depois["tags"]
    assert depois["extent"] and len(depois["extent"]) == 4
    assert depois["dados"]["procedencia"]["fonte"]
    assert j["metadado_iso_guardado"]["contato"]["email"] == "ibge@ibge.gov.br"
    assert j["metadado_iso_guardado"]["sistema_referencia"]["codigo"] == "SIRGAS2000"
    # o que a ISO trouxe e a plataforma não guarda sai nomeado, com caminho e linha
    assert len(j["nao_coube"]) > 10
    assert all(e["caminho"] and e["linha"] >= 0 for e in j["nao_coube"])


def test_ida_e_volta_pela_api_nao_perde_campo_do_perfil(sessao_a, itens_a):
    """Exporta o metadado de um item e importa noutro: os campos do perfil chegam iguais (diff = 0)."""
    origem = itens_a.criar(
        "camada_vetorial",
        resumo="Resumo do conjunto de dados de teste interno",
        tags=["agro", "zt-iso"],
        creditos="Diretoria de teste interno",
        termos_de_uso="Uso interno; sem redistribuição",
        extent=[-50.5, -20.25, -40.125, -10.0625],
    )
    assert sessao_a.patch(f"/api/itens/{origem['id']}", json={"status": "autoritativo"}).status_code == 200
    xml = sessao_a.get(f"/api/itens/{origem['id']}/metadado.xml")
    assert xml.status_code == 200, xml.text
    destino = itens_a.criar("camada_vetorial")
    r = _importar(sessao_a, destino["id"], xml.content)
    assert r.status_code == 200, r.text
    a = sessao_a.get(f"/api/itens/{origem['id']}").json()
    b = sessao_a.get(f"/api/itens/{destino['id']}").json()
    diferencas = [c for c in CAMPOS_DO_PERFIL if a[c] != b[c]]
    assert diferencas == [], {c: (a[c], b[c]) for c in diferencas}
    assert sorted(a["tags"]) == sorted(b["tags"])
    assert [round(v, 6) for v in a["extent"]] == [round(v, 6) for v in b["extent"]]


def test_xml_ilegivel_responde_422_com_linha_e_coluna(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = _importar(sessao_a, it["id"], b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">\n<gmd:x>\n')
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "xml_invalido"
    assert j["detalhe"][0]["linha"] >= 2 and j["detalhe"][0]["coluna"] > 0


def test_raiz_de_outro_namespace_responde_422(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = _importar(sessao_a, it["id"], b'<MD_Metadata xmlns="http://www.isotc211.org/2005/gmx"/>')
    assert r.status_code == 422
    assert "gmx" in r.json()["detalhe"][0]["erro"]


def test_estrito_recusa_o_que_o_xsd_reprova_e_o_padrao_so_avisa(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = _importar(sessao_a, it["id"], INDE.read_bytes(), estrito=True)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "xml_invalido"
    assert r.json()["detalhe"][0]["linha"] > 0
    # sem estrito, o mesmo documento entra e os erros do XSD saem como aviso, com posição
    r2 = _importar(sessao_a, it["id"], INDE.read_bytes())
    assert r2.status_code == 200
    assert r2.json()["avisos_xsd"] and r2.json()["avisos_xsd"][0]["linha"] > 0


def test_aplicar_falso_devolve_o_relatorio_sem_gravar(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    antes = sessao_a.get(f"/api/itens/{it['id']}").json()
    r = _importar(sessao_a, it["id"], INDE.read_bytes(), aplicar=False)
    assert r.status_code == 200, r.text
    assert r.json()["aplicado"] is False
    assert len(r.json()["preenchidos"]) >= 15
    depois = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert depois["titulo"] == antes["titulo"]
    assert depois["versao_atual"] == antes["versao_atual"]


def test_tipo_que_nao_aceita_procedencia_diz_isso_em_vez_de_gravar_a_forca(sessao_a, itens_a):
    """`mapa` tem esquema fechado (additionalProperties:false): a linhagem não vira `dados.procedencia`, e o
    motivo aparece no relatório — nunca um armazém improvisado."""
    it = itens_a.criar("mapa")
    r = _importar(sessao_a, it["id"], INDE.read_bytes())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["procedencia"] == {}
    motivos = [e.get("motivo") for e in j["nao_coube"] if e.get("motivo")]
    assert any("procedencia" in (m or "") for m in motivos), motivos
    assert sessao_a.get(f"/api/itens/{it['id']}").json()["titulo"].startswith("CARTA IMAGEM")


def test_item_de_outro_inquilino_nao_recebe_importacao(sessao_a, sessao_b, itens_b):
    de_b = itens_b.criar("mapa")
    r = _importar(sessao_a, de_b["id"], INDE.read_bytes())
    assert r.status_code == 404
    assert sessao_b.get(f"/api/itens/{de_b['id']}").json()["titulo"] != "CARTA IMAGEM"


def test_xml_grande_demais_e_recusado(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = _importar(sessao_a, it["id"], b"<gmd:MD_Metadata>" + b"a" * (3 * 1024 * 1024))
    assert r.status_code in (413, 422), r.text
