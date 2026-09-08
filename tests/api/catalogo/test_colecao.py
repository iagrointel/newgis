"""Coleção (L5-04-c-temas-capa-colecao): tipo `colecao` com capa, metadados e itens citados por uuid; relações
`item_de_colecao` sincronizadas do corpo (dependência inexistente = 422); `capa.midia`/`metadados.miniatura` só
caminho da casa ou https; criar link devolve `avisos` com o que ficou de fora e o recriar com `itens_incluidos`
encerra o aviso; `og:` só na página pública /c/<token> — as internas (/colecao, /conteudo) nunca levam."""

import uuid

from app.settings import settings
from tests.api.catalogo.conftest import titulo_zt
from tests.api.conftest import novo_cliente

ITEM = "L5-04-c-temas-capa-colecao"


def dados_colecao(refs, capa=None, metadados=None):
    corpo = {"capa": capa if capa is not None else {"titulo": "capa da coleção"}, "itens": refs}
    if metadados is not None:
        corpo["metadados"] = metadados
    return {"tipo": "colecao", "esquema_versao": 1, "corpo": corpo}


def _criar_colecao(sessao, itens, refs, **kw):
    r = sessao.post(
        "/api/itens", json={"tipo": "colecao", "titulo": titulo_zt("colecao"), "dados": dados_colecao(refs, **kw)}
    )
    assert r.status_code == 201, r.text
    j = r.json()
    itens.criados.append(j["id"])
    return j


def test_cria_relaciona_e_edita(sessao_a, itens_a):
    filhos = [itens_a.criar("app"), itens_a.criar("painel"), itens_a.criar("mapa")]
    refs = [{"item_id": f["id"], "rotulo": f"peça {i}"} for i, f in enumerate(filhos)]
    colecao = _criar_colecao(sessao_a, itens_a, refs)
    det = sessao_a.get(f"/api/itens/{colecao['id']}").json()
    assert det["dados"]["corpo"]["capa"]["titulo"] == "capa da coleção"
    assert det["tipo"] == "colecao" and det["familia"] == "documento"
    dep = sessao_a.get(f"/api/itens/{colecao['id']}/compartilhamento").json()["dependencias"]
    assert [d["id"] for d in dep] == [f["id"] for f in filhos], dep
    assert all(d["tipo_relacao"] == "item_de_colecao" for d in dep)
    # editar o corpo reordena e remove: a relação segue o corpo (sincronizar)
    refs_novos = list(reversed(refs[:2]))
    r = sessao_a.put(f"/api/itens/{colecao['id']}", json={"dados": dados_colecao(refs_novos)})
    assert r.status_code == 200, r.text
    dep = sessao_a.get(f"/api/itens/{colecao['id']}/compartilhamento").json()["dependencias"]
    assert [d["id"] for d in dep] == [refs_novos[0]["item_id"], refs_novos[1]["item_id"]]


def test_recusa_item_inexistente_si_mesma_e_esquema(sessao_a, itens_a):
    r = sessao_a.post(
        "/api/itens",
        json={
            "tipo": "colecao",
            "titulo": titulo_zt("colecao"),
            "dados": dados_colecao([{"item_id": str(uuid.uuid4())}]),
        },
    )
    assert r.status_code == 422 and r.json()["erro"] == "relacao_com_outro_inquilino", r.text
    # capa sem título reprova no esquema do tipo
    r = sessao_a.post(
        "/api/itens",
        json={"tipo": "colecao", "titulo": titulo_zt("colecao"), "dados": dados_colecao([], capa={})},
    )
    assert r.status_code == 422 and r.json()["erro"] == "dados_invalidos", r.text
    # citar a própria coleção (PUT, quando o id já existe) = 422
    colecao = _criar_colecao(sessao_a, itens_a, [])
    r = sessao_a.put(
        f"/api/itens/{colecao['id']}", json={"dados": dados_colecao([{"item_id": colecao["id"]}])}
    )
    assert r.status_code == 422 and r.json()["erro"] == "relacao_com_outro_inquilino", r.text


def test_midia_e_miniatura_tem_formato_guardado(sessao_a, itens_a):
    base = {"titulo": "capa"}
    for campo, valor in (
        ("capa_midia", "javascript:alerta(1)"),
        ("capa_midia", "data:text/html;base64,AAAA"),
        ("miniatura", "http://exemplo.gov.br/a.png"),  # http puro não vale
    ):
        corpo = {"capa": dict(base), "itens": []}
        if campo == "capa_midia":
            corpo["capa"]["midia"] = valor
        else:
            corpo["metadados"] = {"miniatura": valor}
        dados = {"tipo": "colecao", "esquema_versao": 1, "corpo": corpo}
        r = sessao_a.post("/api/itens", json={"tipo": "colecao", "titulo": titulo_zt("colecao"), "dados": dados})
        assert r.status_code == 422 and r.json()["erro"] == "colecao_invalida", (campo, valor, r.text)
    # caminho da casa e https passam
    j = _criar_colecao(
        sessao_a,
        itens_a,
        [],
        capa={"titulo": "capa", "midia": "/static/favicon.svg"},
        metadados={"miniatura": "https://exemplo.gov.br/a.png"},
    )
    det = sessao_a.get(f"/api/itens/{j['id']}").json()
    assert det["dados"]["corpo"]["capa"]["midia"] == "/static/favicon.svg"


def test_link_avisos_e_corrigir(sessao_a, itens_a):
    camada = itens_a.criar("camada_vetorial")
    refs = [{"item_id": camada["id"], "rotulo": "camada privada"}]
    colecao = _criar_colecao(sessao_a, itens_a, refs)
    anon = novo_cliente()
    # publica SEM incluir: 201 com aviso nomeando o que ficou de fora
    r = sessao_a.post(f"/api/itens/{colecao['id']}/links", json={})
    assert r.status_code == 201, r.text
    j = r.json()
    assert [a["id"] for a in j["avisos"]] == [camada["id"]] and j["avisos"][0]["titulo"], j.get("avisos")
    tok_fora = j["token"]
    # anônimo lê a coleção e o corpo cita o uuid ausente (a leitora computa o aviso a partir disso)
    leitura = anon.get(f"/api/compartilhado/{tok_fora}").json()
    assert leitura["itens_incluidos"] == []
    assert leitura["item"]["dados"]["corpo"]["itens"][0]["item_id"] == camada["id"]
    assert anon.get(f"/api/compartilhado/{tok_fora}/itens/{camada['id']}").status_code == 404
    # corrigir: revoga e recria incluindo o citado; o aviso encerra e o anônimo passa a ler
    assert sessao_a.delete(f"/api/itens/{colecao['id']}/links/{j['id']}").status_code == 204
    r = sessao_a.post(f"/api/itens/{colecao['id']}/links", json={"itens_incluidos": [camada["id"]]})
    assert r.status_code == 201 and r.json()["avisos"] == [], r.text
    tok_dentro = r.json()["token"]
    leitura = anon.get(f"/api/compartilhado/{tok_dentro}").json()
    assert [x["id"] for x in leitura["itens_incluidos"]] == [camada["id"]]
    assert anon.get(f"/api/compartilhado/{tok_dentro}/itens/{camada['id']}").status_code == 200
    # item sem dependência nenhuma: aviso vazio de verdade (não é só chave ausente)
    simples = itens_a.criar("app")
    r = sessao_a.post(f"/api/itens/{simples['id']}/links", json={})
    assert r.status_code == 201 and r.json()["avisos"] == [], r.text


def test_og_somente_na_pagina_publica(sessao_a, itens_a):
    metadados = {"titulo": "título para compartilhar", "resumo": "resumo público", "miniatura": "/static/favicon.svg"}
    colecao = _criar_colecao(sessao_a, itens_a, [], metadados=metadados)
    r = sessao_a.post(f"/api/itens/{colecao['id']}/links", json={})
    assert r.status_code == 201, r.text
    tok = r.json()["token"]
    rc = sessao_a.get(f"/c/{tok}")
    texto = rc.text
    assert rc.status_code == 200 and "text/html" in rc.headers["content-type"]
    assert '<meta property="og:title" content="título para compartilhar">' in texto, texto[:400]
    assert '<meta property="og:description" content="resumo público">' in texto
    assert f'<meta property="og:image" content="{settings.PLAT_URL_PUBLICA}/static/favicon.svg">' in texto
    assert rc.headers["cache-control"] == "no-store, must-revalidate"
    # internas não levam og:
    for caminho in ("/colecao", "/conteudo"):
        ri = sessao_a.get(caminho)
        assert ri.status_code == 200 and "og:title" not in ri.text, caminho
    # link inválido: a página abre (o JavaScript mostra o erro) sem og:
    ri = sessao_a.get(f"/c/{'0' * 64}")
    assert ri.status_code == 200 and "og:title" not in ri.text
