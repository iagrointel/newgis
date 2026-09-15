"""Item L0-09-metadado-catalogo, cláusula 3 (refutação G4 do L0-09): editor de metadado NA TELA, sobre
`GET/POST validar/PUT /api/itens/{id}/metadado` — as mesmas rotas que `web/js/catalogo/item_metadado.js` chama
(`api.metadadoObter`/`metadadoValidar`/`metadadoSalvar`) e que `app/catalogo/metadado_mgb.py` (item irmão
L0-09-b) já definia em esquema/validação/leitura sem nunca estar ligado a uma rota. Este arquivo prova a rota,
não o motor (que `tests/api/catalogo/test_metadado_mgb.py` cobre campo a campo): núcleo ISO (título, resumo,
palavras-chave, contato, extensão, sistema de referência, licença, linhagem), validação no servidor, auditoria
na escrita e isolamento por inquilino."""

from tests.api.conftest import novo_cliente


def _camada(itens_a, **campos):
    base = {"resumo": "resumo de teste", "tags": ["agro"], "extent": [-50.0, -20.0, -40.0, -10.0]}
    base.update(campos)
    return itens_a.criar("camada_vetorial", **base)


def test_leitura_inicial_traz_nucleo_iso_sincronizado_e_faltantes(sessao_a, itens_a):
    it = _camada(itens_a, tags=["agro", "zt-editor"])
    r = sessao_a.get(f"/api/itens/{it['id']}/metadado")
    assert r.status_code == 200, r.text
    corpo = r.json()
    campos = corpo["campos"]
    # título/resumo/palavras-chave: sincronizados com o item, nunca digitados de novo no editor
    assert campos["identificacao"]["titulo"] == it["titulo"]
    assert campos["identificacao"]["resumo"] == "resumo de teste"
    assert set(campos["identificacao"]["palavras_chave"]) == {"agro", "zt-editor"}
    # extensão: efetiva a partir do extent do item quando nada foi declarado no metadado próprio
    assert campos["extensao"]["espacial"] == {"xmin": -50.0, "ymin": -20.0, "xmax": -40.0, "ymax": -10.0}
    # contato/sistema de referência/licença ainda vazios: aparecem como falta no essencial
    faltando = {f["campo"] for f in corpo["faltantes_essencial"]}
    assert {"contato.organizacao", "contato.email", "restricoes.licenca", "sistema_referencia.codigo"} <= faltando
    # linhagem computada (nunca digitada): ao menos o evento de criação do item
    assert any(p["evento"] == "itens/adicionar" for p in campos["qualidade_linhagem"]["processos"])


def test_salvar_contato_extensao_sistema_referencia_e_licenca_grava_e_e_auditado(sessao_a, itens_a):
    it = _camada(itens_a)
    corpo_editor = {
        "metadado": {
            "contato": {"organizacao": "iAgroSat", "email": "catalogo@exemplo.org", "papel": "pointOfContact"},
            "restricoes": {"licenca": "CC BY 4.0"},
            "sistema_referencia": {"codigo": "4326", "codespace": "EPSG"},
        }
    }
    r = sessao_a.put(f"/api/itens/{it['id']}/metadado", json=corpo_editor)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["campos"]["contato"]["organizacao"] == "iAgroSat"
    assert corpo["campos"]["restricoes"]["licenca"] == "CC BY 4.0"
    assert corpo["faltantes_essencial"] == []
    # devolve o item atualizado no mesmo corpo (o editor sincroniza a Visão geral sem um segundo GET)
    assert corpo["item"]["id"] == it["id"]
    # persistiu: GET de novo é a mesma leitura, não o corpo de retorno do PUT reaproveitado
    g = sessao_a.get(f"/api/itens/{it['id']}/metadado")
    assert g.json()["campos"]["sistema_referencia"]["codigo"] == "4326"
    # auditoria: a escrita do editor vira evento nomeado, consultável por quem audita
    eventos = sessao_a.get("/api/eventos?limite=50").json()["itens"]
    meus = [e for e in eventos if e["alvo_id"] == it["id"]]
    assert any(e["tipo"] == "itens/metadado_iso_atualizar" for e in meus)


def test_validar_nao_grava(sessao_a, itens_a):
    it = _camada(itens_a, tags=[])
    antes = sessao_a.get(f"/api/itens/{it['id']}/metadado").json()
    r = sessao_a.post(
        f"/api/itens/{it['id']}/metadado/validar",
        json={"metadado": {"contato": {"organizacao": "só de mentira, para validar"}}},
    )
    assert r.status_code == 200, r.text
    assert "identificacao.palavras_chave" in {f["campo"] for f in r.json()["faltantes_essencial"]}
    depois = sessao_a.get(f"/api/itens/{it['id']}/metadado").json()
    assert depois["campos"]["contato"] == antes["campos"]["contato"] == {}


def test_estrutura_invalida_e_recusada_no_servidor(sessao_a, itens_a):
    it = _camada(itens_a)
    r = sessao_a.put(
        f"/api/itens/{it['id']}/metadado", json={"metadado": {"sistema_referencia": {"codigo": "4326" * 20}}}
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "metadado_invalido"


def test_isolamento_por_inquilino(sessao_a, sessao_b, itens_b):
    de_b = itens_b.criar("camada_vetorial")
    c = novo_cliente()
    assert sessao_a.get(f"/api/itens/{de_b['id']}/metadado").status_code == 404
    assert sessao_a.put(f"/api/itens/{de_b['id']}/metadado", json={"metadado": {}}).status_code == 404
    assert sessao_a.post(f"/api/itens/{de_b['id']}/metadado/validar", json={"metadado": {}}).status_code == 404
    assert sessao_b.get(f"/api/itens/{de_b['id']}/metadado").status_code == 200
    assert c.get(f"/api/itens/{de_b['id']}/metadado").status_code == 401
