"""Item L5-04-a-blocos-de-conteudo pela API, contra Postgres real: o tipo `narrativa` existe e valida o envelope
(ULID, tipos de bloco), a publicação (L5-14) recusa imagem sem texto alternativo com mensagem e lista de blocos,
publica quando o texto entra, e a página pública devolve o documento de narrativa; as relações do bloco `mapa`
chegam a `usado-por` e às `camadas_citadas` do token da publicação (narrativa → mapa → camada)."""

import secrets

from app.catalogo.documento import gerar_ulid
from tests.api.catalogo.conftest import titulo_zt

ITEM = "L5-04-a-blocos-de-conteudo"


def _bloco(tipo, **propriedades):
    return {"id": gerar_ulid(), "tipo": tipo, "pai": None, "largura_colunas": 12, "propriedades": propriedades}


def _narrativa(itens_a, *blocos, sessao=None):
    return itens_a.criar(
        "narrativa", sessao=sessao, titulo=titulo_zt("narrativa"),
        dados={"tipo": "narrativa", "esquema_versao": 1, "corpo": {"nos": list(blocos), "ligacoes": []}},
    )


def _slug():
    return f"zt-nar-{secrets.token_hex(4)}"


def test_tipo_narrativa_valida_envelope_e_blocos(sessao_a, itens_a):
    n = _narrativa(itens_a, _bloco("capa", titulo="T"), _bloco("texto", markdown="# olá"))
    assert n["tipo"] == "narrativa" and len(n["dados"]["corpo"]["nos"]) == 2
    # bloco de tipo fora da lista: recusado pelo esquema do tipo (422), nunca gravado
    r = sessao_a.post("/api/itens", json={"tipo": "narrativa", "titulo": titulo_zt("narrativa"), "dados": {
        "tipo": "narrativa", "esquema_versao": 1,
        "corpo": {"nos": [_bloco("script", html="<script>")], "ligacoes": []}}})
    assert r.status_code == 422, r.text
    # id repetido: validar_grafo (a família narrativa entrou em FAMILIAS_GRAFO)
    b = _bloco("texto", markdown="x")
    r = sessao_a.post("/api/itens", json={"tipo": "narrativa", "titulo": titulo_zt("narrativa"), "dados": {
        "tipo": "narrativa", "esquema_versao": 1, "corpo": {"nos": [b, dict(b)], "ligacoes": []}}})
    assert r.status_code == 422 and r.json()["erro"] == "grafo_invalido", r.text
    # o esquema do tipo é servido para o editor e para o agente
    r = sessao_a.get("/api/esquemas/narrativa")
    assert r.status_code == 200 and r.json()["properties"]["tipo"]["const"] == "narrativa", r.text


def test_imagem_sem_texto_alternativo_bloqueia_a_publicacao_com_mensagem(sessao_a, itens_a):
    sem_alt = _bloco("imagem", url="/static/favicon.svg", alternativo="", legenda="figura")
    n = _narrativa(itens_a, _bloco("capa", titulo="T"), sem_alt, _bloco("texto", markdown="corpo"))
    r = sessao_a.post(f"/api/itens/{n['id']}/publicacao", json={"slug": _slug()})
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "narrativa_nao_publicavel" and "texto alternativo" in j["mensagem"]
    assert j["detalhe"] == [{"bloco": sem_alt["id"], "tipo": "imagem", "campo": "alternativo",
                             "erro": "imagem sem texto alternativo: descreva a imagem para quem não a vê"}]
    assert sessao_a.get(f"/api/itens/{n['id']}/publicacao").json() is None  # nada foi publicado
    # com o texto alternativo, publica; a página pública devolve o documento de narrativa
    nos = n["dados"]["corpo"]["nos"]
    nos[1]["propriedades"]["alternativo"] = "logotipo da plataforma"
    r = sessao_a.patch(f"/api/itens/{n['id']}", json={"dados": n["dados"], "versao_atual": n["versao_atual"]})
    assert r.status_code == 200, r.text
    slug = _slug()
    r = sessao_a.post(f"/api/itens/{n['id']}/publicacao", json={"slug": slug})
    assert r.status_code == 201, r.text
    assert r.json()["url"].endswith(f"/p/demo/{slug}")
    r = sessao_a.get(f"/api/p/demo/{slug}")
    assert r.status_code == 200, r.text
    corpo = r.json()["corpo"]
    assert corpo["tipo"] == "narrativa" and [b["tipo"] for b in corpo["corpo"]["nos"]] == ["capa", "imagem", "texto"]
    assert corpo["corpo"]["nos"][1]["propriedades"]["alternativo"] == "logotipo da plataforma"
    # rascunho alterado depois não muda o publicado (L5-14) — a versão publicada é a que passou na validação
    nos[1]["propriedades"]["alternativo"] = ""
    atual = sessao_a.get(f"/api/itens/{n['id']}").json()["versao_atual"]
    r = sessao_a.patch(f"/api/itens/{n['id']}", json={"dados": n["dados"], "versao_atual": atual})
    assert r.status_code == 200, r.text
    assert sessao_a.get(f"/api/p/demo/{slug}").json()["corpo"]["corpo"]["nos"][1]["propriedades"]["alternativo"] \
        == "logotipo da plataforma"


def test_bloco_de_mapa_cita_o_mapa_e_o_token_le_as_camadas_dele(sessao_a, itens_a):
    camada = itens_a.criar("camada_vetorial", sessao=sessao_a)
    mapa = itens_a.criar("mapa", sessao=sessao_a, dados={"esquema_versao": 1, "corpo": {"camadas": [camada["id"]]}})
    vista = {"bbox": [-46.7, -23.6, -46.5, -23.4], "centro": [-46.6, -23.5], "zoom": 11, "rotacao": 0,
             "proporcao": 0.6, "camadas": [camada["id"]]}
    n = _narrativa(itens_a, _bloco("capa", titulo="T"), _bloco("mapa", mapa_id=mapa["id"], vista=vista, legenda="mapa"))
    r = sessao_a.get(f"/api/itens/{mapa['id']}/usado-por")
    assert r.status_code == 200, r.text
    assert any(u["id"] == n["id"] for u in r.json()), r.text
    r = sessao_a.post(f"/api/itens/{n['id']}/publicacao", json={"slug": _slug()})
    assert r.status_code == 201, r.text
    assert r.json()["camadas_citadas"] == [camada["id"]]


def test_vista_de_mapa_incompleta_e_enderecos_inseguros_nao_publicam(sessao_a, itens_a):
    n = _narrativa(itens_a,
                   _bloco("mapa", vista={"bbox": [1, 2, 0, 3], "centro": [0, 0], "zoom": 5, "proporcao": 0.5}),
                   _bloco("incorporar", url="https://exemplo.org/x", titulo="ok"),
                   _bloco("botao", rotulo="ir", url="https://exemplo.org"))
    r = sessao_a.post(f"/api/itens/{n['id']}/publicacao", json={"slug": _slug()})
    assert r.status_code == 422 and r.json()["erro"] == "narrativa_nao_publicavel", r.text
    assert [d["campo"] for d in r.json()["detalhe"]] == ["vista"]
