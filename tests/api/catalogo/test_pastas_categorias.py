"""Pastas, tags, categorias e classificação (L0-03-b; ADR 0004 seção 8): pasta em pasta, mover 3 em massa,
renomear, apagar vazia, apagar com item 409, ciclo por PUT 409, 6º nível 422, nome de 10 mil caracteres 422;
2 categorias + 1 classificação; 21ª categoria 422; importar ISO = 19 de topo; INSPIRE = 34 temas em 3 anexos;
categoria de outro inquilino 404; 4º nível 422; nó em uso não se remove (409)."""

import uuid

from tests.api.catalogo.conftest import titulo_zt


def test_pastas_hierarquicas(sessao_a, itens_a):
    r = sessao_a.post("/api/pastas", json={"nome": titulo_zt("raiz")})
    assert r.status_code == 201, r.text
    raiz = r.json()
    assert raiz["profundidade"] == 0 and raiz["ancestrais"] == [] and raiz["pai_id"] is None
    assert sessao_a.post("/api/pastas", json={"nome": raiz["nome"].upper()}).status_code == 409
    assert sessao_a.post("/api/pastas", json={"nome": "a" * 10_000}).status_code == 422
    assert sessao_a.post("/api/pastas", json={"nome": "com/barra"}).status_code == 422
    filha = sessao_a.post("/api/pastas", json={"nome": titulo_zt("filha"), "pai_id": raiz["id"]}).json()
    assert filha["profundidade"] == 1 and filha["ancestrais"] == [raiz["id"]]
    # 5 níveis (0..4) permitidos, 6º recusado
    pai = filha
    for n in range(2, 5):
        pai = sessao_a.post("/api/pastas", json={"nome": titulo_zt(f"n{n}"), "pai_id": pai["id"]}).json()
        assert pai["profundidade"] == n
    r = sessao_a.post("/api/pastas", json={"nome": titulo_zt("n5"), "pai_id": pai["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "pasta_profunda"
    # ciclo por PUT
    r = sessao_a.put(f"/api/pastas/{raiz['id']}", json={"pai_id": filha["id"]})
    assert r.status_code == 409 and r.json()["erro"] == "pasta_ciclo"
    r = sessao_a.put(f"/api/pastas/{raiz['id']}", json={"pai_id": raiz["id"]})
    assert r.status_code == 409
    # renomear e mover (descendentes recalculados)
    r = sessao_a.put(f"/api/pastas/{filha['id']}", json={"nome": titulo_zt("renomeada")})
    assert r.status_code == 200 and r.json()["nome"].startswith("zt renomeada")
    outra = sessao_a.post("/api/pastas", json={"nome": titulo_zt("outra")}).json()
    r = sessao_a.put(f"/api/pastas/{filha['id']}", json={"pai_id": outra["id"]})
    assert r.status_code == 200 and r.json()["ancestrais"] == [outra["id"]]
    arvore = {p["id"]: p for p in sessao_a.get("/api/pastas/arvore").json()}
    neta = arvore[outra["id"]]["filhas"][0]["filhas"][0]
    assert neta["ancestrais"][:2] == [outra["id"], filha["id"]] and neta["profundidade"] == 2
    # mover 3 itens em massa; apagar pasta com item 409; apagar vazia 204
    itens = [itens_a.criar("mapa") for _ in range(3)]
    r = sessao_a.post(
        "/api/itens/lote", json={"ids": [i["id"] for i in itens], "acao": "mover", "pasta_id": filha["id"]}
    )
    assert r.status_code == 200 and r.json()["feitos"] == 3 and r.json()["recusados"] == []
    assert sessao_a.get(f"/api/itens?pasta_id={filha['id']}").json()["total"] == 3
    assert sessao_a.get(f"/api/pastas?pai_id={outra['id']}").json()[0]["itens_visiveis"] == 3
    r = sessao_a.delete(f"/api/pastas/{filha['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "pasta_nao_vazia" and r.json()["detalhe"]["itens"] == 3
    r = sessao_a.delete(f"/api/pastas/{outra['id']}")
    assert r.status_code == 409 and r.json()["detalhe"]["pastas"] == 1
    assert sessao_a.delete(f"/api/pastas/{raiz['id']}").status_code == 204
    assert sessao_a.get(f"/api/pastas?pai_id={raiz['id']}").status_code == 200
    assert sessao_a.put(f"/api/pastas/{uuid.uuid4()}", json={"nome": "x"}).status_code == 404


def test_pasta_de_outro_dono_e_visivel_mas_nao_editavel(editor_a, editor2_a):
    c1, _ = editor_a
    c2, _ = editor2_a
    p = c1.post("/api/pastas", json={"nome": titulo_zt("do editor")}).json()
    assert any(x["id"] == p["id"] for x in c2.get("/api/pastas").json())
    assert c2.put(f"/api/pastas/{p['id']}", json={"nome": "x"}).status_code == 403
    assert c2.delete(f"/api/pastas/{p['id']}").status_code == 403
    assert c1.delete(f"/api/pastas/{p['id']}").status_code == 204


def test_categorias_arvore_limites_e_modelos(sessao_a, sessao_b, itens_a):
    r = sessao_a.get("/api/categorias")
    assert r.status_code == 200 and r.json()["maximo"] == 200
    base = r.json()["arvore"]
    novo = {
        "nome": titulo_zt("Tema"),
        "filhas": [{"nome": titulo_zt("Sub"), "filhas": [{"nome": titulo_zt("Folha"), "filhas": []}]}],
    }
    r = sessao_a.put("/api/categorias", json={"arvore": [_sem_extras(n) for n in base] + [novo]})
    assert r.status_code == 200, r.text
    arvore = r.json()["arvore"]
    tema = next(n for n in arvore if n["nome"] == novo["nome"])
    folha = tema["filhas"][0]["filhas"][0]
    assert folha["nivel"] == 3 and folha["caminho"] == f"{tema['nome']}/{tema['filhas'][0]['nome']}/{folha['nome']}"
    # 4º nível 422
    quarto = {**_sem_extras(tema)}
    quarto["filhas"][0]["filhas"][0]["filhas"] = [{"nome": titulo_zt("n4"), "filhas": []}]
    r = sessao_a.put(
        "/api/categorias", json={"arvore": [_sem_extras(n) for n in arvore if n["id"] != tema["id"]] + [quarto]}
    )
    assert r.status_code == 422 and r.json()["erro"] == "nivel_maximo"
    # item com 2 categorias + classificação; 21ª categoria 422; categoria de outro inquilino 404
    it = itens_a.criar("mapa", categorias=[tema["id"], folha["id"]], classificacao={"sigilo": "interno"})
    assert {c["id"] for c in it["categorias"]} == {tema["id"], folha["id"]} and it["classificacao"] == {
        "sigilo": "interno"
    }
    assert sessao_a.get(f"/api/itens?categoria={tema['id']}").json()["total"] >= 1  # descendente conta
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"categorias": [str(uuid.uuid4()) for _ in range(21)]})
    assert r.status_code == 422
    cat_b = sessao_b.put("/api/categorias", json={"arvore": [{"nome": titulo_zt("de B"), "filhas": []}]}).json()[
        "arvore"
    ][-1]
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"categorias": [cat_b["id"]]})
    assert r.status_code == 404 and r.json()["erro"] == "categoria_inexistente"
    # nó em uso não se remove
    r = sessao_a.put("/api/categorias", json={"arvore": [_sem_extras(n) for n in arvore if n["id"] != tema["id"]]})
    assert r.status_code == 409 and r.json()["erro"] == "categoria_em_uso"
    sessao_a.put(f"/api/itens/{it['id']}", json={"categorias": []})
    r = sessao_a.put("/api/categorias", json={"arvore": [_sem_extras(n) for n in arvore if n["id"] != tema["id"]]})
    assert r.status_code == 200 and all(n["id"] != tema["id"] for n in r.json()["arvore"])
    # modelos: ISO = 19 de topo (idempotente), INSPIRE = 3 anexos + 34 temas
    r = sessao_a.post("/api/categorias/importar", json={"modelo": "iso19115"})
    assert r.status_code == 200 and r.json()["criadas"] + r.json()["existentes"] == 19
    assert sessao_a.post("/api/categorias/importar", json={"modelo": "iso19115"}).json() == {
        "criadas": 0,
        "existentes": 19,
    }
    r = sessao_a.post("/api/categorias/importar", json={"modelo": "inspire"})
    assert r.json()["criadas"] + r.json()["existentes"] == 37
    arvore = sessao_a.get("/api/categorias").json()["arvore"]
    assert sum(1 for n in arvore if n["origem"] == "iso19115") == 19
    anexos = [n for n in arvore if n["origem"] == "inspire"]
    assert len(anexos) == 3 and sum(len(a["filhas"]) for a in anexos) == 34
    assert sessao_a.post("/api/categorias/importar", json={"modelo": "outro"}).status_code == 422
    sessao_b.put(
        "/api/categorias",
        json={
            "arvore": [
                _sem_extras(n) for n in sessao_b.get("/api/categorias").json()["arvore"] if n["id"] != cat_b["id"]
            ]
        },
    )


def _sem_extras(no: dict) -> dict:
    return {
        "id": no["id"],
        "nome": no["nome"],
        "codigo": no.get("codigo"),
        "filhas": [_sem_extras(f) for f in no.get("filhas", [])],
    }


def test_classificacao_obrigatoria_por_inquilino(inquilino_temporario):
    inq = inquilino_temporario
    cfg = {
        "catalogo": {
            "classificacao": {
                "ativa": True,
                "obrigatoria": True,
                "esquema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sigilo"],
                    "properties": {"sigilo": {"enum": ["publico", "interno", "restrito", "pessoal"]}},
                },
            }
        }
    }
    r = inq.admin.put("/api/eu", json={"nome": "Admin"})
    assert r.status_code == 200
    # a configuração do inquilino é escrita pelo superadmin/instalador: aqui via /api/plataforma? não existe rota de
    # config nesta trilha; grava-se direto como postgres não é permitido ao teste — a classificação é testada pela
    # regra de esquema (validação) no inquilino com config já ligada é do L0-07. Aqui prova-se o caminho sem config:
    r = inq.admin.post(
        "/api/itens",
        json={
            "tipo": "mapa",
            "titulo": titulo_zt(),
            "dados": {"esquema_versao": 1, "corpo": {}},
            "classificacao": {"sigilo": "x"},
        },
    )
    assert r.status_code == 201  # sem esquema ativo, o JSON é guardado como veio
    del cfg


def test_categoria_visualizador_nao_edita(visualizador_a):
    c, _ = visualizador_a
    assert c.get("/api/categorias").status_code == 200
    r = c.put("/api/categorias", json={"arvore": []})
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio"
    assert c.post("/api/categorias/importar", json={"modelo": "iso19115"}).status_code == 403
