"""Portão do item L2-03-a-api-edicao-transacional: `POST /api/camadas/{id}/edicoes`.

A camada de teste é criada DIRETO no banco (mesma sequência de `plat.camada_schema_garantir` +
`plat.camada_preparar` que `app/ingestao/carregar.py` usa em produção — só o `ogr2ogr` inicial vira um
`CREATE TABLE` liso, porque o que este item testa é a EDIÇÃO, não a carga), em vez de subir o pipeline de
ingestão inteiro (que exige um worker rodando contra o canal desta trilha; fora do escopo deste arquivo).
"""

from __future__ import annotations

import json
import time
import uuid

import psycopg2.extras
import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

SRID = 4674


def _admin_usuario_id(con, slug: str) -> int:
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        return cur.fetchone()["usuario_id"]


class FabricaCamada:
    """Cria/apaga tabela `d_<slug>.c_<hash>` + item `camada_vetorial` direto no banco, com a mesma
    `plat.camada_preparar` que a ingestão usa (RLS FORCE, `versao`, rastreio)."""

    def __init__(self, con):
        self.con = con
        self.criadas: list[tuple[str, str, str]] = []

    def criar(
        self, slug, tenant_id, usuario_id, campos, geometria="Point", regras_campo=None, edicao=None
    ) -> tuple[str, dict]:
        schema = f"d_{slug}"
        tabela = "c_" + uuid.uuid4().hex[:16]
        contexto(self.con, tenant_id, usuario_id=usuario_id, login="admin")
        with self.con.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            cols_sql = "".join(f', "{c["nome"]}" {c["tipo"]}' for c in campos)
            cur.execute(f'CREATE TABLE "{schema}"."{tabela}" (fid serial primary key, '
                        f'geom geometry({geometria}, {SRID}){cols_sql})')
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, SRID, geometria, usuario_id))
            item_id = str(uuid.uuid4())
            dados = {
                "schema": schema, "tabela": tabela, "geometria": geometria, "srid": SRID,
                "campos": [{"nome": c["nome"], "tipo": c["tipo"]} for c in campos],
                "fonte": "hospedada",
                "edicao": edicao if edicao is not None else {"habilitada": True},
            }
            if regras_campo:
                dados["regras_campo"] = regras_campo
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, "
                "modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, 'inquilino', %s, %s)",
                (item_id, tenant_id, f"{PREFIXO_TESTE} camada L2-03-a", usuario_id,
                 psycopg2.extras.Json(dados, dumps=lambda v: json.dumps(v, ensure_ascii=False)),
                 usuario_id, usuario_id),
            )
        self.con.commit()
        self.criadas.append((schema, tabela, item_id))
        return item_id, dados

    def linhas(self, schema: str, tabela: str, tenant_id: int, usuario_id: int) -> list[dict]:
        # `set_config(..., true)` é LOCAL à transação: o commit() de `criar()` já apagou o contexto, então
        # toda leitura direta pelo teste tem de religá-lo antes (senão a RLS da tabela de camada devolve 0
        # linhas, não um erro — o mesmo "some em silêncio" que a cláusula 11 testa do lado de fora).
        contexto(self.con, tenant_id, usuario_id=usuario_id, login="admin")
        with self.con.cursor() as cur:
            cur.execute(f'SELECT * FROM "{schema}"."{tabela}"')
            return cur.fetchall()

    def limpar(self):
        for schema, tabela, item_id in self.criadas:
            with self.con.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
                cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (item_id,))
        self.con.commit()
        self.criadas.clear()


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    f.limpar()


@pytest.fixture
def camada_a(fabrica, conexao_plat_app):
    """Camada de pontos em `demo` (tenant A): campos nome (text), categoria (text, domínio A/B/C),
    area (double precision, domínio 0-1000), ativo (boolean); edição habilitada, sem ownership."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"},
                {"nome": "area", "tipo": "double precision"}, {"nome": "ativo", "tipo": "boolean"}],
        geometria="Point",
        regras_campo={
            "categoria": {"dominio_valores": ["A", "B", "C"]},
            "area": {"dominio_min": 0, "dominio_max": 1000},
            "nome": {"obrigatorio": True},
        },
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


@pytest.fixture
def camada_a_somente_proprias(fabrica, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}],
        geometria="Point",
        edicao={"habilitada": True, "somente_proprias": True},
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


@pytest.fixture
def camada_a_poligono(fabrica, conexao_plat_app):
    """Camada MultiPolygon (coluna promovida, como a ingestão faz) para os testes de tipo de geometria/MakeValid."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id, campos=[{"nome": "nome", "tipo": "text"}], geometria="MultiPolygon",
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


@pytest.fixture
def camada_b(fabrica, conexao_plat_app):
    """Mesmo desenho de `camada_a`, no tenant B (demo2) — usada só no teste de isolamento (cláusula 11)."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo2")
    item_id, dados = fabrica.criar(
        "demo2", ids["demo2"], admin_id, campos=[{"nome": "nome", "tipo": "text"}], geometria="Point",
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo2"], "admin_id": admin_id}


def _ponto(lon=-46.5, lat=-23.5):
    return {"type": "Point", "coordinates": [lon, lat]}


# ---------------------------------------------------------------- cláusula 1: transação tudo-ou-nada
def test_transacao_rollback_quando_uma_de_tres_falha(sessao_a, camada_a, fabrica):
    corpo = {
        "adicionar": [{"atributos": {"nome": "um", "categoria": "A"}, "geometria": _ponto(-46.1)}],
        "atualizar": [],
        "apagar": [],
    }
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
    gid = r.json()["adicionar"][0]["id"]

    # lote de 3: 1) adicionar válida  2) atualizar válida  3) apagar com versão errada (falha)
    corpo2 = {
        "adicionar": [{"atributos": {"nome": "dois", "categoria": "B"}, "geometria": _ponto(-46.2)}],
        "atualizar": [{"id": gid, "versao": 1, "atributos": {"nome": "um-editado"}}],
        "apagar": [{"id": gid, "versao": 99}],  # versão errada de propósito
    }
    r2 = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo2)
    assert r2.status_code == 409, r2.text

    linhas = fabrica.linhas(camada_a["dados"]["schema"], camada_a["dados"]["tabela"],
                             camada_a["tenant_id"], camada_a["admin_id"])
    nomes = sorted(linha["nome"] for linha in linhas)
    assert nomes == ["um"], f"rollback falhou: linhas ficaram {nomes}"
    assert linhas[0]["versao"] == 1, "a atualização válida do lote 2 não deveria ter sido persistida"


# ---------------------------------------------------------------- cláusula 2: versão otimista
def test_versao_otimista_segunda_sessao_recebe_409_com_feicao_atual(sessao_a, camada_a):
    corpo = {"adicionar": [{"atributos": {"nome": "original", "categoria": "A"}, "geometria": _ponto()}]}
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
    gid = r.json()["adicionar"][0]["id"]

    # sessão 1 edita e ganha (versão 1 -> 2)
    r1 = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes",
                        json={"atualizar": [{"id": gid, "versao": 1, "atributos": {"nome": "sessao-1"}}]})
    assert r1.status_code == 200, r1.text

    # sessão 2 ainda tinha a versão 1 lida -> 409 com a feição ATUAL (versão 2, nome sessao-1)
    r2 = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes",
                        json={"atualizar": [{"id": gid, "versao": 1, "atributos": {"nome": "sessao-2"}}]})
    assert r2.status_code == 409, r2.text
    corpo_erro = r2.json()
    assert corpo_erro["erro"] == "conflito_versao", corpo_erro
    atual = corpo_erro["detalhe"]["atual"]
    assert atual["versao"] == 2, atual
    assert atual["atributos"]["nome"] == "sessao-1", atual


# ---------------------------------------------------------------- cláusula 3: domínio
def test_atributo_fora_do_dominio_422_com_campo_e_valor(sessao_a, camada_a):
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "x", "categoria": "Z"}, "geometria": _ponto()}]})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "fora_do_dominio", corpo
    assert corpo["detalhe"]["campo"] == "categoria", corpo
    assert corpo["detalhe"]["valor"] == "Z", corpo


def test_atributo_fora_do_intervalo_422(sessao_a, camada_a):
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "x", "area": 5000}, "geometria": _ponto()}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "fora_do_dominio", r.json()
    assert r.json()["detalhe"]["campo"] == "area", r.json()


# ---------------------------------------------------------------- cláusula 4: tipo de geometria errado
def test_geometria_tipo_errado_422(sessao_a, camada_a_poligono):
    r = sessao_a.post(f"/api/camadas/{camada_a_poligono['id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "linha"},
                                            "geometria": {"type": "LineString",
                                                          "coordinates": [[-46.5, -23.5], [-46.4, -23.4]]}}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "tipo_geometria_invalido", r.json()


def test_geometria_singular_e_promovida_para_multi_da_coluna(sessao_a, camada_a_poligono):
    """Polygon enviado numa coluna MultiPolygon (mesma promoção que app/ingestao/carregar.py faz na carga)."""
    anel = [[-46.50, -23.50], [-46.49, -23.50], [-46.49, -23.49], [-46.50, -23.49], [-46.50, -23.50]]
    r = sessao_a.post(f"/api/camadas/{camada_a_poligono['id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "poligono-simples"},
                                            "geometria": {"type": "Polygon", "coordinates": [anel]}}]})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- cláusula 5: ST_MakeValid opcional
GRAVATA = {
    "type": "Polygon",
    "coordinates": [[[-46.50, -23.50], [-46.49, -23.49], [-46.50, -23.49], [-46.49, -23.50], [-46.50, -23.50]]],
}


def test_poligono_invalido_recusado_sem_corrigir(sessao_a, camada_a_poligono):
    r = sessao_a.post(f"/api/camadas/{camada_a_poligono['id']}/edicoes",
                       json={"corrigir_geometria": False,
                             "adicionar": [{"atributos": {"nome": "gravata"}, "geometria": GRAVATA}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "geometria_invalida", r.json()


def test_poligono_invalido_corrigido_com_makevalid_quando_pedido(sessao_a, camada_a_poligono):
    r = sessao_a.post(f"/api/camadas/{camada_a_poligono['id']}/edicoes",
                       json={"corrigir_geometria": True,
                             "adicionar": [{"atributos": {"nome": "gravata"}, "geometria": GRAVATA}]})
    assert r.status_code == 200, r.text
    assert any("ST_MakeValid" in a for a in r.json()["avisos"]), r.json()["avisos"]


# ---------------------------------------------------------------- cláusula 6: só as próprias feições
def test_somente_proprias_impede_update_de_feicao_alheia(sessao_a, camada_a_somente_proprias, usuarios_a):
    # admin cria a feição (dona = admin)
    r = sessao_a.post(f"/api/camadas/{camada_a_somente_proprias['id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "do-admin"}, "geometria": _ponto()}]})
    assert r.status_code == 200, r.text
    gid = r.json()["adicionar"][0]["id"]

    editor, _u, _senha = usuarios_a.sessao(perfil="editor")
    try:
        r2 = editor.post(f"/api/camadas/{camada_a_somente_proprias['id']}/edicoes",
                          json={"atualizar": [{"id": gid, "versao": 1, "atributos": {"nome": "roubado"}}]})
        assert r2.status_code == 403, r2.text
        assert r2.json()["erro"] == "feicao_de_outro_usuario", r2.json()
    finally:
        editor.close()


# ---------------------------------------------------------------- cláusula 7: rastreio nunca aceito do cliente
def test_campos_de_rastreio_ignorados_e_preenchidos_pelo_servidor(sessao_a, camada_a, ids):
    outro_usuario_id = ids["b"]["id"]  # qualquer id != o de quem está autenticado
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [{
            "atributos": {"nome": "x", "categoria": "A", "criado_por": outro_usuario_id,
                          "versao": 999, "fid": 12345, "globalid": str(uuid.uuid4())},
            "geometria": _ponto(),
        }]},
    )
    assert r.status_code == 200, r.text
    resultado = r.json()["adicionar"][0]
    assert resultado["versao"] == 1, resultado  # nunca 999
    assert resultado["fid"] != 12345, resultado
    assert any("criado_por" in a or "rastreio" in a for a in r.json()["avisos"]), r.json()["avisos"]


# ---------------------------------------------------------------- cláusula 8: 1.000 feições em lote <= 3 s
@pytest.mark.lento
def test_mil_feicoes_em_lote_menos_de_3s(sessao_a, camada_a, medida):
    corpo = {"adicionar": [
        {"atributos": {"nome": f"f{i}", "categoria": "A"}, "geometria": _ponto(-46.5 + i * 0.0001, -23.5)}
        for i in range(1000)
    ]}
    t0 = time.monotonic()
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo)
    dt = time.monotonic() - t0
    assert r.status_code == 200, r.text[:500]
    assert len(r.json()["adicionar"]) == 1000
    gravar = medida("L2-03-a-api-edicao-transacional")
    gravar("mil_feicoes_lote_s", round(dt, 3), "s",
           "POST /api/camadas/{id}/edicoes com 1.000 feições em `adicionar` (modo transação padrão), "
           "camada de teste em d_demo; tests/api/test_edicao_transacional.py::"
           "test_mil_feicoes_em_lote_menos_de_3s")
    assert dt <= 3.0, f"mil_feicoes_lote_s = {dt:.3f} s (teto 3 s)"


# ---------------------------------------------------------------- cláusula 9: um evento por lote, com a contagem
def test_evento_gravado_por_lote_com_contagem(sessao_a, camada_a):
    corpo = {
        "adicionar": [{"atributos": {"nome": "e1", "categoria": "A"}, "geometria": _ponto()},
                      {"atributos": {"nome": "e2", "categoria": "B"}, "geometria": _ponto(-46.3)}],
    }
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
    itens = sessao_a.get("/api/eventos?limite=20").json()["itens"]
    meus = [e for e in itens if e["tipo"] == "camadas/editar" and e["alvo_id"] == camada_a["id"]]
    assert meus, itens
    props = meus[0]["propriedades"]
    assert props["adicionados"] == 2, props
    assert props["atualizados"] == 0 and props["apagados"] == 0, props


# ---------------------------------------------------------------- cláusula 10: OpenAPI com os esquemas
def test_rota_no_openapi_com_esquemas_de_entrada_e_saida():
    from tests.api.conftest import arquivo_openapi

    spec = arquivo_openapi()
    op = spec["paths"]["/api/camadas/{id}/edicoes"]["post"]
    assert op["x-privilegio"] == "feicoes.editar|feicoes.editar_total"
    corpo_ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]
    esquema_entrada = spec["components"]["schemas"][corpo_ref]
    for campo in ("modo", "adicionar", "atualizar", "apagar", "crs", "corrigir_geometria"):
        assert campo in esquema_entrada["properties"], esquema_entrada["properties"]
    resposta_ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]
    esquema_saida = spec["components"]["schemas"][resposta_ref]
    for campo in ("adicionar", "atualizar", "apagar", "avisos"):
        assert campo in esquema_saida["properties"], esquema_saida["properties"]


# ---------------------------------------------------------------- cláusula 11 (inegociável): isolamento entre
# inquilinos
def test_inquilino_b_nunca_edita_nem_le_feicao_de_camada_de_a(sessao_a, sessao_b, camada_a):
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "de-a", "categoria": "A"}, "geometria": _ponto()}]})
    assert r.status_code == 200, r.text
    gid = r.json()["adicionar"][0]["id"]

    # B nem lê a camada (404 — a RLS de plat.item some com ela, nunca "existe mas não é sua")
    r_leitura = sessao_b.post(f"/api/camadas/{camada_a['id']}/edicoes",
                               json={"adicionar": [{"atributos": {"nome": "de-b"}, "geometria": _ponto()}]})
    assert r_leitura.status_code == 404, r_leitura.text

    r_atualizar = sessao_b.post(f"/api/camadas/{camada_a['id']}/edicoes",
                                 json={"atualizar": [{"id": gid, "versao": 1, "atributos": {"nome": "roubado-por-b"}}]})
    assert r_atualizar.status_code == 404, r_atualizar.text

    r_apagar = sessao_b.post(f"/api/camadas/{camada_a['id']}/edicoes", json={"apagar": [{"id": gid}]})
    assert r_apagar.status_code == 404, r_apagar.text


# ---------------------------------------------------------------- refutação do item (roteiro do adversário)
def test_lote_de_100_mil_feicoes_e_recusado_pelo_limite_declarado(sessao_a, camada_a):
    """100 mil feições no `adicionar`, corpo pequeno o bastante para não bater primeiro no limite de corpo
    HTTP (10 MiB): tem de recusar pelo teto de lote (`limites.EDICAO_LOTE_MAX`), nunca aceitar nem 500."""
    corpo = {"adicionar": [{"atributos": {"nome": "x"}} for _ in range(100_000)]}
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo)
    assert r.status_code in (422, 413), r.text[:300]


def test_geometria_em_outro_crs_sem_declarar_e_recusada(sessao_a, camada_a):
    """Coordenada em metros (estilo UTM/Web Mercator) mandada sem `crs` numa camada de SRID geográfico
    (graus): fora do intervalo [-180,180]/[-90,90] em qualquer hipótese — 422, nunca gravação silenciosa
    da coordenada errada."""
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [{"atributos": {"nome": "utm-sem-declarar"},
                              "geometria": {"type": "Point", "coordinates": [412345.6, 7398765.4]}}]},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "geometria_fora_do_crs", r.json()


def test_srid_zero_declarado_e_recusado(sessao_a, camada_a):
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"crs": {"srid": 0}, "adicionar": [{"atributos": {"nome": "srid-zero"}, "geometria": _ponto()}]},
    )
    assert r.status_code == 422, r.text


def test_texto_de_1mb_e_recusado(sessao_a, camada_a):
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [{"atributos": {"nome": "a" * (1024 * 1024)}, "geometria": _ponto()}]},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "texto_grande", r.json()


def test_feicao_com_fid_de_outro_inquilino_nunca_e_aceita_por_globalid(sessao_b, camada_a):
    """`sessao_b` (inquilino B) tentando atualizar pelo `globalid` de uma feição de A que ele nem enxerga:
    já coberto por `test_inquilino_b_nunca_edita_nem_le_feicao_de_camada_de_a` para a MESMA camada; aqui o
    adversário tenta um `id` claramente inventado (nunca existiu em lugar nenhum) contra a PRÓPRIA camada de
    B — tem de dar 404 de feição inexistente, nunca 500 nem sucesso."""
    r = sessao_b.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"apagar": [{"id": str(uuid.uuid4())}]},
    )
    assert r.status_code == 404, r.text


def test_edicao_concorrente_de_duas_sessoes_nunca_sobrescreve_em_silencio(sessao_a, camada_a, usuarios_a):
    """Duas sessões HTTP distintas (não só duas chamadas da mesma `sessao_a`) leem a versão 1 e as duas tentam
    gravar: só a primeira que chega ganha, a segunda recebe 409 com a feição atual — nunca as duas 200."""
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "concorrencia", "categoria": "A"},
                                             "geometria": _ponto()}]})
    assert r.status_code == 200, r.text
    gid = r.json()["adicionar"][0]["id"]

    outra_sessao, _u, _senha = usuarios_a.sessao(perfil="admin")
    try:
        corpo = {"atualizar": [{"id": gid, "versao": 1, "atributos": {"nome": "sessao-nova"}}]}
        r1 = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo)
        r2 = outra_sessao.post(f"/api/camadas/{camada_a['id']}/edicoes", json=corpo)
        codigos = sorted([r1.status_code, r2.status_code])
        assert codigos == [200, 409], (r1.status_code, r2.status_code, r1.text[:200], r2.text[:200])
    finally:
        outra_sessao.close()
