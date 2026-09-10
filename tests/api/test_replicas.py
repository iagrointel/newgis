"""Portão do item L2-13-b-replicas-sincronizacao: réplicas para trabalho desconectado.

Camadas de teste criadas direto no banco pela MESMA sequência de `plat.camada_schema_garantir` +
`plat.camada_preparar` que a ingestão usa (reaproveita `FabricaCamada` do L2-03-a — o que este arquivo
testa é a réplica, não a carga).

O pacote é gerado chamando a TAREFA registrada `replicas.criar` (app/replica/tarefas.py) com um contexto de
job mínimo: a trilha não tem worker de pé, e esperar por um deixaria o portão dependendo de infraestrutura
em vez do código do item. O caminho exercitado é o de produção — mesma função, mesmo `ctx.db()`.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path

import psycopg2
import pytest

from app import db as banco
from app.jobs.tipos import REGISTRO
from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_rls import ids_por_slug

MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / "L2-13-b-replicas-sincronizacao.json"


class ContextoJobTeste:
    """O mínimo que `replicas.criar` usa do ContextoJob real: `db()` (cursor no inquilino) e `progresso()`.
    Não substitui nada do código sob teste — só a fila que o entregaria."""

    def __init__(self, tenant_id: int, usuario_id: int):
        self._ctx = banco.Contexto(tenant_id, usuario_id, "teste")
        self.passos: list[tuple[int, str]] = []

    def db(self):
        return banco.db(self._ctx)

    def progresso(self, pct: int, mensagem: str = "") -> None:
        self.passos.append((pct, mensagem))


def gerar_pacote(replica_id: str, tenant_id: int, usuario_id: int) -> dict:
    return REGISTRO["replicas.criar"].funcao(
        ContextoJobTeste(tenant_id, usuario_id), replica_id=uuid.UUID(replica_id)
    )


# ---------------------------------------------------------------- fábricas
class FabricaSemCorrida(FabricaCamada):
    """A fábrica do L2-03-a, com repetição no `tuple concurrently updated`.

    `plat.camada_schema_garantir` reemite `GRANT USAGE ON SCHEMA d_<slug>` a cada chamada, e o schema
    `d_demo` é o MESMO objeto de catálogo para TODAS as trilhas desta máquina (o que muda entre trilhas é o
    schema `plat_*`, não o `d_*`). Duas trilhas criando camada ao mesmo tempo colidem no tuplo de
    `pg_namespace`. Isso é da árvore compartilhada, não do item: a repetição é do TESTE, o produto não muda.
    """

    def criar(self, *args, **kwargs):
        for tentativa in range(8):
            try:
                return super().criar(*args, **kwargs)
            except psycopg2.errors.InternalError_:
                self.con.rollback()
                time.sleep(0.25 * (tentativa + 1))
        return super().criar(*args, **kwargs)


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaSemCorrida(conexao_plat_app)
    yield f
    f.limpar()


@pytest.fixture
def contexto_a(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    return {"tenant_id": ids["demo"], "admin_id": _admin_usuario_id(conexao_plat_app, "demo")}


@pytest.fixture
def contexto_b(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    return {"tenant_id": ids["demo2"], "admin_id": _admin_usuario_id(conexao_plat_app, "demo2")}


def _camada(fabrica, ctx, slug="demo", campos=None, geometria="Point"):
    item_id, dados = fabrica.criar(
        slug, ctx["tenant_id"], ctx["admin_id"],
        campos=campos or [{"nome": "nome", "tipo": "text"}, {"nome": "grupo", "tipo": "text"}],
        geometria=geometria,
    )
    return {"id": item_id, "dados": dados}


def _ponto(lon=-46.5, lat=-23.5):
    return {"type": "Point", "coordinates": [lon, lat]}


def _adicionar(sessao, camada_id, feicoes) -> list[str]:
    r = sessao.post(f"/api/camadas/{camada_id}/edicoes", json={"adicionar": feicoes})
    assert r.status_code == 200, r.text
    return [x["id"] for x in r.json()["adicionar"]]


@pytest.fixture
def replicas_criadas(sessao_a):
    criadas: list[str] = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/replicas/{rid}")


def _criar_replica(sessao, replicas_criadas, camadas, **extra) -> dict:
    corpo = {"nome": "zt replica de campo", "camadas": camadas, **extra}
    r = sessao.post("/api/replicas", json=corpo)
    assert r.status_code == 202, r.text
    replicas_criadas.append(r.json()["id"])
    return r.json()


def _abrir_no_gdal(caminho: Path) -> dict:
    """`ogrinfo -json`: a prova de que o arquivo é um GeoPackage legível, e as contagens por camada."""
    r = subprocess.run(["ogrinfo", "-ro", "-so", "-json", str(caminho)],
                       capture_output=True, text=True, timeout=180, check=False)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["driverShortName"] == "GPKG", d["driverShortName"]
    return {c["name"]: c for c in d["layers"]}


def _baixar(sessao, replica_id: str, tmp_path: Path) -> Path:
    r = sessao.get(f"/api/replicas/{replica_id}/pacote")
    assert r.status_code == 200, r.text
    caminho = tmp_path / "replica.gpkg"
    caminho.write_bytes(r.content)
    return caminho


# ================================================================ cláusula 1
# "réplica de 2 camadas com filtro -> GeoPackage abre no GDAL com as contagens do filtro"
def test_replica_de_duas_camadas_com_filtro_abre_no_gdal_com_as_contagens(
    sessao_a, fabrica, contexto_a, replicas_criadas, tmp_path
):
    c1 = _camada(fabrica, contexto_a)
    c2 = _camada(fabrica, contexto_a)
    _adicionar(sessao_a, c1["id"], [
        {"atributos": {"nome": f"a{i}", "grupo": "norte" if i < 3 else "sul"}, "geometria": _ponto(-46.5 + i / 100)}
        for i in range(7)
    ])
    _adicionar(sessao_a, c2["id"], [
        {"atributos": {"nome": f"b{i}", "grupo": "sul"}, "geometria": _ponto(-46.0 + i / 100)} for i in range(4)
    ])

    replica = _criar_replica(sessao_a, replicas_criadas, [
        {"camada_id": c1["id"], "nome_gpkg": "pontos_um", "filtro": "grupo = 'norte'"},
        {"camada_id": c2["id"], "nome_gpkg": "pontos_dois"},
    ])
    assert replica["estado"] == "criando" and replica["job_id"], replica
    resultado = gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    assert resultado["camadas"] == 2 and resultado["feicoes"] == 3 + 4, resultado

    caminho = _baixar(sessao_a, replica["id"], tmp_path)
    camadas = _abrir_no_gdal(caminho)
    assert camadas["pontos_um"]["featureCount"] == 3, camadas["pontos_um"]
    assert camadas["pontos_dois"]["featureCount"] == 4, camadas["pontos_dois"]
    # tabelas de serviço do pacote: plat_sync (fid+versão por feição), metadado e domínio declarado
    assert camadas["plat_sync"]["featureCount"] == 7, camadas["plat_sync"]
    assert camadas["plat_replica"]["featureCount"] == 2, camadas["plat_replica"]


def test_pacote_de_camada_com_dominio_leva_tabela_de_dominio(
    sessao_a, fabrica, conexao_plat_app, contexto_a, replicas_criadas, tmp_path
):
    item_id, _dados = fabrica.criar(
        "demo", contexto_a["tenant_id"], contexto_a["admin_id"],
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"}],
        geometria="Point", regras_campo={"categoria": {"dominio_valores": ["A", "B", "C"]}},
    )
    _adicionar(sessao_a, item_id, [{"atributos": {"nome": "x", "categoria": "A"}, "geometria": _ponto()}])
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": item_id, "nome_gpkg": "com_dominio"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    camadas = _abrir_no_gdal(_baixar(sessao_a, replica["id"], tmp_path))
    assert camadas["plat_dominio"]["featureCount"] == 3, camadas["plat_dominio"]


# ================================================================ cláusula 2
# "editar 20 feições no GeoPackage (por ogr) e sincronizar sobe 20 e baixa as mudanças do servidor
#  feitas no intervalo"
def _editar_no_gpkg(caminho: Path, nome_camada: str, novo_valor: str, quantos: int) -> list[dict]:
    """Edita de verdade DENTRO do GeoPackage, com o ogr — não em memória. Devolve o que o cliente
    desconectado tem em mãos para subir: globalid, versão lida e o atributo novo."""
    sql = (f"UPDATE {nome_camada} SET nome = '{novo_valor}' "
           f"WHERE fid IN (SELECT fid FROM {nome_camada} ORDER BY fid LIMIT {quantos})")
    r = subprocess.run(["ogrinfo", "-dialect", "SQLITE", "-sql", sql, str(caminho)],
                       capture_output=True, text=True, timeout=180, check=False)
    assert r.returncode == 0, r.stderr
    leitura = subprocess.run(
        ["ogr2ogr", "-f", "GeoJSON", "/vsistdout/", str(caminho), "-dialect", "SQLITE",
         "-sql", f"SELECT globalid, versao, nome FROM {nome_camada} WHERE nome = '{novo_valor}'"],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert leitura.returncode == 0, leitura.stderr
    feicoes = json.loads(leitura.stdout)["features"]
    assert len(feicoes) == quantos, f"o ogr editou {len(feicoes)} de {quantos}"
    return [f["properties"] for f in feicoes]


def test_sincronizar_sobe_vinte_editadas_no_gpkg_e_baixa_o_que_o_servidor_mudou(
    sessao_a, fabrica, contexto_a, replicas_criadas, tmp_path
):
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"], [
        {"atributos": {"nome": f"orig{i}", "grupo": "g"}, "geometria": _ponto(-46.5 + i / 1000)}
        for i in range(25)
    ])
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "campo"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    caminho = _baixar(sessao_a, replica["id"], tmp_path)

    # ...o cliente edita 20 feições no arquivo, fora de rede
    editadas = _editar_no_gpkg(caminho, "campo", "editado-no-campo", 20)

    # ...e o servidor, no MESMO intervalo, muda duas outras: uma alterada e uma apagada
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes",
                      json={"atualizar": [{"id": ids[24], "versao": 1, "atributos": {"nome": "mudou-no-servidor"}}],
                            "apagar": [{"id": ids[23], "versao": 1}]})
    assert r.status_code == 200, r.text

    corpo = {"idempotencia": f"zt-lote-{uuid.uuid4()}", "camadas": [{
        "camada_id": camada["id"],
        "atualizar": [{"id": f["globalid"], "versao": int(f["versao"]), "atributos": {"nome": f["nome"]}}
                      for f in editadas],
    }]}
    r = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar", json=corpo)
    assert r.status_code == 200, r.text
    saida = r.json()
    assert saida["subidas"]["atualizadas"] == 20, saida["subidas"]
    assert saida["conflitos"] == [], saida["conflitos"]

    baixada = saida["baixadas"][0]
    por_id = {m["id"]: m for m in baixada["mudancas"]}
    assert ids[24] in por_id and por_id[ids[24]]["atributos"]["nome"] == "mudou-no-servidor", por_id.get(ids[24])
    assert ids[23] in por_id and por_id[ids[23]]["operacao"] == "apagar", por_id.get(ids[23])
    # o que o próprio cliente acabou de subir NÃO volta na descida
    assert not ({f["globalid"] for f in editadas} & set(por_id)), "a réplica recebeu de volta a própria edição"


# ================================================================ cláusula 3
# "conflito por versão divergente resolvido pela política (3 casos testados)"
def _preparar_conflito(sessao, fabrica, ctx, replicas_criadas, politica: str):
    camada = _camada(fabrica, ctx)
    ids = _adicionar(sessao, camada["id"], [{"atributos": {"nome": "v1", "grupo": "g"}, "geometria": _ponto()}])
    replica = _criar_replica(sessao, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "conf"}],
                             politica_conflito=politica)
    gerar_pacote(replica["id"], ctx["tenant_id"], ctx["admin_id"])
    # o servidor avança para a versão 2 enquanto o dispositivo estava fora de rede com a versão 1
    r = sessao.post(f"/api/camadas/{camada['id']}/edicoes",
                    json={"atualizar": [{"id": ids[0], "versao": 1, "atributos": {"nome": "v2-servidor"}}]})
    assert r.status_code == 200, r.text
    return camada, replica, ids[0]


def _sincronizar_com_versao_velha(sessao, replica, camada, globalid):
    corpo = {"idempotencia": f"zt-conf-{uuid.uuid4()}", "camadas": [{
        "camada_id": camada["id"],
        "atualizar": [{"id": globalid, "versao": 1, "atributos": {"nome": "v2-cliente"}}],
    }]}
    r = sessao.post(f"/api/replicas/{replica['id']}/sincronizar", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _nome_no_servidor(sessao, camada_id, globalid) -> str:
    r = sessao.get(f"/api/camadas/{camada_id}/feicoes/{globalid}")
    assert r.status_code == 200, r.text
    return r.json()["atributos"]["nome"]


def test_conflito_politica_servidor_vence(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada, replica, gid = _preparar_conflito(sessao_a, fabrica, contexto_a, replicas_criadas, "servidor_vence")
    saida = _sincronizar_com_versao_velha(sessao_a, replica, camada, gid)
    assert len(saida["conflitos"]) == 1, saida["conflitos"]
    assert saida["conflitos"][0]["resolucao"] == "servidor", saida["conflitos"][0]
    assert saida["subidas"]["atualizadas"] == 0, saida["subidas"]
    assert _nome_no_servidor(sessao_a, camada["id"], gid) == "v2-servidor"


def test_conflito_politica_cliente_vence(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada, replica, gid = _preparar_conflito(sessao_a, fabrica, contexto_a, replicas_criadas, "cliente_vence")
    saida = _sincronizar_com_versao_velha(sessao_a, replica, camada, gid)
    assert saida["conflitos"][0]["resolucao"] == "cliente", saida["conflitos"][0]
    assert saida["subidas"]["atualizadas"] == 1, saida["subidas"]
    assert _nome_no_servidor(sessao_a, camada["id"], gid) == "v2-cliente"


def test_conflito_politica_pergunta_nao_aplica_e_devolve_o_atual(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada, replica, gid = _preparar_conflito(sessao_a, fabrica, contexto_a, replicas_criadas, "pergunta")
    saida = _sincronizar_com_versao_velha(sessao_a, replica, camada, gid)
    conflito = saida["conflitos"][0]
    assert conflito["resolucao"] == "pendente", conflito
    assert conflito["versao_cliente"] == 1 and conflito["versao_servidor"] == 2, conflito
    assert conflito["atual"]["atributos"]["nome"] == "v2-servidor", conflito["atual"]
    assert _nome_no_servidor(sessao_a, camada["id"], gid) == "v2-servidor"


# ================================================================ cláusula 4
# "segunda sincronização do mesmo lote = 0 aplicadas (idempotência)"
def test_mesmo_lote_repetido_aplica_zero_e_devolve_a_mesma_resposta(
    sessao_a, fabrica, contexto_a, replicas_criadas, conexao_plat_app
):
    camada = _camada(fabrica, contexto_a)
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "idem"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])

    corpo = {"idempotencia": f"zt-idem-{uuid.uuid4()}", "camadas": [{
        "camada_id": camada["id"],
        "adicionar": [{"atributos": {"nome": "coletado", "grupo": "g"}, "geometria": _ponto()}],
    }]}
    primeira = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar", json=corpo)
    assert primeira.status_code == 200, primeira.text
    assert primeira.json()["subidas"]["adicionadas"] == 1, primeira.json()

    segunda = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar", json=corpo)
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["repetida"] is True, segunda.json()
    assert segunda.json()["subidas"] == primeira.json()["subidas"], segunda.json()
    assert segunda.json()["geracao"] == primeira.json()["geracao"], "geração avançou num lote repetido"

    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            contexto_a["tenant_id"], contexto_a["admin_id"])
    assert len([x for x in linhas if x["nome"] == "coletado"]) == 1, "o lote repetido duplicou a feição"


# ================================================================ cláusula 5
# "geração avança monotonicamente"
def test_geracao_avanca_monotonicamente(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada = _camada(fabrica, contexto_a)
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "ger"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    geracoes = []
    for _ in range(4):
        r = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar",
                          json={"idempotencia": f"zt-ger-{uuid.uuid4()}", "camadas": []})
        assert r.status_code == 200, r.text
        geracoes.append(r.json()["geracao"])
    assert geracoes == sorted(geracoes) and len(set(geracoes)) == 4, geracoes
    assert geracoes[0] == 1, geracoes


def test_ponteiro_da_camada_avanca_e_nao_reenvia_a_mesma_mudanca(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"], [{"atributos": {"nome": "um", "grupo": "g"}, "geometria": _ponto()}])
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "ponteiro"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])

    sessao_a.post(f"/api/camadas/{camada['id']}/edicoes",
                  json={"atualizar": [{"id": ids[0], "versao": 1, "atributos": {"nome": "dois"}}]})
    primeira = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar",
                             json={"idempotencia": f"zt-p1-{uuid.uuid4()}", "camadas": []}).json()
    assert len(primeira["baixadas"][0]["mudancas"]) == 1, primeira["baixadas"][0]
    segunda = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar",
                            json={"idempotencia": f"zt-p2-{uuid.uuid4()}", "camadas": []}).json()
    assert segunda["baixadas"][0]["mudancas"] == [], segunda["baixadas"][0]
    assert segunda["baixadas"][0]["desde"] == primeira["baixadas"][0]["ate"], segunda["baixadas"][0]


# ================================================================ cláusula 6
# "réplica de A não baixa camada de B"
def test_replica_de_a_nao_alcanca_camada_de_b(sessao_a, fabrica, contexto_a, contexto_b, replicas_criadas):
    camada_b = _camada(fabrica, contexto_b, slug="demo2")
    r = sessao_a.post("/api/replicas", json={"nome": "zt cruzada",
                                             "camadas": [{"camada_id": camada_b["id"], "nome_gpkg": "de_b"}]})
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "item_inexistente", r.json()


def test_sincronizar_camada_que_nao_e_da_replica_da_404(sessao_a, fabrica, contexto_a, replicas_criadas):
    dentro = _camada(fabrica, contexto_a)
    fora = _camada(fabrica, contexto_a)
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": dentro["id"], "nome_gpkg": "dentro"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    r = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar", json={
        "idempotencia": f"zt-fora-{uuid.uuid4()}",
        "camadas": [{"camada_id": fora["id"],
                     "adicionar": [{"atributos": {"nome": "x", "grupo": "g"}, "geometria": _ponto()}]}],
    })
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "camada_fora_da_replica", r.json()
    linhas = fabrica.linhas(fora["dados"]["schema"], fora["dados"]["tabela"],
                            contexto_a["tenant_id"], contexto_a["admin_id"])
    assert linhas == [], "escreveu em camada fora do recorte declarado"


def test_replica_de_b_e_404_para_a(sessao_a, sessao_b, fabrica, contexto_b):
    camada_b = _camada(fabrica, contexto_b, slug="demo2")
    r = sessao_b.post("/api/replicas", json={"nome": "zt de b",
                                             "camadas": [{"camada_id": camada_b["id"], "nome_gpkg": "de_b"}]})
    assert r.status_code == 202, r.text
    replica_b = r.json()["id"]
    try:
        for caminho in (f"/api/replicas/{replica_b}", f"/api/replicas/{replica_b}/pacote"):
            assert sessao_a.get(caminho).status_code == 404, caminho
        assert sessao_a.post(f"/api/replicas/{replica_b}/sincronizar",
                             json={"idempotencia": "zt-cruzado-abc", "camadas": []}).status_code == 404
        assert replica_b not in [x["id"] for x in sessao_a.get("/api/replicas").json()]
    finally:
        sessao_b.delete(f"/api/replicas/{replica_b}")


# ================================================================ cláusula 7 (refutação)
# "adversário sobe mudança com versão antiga sem política 'cliente vence' e confere que não sobrescreve"
# está em test_conflito_politica_servidor_vence e test_conflito_politica_pergunta_...; aqui, réplica expirada.
def test_replica_expirada_recusa_sincronizacao(
    sessao_a, fabrica, contexto_a, replicas_criadas, conexao_plat_app
):
    from tests.api.test_rls import contexto as ctx_banco

    camada = _camada(fabrica, contexto_a)
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "velha"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    ctx_banco(conexao_plat_app, contexto_a["tenant_id"], usuario_id=contexto_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("UPDATE plat.replica SET expira_em = now() - interval '1 day' WHERE id = %s::uuid",
                    (replica["id"],))
        assert cur.rowcount == 1, "a RLS engoliu o UPDATE (contexto de inquilino ausente)"
    conexao_plat_app.commit()

    r = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar",
                      json={"idempotencia": f"zt-exp-{uuid.uuid4()}", "camadas": [{
                          "camada_id": camada["id"],
                          "adicionar": [{"atributos": {"nome": "tarde", "grupo": "g"},
                                         "geometria": _ponto()}]}]})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "replica_expirada", r.json()
    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            contexto_a["tenant_id"], contexto_a["admin_id"])
    assert linhas == [], "réplica vencida conseguiu escrever"
    assert sessao_a.get(f"/api/replicas/{replica['id']}").json()["expirada"] is True


def test_lote_acima_do_teto_declarado_e_recusado(sessao_a, fabrica, contexto_a, replicas_criadas):
    """Refutação 'sobe 1 mi de mudanças': o teto declarado (limites.REPLICA_SINCRONIZAR_LOTE_MAX) recusa
    o pedido no pydantic, sem tocar no banco. Um milhão de itens de verdade não cabe no corpo máximo, então
    o teste manda o menor lote que já passa do teto — é o mesmo caminho de recusa."""
    from app import limites

    camada = _camada(fabrica, contexto_a)
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "teto"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    demais = [{"atributos": {"nome": "x", "grupo": "g"}, "geometria": _ponto()}
              for _ in range(limites.REPLICA_SINCRONIZAR_LOTE_MAX + 1)]
    r = sessao_a.post(f"/api/replicas/{replica['id']}/sincronizar",
                      json={"idempotencia": f"zt-teto-{uuid.uuid4()}",
                            "camadas": [{"camada_id": camada["id"], "adicionar": demais}]})
    assert r.status_code == 422, r.status_code
    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            contexto_a["tenant_id"], contexto_a["admin_id"])
    assert linhas == [], "lote acima do teto chegou a escrever"


def test_filtro_com_campo_de_fora_da_camada_e_recusado_na_criacao(sessao_a, fabrica, contexto_a):
    camada = _camada(fabrica, contexto_a)
    r = sessao_a.post("/api/replicas", json={"nome": "zt filtro", "camadas": [
        {"camada_id": camada["id"], "nome_gpkg": "f", "filtro": "tenant_id = 1"}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "filtro_invalido", r.json()


# ================================================================ cláusula 8
# "100 mil feições em réplica em tempo medido"
@pytest.mark.lento
def test_cem_mil_feicoes_em_replica_com_tempo_medido(
    sessao_a, fabrica, conexao_plat_app, contexto_a, replicas_criadas, tmp_path, medida
):
    import os

    from tests.api.test_rls import contexto as ctx_banco

    quantas = int(os.environ.get("PLAT_REPLICA_FEICOES", "100000"))
    camada = _camada(fabrica, contexto_a)
    dados = camada["dados"]
    ctx_banco(conexao_plat_app, contexto_a["tenant_id"], usuario_id=contexto_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        # carga por generate_series: o que se mede aqui é a EXPORTAÇÃO, não a inserção linha a linha pela API
        cur.execute(
            f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" (nome, grupo, geom) '
            f"SELECT 'f' || i, CASE WHEN i %% 2 = 0 THEN 'par' ELSE 'impar' END, "
            f"ST_SetSRID(ST_MakePoint(-46.5 + (i %% 1000)/10000.0, -23.5 + (i / 1000)/10000.0), 4674) "
            f"FROM generate_series(1, %s) i",
            (quantas,),
        )
        assert cur.rowcount == quantas
    conexao_plat_app.commit()

    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "grande"}])
    inicio = time.monotonic()
    resultado = gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    segundos = time.monotonic() - inicio
    assert resultado["feicoes"] == quantas, resultado

    caminho = _baixar(sessao_a, replica["id"], tmp_path)
    camadas = _abrir_no_gdal(caminho)
    assert camadas["grande"]["featureCount"] == quantas
    gravar = medida("L2-13-b-replicas-sincronizacao")
    gravar("replica_100k_segundos", round(segundos, 2), "s",
           "pytest tests/api/test_replicas.py::test_cem_mil_feicoes_em_replica_com_tempo_medido")
    gravar("replica_100k_feicoes", quantas, "feicoes", "generate_series + replicas.criar")
    gravar("replica_100k_pacote_bytes", resultado["bytes"], "bytes", "objetos.guardar do GeoPackage")
    gravar("replica_100k_carga_1min", os.getloadavg()[0], "carga",
           "os.getloadavg() no instante da medida (12 núcleos)")


# ================================================================ cláusula 9
# "QField abrindo o GeoPackage = teste manual registrado com data e versão (não bloqueia)"
def test_pacote_tem_a_forma_que_o_qfield_le(sessao_a, fabrica, contexto_a, replicas_criadas, tmp_path):
    """O QField lê GeoPackage por GDAL/QGIS. O que se pode PROVAR por máquina é a forma: driver GPKG,
    camada com índice espacial, geometria e CRS declarados, e as tabelas de atributo registradas em
    gpkg_contents (sem esse registro o QGIS não as lista). A abertura no aparelho é o teste manual
    registrado nas medidas do item, e não bloqueia o portão."""
    camada = _camada(fabrica, contexto_a)
    _adicionar(sessao_a, camada["id"], [{"atributos": {"nome": "p", "grupo": "g"}, "geometria": _ponto()}])
    replica = _criar_replica(sessao_a, replicas_criadas, [{"camada_id": camada["id"], "nome_gpkg": "qfield"}])
    gerar_pacote(replica["id"], contexto_a["tenant_id"], contexto_a["admin_id"])
    caminho = _baixar(sessao_a, replica["id"], tmp_path)

    camadas = _abrir_no_gdal(caminho)
    assert camadas["qfield"]["geometryFields"][0]["coordinateSystem"]["projjson"], camadas["qfield"]
    import sqlite3

    with sqlite3.connect(f"file:{caminho}?mode=ro", uri=True) as con:
        registradas = {n for (n,) in con.execute("SELECT table_name FROM gpkg_contents")}
        tipos = dict(con.execute("SELECT table_name, data_type FROM gpkg_contents"))
    assert {"qfield", "plat_sync", "plat_replica"} <= registradas, registradas
    assert tipos["qfield"] == "features" and tipos["plat_sync"] == "attributes", tipos
