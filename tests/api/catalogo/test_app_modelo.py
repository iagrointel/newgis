"""Item L5-07: a API recusa o que o construtor recusaria (422 `modelo_invalido` com campo e regra) e aceita o
modelo válido; documento v2 é migrado na leitura para v3 (três listas vazias); `GET /api/esquemas/app` publica o
esquema 3 com fontes/vistas/mensagens."""

import secrets

ULIDS = [f"01K5{str(i).zfill(22)}" for i in range(1, 12)]
F1, F2, VA, VC, W1, W2, M1 = ULIDS[:7]


def _corpo(relacao):
    return {
        "nos": [{"id": W1, "tipo": "mapa", "configuracao": {"vista": VA}},
                {"id": W2, "tipo": "tabela", "configuracao": {"vista": VC, "colunas": []}}],
        "ligacoes": [],
        "fontes": [
            {"id": F1, "nome": "municipios", "origem": {"tipo": "embutida", "feicoes": []},
             "campos": [{"nome": "cod", "tipo": "inteiro"}, {"nome": "geometria", "tipo": "geometria"}]},
            {"id": F2, "nome": "escolas", "origem": {"tipo": "embutida", "feicoes": []},
             "campos": [{"nome": "cod_mun", "tipo": "texto"}]},
        ],
        "vistas": [{"id": VA, "nome": "A", "fonte": F1}, {"id": VC, "nome": "C", "fonte": F2}],
        "mensagens": [{"id": M1, "gatilho": {"origem": W1, "evento": "selecao_mudou"},
                       "acoes": [{"alvo": VC, "acao": "filtrar", "parametros": {}, "relacao": relacao}]}],
    }


def _item(sessao, corpo, versao=3):
    r = sessao.post("/api/itens", json={"tipo": "app", "titulo": f"zt-app-modelo-{secrets.token_hex(2)}",
                                        "dados": {"tipo": "app", "esquema_versao": versao, "corpo": corpo}})
    return r


def test_sem_relacao_422_modelo_invalido_e_tipos_que_nao_casam(sessao_a):
    r = _item(sessao_a, _corpo(None))
    assert r.status_code == 422 and r.json()["erro"] == "modelo_invalido", r.text
    assert r.json()["detalhe"][0]["regra"] == "relacao_ausente"
    assert r.json()["detalhe"][0]["campo"] == "corpo.mensagens.0.acoes.0.relacao"
    r = _item(sessao_a, _corpo({"tipo": "atributo", "campo_origem": "cod", "campo_alvo": "cod_mun", "operador": "in"}))
    assert r.status_code == 422 and r.json()["detalhe"][0]["regra"] == "relacao_tipos", r.text


def test_modelo_valido_grava_e_v2_migra_na_leitura(sessao_a):
    corpo = _corpo({"tipo": "espacial"})
    corpo["fontes"][1]["campos"].append({"nome": "geometria", "tipo": "geometria"})
    r = _item(sessao_a, corpo)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    try:
        d = sessao_a.get(f"/api/itens/{iid}").json()["dados"]
        assert d["esquema_versao"] == 3 and len(d["corpo"]["mensagens"]) == 1 and d["corpo"]["vistas"][1]["fonte"] == F2
        # PATCH com relação inválida também é recusado
        versao = sessao_a.get(f"/api/itens/{iid}").json()["versao_atual"]
        corpo_ruim = {"dados": {"tipo": "app", "esquema_versao": 3, "corpo": _corpo(None)}, "versao_atual": versao}
        r = sessao_a.patch(f"/api/itens/{iid}", json=corpo_ruim)
        assert r.status_code == 422 and r.json()["erro"] == "modelo_invalido"
    finally:
        sessao_a.delete(f"/api/itens/{iid}")
    # v2 sem as listas: aceito e lido como v3 com fontes/vistas/mensagens vazias
    r = _item(sessao_a, {"nos": [], "ligacoes": []}, versao=2)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    try:
        d = sessao_a.get(f"/api/itens/{iid}").json()["dados"]
        assert d["esquema_versao"] == 3 and d["corpo"]["fontes"] == [] and d["corpo"]["mensagens"] == []
    finally:
        sessao_a.delete(f"/api/itens/{iid}")


def test_esquema_publicado_tem_as_tres_listas(sessao_a):
    r = sessao_a.get("/api/esquemas/app")
    assert r.status_code == 200, r.text
    props = (r.json().get("esquema") or r.json())["properties"]["corpo"]["properties"]
    assert {"fontes", "vistas", "mensagens"} <= set(props)
    eventos = props["mensagens"]["items"]["properties"]["gatilho"]["properties"]["evento"]["enum"]
    assert eventos == ["clique", "dado_adicionado", "filtro_mudou", "extensao_mudou", "localizacao",
                       "registros_carregados", "selecao_mudou", "vista_mudou"]
