"""Pacote entre inquilinos e galeria de modelos (item L5-37-pacotes-modelos-entre-inquilinos), portão de
pronto cláusula por cláusula, contra a API de verdade e nos DOIS inquilinos (demo = A, demo2 = B):

1. "pacote exportado de A importa em B mapeando 3 fontes e o app funciona (e2e nos dois inquilinos)":
   `test_exportar_de_a_importar_em_b_com_tres_fontes` monta em A camadas → mapa → app, exporta, cria em B
   três camadas de esquema igual, importa mapeando as três e prova que o app importado ABRE PUBLICADO em B
   (`/api/p/demo2/<slug>`, o caminho do L5-14) sem que o de A tenha mudado.
2. "esquema incompatível listado campo a campo antes de importar": `test_esquema_incompativel_*`.
3. "ids regenerados sem quebrar referências (teste de integridade)": `test_integridade_dos_ids_importados`.
4. "pacote assinado (sha256 do conteúdo) e conferido": `test_assinatura_conferida_na_importacao`.
Refutação: `test_id_de_outro_inquilino_e_recusado`, `test_zip_com_caminho_para_fora_e_recusado`,
`test_importar_duas_vezes_da_dois_apps_distintos`.
"""

import base64
import io
import json
import secrets
import zipfile

from app.catalogo import pacote as mod_pacote
from app.catalogo.documento import ULID_RE, gerar_ulid, sha256_canonico
from tests.api.catalogo.conftest import titulo_zt

ITEM = "L5-37-pacotes-modelos-entre-inquilinos"
CAMPOS = {
    "talhao": [{"nome": "codigo", "tipo": "text"}, {"nome": "area_ha", "tipo": "numeric"}],
    "via": [{"nome": "nome", "tipo": "text"}, {"nome": "classe", "tipo": "text"}],
    "ponto": [{"nome": "rotulo", "tipo": "text"}],
}
GEOMETRIA = {"talhao": "MultiPolygon", "via": "MultiLineString", "ponto": "Point"}


def _dados_camada(papel: str, campos=None, geometria=None, srid=4674) -> dict:
    import os

    return {
        "schema": os.environ.get("PLAT_SCHEMA_TRABALHO", "plat_trabalho"),
        "tabela": f"zt_{papel}",
        "geometria": geometria or GEOMETRIA[papel],
        "srid": srid,
        "campos": campos if campos is not None else CAMPOS[papel],
        "fonte": "hospedada",
    }


def _montar_origem(itens, sessao):
    """Três camadas → um mapa que cita as três → um app que cita o mapa. É a cadeia que o pacote atravessa."""
    camadas = {p: itens.criar("camada_vetorial", sessao=sessao, dados=_dados_camada(p)) for p in CAMPOS}
    mapa = itens.criar(
        "mapa",
        sessao=sessao,
        dados={"esquema_versao": 1, "corpo": {"camadas": [c["id"] for c in camadas.values()]}},
    )
    no_visor, no_legenda = gerar_ulid(), gerar_ulid()
    app = itens.criar(
        "app",
        sessao=sessao,
        dados={
            "tipo": "app",
            "esquema_versao": 2,
            "corpo": {
                "mapas": [mapa["id"]],
                "nos": [
                    {"id": no_visor, "tipo": "visor_mapa", "mapa": mapa["id"]},
                    {"id": no_legenda, "tipo": "legenda"},
                ],
                "ligacoes": [{"origem": no_visor, "alvo": no_legenda}],
            },
        },
    )
    return camadas, mapa, app


def _exportar(sessao, item_id: str) -> bytes:
    r = sessao.get(f"/api/itens/{item_id}/pacote")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/zip")
    return r.content


def _manifesto(conteudo: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        return json.loads(zf.read(mod_pacote.ARQUIVO_MANIFESTO))


def _b64(conteudo: bytes) -> str:
    return base64.b64encode(conteudo).decode("ascii")


def _camadas_de_destino(itens_b, sessao_b, campos_por_papel=None):
    campos_por_papel = campos_por_papel or {}
    return {
        p: itens_b.criar(
            "camada_vetorial",
            sessao=sessao_b,
            dados=_dados_camada(p, campos=campos_por_papel.get(p)),
        )
        for p in CAMPOS
    }


def _mapeamento(manifesto, camadas_origem, camadas_destino) -> dict:
    por_id = {c["id"]: p for p, c in camadas_origem.items()}
    return {f["id"]: camadas_destino[por_id[f["id"]]]["id"] for f in manifesto["fontes"]}


# ---------------------------------------------------------------- cláusula 1: A → B com 3 fontes
def test_exportar_de_a_importar_em_b_com_tres_fontes(sessao_a, sessao_b, itens_a, itens_b, medida):
    camadas_a, mapa_a, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    m = _manifesto(conteudo)
    # o pacote leva os DOIS documentos (app e mapa) e declara as TRÊS camadas como fontes, sem dado nenhum
    assert {d["tipo"] for d in m["documentos"]} == {"app", "mapa"}
    assert len(m["fontes"]) == 3 and all(f["tipo"] == "camada_vetorial" for f in m["fontes"])
    assert all("tabela" not in f for f in m["fontes"])

    camadas_b = _camadas_de_destino(itens_b, sessao_b)
    mapeamento = _mapeamento(m, camadas_a, camadas_b)
    r = sessao_b.post("/api/pacotes/verificar", json={"conteudo": _b64(conteudo), "mapeamento": mapeamento})
    assert r.status_code == 200, r.text
    assert r.json()["pronto"] is True and len(r.json()["fontes"]) == 3

    r = sessao_b.post("/api/pacotes/importar", json={"conteudo": _b64(conteudo), "mapeamento": mapeamento})
    assert r.status_code == 201, r.text
    importado = r.json()
    itens_b.criados.extend([x["id"] for x in importado["itens"]])
    assert importado["fontes_mapeadas"] == 3 and len(importado["itens"]) == 2

    # o app importado aponta para as camadas DE B (relações declaradas, não texto solto)
    r = sessao_b.get(f"/api/itens/{importado['raiz']}/criado-a-partir-de")
    assert r.status_code == 200, r.text
    mapa_novo = [x for x in r.json() if x["tipo"] == "mapa"]
    assert len(mapa_novo) == 1 and mapa_novo[0]["id"] != mapa_a["id"]
    r = sessao_b.get(f"/api/itens/{mapa_novo[0]['id']}/criado-a-partir-de")
    assert {x["id"] for x in r.json()} == {c["id"] for c in camadas_b.values()}

    # "o app funciona" nos DOIS inquilinos: publicado e aberto pelo caminho público do L5-14
    for sessao, slug_inquilino, item_id in (
        (sessao_a, "demo", app_a["id"]),
        (sessao_b, "demo2", importado["raiz"]),
    ):
        slug = f"zt-pac-{secrets.token_hex(4)}"
        assert sessao.post(f"/api/itens/{item_id}/publicacao", json={"slug": slug}).status_code == 201
        rl = sessao.post(f"/api/itens/{item_id}/links", json={"nome": "zt pacote"})
        assert rl.status_code == 201, rl.text
        r = sessao.get(f"/api/p/{slug_inquilino}/{slug}?link={rl.json()['token']}")
        assert r.status_code == 200, r.text
        assert len(r.json()["corpo"]["corpo"]["nos"]) == 2
        sessao.delete(f"/api/itens/{item_id}/publicacao")

    # o original de A não mudou (importar em B não toca em A)
    r = sessao_a.get(f"/api/itens/{app_a['id']}")
    assert r.json()["dados"]["corpo"]["mapas"] == [mapa_a["id"]]
    medida(ITEM)("documentos_no_pacote", len(m["documentos"]), "documentos", "GET /api/itens/{id}/pacote")
    medida(ITEM)("fontes_mapeadas", 3, "fontes", "POST /api/pacotes/importar")
    # o pacote leva documento e declaração de fonte, nunca dado: por isso cabe em poucos milhares de bytes
    medida(ITEM)("bytes_do_pacote", len(conteudo), "bytes", "GET /api/itens/{id}/pacote")


# ---------------------------------------------------------------- cláusula 2: esquema campo a campo
def test_esquema_incompativel_e_listado_campo_a_campo_antes_de_importar(sessao_a, sessao_b, itens_a, itens_b):
    camadas_a, _, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    m = _manifesto(conteudo)
    # em B, a camada de talhão perde um campo e troca o tipo de outro
    camadas_b = _camadas_de_destino(
        itens_b, sessao_b, {"talhao": [{"nome": "codigo", "tipo": "integer"}]}
    )
    mapeamento = _mapeamento(m, camadas_a, camadas_b)
    r = sessao_b.post("/api/pacotes/verificar", json={"conteudo": _b64(conteudo), "mapeamento": mapeamento})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["pronto"] is False
    ruim = [f for f in a["fontes"] if f["erro"] == "esquema_incompativel"]
    assert len(ruim) == 1
    por_campo = {d["campo"]: d for d in ruim[0]["diferencas"]}
    assert por_campo["area_ha"]["regra"] == "campo_ausente" and por_campo["area_ha"]["bloqueia"] is True
    assert por_campo["codigo"]["regra"] == "tipo_diferente"
    assert por_campo["codigo"]["esperado"] == "text" and por_campo["codigo"]["encontrado"] == "integer"
    # e a importação recusa com a MESMA lista, sem criar nada
    antes = sessao_b.get("/api/itens?tipo=app&limite=1").json()["total"]
    r = sessao_b.post("/api/pacotes/importar", json={"conteudo": _b64(conteudo), "mapeamento": mapeamento})
    assert r.status_code == 422 and r.json()["erro"] == "pacote_incompativel", r.text
    assert sessao_b.get("/api/itens?tipo=app&limite=1").json()["total"] == antes


def test_fonte_nao_mapeada_impede_a_importacao(sessao_a, sessao_b, itens_a):
    _, _, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    r = sessao_b.post("/api/pacotes/verificar", json={"conteudo": _b64(conteudo), "mapeamento": {}})
    assert r.status_code == 200 and r.json()["pronto"] is False
    assert {f["erro"] for f in r.json()["fontes"]} == {"fonte_nao_mapeada"}
    r = sessao_b.post("/api/pacotes/importar", json={"conteudo": _b64(conteudo), "mapeamento": {}})
    assert r.status_code == 422 and r.json()["erro"] == "pacote_incompativel", r.text


# ---------------------------------------------------------------- cláusula 3: integridade dos ids
def test_integridade_dos_ids_importados(sessao_a, sessao_b, itens_a, itens_b):
    camadas_a, mapa_a, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    m = _manifesto(conteudo)
    camadas_b = _camadas_de_destino(itens_b, sessao_b)
    r = sessao_b.post(
        "/api/pacotes/importar",
        json={"conteudo": _b64(conteudo), "mapeamento": _mapeamento(m, camadas_a, camadas_b)},
    )
    assert r.status_code == 201, r.text
    itens_b.criados.extend([x["id"] for x in r.json()["itens"]])
    novo = sessao_b.get(f"/api/itens/{r.json()['raiz']}").json()
    corpo = novo["dados"]["corpo"]
    # nenhum id do pacote sobrou: nem o do app, nem o do mapa, nem o das camadas, nem o dos nós
    ids_da_origem = {app_a["id"], mapa_a["id"], *[c["id"] for c in camadas_a.values()]}
    texto = json.dumps(novo, ensure_ascii=False)
    assert not (ids_da_origem & mod_pacote.uuids_citados(json.loads(texto)))
    # as referências internas continuam de pé: as duas pontas da ligação são nós que existem
    ids_nos = [n["id"] for n in corpo["nos"]]
    assert len(ids_nos) == 2 and all(ULID_RE.match(i) for i in ids_nos)
    assert corpo["ligacoes"][0]["origem"] in ids_nos and corpo["ligacoes"][0]["alvo"] in ids_nos
    # o nó que apontava para o mapa aponta para o mapa NOVO, e o mapa novo é o que o app cita
    assert corpo["nos"][0]["mapa"] == corpo["mapas"][0]
    r = sessao_b.get(f"/api/itens/{r.json()['raiz']}/integridade")
    assert r.status_code == 200, r.text


def test_importar_duas_vezes_da_dois_apps_distintos(sessao_a, sessao_b, itens_a, itens_b):
    camadas_a, _, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    m = _manifesto(conteudo)
    camadas_b = _camadas_de_destino(itens_b, sessao_b)
    mapeamento = _mapeamento(m, camadas_a, camadas_b)
    raizes = []
    for _ in range(2):
        r = sessao_b.post("/api/pacotes/importar", json={"conteudo": _b64(conteudo), "mapeamento": mapeamento})
        assert r.status_code == 201, r.text
        itens_b.criados.extend([x["id"] for x in r.json()["itens"]])
        raizes.append(r.json()["raiz"])
    assert raizes[0] != raizes[1]
    a, b = (sessao_b.get(f"/api/itens/{x}").json() for x in raizes)
    assert a["dados"]["corpo"]["mapas"] != b["dados"]["corpo"]["mapas"]  # cada um com o seu mapa
    nos_a = {n["id"] for n in a["dados"]["corpo"]["nos"]}
    nos_b = {n["id"] for n in b["dados"]["corpo"]["nos"]}
    assert nos_a.isdisjoint(nos_b)


# ---------------------------------------------------------------- cláusula 4: assinatura
def test_assinatura_conferida_na_importacao(sessao_a, sessao_b, itens_a):
    camadas_a, _, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    m = _manifesto(conteudo)
    sem = {k: v for k, v in m.items() if k != "sha256_conteudo"}
    assert sha256_canonico(sem) == m["sha256_conteudo"]
    # troca o título de um documento dentro do zip e mantém o manifesto: a importação recusa
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        arquivos = {n: zf.read(n) for n in zf.namelist()}
    alvo = next(n for n in arquivos if n.startswith(mod_pacote.PASTA_DOCUMENTOS))
    doc = json.loads(arquivos[alvo])
    doc["titulo"] = "documento trocado"
    arquivos[alvo] = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, b in arquivos.items():
            zf.writestr(n, b)
    r = sessao_b.post("/api/pacotes/verificar", json={"conteudo": _b64(saida.getvalue()), "mapeamento": {}})
    assert r.status_code == 422 and r.json()["erro"] == "pacote_adulterado", r.text


# ---------------------------------------------------------------- refutação do adversário
def test_id_de_outro_inquilino_e_recusado(sessao_a, sessao_b, itens_a, itens_b):
    """Pacote com o UUID de um item que o inquilino de destino não recebeu nem mapeou: recusa, sem criar nada."""
    camadas_a, _, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    m = _manifesto(conteudo)
    item_de_a = itens_a.criar("mapa", sessao=sessao_a)  # id que existe, mas em OUTRO inquilino
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        arquivos = {n: zf.read(n) for n in zf.namelist()}
    alvo = next(
        n
        for n in arquivos
        if n.startswith(mod_pacote.PASTA_DOCUMENTOS) and json.loads(arquivos[n])["tipo"] == "app"
    )
    doc = json.loads(arquivos[alvo])
    doc["dados"]["corpo"]["nos"][1]["fonte_escondida"] = item_de_a["id"]
    arquivos[alvo] = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    entrada = next(e for e in m["documentos"] if e["arquivo"] == alvo)
    entrada["sha256"] = sha256_canonico(doc)  # o adversário reassina o pacote inteiro, como faria de verdade
    m.pop("sha256_conteudo")
    m["sha256_conteudo"] = sha256_canonico(m)
    arquivos[mod_pacote.ARQUIVO_MANIFESTO] = json.dumps(
        m, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, b in arquivos.items():
            zf.writestr(n, b)
    camadas_b = _camadas_de_destino(itens_b, sessao_b)
    corpo = {"conteudo": _b64(saida.getvalue()), "mapeamento": _mapeamento(m, camadas_a, camadas_b)}
    antes = sessao_b.get("/api/itens?tipo=app&limite=1").json()["total"]
    r = sessao_b.post("/api/pacotes/importar", json=corpo)
    assert r.status_code == 422 and r.json()["erro"] == "referencia_desconhecida", r.text
    assert item_de_a["id"] in r.json()["detalhe"]["ids"]
    assert sessao_b.get("/api/itens?tipo=app&limite=1").json()["total"] == antes


def test_zip_com_caminho_para_fora_e_recusado(sessao_a, sessao_b, itens_a):
    _, _, app_a = _montar_origem(itens_a, sessao_a)
    conteudo = _exportar(sessao_a, app_a["id"])
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        arquivos = {n: zf.read(n) for n in zf.namelist()}
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, b in arquivos.items():
            zf.writestr(n, b)
        zf.writestr("../../../etc/plat/segredos/roubado.txt", "x")
    r = sessao_b.post("/api/pacotes/verificar", json={"conteudo": _b64(saida.getvalue()), "mapeamento": {}})
    assert r.status_code == 422 and r.json()["erro"] == "pacote_invalido", r.text
    assert "zip recusado" in r.json()["mensagem"]


# ---------------------------------------------------------------- galeria de modelos
def test_galeria_publica_lista_baixa_e_apaga(sessao_a, sessao_b, itens_a, itens_b):
    camadas_a, _, app_a = _montar_origem(itens_a, sessao_a)
    nome = titulo_zt("modelo")
    r = sessao_a.post("/api/modelos", json={"nome": nome, "descricao": "modelo de teste", "item_id": app_a["id"]})
    assert r.status_code == 201, r.text
    modelo = r.json()
    assert modelo["escopo"] == "inquilino" and modelo["documentos"] == 2 and modelo["fontes"] == 3
    assert modelo["do_inquilino"] is True and len(modelo["sha256"]) == 64
    # A vê o modelo; B não vê nada dele
    assert nome in [m["nome"] for m in sessao_a.get("/api/modelos").json()]
    assert nome not in [m["nome"] for m in sessao_b.get("/api/modelos").json()]
    assert sessao_b.get(f"/api/modelos/{modelo['id']}/pacote").status_code == 404
    assert sessao_b.delete(f"/api/modelos/{modelo['id']}").status_code == 404
    # o pacote baixado é o mesmo que a exportação direta produz (mesma assinatura)
    r = sessao_a.get(f"/api/modelos/{modelo['id']}/pacote")
    assert r.status_code == 200 and _manifesto(r.content)["sha256_conteudo"] == modelo["sha256"]
    # e serve de origem para uma importação por `modelo_id`, dentro do próprio inquilino
    camadas_a2 = {p: itens_a.criar("camada_vetorial", sessao=sessao_a, dados=_dados_camada(p)) for p in CAMPOS}
    mapeamento = _mapeamento(_manifesto(r.content), camadas_a, camadas_a2)
    r2 = sessao_a.post("/api/pacotes/importar", json={"modelo_id": modelo["id"], "mapeamento": mapeamento})
    assert r2.status_code == 201, r2.text
    itens_a.criados.extend([x["id"] for x in r2.json()["itens"]])
    assert sessao_a.delete(f"/api/modelos/{modelo['id']}").status_code == 204
    assert sessao_a.get(f"/api/modelos/{modelo['id']}/pacote").status_code == 404


def test_escopo_plataforma_exige_superadmin(sessao_a, sessao_plat, itens_a):
    _, _, app_a = _montar_origem(itens_a, sessao_a)
    r = sessao_a.post(
        "/api/modelos", json={"nome": titulo_zt("modelo"), "escopo": "plataforma", "item_id": app_a["id"]}
    )
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio", r.text


def test_entrada_sem_conteudo_nem_modelo_e_recusada(sessao_b):
    r = sessao_b.post("/api/pacotes/verificar", json={"mapeamento": {}})
    assert r.status_code == 422 and r.json()["erro"] == "entrada_invalida", r.text
    r = sessao_b.post("/api/pacotes/verificar", json={"conteudo": "nao-e-base64!!", "mapeamento": {}})
    assert r.status_code == 422 and r.json()["erro"] == "entrada_invalida", r.text
