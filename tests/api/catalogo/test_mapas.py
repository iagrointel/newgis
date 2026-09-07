"""Rotas do mapa (item L2-01-a-documento-mapa): POST/GET/PUT /api/mapas, GET /api/mapas/{id}/completo.

Cobre, cláusula por cláusula, o portão do item: esquema validado no servidor com o caminho do campo no 422;
`/completo` de um mapa com 10 camadas dentro do teto de tempo; referência a camada de outro inquilino = 404 no
salvar; apagar camada usada por mapa = 409 com a lista de mapas; e a bateria da refutação (500 camadas, 5 níveis
de grupo, ciclo de grupo, extensão fora do mundo) — nenhuma delas pode dar 200 nem 500.
"""

import statistics
import time

import pytest

from app.catalogo.documento import gerar_ulid
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-01-a"
COMPLETO_P95_MS_MAX = 150.0


def documento(**corpo) -> dict:
    return {"esquema_versao": 1, "corpo": corpo}


def camada(ref: str, **extra) -> dict:
    return {"id": gerar_ulid(), "ref": ref, **extra}


@pytest.fixture
def camadas_a(itens_a) -> list[str]:
    return [itens_a.criar("camada_vetorial")["id"] for _ in range(10)]


def criar_mapa(sessao, itens_a, **corpo):
    r = sessao.post("/api/mapas", json={"titulo": f"zt mapa {gerar_ulid()[:8]}", "dados": documento(**corpo)})
    if r.status_code == 201:
        itens_a.criados.append(r.json()["id"])
    return r


# ---------------------------------------------------------------- esquema publicado
def test_esquema_do_tipo_mapa_e_o_arquivo_publicado(sessao_a):
    import json
    from pathlib import Path

    r = sessao_a.get("/api/esquemas/mapa")
    assert r.status_code == 200
    do_banco = r.json()
    arquivo = Path(__file__).resolve().parents[3] / "docs" / "esquemas" / "mapa-v1.json"
    assert json.loads(arquivo.read_text(encoding="utf-8")) == do_banco
    assert do_banco["properties"]["corpo"]["properties"]["crs_exibicao"]["const"] == 3857


def test_documento_fora_do_esquema_e_422_com_o_caminho_do_campo(sessao_a):
    r = sessao_a.post(
        "/api/mapas",
        json={"titulo": "zt mapa invalido", "dados": documento(camadas=[{"id": "nao-e-ulid", "ref": "nao-e-uuid"}])},
    )
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "dados_invalidos"
    campos = {d["campo"] for d in j["detalhe"]}
    assert "corpo.camadas.0.id" in campos and "corpo.camadas.0.ref" in campos


def test_crs_de_exibicao_diferente_de_3857_e_recusado(sessao_a):
    r = sessao_a.post("/api/mapas", json={"titulo": "zt mapa crs", "dados": documento(crs_exibicao=4326)})
    assert r.status_code == 422
    assert r.json()["detalhe"][0]["campo"] == "corpo.crs_exibicao"


def test_chave_desconhecida_no_documento_e_recusada(sessao_a):
    r = sessao_a.post("/api/mapas", json={"titulo": "zt mapa extra", "dados": documento(camadaz=[])})
    assert r.status_code == 422 and r.json()["erro"] == "dados_invalidos"


# ---------------------------------------------------------------- ciclo de vida
def test_criar_ler_editar_e_ordem_preservada(sessao_a, itens_a, camadas_a):
    ordem = [camada(c) for c in camadas_a[:3]]
    r = criar_mapa(sessao_a, itens_a, camadas=ordem, extensao_inicial=[-47, -24, -46, -23])
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    lido = sessao_a.get(f"/api/mapas/{mid}")
    assert lido.status_code == 200
    assert [c["ref"] for c in lido.json()["dados"]["corpo"]["camadas"]] == camadas_a[:3]

    invertida = list(reversed(ordem))
    p = sessao_a.put(f"/api/mapas/{mid}", json={"dados": documento(camadas=invertida)})
    assert p.status_code == 200, p.text
    de_novo = sessao_a.get(f"/api/mapas/{mid}").json()["dados"]["corpo"]["camadas"]
    assert [c["ref"] for c in de_novo] == list(reversed(camadas_a[:3]))

    # a ordem também vira posição em plat.item_relacao (é dela que sai a lista de dependentes)
    rel = sessao_a.get(f"/api/itens/{mid}/criado-a-partir-de").json()
    por_posicao = sorted((x for x in rel if x["tipo_relacao"] == "camada_de_mapa"), key=lambda x: x["posicao"])
    assert [x["id"] for x in por_posicao] == list(reversed(camadas_a[:3])), rel


def test_lista_de_mapas_so_traz_mapas(sessao_a, itens_a):
    r = criar_mapa(sessao_a, itens_a)
    assert r.status_code == 201
    itens_a.criar("camada_vetorial")
    lista = sessao_a.get("/api/mapas?limite=50&meus=1")
    assert lista.status_code == 200
    assert {i["tipo"] for i in lista.json()["itens"]} == {"mapa"}


def test_mapa_inexistente_e_item_que_nao_e_mapa_dao_404(sessao_a, itens_a):
    cam = itens_a.criar("camada_vetorial")["id"]
    assert sessao_a.get(f"/api/mapas/{cam}").status_code == 404
    assert sessao_a.get("/api/mapas/11111111-1111-4111-8111-111111111111").status_code == 404
    assert sessao_a.get(f"/api/mapas/{cam}/completo").status_code == 404


# ---------------------------------------------------------------- isolamento entre inquilinos
def test_camada_de_outro_inquilino_e_404_ao_salvar(sessao_a, itens_a, itens_b):
    de_b = itens_b.criar("camada_vetorial")["id"]
    r = criar_mapa(sessao_a, itens_a, camadas=[camada(de_b)])
    assert r.status_code == 404, r.text
    j = r.json()
    assert j["erro"] == "referencia_inexistente"
    assert j["detalhe"][0]["ref"] == de_b and j["detalhe"][0]["campo"] == "corpo.camadas.0.ref"


def test_uuid_inexistente_e_o_mesmo_404_da_camada_de_outro_inquilino(sessao_a, itens_a, itens_b):
    de_b = itens_b.criar("camada_vetorial")["id"]
    inexistente = "99999999-9999-4999-8999-999999999999"
    r1 = criar_mapa(sessao_a, itens_a, camadas=[camada(de_b)])
    r2 = criar_mapa(sessao_a, itens_a, camadas=[camada(inexistente)])
    assert r1.status_code == r2.status_code == 404
    assert r1.json()["erro"] == r2.json()["erro"] == "referencia_inexistente"
    assert r1.json()["mensagem"] == r2.json()["mensagem"]


def test_editar_mapa_com_camada_de_outro_inquilino_e_404(sessao_a, itens_a, itens_b, camadas_a):
    mid = criar_mapa(sessao_a, itens_a, camadas=[camada(camadas_a[0])]).json()["id"]
    de_b = itens_b.criar("camada_vetorial")["id"]
    r = sessao_a.put(f"/api/mapas/{mid}", json={"dados": documento(camadas=[camada(de_b)])})
    assert r.status_code == 404 and r.json()["erro"] == "referencia_inexistente"
    # e o documento gravado continua o de antes
    assert [c["ref"] for c in sessao_a.get(f"/api/mapas/{mid}").json()["dados"]["corpo"]["camadas"]] == [camadas_a[0]]


def test_referencia_para_tipo_incompativel_e_422(sessao_a, itens_a, camadas_a):
    outro_mapa = criar_mapa(sessao_a, itens_a).json()["id"]
    r = criar_mapa(sessao_a, itens_a, camadas=[camada(outro_mapa)])
    assert r.status_code == 422 and r.json()["erro"] == "referencia_de_tipo_invalido"
    r2 = criar_mapa(sessao_a, itens_a, camadas=[camada(camadas_a[0], estilo={"ref": camadas_a[1]})])
    assert r2.status_code == 422 and r2.json()["detalhe"][0]["campo"] == "corpo.camadas.0.estilo.ref"


# ---------------------------------------------------------------- dependência (L0-03-i)
def test_apagar_camada_usada_por_mapa_da_409_com_a_lista_de_mapas(sessao_a, itens_a, camadas_a):
    m1 = criar_mapa(sessao_a, itens_a, camadas=[camada(camadas_a[0])]).json()
    m2 = criar_mapa(sessao_a, itens_a, camadas=[camada(camadas_a[0])]).json()
    r = sessao_a.delete(f"/api/itens/{camadas_a[0]}")
    assert r.status_code == 409, r.text
    j = r.json()
    assert j["erro"] == "possui_dependentes"
    dependentes = {x["id"] for x in j["detalhe"]["ordem"]}
    assert {m1["id"], m2["id"]} <= dependentes
    assert {x["titulo"] for x in j["detalhe"]["ordem"] if x["id"] == m1["id"]} == {m1["titulo"]}


def test_apagar_estilo_usado_por_mapa_da_409(sessao_a, itens_a, camadas_a):
    estilo = itens_a.criar("estilo")["id"]
    mapa = criar_mapa(sessao_a, itens_a, camadas=[camada(camadas_a[0], estilo={"ref": estilo})]).json()
    r = sessao_a.delete(f"/api/itens/{estilo}")
    assert r.status_code == 409
    assert mapa["id"] in {x["id"] for x in r.json()["detalhe"]["ordem"]}


# ---------------------------------------------------------------- /completo
def test_completo_resolve_camadas_estilo_e_campos(sessao_a, itens_a, camadas_a, conexao_plat_app):
    # item L2-02-a-modelo-estilo: o corpo de um item `estilo` é sempre {plat_construtor, maplibre}; o
    # servidor recompila `maplibre` a partir do construtor na gravação (app/estilos/validador.py), então
    # o que este teste confere aqui é o que fica gravado de fato, não o que foi mandado no POST.
    from app.estilos import compilador

    pc = {"tipo": "unico", "geometria": "poligono", "versao": 1, "simbolo": {"cor": "#4e79a7"}}
    maplibre_canonico = compilador.compilar(pc)
    estilo = itens_a.criar(
        "estilo",
        dados={"esquema_versao": 1, "corpo": {"plat_construtor": pc, "maplibre": maplibre_canonico}},
    )
    c = camada(camadas_a[0], estilo={"ref": estilo["id"]}, opacidade=0.5, visivel=False)
    mid = criar_mapa(sessao_a, itens_a, camadas=[c], mapa_base={"id": "osm-guarulhos"}).json()["id"]

    r = sessao_a.get(f"/api/mapas/{mid}/completo")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["crs_exibicao"] == 3857 and j["mapa_base"]["id"] == "osm-guarulhos"
    (saida,) = j["camadas"]
    assert saida["ref"] == camadas_a[0] and saida["tipo"] == "camada_vetorial"
    assert saida["opacidade"] == 0.5 and saida["visivel"] is False
    assert saida["estilo"]["origem"] == "item"
    assert saida["estilo"]["corpo"]["plat_construtor"] == pc
    assert saida["estilo"]["corpo"]["maplibre"] == maplibre_canonico
    assert saida["tiles"]["pronto"] is False  # nenhum servidor de tiles instalado nesta máquina
    assert saida["dominios"] == {}

    # confere contra o banco, sem passar pela API (o que o adversário faz)
    tid = ids_por_slug(conexao_plat_app)["demo"]
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        admin_id = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, tid, usuario_id=admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT titulo, dados FROM plat.item WHERE id = %s::uuid", (camadas_a[0],))
        linha = cur.fetchone()
    assert saida["titulo"] == linha["titulo"]
    assert saida["campos"] == linha["dados"]["campos"]
    assert saida["srid"] == linha["dados"]["srid"] and saida["geometria"] == linha["dados"]["geometria"]


def test_completo_traz_grupos_favoritos_e_documento_opcional(sessao_a, itens_a, camadas_a):
    g = gerar_ulid()
    c = camada(camadas_a[0], grupo=g)
    mid = criar_mapa(
        sessao_a,
        itens_a,
        camadas=[c],
        grupos=[{"id": g, "titulo": "base"}],
        favoritos=[{"nome": "cidade", "extensao": [-47, -24, -46, -23], "camadas_visiveis": [c["id"]]}],
    ).json()["id"]
    j = sessao_a.get(f"/api/mapas/{mid}/completo?incluir_documento=true").json()
    assert j["grupos"][0]["titulo"] == "base" and j["favoritos"][0]["nome"] == "cidade"
    assert j["camadas"][0]["grupo"] == g
    assert j["documento"]["corpo"]["camadas"][0]["id"] == c["id"]


def test_completo_de_mapa_com_10_camadas_p95(sessao_a, itens_a, camadas_a, medida):
    mid = criar_mapa(sessao_a, itens_a, camadas=[camada(c) for c in camadas_a]).json()["id"]
    assert len(sessao_a.get(f"/api/mapas/{mid}/completo").json()["camadas"]) == 10
    tempos = []
    for _ in range(50):
        t0 = time.perf_counter()
        r = sessao_a.get(f"/api/mapas/{mid}/completo")
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    p95 = statistics.quantiles(tempos, n=20)[18]
    medida(ITEM)(
        "completo_10_camadas_p95_ms",
        round(p95, 1),
        "ms",
        "venv/bin/pytest tests/api/catalogo/test_mapas.py::test_completo_de_mapa_com_10_camadas_p95",
    )
    medida(ITEM)("completo_10_camadas_mediana_ms", round(statistics.median(tempos), 1), "ms", "idem")
    medida(ITEM)("completo_10_camadas_chamadas", len(tempos), "chamadas", "idem")
    assert p95 <= COMPLETO_P95_MS_MAX, (p95, max(tempos))


# ---------------------------------------------------------------- refutação
def test_quinhentas_camadas_sao_recusadas(sessao_a, itens_a, camadas_a):
    muitas = [camada(camadas_a[i % len(camadas_a)]) for i in range(500)]
    r = criar_mapa(sessao_a, itens_a, camadas=muitas)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "dados_invalidos"


def test_cinco_niveis_de_grupo_sao_recusados(sessao_a, itens_a):
    ids = [gerar_ulid() for _ in range(5)]
    grupos = [{"id": ids[0], "titulo": "1"}] + [
        {"id": ids[i], "titulo": str(i + 1), "pai": ids[i - 1]} for i in range(1, 5)
    ]
    r = criar_mapa(sessao_a, itens_a, grupos=grupos)
    assert r.status_code == 422
    assert {d["regra"] for d in r.json()["detalhe"]} == {"grupo_profundo"}


def test_ciclo_de_grupo_e_recusado_sem_travar(sessao_a, itens_a):
    a, b = gerar_ulid(), gerar_ulid()
    grupos = [{"id": a, "titulo": "a", "pai": b}, {"id": b, "titulo": "b", "pai": a}]
    r = criar_mapa(sessao_a, itens_a, grupos=grupos)
    assert r.status_code == 422
    assert "grupo_ciclo" in {d["regra"] for d in r.json()["detalhe"]}


@pytest.mark.parametrize(
    "extensao", [[-200, -24, -46, -23], [-47, -100, -46, -23], [-47, -24, 200, -23], [-47, -24, -46, 100]]
)
def test_extensao_fora_do_mundo_e_recusada(sessao_a, itens_a, extensao):
    r = criar_mapa(sessao_a, itens_a, extensao_inicial=extensao)
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "dados_invalidos"


def test_extensao_invertida_e_recusada(sessao_a, itens_a):
    r = criar_mapa(sessao_a, itens_a, extensao_inicial=[-46, -23, -47, -24])
    assert r.status_code == 422 and r.json()["erro"] == "documento_incoerente"


def test_opacidade_e_rotacao_fora_da_faixa_sao_recusadas(sessao_a, itens_a, camadas_a):
    assert criar_mapa(sessao_a, itens_a, camadas=[camada(camadas_a[0], opacidade=2)]).status_code == 422
    assert criar_mapa(sessao_a, itens_a, rotacao=999).status_code == 422
