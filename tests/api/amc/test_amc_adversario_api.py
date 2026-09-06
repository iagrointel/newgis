"""Ataque independente ao motor multicritério (itens L3-01-a e L3-01-b) pela API e pelo banco.

Escrito por um agente que NÃO construiu o motor, sobre um schema de trilha próprio (PLAT_SCHEMA), sem disputar o
banco com as outras trilhas. Regra: cada teste ou prova que o produto se defende, ou expõe um defeito; os que
expõem defeito ficam `xfail(strict=True)` para virarem prova no dia do conserto.

Frentes:
1. imutabilidade do modelo já executado (rota de atualização, rota parcial, reordenação de chaves, escrita direta
   na tabela com a role da aplicação);
2. vazamento entre inquilinos nas 18 rotas de /api/amc (todas, não só as de id direto), por id de caminho, por
   parâmetro de consulta, por corpo e pelo id do conjunto de unidades;
3. a grade conferida por shapely/pyproj, com buraco, multipolígono, auto-interseção, antimeridiano e área ~0;
4. a extrapolação declarada: o campo está marcado e a reta se sustenta em dois pontos medidos.
"""

import json
import math
import time

import psycopg2
import pyproj
import pytest
from shapely.geometry import shape
from shapely.ops import transform

from app.amc import unidades as mod_unidades
from app.settings import settings
from tests.api.amc import exemplos
from tests.api.amc.test_unidades import ContextoDeTeste

ESQ = settings.PLAT_SCHEMA
PREFIXO = "zt-amcadv"
MARCA_UNIDADE = "marca-de-B-9f3c1a7e"  # id de unidade improvável de aparecer por acaso num hash
GEOD = pyproj.Geod(ellps="GRS80")


def ids_por_slug(con):
    """Como tests/api/test_rls.ids_por_slug, mas honrando PLAT_SCHEMA."""
    ids = {}
    with con.cursor() as cur:
        for slug in ("demo", "demo2"):
            cur.execute(f"SELECT tenant_id FROM {ESQ}.auth_login(%s, 'admin')", (slug,))
            r = cur.fetchone()
            assert r is not None, f"admin de {slug} não semeado"
            ids[slug] = r["tenant_id"]
    return ids


def contexto(con, tenant_id, usuario_id=0):
    """Como tests/api/test_rls.contexto, mas honrando PLAT_SCHEMA (o helper do repositório fixa 'plat')."""
    with con.cursor() as cur:
        cur.execute(f"SET search_path = {ESQ}, public")
        cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                    "set_config('plat.login', 'adversario', true)", (str(tenant_id), str(usuario_id)))


def criar_item(sessao, titulo: str) -> str:
    r = sessao.post("/api/itens", json={"tipo": "mapa", "titulo": f"{PREFIXO} {titulo}",
                                        "dados": {"esquema_versao": 1, "corpo": {}}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def modelo_com_itens(sessao) -> dict:
    m = exemplos.modelo_valido()
    m["nome"] = f"{PREFIXO} modelo"
    m["fatores"][0]["camada"]["id"] = criar_item(sessao, "raster")
    m["fatores"][1]["camada"]["id"] = criar_item(sessao, "vias")
    m["restricoes"][0]["camada"]["id"] = criar_item(sessao, "alagavel")
    return m


def conjunto_pronto(sessao, con, marca: str) -> dict:
    """Conjunto de grade pequeno, já gerado (o worker não conhece o tipo de job antes do merge, então a função do
    job é chamada direto — mesma escolha do construtor). Grade, e não feições, porque o caminho de feições está
    quebrado fora do schema `plat` (ver test_adv_conjunto_de_feicoes_funciona_em_qualquer_schema)."""
    r = sessao.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} conjunto {marca}", "tipo": "quadrada",
                                                "lado_m": 500.0,
                                                "area_estudo": exemplos.area_retangulo(-49.30, -16.70, 0.01, 0.01)})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    mod_unidades.gerar_grade(ContextoDeTeste(ids_por_slug(con)["demo" if marca == "a" else "demo2"]),
                             conjunto["id"])
    return sessao.get(f"/api/amc/conjuntos/{conjunto['id']}").json()


@pytest.fixture
def cenario_a(sessao_a, conexao_plat_app):
    """Modelo + conjunto + execução em A, apagados no fim."""
    definicao = modelo_com_itens(sessao_a)
    r = sessao_a.post("/api/amc/modelos", json={"definicao": definicao})
    assert r.status_code == 201, r.text
    modelo = r.json()
    conjunto = conjunto_pronto(sessao_a, conexao_plat_app, "a")
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": modelo["id"], "conjunto_id": conjunto["id"],
                                                  "semente": 11})
    assert r.status_code == 201, r.text
    execucao = r.json()
    yield {"definicao": definicao, "modelo": modelo, "conjunto": conjunto, "execucao": execucao}
    sessao_a.delete(f"/api/amc/execucoes/{execucao['id']}")
    sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
    sessao_a.delete(f"/api/amc/modelos/{modelo['id']}")


# ================================================================ 1. imutabilidade do modelo já executado
def test_adv_modelo_executado_nao_se_altera_por_nenhuma_via(sessao_a, conexao_plat_app, cenario_a):
    """O portão do item. Grava resultados na execução e tenta mudar a definição que rodou por seis vias:
    PUT (rota legítima, que tem de criar versão NOVA), PATCH/POST parciais, reordenação de chaves do JSON,
    UPDATE e DELETE diretos na tabela de versões com a role da aplicação, e UPDATE direto na execução."""
    modelo, definicao, execucao = cenario_a["modelo"], cenario_a["definicao"], cenario_a["execucao"]
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"INSERT INTO {ESQ}.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, cobertura) "
                    "VALUES (%s::uuid, %s, 'a1', 61.5, 1.0)", (execucao["id"], ids["demo"]))
    conexao_plat_app.commit()
    try:
        antes = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/resultados").json()["resultados"]

        # (a) reordenar as chaves do JSON não cria versão: o hash é do JSON canônico
        embaralhado = json.loads(json.dumps({k: definicao[k] for k in reversed(list(definicao))}))
        r = sessao_a.put(f"/api/amc/modelos/{modelo['id']}", json={"definicao": embaralhado})
        assert r.status_code == 200 and r.json()["versao_nova"] is False, r.text
        assert r.json()["versao_hash"] == modelo["versao_hash"]

        # (b) não existe rota parcial: PATCH e POST no recurso do modelo não existem
        assert sessao_a.patch(f"/api/amc/modelos/{modelo['id']}", json={"definicao": definicao}).status_code == 405
        assert sessao_a.post(f"/api/amc/modelos/{modelo['id']}", json={"definicao": definicao}).status_code == 405

        # (c) escrita direta na tabela de versões com a role da aplicação: barrada pelo gatilho
        contexto(conexao_plat_app, ids["demo"])
        for sql in (f"UPDATE {ESQ}.amc_modelo_versao SET definicao = '{{}}'::jsonb WHERE modelo_id = %s::uuid",
                    f"DELETE FROM {ESQ}.amc_modelo_versao WHERE modelo_id = %s::uuid"):
            with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.Error) as e:
                cur.execute(sql, (modelo["id"],))
            assert "amc_versao_imutavel" in str(e.value)
            conexao_plat_app.rollback()
            contexto(conexao_plat_app, ids["demo"])

        # (d) e a proveniência da execução também: mudar a versão que rodou é barrado
        with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.Error) as e:
            cur.execute(f"UPDATE {ESQ}.amc_execucao SET versao_hash = %s WHERE id = %s::uuid",
                        ("0" * 64, execucao["id"]))
        assert "amc_execucao_proveniencia_imutavel" in str(e.value)
        conexao_plat_app.rollback()
        contexto(conexao_plat_app, ids["demo"])
        with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.Error) as e:
            cur.execute(f"UPDATE {ESQ}.amc_resultado SET favorabilidade = 100 WHERE execucao_id = %s::uuid",
                        (execucao["id"],))
        assert "amc_resultado_imutavel" in str(e.value)
        conexao_plat_app.rollback()

        # (e) a edição legítima cria versão nova e NÃO move a execução
        nova = json.loads(json.dumps(definicao))
        nova["fatores"][0]["peso"] = 42.0
        nova["fatores"][0]["transformacao"] = {"tipo": "linear", "minimo": 0, "maximo": 9, "direcao": "crescente"}
        r = sessao_a.put(f"/api/amc/modelos/{modelo['id']}", json={"definicao": nova})
        assert r.status_code == 200 and r.json()["versao_nova"] is True, r.text

        agora = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}").json()
        assert agora["versao_hash"] == execucao["versao_hash"]
        assert agora["definicao"] == definicao
        assert agora["pesos"] == execucao["pesos"] and agora["motor_versao"] == execucao["motor_versao"]
        depois = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/resultados").json()["resultados"]
        assert depois == antes
        # a versão antiga continua legível e íntegra
        v = sessao_a.get(f"/api/amc/modelos/{modelo['id']}/versoes/{execucao['versao_hash']}").json()
        assert v["definicao"] == definicao
    finally:
        contexto(conexao_plat_app, ids["demo"])
        with conexao_plat_app.cursor() as cur:
            cur.execute(f"DELETE FROM {ESQ}.amc_resultado WHERE execucao_id = %s::uuid", (execucao["id"],))
        conexao_plat_app.commit()


def _hash_por_fora(definicao) -> str:
    """A regra do hash escrita de novo aqui, sem importar app.amc.esquema nem scripts/amc_hash_independente.py."""
    import hashlib

    texto = json.dumps(definicao, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def test_adv_hash_gravado_confere_com_recomputo_independente(sessao_a, conexao_plat_app, cenario_a):
    modelo = cenario_a["modelo"]
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"SELECT versao_hash, definicao FROM {ESQ}.amc_modelo_versao WHERE modelo_id = %s::uuid",
                    (modelo["id"],))
        linhas = cur.fetchall()
    conexao_plat_app.rollback()
    assert linhas
    for v in linhas:
        assert _hash_por_fora(v["definicao"]) == v["versao_hash"]


def test_adv_versao_forjada_no_banco_e_aceita_pelo_banco_mas_denunciada_pelo_recomputo(
        sessao_a, conexao_plat_app, cenario_a):
    """Fronteira honesta: NÃO há restrição no banco ligando `versao_hash` a sha256(`definicao`). A role da
    aplicação consegue INSERIR uma versão com hash que não corresponde à definição (o gatilho só barra UPDATE e
    DELETE). O que sustenta a proveniência é o recomputo por fora — este teste prova as duas coisas."""
    modelo = cenario_a["modelo"]
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    forjado = "f" * 64
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"INSERT INTO {ESQ}.amc_modelo_versao(modelo_id, versao_hash, tenant_id, numero, definicao) "
                    "VALUES (%s::uuid, %s, %s, 900, %s::jsonb)",
                    (modelo["id"], forjado, ids["demo"], json.dumps({"esquema": "amc_modelo.v1", "mentira": True})))
        cur.execute(f"SELECT definicao FROM {ESQ}.amc_modelo_versao WHERE modelo_id = %s::uuid AND versao_hash = %s",
                    (modelo["id"], forjado))
        gravada = cur.fetchone()["definicao"]
    assert _hash_por_fora(gravada) != forjado, "o banco recusou a versão forjada (então há restrição)"
    conexao_plat_app.rollback()


# ================================================================ 2. vazamento entre inquilinos: 18 rotas
def _rotas_amc() -> list[tuple[str, str]]:
    from tests.api.conftest import arquivo_openapi

    doc = arquivo_openapi()
    return sorted((m.upper(), p) for p, v in doc["paths"].items() if p.startswith("/api/amc") for m in v)


def test_adv_as_18_rotas_de_amc_estao_todas_cobertas_por_este_ataque():
    assert len(_rotas_amc()) == 18, _rotas_amc()


def test_adv_nenhuma_das_18_rotas_entrega_dado_de_outro_inquilino(sessao_a, sessao_b, conexao_plat_app):
    """A de B, lida por A: id no caminho, id no corpo, id no parâmetro de consulta e id do CONJUNTO de unidades.
    Qualquer 200 que carregue identificador de B é vazamento."""
    definicao_b = modelo_com_itens(sessao_b)
    r = sessao_b.post("/api/amc/modelos", json={"definicao": definicao_b})
    assert r.status_code == 201, r.text
    modelo_b = r.json()
    conjunto_b = conjunto_pronto(sessao_b, conexao_plat_app, "b")
    r = sessao_b.post("/api/amc/execucoes", json={"modelo_id": modelo_b["id"], "conjunto_id": conjunto_b["id"]})
    assert r.status_code == 201, r.text
    execucao_b = r.json()
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo2"])
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"INSERT INTO {ESQ}.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade) "
                    "VALUES (%s::uuid, %s, %s, 88.0)", (execucao_b["id"], ids["demo2"], MARCA_UNIDADE))
    conexao_plat_app.commit()

    mid, cid, eid, vh = modelo_b["id"], conjunto_b["id"], execucao_b["id"], modelo_b["versao_hash"]
    # marcas longas de propósito: "b1" apareceria por acaso dentro de qualquer sha256
    marcas = {mid, cid, eid, MARCA_UNIDADE}
    # o hash da versão e o id do item de B são função do DOCUMENTO que A mandou (A escreve o que quiser no
    # próprio modelo), então nas duas rotas que ECOAM o documento eles não são vazamento. O que importaria —
    # A conseguir RESOLVER a camada de B — é conferido logo abaixo com POST /api/amc/execucoes.
    ecoados = {vh, definicao_b["fatores"][0]["camada"]["id"]}
    ecoam = {("POST", "/api/amc/modelos"), ("POST", "/api/amc/modelos/validar")}
    # (método, caminho do openapi, url concreta, corpo)
    sondas = [
        ("GET", "/api/amc/modelos", "/api/amc/modelos?limite=200", None),
        ("POST", "/api/amc/modelos", "/api/amc/modelos", {"definicao": definicao_b}),
        ("POST", "/api/amc/modelos/validar", "/api/amc/modelos/validar", {"definicao": definicao_b}),
        ("GET", "/api/amc/modelos/{modelo_id}", f"/api/amc/modelos/{mid}", None),
        ("PUT", "/api/amc/modelos/{modelo_id}", f"/api/amc/modelos/{mid}", {"definicao": definicao_b}),
        ("DELETE", "/api/amc/modelos/{modelo_id}", f"/api/amc/modelos/{mid}", None),
        ("GET", "/api/amc/modelos/{modelo_id}/versoes", f"/api/amc/modelos/{mid}/versoes", None),
        ("GET", "/api/amc/modelos/{modelo_id}/versoes/{versao_hash}", f"/api/amc/modelos/{mid}/versoes/{vh}", None),
        ("GET", "/api/amc/conjuntos", "/api/amc/conjuntos?limite=200", None),
        ("POST", "/api/amc/conjuntos", "/api/amc/conjuntos",
         {"nome": f"{PREFIXO} sonda", "tipo": "feicoes", "feicoes": {"type": "FeatureCollection", "features": []}}),
        ("GET", "/api/amc/conjuntos/{conjunto_id}", f"/api/amc/conjuntos/{cid}", None),
        ("GET", "/api/amc/conjuntos/{conjunto_id}/unidades", f"/api/amc/conjuntos/{cid}/unidades?limite=5000", None),
        ("DELETE", "/api/amc/conjuntos/{conjunto_id}", f"/api/amc/conjuntos/{cid}", None),
        ("GET", "/api/amc/execucoes", f"/api/amc/execucoes?modelo_id={mid}&limite=200", None),
        ("POST", "/api/amc/execucoes", "/api/amc/execucoes", {"modelo_id": mid, "conjunto_id": cid}),
        ("GET", "/api/amc/execucoes/{execucao_id}", f"/api/amc/execucoes/{eid}", None),
        ("GET", "/api/amc/execucoes/{execucao_id}/resultados", f"/api/amc/execucoes/{eid}/resultados", None),
        ("DELETE", "/api/amc/execucoes/{execucao_id}", f"/api/amc/execucoes/{eid}", None),
    ]
    assert sorted((m, p) for m, p, _u, _c in sondas) == _rotas_amc(), "sonda não cobre as 18 rotas"
    criados = []
    try:
        for metodo, _padrao, url, corpo in sondas:
            resposta = sessao_a.request(metodo, url, json=corpo)
            texto = resposta.text
            alvos = marcas if (metodo, _padrao) in ecoam else marcas | ecoados
            for marca in alvos:
                assert marca not in texto, (metodo, url, marca, texto[:300])
            if resposta.status_code == 201 and metodo == "POST" and "/modelos" in url:
                criados.append(("/api/amc/modelos", resposta.json()["id"]))
            if resposta.status_code == 201 and metodo == "POST" and url.endswith("/conjuntos"):
                criados.append(("/api/amc/conjuntos", resposta.json()["id"]))
        # A copiou o documento de B (ele foi ecoado); mesmo assim não consegue RESOLVER as camadas de B
        r = sessao_a.post("/api/amc/modelos", json={"definicao": definicao_b})
        assert r.status_code == 201, r.text
        copia = r.json()["id"]
        criados.append(("/api/amc/modelos", copia))
        conjunto_a = conjunto_pronto(sessao_a, conexao_plat_app, "a")
        criados.append(("/api/amc/conjuntos", conjunto_a["id"]))
        r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": copia, "conjunto_id": conjunto_a["id"]})
        assert r.status_code == 422 and r.json()["erro"] == "camada_inexistente", r.text

        # o que era de B continua intacto e visível SÓ para B
        assert sessao_b.get(f"/api/amc/modelos/{mid}").status_code == 200
        assert sessao_b.get(f"/api/amc/execucoes/{eid}").json()["versao_hash"] == execucao_b["versao_hash"]
        # e A não vê nada de B nas listagens
        for rota, chave in (("/api/amc/modelos?limite=200", "modelos"), ("/api/amc/conjuntos?limite=200", "conjuntos"),
                            ("/api/amc/execucoes?limite=200", "execucoes")):
            assert not [x for x in sessao_a.get(rota).json()[chave] if x["id"] in marcas]
    finally:
        for rota, ident in criados:
            sessao_a.delete(f"{rota}/{ident}")
        contexto(conexao_plat_app, ids["demo2"])
        with conexao_plat_app.cursor() as cur:
            cur.execute(f"DELETE FROM {ESQ}.amc_resultado WHERE execucao_id = %s::uuid", (eid,))
        conexao_plat_app.commit()
        sessao_b.delete(f"/api/amc/execucoes/{eid}")
        sessao_b.delete(f"/api/amc/conjuntos/{cid}")
        sessao_b.delete(f"/api/amc/modelos/{mid}")


# ================================================================ 3. validação pela API (corpo cru)
def _bruto(sessao, rota, texto):
    return sessao.post(rota, content=texto, headers={"content-type": "application/json"})


def test_adv_nan_e_corpo_gigante_dao_422_e_413_nunca_500(sessao_a):
    m = exemplos.modelo_valido()
    r = _bruto(sessao_a, "/api/amc/modelos/validar",
               json.dumps({"definicao": m}).replace('"peso": 3.0', '"peso": NaN', 1))
    assert r.status_code == 422 and r.json()["erro"] == "modelo_invalido", r.text
    grande = json.loads(json.dumps(m))
    grande["fatores"][0]["extrator"]["parametros"] = {"lixo": ["y" * 1000] * 11000}
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": grande})
    assert r.status_code == 413 and r.json()["erro"] == "corpo_grande", r.text


# CONSERTADO em 06/09/2026 (achado 5 do laudo): as três rotas de modelo passam por
# app.amc.rotas.corpo_json_sem_chave_repetida e devolvem 422 `json_ambiguo`. Era: "chave repetida no JSON cru é
# aceita em silêncio — a primeira ocorrência é descartada pelo parser e o modelo é gravado com a última; quem
# enviou não sabe qual das duas valeu". A marca xfail(strict) saiu.
def test_adv_chave_repetida_no_corpo_cru_deveria_ser_recusada(sessao_a):
    texto = json.dumps({"definicao": exemplos.modelo_valido()}, ensure_ascii=False)
    alvo = '"nome": "modelo de teste interno"'
    r = _bruto(sessao_a, "/api/amc/modelos/validar", texto.replace(alvo, '"nome": "MODELO FALSO", ' + alvo, 1))
    assert r.status_code == 422, r.text


# CONSERTADO em 06/09/2026 (achado 2 do laudo). Era: "transformação linear com mínimo maior que o máximo entra
# no modelo, no hash e na execução sem uma violação". A marca xfail(strict) saiu.
def test_adv_transformacao_invertida_deveria_ser_recusada_pela_api(sessao_a):
    m = exemplos.modelo_valido()
    m["fatores"][0]["transformacao"] = {"tipo": "linear", "minimo": 30, "maximo": 0, "direcao": "crescente"}
    assert sessao_a.post("/api/amc/modelos/validar", json={"definicao": m}).status_code == 422


# ================================================================ 4. a grade, conferida por fora
def _area_plano_m2(geojson: dict, srid: int) -> float:
    t = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{srid}", always_xy=True)
    return transform(t.transform, shape(geojson)).area


def _area_geodesica_m2(geojson: dict) -> float:
    """Área geodésica com buraco descontado. `Geod.geometry_area_perimeter` SOMA o valor absoluto dos anéis
    internos (conferido: polígono com buraco dá exterior + buraco), então os anéis são somados um a um."""
    def _do_poligono(pol) -> float:
        fora = abs(GEOD.polygon_area_perimeter(*zip(*pol.exterior.coords, strict=True))[0])
        for anel in pol.interiors:
            fora -= abs(GEOD.polygon_area_perimeter(*zip(*anel.coords, strict=True))[0])
        return fora

    g = shape(geojson)
    return sum(_do_poligono(p) for p in (g.geoms if g.geom_type == "MultiPolygon" else [g]))


def _gerar(sessao_a, conexao_plat_app, nome, tipo, lado_m, area) -> tuple[dict, float]:
    ids = ids_por_slug(conexao_plat_app)
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} {nome}", "tipo": tipo, "lado_m": lado_m,
                                                  "area_estudo": area})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    assert conjunto["estado"] == "pendente" and conjunto["job_id"]
    t0 = time.monotonic()
    mod_unidades.gerar_grade(ContextoDeTeste(ids["demo"]), conjunto["id"])
    segundos = time.monotonic() - t0
    return sessao_a.get(f"/api/amc/conjuntos/{conjunto['id']}").json(), segundos


@pytest.mark.lento
def test_adv_grade_250m_recontada_por_shapely_e_pyproj(sessao_a, conexao_plat_app):
    """A cláusula do portão, refeita do zero: 250 m sobre ~2.000 km², contagem e área conferidas fora do banco."""
    area = exemplos.area_retangulo(-49.5, -16.9, 0.42, 0.42)
    conjunto, segundos = _gerar(sessao_a, conexao_plat_app, "grade250", "quadrada", 250.0, area)
    try:
        ficha = conjunto["ficha"]
        srid = ficha["srid_trabalho"]
        area_plano = _area_plano_m2(area, srid)
        esperado = area_plano / (250.0 * 250.0)
        desvio = (conjunto["n_unidades"] - esperado) / esperado * 100.0
        area_geo = _area_geodesica_m2(area)
        print(f"\n[adversario] 250 m · {conjunto['n_unidades']} células · {segundos:.2f} s · esperado "
              f"{esperado:,.0f} · desvio {desvio:+.3f} % · área plano {area_plano:,.0f} m² · geodésica "
              f"{area_geo:,.0f} m² · soma das células {conjunto['area_total_m2']:,.0f} m²")
        assert abs(desvio) <= 2.0, desvio
        assert segundos <= 60.0, segundos
        # a soma das áreas geodésicas das células reproduz a área geodésica da região (nada perdido nem duplicado)
        assert abs(conjunto["area_total_m2"] - area_geo) / area_geo <= 0.005
        # e a área do plano NÃO é a geodésica: a distorção declarada na ficha explica a diferença
        distorcao_medida = (area_plano - area_geo) / area_geo * 100.0
        assert ficha["distorcao_area_min_pct"] - 0.02 <= distorcao_medida <= ficha["distorcao_area_max_pct"] + 0.02, (
            distorcao_medida, ficha["distorcao_area_min_pct"], ficha["distorcao_area_max_pct"])
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


@pytest.mark.lento
def test_adv_extrapolacao_do_milhao_esta_marcada_e_a_reta_se_sustenta(sessao_a, conexao_plat_app):
    """O construtor NÃO gerou 1 milhão de células: mediu 250.986 e extrapolou. Aqui: (a) o campo do arquivo de
    medidas tem de dizer que é extrapolado, (b) nenhum documento pode apresentar o número como medido, e (c) a
    projeção linear tem de se sustentar — dois pontos medidos por mim, com o custo por célula comparado."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    medidas = json.loads((raiz / "tests" / "medidas" / "L3-01-b.json").read_text(encoding="utf-8"))["medidas"]
    extrapolados = [k for k in medidas if k.endswith("EXTRAPOLADO")]
    assert extrapolados, "nenhum campo marcado como extrapolado"
    for k in extrapolados:
        assert "extrapola" in medidas[k]["unidade"].lower() and "NÃO medido" in medidas[k]["unidade"]
    for texto in ((raiz / "CHANGELOG.md").read_text(encoding="utf-8"),
                  (raiz / "docs" / "adr" / "0016-motor-amc-modelo-e-unidades.md").read_text(encoding="utf-8")):
        if "34,3" in texto or "34.3" in texto:
            assert "NÃO foi gerado" in texto or "não foi gerado" in texto or "projeção" in texto

    area = exemplos.area_retangulo(-49.5, -16.9, 0.42, 0.42)
    pontos = []
    for nome, lado in (("reta500", 500.0), ("reta250", 250.0)):
        conjunto, segundos = _gerar(sessao_a, conexao_plat_app, nome, "quadrada", lado, area)
        pontos.append((conjunto["n_unidades"], segundos, conjunto["id"]))
        print(f"\n[adversario] lado {lado:g} m · {conjunto['n_unidades']} células · {segundos:.2f} s · "
              f"{segundos / conjunto['n_unidades'] * 1e6:.1f} µs/célula")
    try:
        (n1, s1, _), (n2, s2, _) = pontos
        us1, us2 = s1 / n1 * 1e6, s2 / n2 * 1e6
        razao = max(us1, us2) / min(us1, us2)
        assert n2 > 3 * n1, (n1, n2)
        assert razao <= 4.0, (f"o custo por célula muda {razao:.2f}× entre {n1} e {n2} células: a extrapolação "
                              f"linear para 1 milhão não é sustentada por estes dois pontos", us1, us2)
    finally:
        for _n, _s, cid in pontos:
            sessao_a.delete(f"/api/amc/conjuntos/{cid}")


def test_adv_grade_com_buraco_e_multipoligono_desconta_a_area(sessao_a, conexao_plat_app):
    """Polígono com buraco e MultiPolygon: a contagem tem de acompanhar a área REAL, não a do anel externo."""
    externo = [[-49.50, -16.90], [-49.40, -16.90], [-49.40, -16.80], [-49.50, -16.80], [-49.50, -16.90]]
    buraco = [[-49.47, -16.87], [-49.43, -16.87], [-49.43, -16.83], [-49.47, -16.83], [-49.47, -16.87]]
    com_buraco = {"type": "Polygon", "coordinates": [externo, buraco]}
    multi = {"type": "MultiPolygon", "coordinates": [
        [[[-49.50, -16.90], [-49.46, -16.90], [-49.46, -16.86], [-49.50, -16.86], [-49.50, -16.90]]],
        [[[-49.44, -16.84], [-49.40, -16.84], [-49.40, -16.80], [-49.44, -16.80], [-49.44, -16.84]]]]}
    for nome, geom in (("buraco", com_buraco), ("multi", multi)):
        conjunto, _s = _gerar(sessao_a, conexao_plat_app, nome, "quadrada", 500.0, geom)
        try:
            srid = conjunto["ficha"]["srid_trabalho"]
            t = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{srid}", always_xy=True)
            no_plano = transform(t.transform, shape(geom))
            esperado = no_plano.area / (500.0 * 500.0)
            borda = no_plano.length / 500.0  # células que a borda corta e que entram recortadas
            desvio = (conjunto["n_unidades"] - esperado) / esperado * 100.0
            print(f"\n[adversario] {nome}: {conjunto['n_unidades']} células · esperado {esperado:,.1f} · "
                  f"faixa honesta [{esperado:,.0f}, {esperado + borda:,.0f}] · desvio {desvio:+.2f} %")
            assert esperado - 1 <= conjunto["n_unidades"] <= esperado + borda + 1, (nome, conjunto["n_unidades"])
            geo = _area_geodesica_m2(geom)
            assert abs(conjunto["area_total_m2"] - geo) / geo <= 0.01, nome
        finally:
            sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


def test_adv_geometria_invalida_antimeridiano_e_area_quase_zero(sessao_a):
    """Nenhum destes pode virar 500 nem conjunto silenciosamente errado."""
    # (a) auto-interseção (gravata): ST_MakeValid dá duas partes; a área tem de ser a das duas
    gravata = {"type": "Polygon", "coordinates": [[[-49.50, -16.90], [-49.40, -16.80], [-49.40, -16.90],
                                                   [-49.50, -16.80], [-49.50, -16.90]]]}
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} gravata", "tipo": "quadrada", "lado_m": 500.0,
                                                  "area_estudo": gravata})
    assert r.status_code in (201, 422), r.text
    if r.status_code == 201:
        conjunto = r.json()
        assert conjunto["ficha"]["area_estudo_geodesica_m2"] > 0
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
    # (b) antimeridiano: fora da cobertura SIRGAS 2000, tem de recusar em vez de escolher um CRS qualquer
    anti = {"type": "Polygon", "coordinates": [[[179.9, -16.9], [-179.9, -16.9], [-179.9, -16.8], [179.9, -16.8],
                                                [179.9, -16.9]]]}
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} anti", "tipo": "quadrada", "lado_m": 500.0,
                                                  "area_estudo": anti})
    assert r.status_code == 422 and r.json()["erro"] == "crs_fora_da_cobertura", (r.status_code, r.text)
    # (c) área quase zero: ~1 m² com célula de 500 m
    minusculo = exemplos.area_retangulo(-49.5, -16.9, 0.00001, 0.00001)
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} minusculo", "tipo": "quadrada",
                                                  "lado_m": 500.0, "area_estudo": minusculo})
    assert r.status_code in (201, 422), r.text
    if r.status_code == 201:
        conjunto = r.json()
        assert 0 < conjunto["ficha"]["area_estudo_geodesica_m2"] < 10.0, conjunto["ficha"]
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
    # (d) linha e ponto não são unidade de análise
    for geom in ({"type": "LineString", "coordinates": [[-49.5, -16.9], [-49.4, -16.8]]},
                 {"type": "Point", "coordinates": [-49.5, -16.9]}):
        r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} nao area", "tipo": "quadrada",
                                                      "lado_m": 500.0, "area_estudo": geom})
        assert r.status_code == 422 and r.json()["erro"] == "geometria_invalida", r.text


def test_adv_area_que_cruza_duas_zonas_declara_crs_e_distorcao_na_ficha(sessao_a):
    """A ficha que a API devolve tem de trazer o CRS escolhido, a distorção medida e o aviso — nunca escondidos."""
    area = exemplos.area_retangulo(-49.5, -20.0, 3.0, 0.3)
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} duas zonas", "tipo": "quadrada",
                                                  "lado_m": 5000.0, "area_estudo": area})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    try:
        ficha = sessao_a.get(f"/api/amc/conjuntos/{conjunto['id']}").json()["ficha"]
        for campo in ("srid_trabalho", "crs_nome", "zona_utm", "hemisferio", "meridiano_central",
                      "distorcao_area_min_pct", "distorcao_area_max_pct", "distorcao_area_max_abs_pct",
                      "zonas_utm_cobertas", "cruza_zonas_utm", "avisos", "metodo"):
            assert campo in ficha, campo
        assert ficha["cruza_zonas_utm"] is True and len(ficha["avisos"]) >= 1
        assert ficha["distorcao_area_max_abs_pct"] > 0.1, ficha["distorcao_area_max_abs_pct"]
        # a distorção declarada tem de cobrir a que se mede ponto a ponto na borda mais afastada
        proj = pyproj.Proj(pyproj.CRS.from_epsg(ficha["srid_trabalho"]))
        pior = max((proj.get_factors(lon, -19.85).areal_scale - 1.0) * 100.0 for lon in (-49.5, -46.5))
        assert pior <= ficha["distorcao_area_max_pct"] + 1e-6, (pior, ficha["distorcao_area_max_pct"])
        assert math.isfinite(pior)
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


# ================================================================ 5. o schema do ambiente
# CONSERTADO em 06/09/2026 (achado 1 do laudo), nos dois níveis: `gravar_feicoes` não usa mais
# `psycopg2.extras.execute_values` (um `cur.execute` em TEXTO com `jsonb_to_recordset`), e
# `app/schema_ambiente.py` passou a reescrever `bytes` além de `str` — e `executemany`, `callproc`, `mogrify` e
# `copy_expert` além de `execute`. Era: "o conjunto do tipo 'feicoes' morre fora do schema `plat` e o erro que o
# cliente vê é 403 'operação fora do inquilino da sessão' — que não é o que aconteceu (foi 'permission denied for
# schema plat')". A mensagem enganosa também foi consertada (app/auth/comum._erro_de_privilegio). A marca
# xfail(strict), que era condicional a PLAT_SCHEMA != "plat", saiu: agora o teste tem de passar em QUALQUER schema.
def test_adv_conjunto_de_feicoes_funciona_em_qualquer_schema(sessao_a):
    """Passa em produção E em qualquer schema de ambiente. É a prova de que o item não quebra a homologação."""
    colecao = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "f1", "properties": {},
         "geometry": exemplos.area_retangulo(-49.30, -16.70, 0.01, 0.01)}]}
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} feicoes", "tipo": "feicoes",
                                                  "feicoes": colecao})
    assert r.status_code == 201, r.text
    sessao_a.delete(f"/api/amc/conjuntos/{r.json()['id']}")


def test_adv_execute_values_e_o_unico_desvio_da_reescrita_de_schema():
    """O MESMO teste, refeito depois do conserto — o autor deixou escrito "a guarda mudou; refazer este teste" na
    asserção que dependia da forma da guarda, e a guarda mudou. Antes ele media a CAUSA do defeito (a reescrita só
    agia sobre texto e `execute_values` manda bytes); agora mede o conserto, sem depender do ambiente:

    1. `app/amc/unidades.py` não usa mais `execute_values` em lugar nenhum — a gravação de feições é um
       `cur.execute` em TEXTO, que passa pela reescrita como qualquer outra consulta;
    2. a reescrita cobre texto E bytes, e o mesmo mecanismo vale para `executemany`/`callproc`/`mogrify`/
       `copy_expert`, não só `execute` (a trava que impede um caminho novo de escapar está em
       tests/unit/test_schema_ambiente.py)."""
    import inspect

    from app.schema_ambiente import CursorSchemaAmbiente, MixinReescritaSchema, reescrever_schema

    fonte_unidades = inspect.getsource(mod_unidades)
    assert "execute_values" not in fonte_unidades.replace("`psycopg2.extras.execute_values`", ""), \
        "voltou um execute_values em app/amc/unidades.py: a consulta escapa da reescrita de schema"
    assert "plat.amc_unidade" in inspect.getsource(mod_unidades.gravar_feicoes), "a consulta mudou; refazer o teste"

    assert reescrever_schema("SELECT 1 FROM plat.amc_unidade", "plat_homolog") == \
        "SELECT 1 FROM plat_homolog.amc_unidade"
    # a mesma consulta em bytes, que era o buraco
    assert CursorSchemaAmbiente._reescrever is MixinReescritaSchema._reescrever
    assert set(MixinReescritaSchema.METODOS_COM_CONSULTA) >= {"execute", "executemany", "callproc"}


@pytest.mark.lento
def test_adv_o_milhao_de_celulas_que_nao_foi_gerado(sessao_a, conexao_plat_app):
    """O construtor extrapolou 34,3 s para 1 milhão de células a partir de 250.986 medidas. Aqui a extrapolação
    é CONFERIDA gerando de verdade a escala do portão (100 m sobre ~9.500 km²), com guarda de disco: se
    /mnt/pgdata não tiver folga, o teste é pulado em vez de encher o disco."""
    import shutil

    livre_gb = shutil.disk_usage("/mnt/pgdata").free / 1e9
    if livre_gb < 8:
        pytest.skip(f"/mnt/pgdata com {livre_gb:.1f} GB livres: não se gera 1 milhão de células aqui")
    # 0,92° dava 1.000.175 células com o teto em 1.000.000: desde o conserto do achado 4 (06/09/2026) o teto vale
    # para a CONTAGEM REAL, e um conjunto que passa dele é recusado e limpo. A área encolheu 0,5 % em cada lado
    # para caber; a escala do portão (100 m sobre ~9.400 km², perto de 1 milhão de células) continua a mesma e
    # nenhuma asserção deste teste mudou.
    area = exemplos.area_retangulo(-49.9, -17.3, 0.915, 0.915)
    conjunto, segundos = _gerar(sessao_a, conexao_plat_app, "milhao", "quadrada", 100.0, area)
    try:
        n = conjunto["n_unidades"]
        esperado = _area_plano_m2(area, conjunto["ficha"]["srid_trabalho"]) / (100.0 * 100.0)
        desvio = (n - esperado) / esperado * 100.0
        print(f"\n[adversario] MEDIDO: {n:,} células em {segundos:.2f} s ({segundos / n * 1e6:.1f} µs/célula) · "
              f"esperado {esperado:,.0f} · desvio {desvio:+.3f} % · faixas {conjunto['ficha']['faixas']}")
        assert n > 800_000, n
        assert abs(desvio) <= 2.0, desvio
        # a projeção do construtor: 34,3 s para 1 milhão. Confere-se a ORDEM, não a casa decimal.
        projetado = 34.3 * n / 1_000_000
        print(f"[adversario] projeção do construtor para {n:,} células: {projetado:.1f} s · medido "
              f"{segundos:.1f} s · razão {segundos / projetado:.2f}×")
        assert segundos <= 60.0, segundos
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


# CONSERTADO em 06/09/2026 (achado 4 do laudo): `app.amc.unidades.gerar_grade` confere AMC_UNIDADES_MAX sobre a
# CONTAGEM REAL depois de gerar; passou do teto, apaga as unidades, marca o conjunto 'falhou' com o motivo, e a
# tarefa `amc.gerar_unidades` levanta FalhaDefinitiva. Era: "o teto é conferido sobre a ESTIMATIVA
# área/área-da-célula, nunca sobre o resultado; as células de borda entram recortadas e o conjunto termina acima do
# teto declarado — medido de verdade: 1.000.175 unidades com o teto em 1.000.000". A marca xfail(strict) saiu.
def test_adv_teto_de_unidades_vale_para_a_contagem_real(sessao_a, conexao_plat_app, monkeypatch):
    """Teto baixado por monkeypatch para provar a mecânica sem gerar um milhão de células."""
    from app import limites

    externo = [[-49.50, -16.90], [-49.40, -16.90], [-49.40, -16.80], [-49.50, -16.80], [-49.50, -16.90]]
    buraco = [[-49.47, -16.87], [-49.43, -16.87], [-49.43, -16.83], [-49.47, -16.83], [-49.47, -16.87]]
    geom = {"type": "Polygon", "coordinates": [externo, buraco]}
    monkeypatch.setattr(limites, "AMC_UNIDADES_MAX", 420)  # a estimativa é ~396: passa na guarda
    conjunto, _s = _gerar(sessao_a, conexao_plat_app, "teto", "quadrada", 500.0, geom)
    try:
        print(f"\n[adversario] teto {limites.AMC_UNIDADES_MAX} · estimativa "
              f"{conjunto['ficha']['contagem_esperada']:.0f} · gerado {conjunto['n_unidades']}")
        assert conjunto["n_unidades"] <= 420, conjunto["n_unidades"]
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
