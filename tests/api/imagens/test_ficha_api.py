"""API da ficha de metadado e licença da imagem (item L1-27), contra a base da trilha.

Cobre as cláusulas do portão que dependem do servidor: item sem licença escrita não sai por link público nem
vira item público; o ISO 19115-2 sai pela rota do editor do L0-09 e valida contra o XSD; a ficha devolve a
atribuição; a lista de licenças vem do código. E cobre a refutação: marcar como CC BY um item que estava com
licença comercial exige privilégio de administrador e fica no log de eventos.
"""

from __future__ import annotations

import pytest
from lxml import etree

from app.catalogo import metadado_imagem
from app.imagens import ficha as fi
from tests.api.catalogo.conftest import titulo_zt

FICHA_LIVRE = {
    "plataforma": "sentinel-2b", "instrumentos": ["msi"], "gsd": 10.0,
    "data_aquisicao": "2026-05-01T13:00:00Z", "fornecedor": "agência de teste interno",
    "licenca": "cc-by-4.0", "fonte": "upload", "atribuicao": "atribuição de teste interno",
    "nuvem_pct": 3.2, "sol_elevacao": 55.1, "sol_azimute": 40.0,
    "orbita_estado": "descending", "orbita_relativa": 24, "constelacao": "sentinel-2",
}
FICHA_SEM_LICENCA = {**FICHA_LIVRE, "licenca": "sem-licenca-escrita"}
FICHA_COMERCIAL = {**FICHA_LIVRE, "licenca": "comercial-eula"}


@pytest.fixture
def raster_a(sessao_a, itens_a):
    """Item raster de A. Sem coleção STAC: a ficha é gravada em plat.item.dados e o espelhamento no pgstac
    é opcional por desenho (ficha preenchida antes da ingestão é caso normal)."""
    return itens_a.criar(
        tipo="raster", sessao=sessao_a, titulo=titulo_zt("raster ficha"),
        dados={"colecao": "sem-colecao", "stac_id": "sem-item", "perfil": "visual",
               "origem": "copiado", "srid_nativo": 4326},
    )


def gravar(sessao, item_id, corpo):
    return sessao.put(f"/api/imagens/{item_id}/ficha", json=corpo)


# ------------------------------------------------------------------ lista de licenças
def test_lista_de_licencas_vem_do_codigo(sessao_a):
    r = sessao_a.get("/api/imagens/licencas")
    assert r.status_code == 200, r.text
    j = r.json()
    assert [x["codigo"] for x in j["licencas"]] == [lic.codigo for lic in fi.LICENCAS]
    assert j["padrao"] == fi.LICENCA_PADRAO


# ------------------------------------------------------------------ ficha: leitura, gravação, atribuição
def test_item_novo_nasce_sem_ficha_e_com_o_aviso_da_regra_d17(sessao_a, raster_a):
    r = sessao_a.get(f"/api/imagens/{raster_a['id']}/ficha")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ficha"] is None
    assert j["licenca"]["codigo"] == "sem-licenca-escrita"
    assert j["licenca"]["vendavel"] is False
    assert j["permite_link_publico"] is False
    assert j["avisos"] and "não vendável" in " ".join(j["avisos"])


def test_ficha_gravada_e_relida_mostra_a_atribuicao(sessao_a, raster_a):
    r = gravar(sessao_a, raster_a["id"], FICHA_LIVRE)
    assert r.status_code == 200, r.text
    assert r.json()["atribuicao"] == FICHA_LIVRE["atribuicao"]
    j = sessao_a.get(f"/api/imagens/{raster_a['id']}/ficha").json()
    assert j["ficha"]["plataforma"] == "sentinel-2b"
    assert j["ficha"]["instrumentos"] == ["msi"]
    assert j["atribuicao"] == FICHA_LIVRE["atribuicao"], "a ficha tem de mostrar a atribuição"
    assert j["propriedades_stac"]["plat:atribuicao"] == FICHA_LIVRE["atribuicao"]
    assert j["permite_link_publico"] is True


def test_licenca_que_exige_atribuicao_sem_o_texto_reprova_com_o_campo(sessao_a, raster_a):
    r = gravar(sessao_a, raster_a["id"], {**FICHA_LIVRE, "atribuicao": None})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "ficha_invalida" and r.json()["detalhe"]["campo"] == "atribuicao"


def test_licenca_fora_da_lista_da_casa_reprova(sessao_a, raster_a):
    r = gravar(sessao_a, raster_a["id"], {**FICHA_LIVRE, "licenca": "cc-by-nc-4.0"})
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "licenca"


def test_ficha_de_item_que_nao_e_raster_nao_existe(sessao_a, itens_a):
    mapa = itens_a.criar(tipo="mapa")
    assert sessao_a.get(f"/api/imagens/{mapa['id']}/ficha").status_code == 404
    assert gravar(sessao_a, mapa["id"], FICHA_LIVRE).status_code == 404


# ------------------------------------------------------------------ link público e acesso público
def test_item_sem_licenca_escrita_nao_pode_ser_compartilhado_por_link_publico(sessao_a, raster_a, medida):
    assert gravar(sessao_a, raster_a["id"], FICHA_SEM_LICENCA).status_code == 200
    r = sessao_a.post(f"/api/itens/{raster_a['id']}/links", json={"nome": "zt-link"})
    assert r.status_code == 400, r.text
    assert r.json()["erro"] == "licenca_sem_redistribuicao"
    assert r.json()["detalhe"]["licenca"] == "sem-licenca-escrita"
    assert sessao_a.get(f"/api/itens/{raster_a['id']}/links").json() == []
    medida("L1-27-ficha-de-metadado-e-licenca-da-imagem")(
        "link_publico_recusado_sem_licenca", r.status_code, "código HTTP",
        "POST /api/itens/{id}/links num item raster com ficha de licença `sem-licenca-escrita` "
        "(400 licenca_sem_redistribuicao; nenhum link ativo fica no item)",
    )


def test_item_sem_ficha_nenhuma_tambem_nao_pode_link_publico(sessao_a, raster_a):
    """Sem ficha o item conta como sem licença escrita — nunca como livre por omissão."""
    r = sessao_a.post(f"/api/itens/{raster_a['id']}/links", json={"nome": "zt-link"})
    assert r.status_code == 400 and r.json()["erro"] == "licenca_sem_redistribuicao"


def test_licenca_comercial_tambem_bloqueia_o_link_publico(sessao_a, raster_a):
    assert gravar(sessao_a, raster_a["id"], FICHA_COMERCIAL).status_code == 200
    r = sessao_a.post(f"/api/itens/{raster_a['id']}/links", json={"nome": "zt-link"})
    assert r.status_code == 400 and r.json()["detalhe"]["licenca"] == "comercial-eula"


def test_licenca_livre_libera_o_link_publico(sessao_a, raster_a):
    assert gravar(sessao_a, raster_a["id"], FICHA_LIVRE).status_code == 200
    r = sessao_a.post(f"/api/itens/{raster_a['id']}/links", json={"nome": "zt-link"})
    assert r.status_code == 201, r.text
    sessao_a.delete(f"/api/itens/{raster_a['id']}/links/{r.json()['id']}")


def test_acesso_publico_do_item_tambem_e_recusado_sem_licenca(sessao_a, raster_a):
    assert gravar(sessao_a, raster_a["id"], FICHA_SEM_LICENCA).status_code == 200
    r = sessao_a.put(f"/api/itens/{raster_a['id']}/compartilhamento", json={"acesso": "publico"})
    # 400 licenca_sem_redistribuicao quando o inquilino permite público; 400 publico_desligado quando não
    # permite (a ordem das duas guardas é essa de propósito: a política do inquilino vem primeiro)
    assert r.status_code == 400, r.text
    assert r.json()["erro"] in ("licenca_sem_redistribuicao", "publico_desligado")


def test_item_de_outro_tipo_nao_e_afetado_pela_guarda_de_licenca(sessao_a, itens_a):
    """A guarda vale só para imagem: um mapa continua compartilhável por link como antes."""
    mapa = itens_a.criar(tipo="mapa")
    r = sessao_a.post(f"/api/itens/{mapa['id']}/links", json={"nome": "zt-link"})
    assert r.status_code == 201, r.text
    sessao_a.delete(f"/api/itens/{mapa['id']}/links/{r.json()['id']}")


# ------------------------------------------------------------------ refutação: afrouxar licença
@pytest.fixture
def raster_do_editor(itens_a, usuarios_a):
    """Raster de um usuário de perfil `editor`: ele é DONO do item (pode editar tudo nele) e não tem
    `org.configurar` — é exatamente o adversário da refutação, sem esbarrar em permissão de edição."""
    editor, _u, _senha = usuarios_a.sessao(perfil="editor")
    item = itens_a.criar(
        tipo="raster", sessao=editor, titulo=titulo_zt("raster refutacao"),
        dados={"colecao": "sem-colecao", "stac_id": "sem-item", "perfil": "visual",
               "origem": "copiado", "srid_nativo": 4326},
    )
    return editor, item


def test_marcar_item_comercial_como_cc_by_exige_administrador_e_fica_no_log(sessao_a, raster_do_editor):
    """Refutação do item: o adversário marca um item comercial como CC BY. Sem `org.configurar` a troca é
    recusada com 403 e registrada; com o privilégio ela passa e o afrouxamento entra no log."""
    editor, item = raster_do_editor
    assert gravar(editor, item["id"], FICHA_COMERCIAL).status_code == 200

    r = gravar(editor, item["id"], FICHA_LIVRE)
    assert r.status_code == 403, r.text
    assert r.json()["detalhe"]["exigido"] == "org.configurar"
    # a licença NÃO mudou
    assert editor.get(f"/api/imagens/{item['id']}/ficha").json()["licenca"]["codigo"] == "comercial-eula"

    eventos = sessao_a.get("/api/eventos", params={"tipo": "imagens/ficha_licenca_recusada", "limite": 50})
    assert eventos.status_code == 200, eventos.text
    assert any(e["alvo_id"] == item["id"] for e in eventos.json()["itens"]), eventos.text

    # o administrador consegue, e o afrouxamento fica registrado
    assert gravar(sessao_a, item["id"], FICHA_LIVRE).status_code == 200
    eventos = sessao_a.get("/api/eventos", params={"tipo": "imagens/ficha_licenca_afrouxada", "limite": 50})
    linhas = [e for e in eventos.json()["itens"] if e["alvo_id"] == item["id"]]
    assert linhas and linhas[0]["propriedades"]["de"] == "comercial-eula"
    assert linhas[0]["propriedades"]["para"] == "cc-by-4.0"


def test_apertar_a_licenca_nao_exige_privilegio_nenhum(raster_do_editor):
    """O caminho contrário (livre -> restrita) é sempre permitido: apertar nunca abre nada."""
    editor, item = raster_do_editor
    assert gravar(editor, item["id"], FICHA_COMERCIAL).status_code == 200


# ------------------------------------------------------------------ ISO 19115-2 pela rota do editor
def test_iso_19115_2_sai_pela_rota_do_editor_e_valida_contra_o_xsd(sessao_a, raster_a):
    assert gravar(sessao_a, raster_a["id"], FICHA_LIVRE).status_code == 200
    r = sessao_a.get(f"/api/itens/{raster_a['id']}/metadado.xml", params={"perfil": "imagem"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml")
    metadado_imagem.validar(r.content)
    assert etree.fromstring(r.content).tag == f"{{{metadado_imagem.GMI}}}MI_Metadata"


def test_licenca_e_data_do_iso_batem_com_as_propriedades_stac_da_mesma_ficha(sessao_a, raster_a):
    """Segunda metade da refutação: exportar o ISO e conferir contra o STAC que a API devolve."""
    assert gravar(sessao_a, raster_a["id"], FICHA_COMERCIAL).status_code == 200
    props = sessao_a.get(f"/api/imagens/{raster_a['id']}/ficha").json()["propriedades_stac"]
    xml = sessao_a.get(f"/api/itens/{raster_a['id']}/metadado.xml", params={"perfil": "imagem"}).content
    stac, casa, data = metadado_imagem.licenca_e_data_do_xml(xml)
    assert (stac, casa, data) == (props["license"], props["plat:licenca"], props["datetime"])


def test_perfil_de_imagem_em_item_sem_ficha_recusa_em_vez_de_inventar(sessao_a, raster_a):
    r = sessao_a.get(f"/api/itens/{raster_a['id']}/metadado.xml", params={"perfil": "imagem"})
    assert r.status_code == 409 and r.json()["erro"] == "sem_ficha_de_imagem"


def test_perfil_generico_continua_saindo_em_iso_19139(sessao_a, raster_a):
    from app.catalogo import metadado

    assert gravar(sessao_a, raster_a["id"], FICHA_LIVRE).status_code == 200
    r = sessao_a.get(f"/api/itens/{raster_a['id']}/metadado.xml", params={"perfil": "generico"})
    assert r.status_code == 200
    assert etree.fromstring(r.content).tag == f"{{{metadado.GMD}}}MD_Metadata"


def test_item_sem_ficha_sai_no_perfil_generico_por_padrao(sessao_a, itens_a):
    from app.catalogo import metadado

    mapa = itens_a.criar(tipo="mapa")
    r = sessao_a.get(f"/api/itens/{mapa['id']}/metadado.xml")
    assert r.status_code == 200
    assert etree.fromstring(r.content).tag == f"{{{metadado.GMD}}}MD_Metadata"


# ------------------------------------------------------------------ isolamento
def test_ficha_de_item_de_outro_inquilino_da_404(sessao_a, sessao_b, itens_b):
    raster_b = itens_b.criar(
        tipo="raster", sessao=sessao_b,
        dados={"colecao": "sem-colecao", "stac_id": "sem-item", "perfil": "visual",
               "origem": "copiado", "srid_nativo": 4326},
    )
    assert sessao_a.get(f"/api/imagens/{raster_b['id']}/ficha").status_code == 404
    assert gravar(sessao_a, raster_b["id"], FICHA_LIVRE).status_code == 404
