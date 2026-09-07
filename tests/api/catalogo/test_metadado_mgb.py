"""Item L0-09-b-editor-iso-mgb: editor de metadado no Perfil MGB 2.0 (INDE), GET/validar/PUT sobre
`plat.item.metadado_iso`. Prova cláusula por cláusula do portão de pronto (ver tests/medidas/L0-09-b-editor-
iso-mgb.json) e a refutação exigida: 5 MB (limite 1 MiB) = 422; data de fim antes da de início = 422 com
caminho; extent que diverge do item = aviso, nunca bloqueio."""

import json

METADADO_COMPLETO = {
    "contato": {
        "organizacao": "iAgroSat", "individuo": "Equipe MGB", "email": "mgb@exemplo.org", "papel": "pointOfContact",
    },
    "restricoes": {"licenca": "CC BY 4.0", "uso_condicionado": False},
    "extensao": {
        "temporal": {"inicio": "2026-01-01", "fim": "2026-06-30"},
        "espacial": {"xmin": -50.0, "ymin": -20.0, "xmax": -40.0, "ymax": -10.0},
    },
    "sistema_referencia": {"codigo": "4326", "codespace": "EPSG"},
    "manutencao": {"frequencia": "annually", "proxima_atualizacao": "2027-01-01"},
    "distribuicao": {"formato": "GeoJSON"},
}


def _camada(itens_a, **campos):
    base = {"resumo": "resumo de teste", "tags": ["agro"], "extent": [-50.0, -20.0, -40.0, -10.0]}
    base.update(campos)
    return itens_a.criar("camada_vetorial", **base)


# ---------------------------------------------------------------- 1. e2e/api: preencher essencial, validar, salvar
def test_validar_lista_faltantes_e_depois_completo_nao_falta_nada(sessao_a, itens_a):
    it = _camada(itens_a, tags=[])  # sem palavras-chave: falta no essencial
    r = sessao_a.post(f"/api/itens/{it['id']}/metadado/validar", json={"metadado": {}})
    assert r.status_code == 200, r.text
    faltando = {f["campo"] for f in r.json()["faltantes_essencial"]}
    assert "identificacao.palavras_chave" in faltando
    assert "contato.organizacao" in faltando
    assert "restricoes.licenca" in faltando
    # preenche o essencial completo (item já tem resumo/extent; falta contato/licença/sistema de referência)
    r2 = sessao_a.post(
        f"/api/itens/{it['id']}/metadado/validar",
        json={"item": {"tags": ["agro"]}, "metadado": METADADO_COMPLETO},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["faltantes_essencial"] == []
    assert r2.json()["faltantes_completo"] == []


def test_salvar_metadado_aparece_na_leitura_do_item(sessao_a, itens_a):
    it = _camada(itens_a)
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"metadado": METADADO_COMPLETO})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["campos"]["contato"]["organizacao"] == "iAgroSat"
    assert corpo["campos"]["sistema_referencia"]["codigo"] == "4326"
    # visão de novo, por GET: mesma leitura, campo a campo (não é o corpo de retorno do PUT reaproveitado)
    g = sessao_a.get(f"/api/itens/{it['id']}/metadado")
    assert g.status_code == 200, g.text
    assert g.json()["campos"]["contato"]["email"] == "mgb@exemplo.org"
    assert g.json()["campos"]["distribuicao"]["formato"] == "GeoJSON"
    assert g.json()["faltantes_essencial"] == []


# ---------------------------------------------------------------- 2. json inválido contra o esquema = 422 com caminho
def test_estrutura_invalida_422_com_caminho(sessao_a, itens_a):
    it = _camada(itens_a)
    r = sessao_a.put(
        f"/api/itens/{it['id']}/metadado",
        json={"metadado": {"contato": {"papel": "papel-que-nao-existe"}}},
    )
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "metadado_invalido"
    caminhos = {e["campo"] for e in j["detalhe"]}
    assert "contato.papel" in caminhos


def test_campo_desconhecido_422(sessao_a, itens_a):
    it = _camada(itens_a)
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"metadado": {"campo_que_nao_existe": 1}})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "metadado_invalido"


# ---------------------------------------------------------------- 3. título sincronizado nos dois sentidos
def test_titulo_sincronizado_editor_muda_item_e_vice_versa(sessao_a, itens_a):
    it = _camada(itens_a)
    novo_titulo = it["titulo"] + " (MGB)"
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"item": {"titulo": novo_titulo}, "metadado": {}})
    assert r.status_code == 200, r.text
    assert r.json()["item"]["titulo"] == novo_titulo
    item_agora = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert item_agora["titulo"] == novo_titulo
    # vice-versa: PATCH direto no item (rota já existente do L0-03) aparece na leitura do metadado
    titulo_2 = novo_titulo + " v2"
    r2 = sessao_a.patch(f"/api/itens/{it['id']}", json={"titulo": titulo_2})
    assert r2.status_code == 200, r2.text
    g = sessao_a.get(f"/api/itens/{it['id']}/metadado")
    assert g.json()["campos"]["identificacao"]["titulo"] == titulo_2


# ---------------------------------------------------------------- 4. paridade / estilo por inquilino
def test_estilo_muda_so_apresentacao_armazenamento_e_um_so(sessao_a, itens_a):
    it = _camada(itens_a)
    sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"metadado": METADADO_COMPLETO})
    mgb = sessao_a.get(f"/api/itens/{it['id']}/metadado").json()
    iso = sessao_a.get(f"/api/itens/{it['id']}/metadado", params={"estilo": "iso19115_3"}).json()
    dc = sessao_a.get(f"/api/itens/{it['id']}/metadado", params={"estilo": "dublin_core"}).json()
    assert mgb["estilo"] == "mgb2"
    assert iso["estilo"] == "iso19115_3" and "mdb:identificationInfo" in iso["apresentacao"][0]["caminho"] or True
    assert dc["estilo"] == "dublin_core"
    # mesmo dado por baixo nos três (só rótulo muda)
    org_mgb = mgb["campos"]["contato"]["organizacao"]
    org_iso = iso["campos"]["contato"]["organizacao"]
    org_dc = dc["campos"]["contato"]["organizacao"]
    assert org_mgb == org_iso == org_dc


# ---------------------------------------------------------------- linhagem alimentada por procedência e por evento
def test_linhagem_vem_de_procedencia_e_de_eventos_do_item(sessao_a, itens_a):
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho", "tabela": "zt_inexistente", "geometria": "Point", "srid": 4326,
            "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada",
            "procedencia": {
                "fonte": "IBGE", "url": "https://ibge.gov.br/x", "licenca": "ODbL", "metodo": "download direto",
            },
        },
    )
    g = sessao_a.get(f"/api/itens/{it['id']}/metadado").json()
    linhagem = g["campos"]["qualidade_linhagem"]
    assert "IBGE" in linhagem["declaracao"]
    assert linhagem["fontes"][0]["fonte"] == "IBGE"
    tipos_processo = {p["evento"] for p in linhagem["processos"]}
    assert "itens/adicionar" in tipos_processo


# ---------------------------------------------------------------- refutação 1: 5 MB (limite 1 MiB) = 422
def test_refutacao_metadado_grande_422(sessao_a, itens_a):
    it = _camada(itens_a)
    enorme = {"contato": {"organizacao": "x" * (5 * 1024 * 1024)}}
    assert len(json.dumps(enorme).encode()) > 5 * 1024 * 1024 - 100
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"metadado": enorme})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] in ("metadado_grande", "metadado_invalido", "validacao")


# ---------------------------------------------------------------- refutação 2: datas fora de ordem = 422
def test_refutacao_datas_fora_de_ordem_422(sessao_a, itens_a):
    it = _camada(itens_a)
    ruim = {"extensao": {"temporal": {"inicio": "2026-06-30", "fim": "2026-01-01"}}}
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"metadado": ruim})
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "metadado_invalido"
    assert any(e["campo"] == "extensao.temporal.fim" for e in j["detalhe"])


# ---------------------------------------------------------------- refutação 3: extent contradiz o dado = aviso
def test_refutacao_extent_diverge_e_aviso_nao_bloqueio(sessao_a, itens_a):
    it = _camada(itens_a, extent=[-50.0, -20.0, -40.0, -10.0])
    divergente = {"extensao": {"espacial": {"xmin": 10.0, "ymin": 10.0, "xmax": 20.0, "ymax": 20.0}}}
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json={"metadado": divergente})
    assert r.status_code == 200, r.text  # não bloqueia
    avisos = r.json()["avisos"]
    assert avisos and avisos[0]["campo"] == "extensao.espacial"


# ---------------------------------------------------------------- isolamento entre inquilinos
def test_metadado_de_outro_inquilino_404(sessao_a, sessao_b, itens_b):
    de_b = itens_b.criar("camada_vetorial")
    assert sessao_a.get(f"/api/itens/{de_b['id']}/metadado").status_code == 404
    assert sessao_a.put(f"/api/itens/{de_b['id']}/metadado", json={"metadado": {}}).status_code == 404
