"""Portão do item L2-04-k-sync-replicas-esri: createReplica, synchronizeReplica, extractChanges,
replicas/replicaInfo, unRegisterReplica e o estado do job assíncrono do FeatureServer — todos sobre o
MESMO mecanismo de réplica do L2-13-b (app/replica/servico.py); este arquivo prova a FACHADA Esri.

Field Maps / ArcGIS Pro REAIS são teste manual PENDENTE (decisão D20 do dono: não há licença Esri
nesta máquina). O que se prova por máquina é o PROTOCOLO — as mesmas chamadas que o cliente Esri
faz, com o GeoPackage conferido pelo GDAL (como o Pro abre) e os estados do job forjados pelas
FUNÇÕES DO WORKER (plat.job_pegar / plat.job_terminar), que é o caminho real de produção.

A camada do serviço é citada como "0"; as outras camadas do inquilino, pelo uuid (extensão da casa,
declarada em docs/PARIDADE.md). O pacote sai por ogr/ogrinfo igual ao L2-13-b.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_replicas import (
    _adicionar,
    _editar_no_gpkg,
    _ponto,
    gerar_pacote,
)
from tests.api.test_rls import ids_por_slug

MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / "L2-04-k-sync-replicas-esri.json"

CAMPOS = [{"nome": "nome", "tipo": "text"}, {"nome": "grupo", "tipo": "text"}]


def _svc(item_id: str, resto: str = "") -> str:
    return f"/rest/services/{item_id}/FeatureServer{resto}"


# ---------------------------------------------------------------- fábricas (iguais ao L2-13-b)
class FabricaSemCorrida(FabricaCamada):
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


def _camada(fabrica, ctx, geometria="Point", campos=None):
    item_id, dados = fabrica.criar("demo", ctx["tenant_id"], ctx["admin_id"],
                                   campos=campos or CAMPOS, geometria=geometria)
    return {"id": item_id, "dados": dados}


@pytest.fixture
def replicas_criadas(sessao_a):
    criadas: list[str] = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/replicas/{rid}")


def _criar_replica_esri(sessao, item_id: str, camadas: list, registrar: list | None = None, **params) -> dict:
    corpo = {"layers": camadas, "dataFormat": "sqlite",
             "transportType": "esriTransportTypeUrl", "f": "json", **params}
    r = sessao.post(_svc(item_id, "/createReplica"), json=corpo)
    assert r.status_code == 200, r.text
    j = r.json()
    if registrar is not None and j.get("replicaID"):
        registrar.append(j["replicaID"])
    return j


# ================================================================ metadados
# cláusula: "campo syncEnabled/syncCapabilities nos metadados"
def test_metadados_do_servico_e_da_camada_anunciam_sync(sessao_a, fabrica, contexto_a):
    camada = _camada(fabrica, contexto_a)
    r = sessao_a.get(_svc(camada["id"]) + "?f=json")
    assert r.status_code == 200, r.text
    servico = r.json()
    assert servico["syncEnabled"] is True, servico
    assert servico["supportsDisconnectedEditing"] is True, servico
    assert servico["hasVersionedData"] is True, servico
    assert "Sync" in servico["capabilities"], servico["capabilities"]
    assert servico["syncModel"] == "perLayer", servico
    assert servico["syncCapabilities"] == {
        "createReplica": True, "synchronizeReplica": True,
        "extractChanges": True, "unRegisterReplica": True,
    }, servico["syncCapabilities"]

    r = sessao_a.get(_svc(camada["id"], "/0?f=json"))
    assert r.status_code == 200, r.text
    desc = r.json()
    assert "Sync" in desc["capabilities"], desc["capabilities"]
    assert desc["syncCanReturnChanges"] is True, desc
    assert desc["syncCapabilities"]["createReplica"] is True, desc
    assert desc["syncModel"] == "perLayer", desc


# ================================================================ cláusula 1
# "createReplica de 2 camadas com filtro devolve GeoPackage com as contagens do filtro"
def test_create_replica_de_duas_camadas_com_filtro_devolve_geopackage(
    sessao_a, fabrica, contexto_a, replicas_criadas, tmp_path
):
    c1 = _camada(fabrica, contexto_a)
    c2 = _camada(fabrica, contexto_a)
    _adicionar(sessao_a, c1["id"], [
        {"atributos": {"nome": f"a{i}", "grupo": "norte" if i < 3 else "sul"},
         "geometria": _ponto(-46.5 + i / 100)}
        for i in range(7)
    ])
    _adicionar(sessao_a, c2["id"], [
        {"atributos": {"nome": f"b{i}", "grupo": "sul"}, "geometria": _ponto(-46.0 + i / 100)}
        for i in range(4)
    ])

    j = _criar_replica_esri(
        sessao_a, c1["id"],
        ["0", c2["id"]],  # extensão da casa: "0" + uuid da segunda camada
        registrar=replicas_criadas,
        layerQueries={"0": {"where": "grupo = 'norte'"}},
        replicaName="zt-esri-duas",
    )
    assert j["transportType"] == "esriTransportTypeUrl", j
    assert j["responseType"] == "esriReplicaResponseTypeData", j
    assert j["syncModel"] == "perLayer", j
    assert {g["id"] for g in j["layerServerGens"]} == {0, c2["id"]}, j["layerServerGens"]
    assert all(g["serverGen"] > 0 for g in j["layerServerGens"]), j["layerServerGens"]
    rid = j["replicaID"]

    # o nome da tabela de cada camada no pacote vem do replicaInfo (id 0 e o uuid da segunda)
    info = sessao_a.get(_svc(c1["id"], f"/replicas/{rid}"))
    assert info.status_code == 200, info.text
    nome_por_id = {str(c["id"]): c["name"] for c in info.json()["layers"]}

    # o pacote baixa PELO URL que a resposta anuncia (caminho Esri, não o da casa)
    caminho_url = j["URL"].replace("http://testserver", "")
    r = sessao_a.get(caminho_url)
    assert r.status_code == 200, r.text
    caminho = tmp_path / "esri.gpkg"
    caminho.write_bytes(r.content)

    leitura = subprocess.run(["ogrinfo", "-ro", "-so", "-json", str(caminho)],
                             capture_output=True, text=True, timeout=180, check=False)
    assert leitura.returncode == 0, leitura.stderr
    d = json.loads(leitura.stdout)
    assert d["driverShortName"] == "GPKG", d["driverShortName"]
    contagens = {c["name"]: c["featureCount"] for c in d["layers"]}
    assert contagens[nome_por_id["0"]] == 3, contagens  # 7 feições, filtro grupo='norte' deixa 3
    assert contagens[nome_por_id[c2["id"]]] == 4, contagens  # sem filtro, a camada inteira
    # o nome da camada "0" deriva do título do item (mesma regra do pacote da casa)
    assert contagens.get("plat_sync") == 7, contagens


def test_create_replica_recusa_id_de_camada_desconhecido_com_corpo_esri(sessao_a, fabrica, contexto_a):
    camada = _camada(fabrica, contexto_a)
    r = sessao_a.post(_svc(camada["id"], "/createReplica"),
                      json={"layers": ["7"], "dataFormat": "sqlite",
                            "transportType": "esriTransportTypeUrl"})
    assert r.status_code == 404, r.text
    corpo = r.json()
    assert set(corpo) == {"error"}, corpo
    assert corpo["error"]["code"] == 404, corpo
    assert "camada_nao_encontrada" in corpo["error"]["message"], corpo


# ================================================================ cláusula 2
# "editar 10 feições fora e synchronizeReplica sobe e desce mudanças"
def test_synchronize_replica_sobe_dez_editadas_e_desce_o_que_o_servidor_mudou(
    sessao_a, fabrica, contexto_a, replicas_criadas, tmp_path
):
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"], [
        {"atributos": {"nome": f"orig{i}", "grupo": "g"}, "geometria": _ponto(-46.5 + i / 1000)}
        for i in range(15)
    ])
    j = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas,
                         replicaName="zt-esri-sinc")
    rid = j["replicaID"]

    # o cliente desconectado edita 10 feições NO GeoPackage (como o Pro faria)
    caminho = tmp_path / "sinc.gpkg"
    baixar = sessao_a.get(j["URL"].replace("http://testserver", ""))
    assert baixar.status_code == 200, baixar.text
    caminho.write_bytes(baixar.content)
    editadas = _editar_no_gpkg(caminho, _nome_gpkg_da_camada(caminho, camada["id"]), "editado-no-campo", 10)

    # e o servidor, no mesmo intervalo, altera uma e apaga outra
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes",
                      json={"atualizar": [{"id": ids[14], "versao": 1, "atributos": {"nome": "mudou-no-servidor"}}],
                            "apagar": [{"id": ids[13], "versao": 1}]})
    assert r.status_code == 200, r.text

    cliente_gen = next(g["serverGen"] for g in j["layerServerGens"] if g["id"] == 0)
    r = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"), json={
        "replicaID": rid,
        "syncDirection": "bidirectional",
        "replicaClientGen": cliente_gen,  # chave de idempotência do cliente (refutação vem depois)
        "edits": [{"id": "0", "features": {"updates": [
            {"globalId": f["globalid"], "versao": int(f["versao"]), "attributes": {"nome": f["nome"]}}
            for f in editadas
        ]}}],
    })
    assert r.status_code == 200, r.text
    saida = r.json()
    assert saida["responseType"] == "esriReplicaResponseTypeEdits", saida
    lote = saida["edits"][0]
    assert len(lote["features"]["updateResults"]) == 10, lote["features"]
    assert all(u["success"] for u in lote["features"]["updateResults"]), lote["features"]
    # a descida traz a alterada e a apagada do servidor, e NÃO devolve as 10 do próprio cliente
    por_id = {u.get("attributes", {}).get("globalid"): u for u in lote["features"]["updates"]}
    por_id.update({f["attributes"]["globalid"]: f for f in lote["features"].get("adds", [])})
    assert ids[14] in por_id and por_id[ids[14]]["attributes"]["nome"] == "mudou-no-servidor", por_id
    assert ids[13] in lote["features"]["deleteIds"], lote["features"]
    sobiram = {f["globalid"] for f in editadas}
    assert not (sobiram & {m for m in por_id}), "a réplica recebeu de volta a própria edição"
    # a geração devolvida avançou (o cliente guarda para a próxima extração)
    novo_gen = next(g["serverGen"] for g in saida["layerServerGens"] if g["id"] == 0)
    assert novo_gen > cliente_gen, saida["layerServerGens"]

    # e o servidor guarda o resultado: as 10 edições estão lá
    r = sessao_a.get(f"/api/camadas/{camada['id']}/feicoes/{editadas[0]['globalid']}")
    assert r.status_code == 200 and r.json()["atributos"]["nome"] == "editado-no-campo", r.text


def _nome_gpkg_da_camada(caminho: Path, camada_id: str) -> str:
    """O nome da tabela no GeoPackage para a camada "0" (deriva do título do item)."""
    import sqlite3

    with sqlite3.connect(f"file:{caminho}?mode=ro", uri=True) as con:
        nomes = [n for (n,) in con.execute("SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")]
    assert len(nomes) == 1, nomes
    return nomes[0]


# ================================================================ cláusula 3
# "duas réplicas editam a mesma feição: conflito detectado e resolvido pela política"
def _duas_replicas_na_mesma_feicao(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"],
                     [{"atributos": {"nome": "v1", "grupo": "g"}, "geometria": _ponto()}])
    r1 = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas,
                         replicaName="zt-esri-r1",
                             politicaConflito="servidor_vence")
    r2 = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas,
                         replicaName="zt-esri-r2",
                             politicaConflito="cliente_vence")
    # o servidor avança para v2 enquanto as duas réplicas estavam fora de rede com a versão 1
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes",
                      json={"atualizar": [{"id": ids[0], "versao": 1, "atributos": {"nome": "v2-servidor"}}]})
    assert r.status_code == 200, r.text
    return camada, ids[0], r1, r2


def test_conflito_entre_replicas_politica_servidor_vence(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada, gid, r1, _r2 = _duas_replicas_na_mesma_feicao(sessao_a, fabrica, contexto_a, replicas_criadas)
    r = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"), json={
        "replicaID": r1["replicaID"], "syncDirection": "upload",
        "edits": [{"id": "0", "features": {"updates": [
            {"globalId": gid, "versao": 1, "attributes": {"nome": "v1-cliente"}}]}}],
    })
    assert r.status_code == 200, r.text
    resultado = r.json()["edits"][0]["features"]["updateResults"][0]
    assert resultado["success"] is False, resultado
    assert "conflito" in resultado["error"]["description"], resultado
    leitura = sessao_a.get(f"/api/camadas/{camada['id']}/feicoes/{gid}")
    assert leitura.json()["atributos"]["nome"] == "v2-servidor", leitura.text


def test_conflito_entre_replicas_politica_cliente_vence(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada, gid, _r1, r2 = _duas_replicas_na_mesma_feicao(sessao_a, fabrica, contexto_a, replicas_criadas)
    r = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"), json={
        "replicaID": r2["replicaID"], "syncDirection": "upload",
        "edits": [{"id": "0", "features": {"updates": [
            {"globalId": gid, "versao": 1, "attributes": {"nome": "v2-cliente"}}]}}],
    })
    assert r.status_code == 200, r.text
    resultado = r.json()["edits"][0]["features"]["updateResults"][0]
    assert resultado["success"] is True, resultado
    leitura = sessao_a.get(f"/api/camadas/{camada['id']}/feicoes/{gid}")
    assert leitura.json()["atributos"]["nome"] == "v2-cliente", leitura.text


def test_update_de_feicao_apagada_no_servidor_e_conflito_sem_insert_silencioso(
    sessao_a, fabrica, contexto_a, replicas_criadas
):
    """Refutação: o cliente sobe um update para um globalid que não existe mais. É conflito
    ('apagada no servidor'), nunca um insert silencioso reconstruindo a feição."""
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"],
                     [{"atributos": {"nome": "viva", "grupo": "g"}, "geometria": _ponto()}])
    j = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas)
    r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json={"apagar": [{"id": ids[0], "versao": 1}]})
    assert r.status_code == 200, r.text

    fantasma = str(uuid.uuid4())
    r = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"), json={
        "replicaID": j["replicaID"], "syncDirection": "upload",
        "edits": [{"id": "0", "features": {"updates": [
            {"globalId": fantasma, "versao": 1, "attributes": {"nome": "ressuscitada"}}]}}],
    })
    assert r.status_code == 200, r.text
    resultado = r.json()["edits"][0]["features"]["updateResults"][0]
    assert resultado["success"] is False and "conflito" in resultado["error"]["description"], resultado
    dados = camada["dados"]
    linhas = fabrica.linhas(dados["schema"], dados["tabela"],
                            contexto_a["tenant_id"], contexto_a["admin_id"])
    assert linhas == [], "o update para globalid inexistente inseriu feição"


def test_update_sem_versao_e_recusado(sessao_a, fabrica, contexto_a, replicas_criadas):
    """Extensão da casa: update no protocolo Esri sem a versão lida do pacote é 400 — sem versão
    não há detecção de conflito, e conflito é cláusula do item."""
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"],
                     [{"atributos": {"nome": "x", "grupo": "g"}, "geometria": _ponto()}])
    j = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas)
    r = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"), json={
        "replicaID": j["replicaID"], "syncDirection": "upload",
        "edits": [{"id": "0", "features": {"updates": [{"globalId": ids[0], "attributes": {"nome": "sem-versao"}}]}}],
    })
    assert r.status_code == 400, r.text
    assert "versao_ausente" in r.json()["error"]["message"], r.text


# ================================================================ cláusula 4 (refutação)
# "mesma réplica 2× com o mesmo replicaClientGen: devolve a mesma resposta e aplica zero"
def test_mesmo_replica_client_gen_repetido_aplica_zero(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"],
                     [{"atributos": {"nome": "original", "grupo": "g"}, "geometria": _ponto()}])
    j = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas)
    cliente_gen = next(g["serverGen"] for g in j["layerServerGens"] if g["id"] == 0)
    corpo = {
        "replicaID": j["replicaID"], "syncDirection": "upload", "replicaClientGen": cliente_gen,
        "edits": [{"id": "0", "features": {"updates": [
            {"globalId": ids[0], "versao": 1, "attributes": {"nome": "uma-vez-so"}}]}}],
    }
    primeira = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"), json=corpo)
    assert primeira.status_code == 200, primeira.text
    segunda = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"), json=corpo)
    assert segunda.status_code == 200, segunda.text
    p, s = primeira.json(), segunda.json()
    assert s.get("repetida") is True, s
    assert s["edits"] == p["edits"], "a resposta repetida não é idêntica à original"
    assert s["layerServerGens"] == p["layerServerGens"], "a geração avançou num lote repetido"
    leitura = sessao_a.get(f"/api/camadas/{camada['id']}/feicoes/{ids[0]}")
    assert leitura.json()["atributos"]["nome"] == "uma-vez-so", leitura.text


# ================================================================ cláusula 5
# "extractChanges devolve só as mudanças após o serverGen"
def test_extract_changes_devolve_so_as_mudancas_apos_o_servergen(
    sessao_a, fabrica, contexto_a, replicas_criadas
):
    camada = _camada(fabrica, contexto_a)
    ids = _adicionar(sessao_a, camada["id"], [
        {"atributos": {"nome": f"e{i}", "grupo": "g"}, "geometria": _ponto(-46.5 + i / 100)}
        for i in range(3)
    ])
    j = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas)
    gen0 = next(g["serverGen"] for g in j["layerServerGens"] if g["id"] == 0)

    sessao_a.post(f"/api/camadas/{camada['id']}/edicoes",
                  json={"atualizar": [{"id": ids[1], "versao": 1, "atributos": {"nome": "trocada"}}]})

    def _extrair(**params):
        r = sessao_a.post(_svc(camada["id"], "/extractChanges"), json={
            "replicaID": j["replicaID"], "layerServerGens": [{"id": "0", "serverGen": gen0}], **params})
        assert r.status_code == 200, r.text
        return r.json()

    saida = _extrair()
    assert saida["responseType"] == "esriDataChangesResponseTypeEdits", saida
    lote = saida["edits"][0]["features"]
    assert len(lote["adds"]) == 0 and len(lote["updates"]) == 1, lote
    assert lote["updates"][0]["attributes"]["nome"] == "trocada", lote
    gen1 = saida["layerServerGens"][0]["serverGen"]
    assert gen1 > gen0, saida

    # no estado ATUAL não há mais nada
    r = sessao_a.post(_svc(camada["id"], "/extractChanges"), json={
        "replicaID": j["replicaID"], "layerServerGens": [{"id": "0", "serverGen": gen1}]})
    assert r.json()["edits"][0]["features"] == {"adds": [], "updates": [], "deleteIds": []}, r.text

    # returnUpdates=false tira o vetor (mesma geração, outro filtro)
    saida = _extrair(returnUpdates="false")
    assert saida["edits"][0]["features"]["updates"] == [], saida

    # e extractChanges NÃO é sincronização: o ponteiro da réplica não andou
    info = sessao_a.get(_svc(camada["id"], f"/replicas/{j['replicaID']}"))
    gen_ponteiro = next(g["serverGen"] for g in info.json()["layerServerGens"] if g["id"] == 0)
    assert gen_ponteiro == gen0, info.text


# ================================================================ cláusula 6
# "unregisterReplica remove o registro"
def test_unregister_replica_remove_o_registro(sessao_a, fabrica, contexto_a, replicas_criadas):
    camada = _camada(fabrica, contexto_a)
    _adicionar(sessao_a, camada["id"],
               [{"atributos": {"nome": "x", "grupo": "g"}, "geometria": _ponto()}])
    j = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas)
    rid = j["replicaID"]
    replicas_criadas.remove(rid) if rid in replicas_criadas else None

    lista = sessao_a.get(_svc(camada["id"], "/replicas"))
    assert lista.status_code == 200, lista.text
    assert any(x["replicaID"] == rid for x in lista.json()["replicas"]), lista.text

    r = sessao_a.post(_svc(camada["id"], "/unRegisterReplica"), json={"replicaID": rid})
    assert r.status_code == 200 and r.json() == {"success": True}, r.text

    assert sessao_a.get(_svc(camada["id"], f"/replicas/{rid}")).status_code == 404
    assert not any(x["replicaID"] == rid for x in sessao_a.get(_svc(camada["id"], "/replicas")).json()["replicas"])
    r = sessao_a.post(_svc(camada["id"], "/synchronizeReplica"),
                      json={"replicaID": rid, "syncDirection": "download", "edits": []})
    assert r.status_code == 404 and "replica_inexistente" in r.json()["error"]["message"], r.text
    # unregister de réplica que não existe mais: 404 de novo, nunca 500
    r = sessao_a.post(_svc(camada["id"], "/unRegisterReplica"), json={"replicaID": rid})
    assert r.status_code == 404, r.text


# ================================================================ cláusula 7
# "job assíncrono com estados esriJobSubmitted/Executing/Succeeded"
def _cur_worker(con):
    """Cursor do worker que reescreve `plat.` para o schema da trilha (PLAT_SCHEMA): a role do worker
    da trilha não tem USAGE no schema `plat` de produção — e não deveria ter."""
    return con.cursor(cursor_factory=CursorSchemaAmbiente)


def _con_worker(env):
    dsn = env.get("PLAT_DSN_WORKER")
    assert dsn, "PLAT_DSN_WORKER ausente no ambiente da trilha"
    return psycopg2.connect(dsn)


def test_job_assincrono_percorre_os_tres_estados(sessao_a, fabrica, contexto_a, replicas_criadas, env):
    camada = _camada(fabrica, contexto_a)
    _adicionar(sessao_a, camada["id"], [
        {"atributos": {"nome": f"j{i}", "grupo": "g"}, "geometria": _ponto()} for i in range(2)
    ])
    r = sessao_a.post(_svc(camada["id"], "/createReplica"),
                      json={"layers": ["0"], "async": True, "replicaName": "zt-esri-async"})
    assert r.status_code == 200, r.text
    j = r.json()
    # a resposta do submit também carrega replicaID/replicaName (extensão declarada): dá para
    # desistir com unRegisterReplica sem esperar o job
    assert {"statusUrl", "jobId", "replicaID"} <= set(j), j
    replicas_criadas.append(j["replicaID"])  # registrado cedo: falha no meio do teste não vaza réplica
    status_url = j["statusUrl"].replace("http://testserver", "")

    pendente = sessao_a.get(status_url).json()
    assert pendente["jobStatus"] == "esriJobSubmitted", pendente
    assert pendente["status"] == "Pending", pendente

    # o worker DE VERDADE pega o job (plat.job_pegar é SECURITY DEFINER do worker; se pegar outro
    # job da fila da trilha, devolve e tenta de novo — a fila é sequencial neste teste)
    jid = uuid.UUID(j["jobId"])
    con = _con_worker(env)
    pego = None
    terminou = False
    try:
        for _ in range(200):
            with _cur_worker(con) as cur:
                cur.execute("SELECT * FROM plat.job_pegar('teste-sync-esri', true)")
                pego = cur.fetchone()
            con.commit()
            if pego is None:
                time.sleep(0.1)
                continue
            if str(pego["id"]) == str(jid):  # o cursor devolve uuid como string
                break
            # conta_tentativa=true com espera 0: volta a pendente sem marcar falha
            # (o atalho conta_tentativa=false exige max_reinicios>0, senão devolve como falhou)
            with _cur_worker(con) as cur:
                cur.execute("SELECT plat.job_devolver(%s, 'teste-sync-esri', 'não é o meu', true, 0, 0, NULL)",
                            (pego["id"],))
            con.commit()
            pego = None
            time.sleep(0.1)
        assert pego is not None and str(pego["id"]) == str(jid), "o job não saiu da fila"

        em_execucao = sessao_a.get(status_url).json()
        assert em_execucao["jobStatus"] == "esriJobExecuting", em_execucao

        # a lógica do job roda pela MESMA tarefa registrada que o worker executa
        resultado = gerar_pacote(j["replicaID"], contexto_a["tenant_id"], contexto_a["admin_id"])
        assert resultado["feicoes"] == 2, resultado
        with _cur_worker(con) as cur:
            cur.execute("SELECT plat.job_terminar(%s, 'teste-sync-esri', 'concluido', %s, NULL, NULL)",
                        (str(jid), json.dumps(resultado)))
            assert cur.fetchone()["job_terminar"] is True
        con.commit()
        terminou = True
    finally:
        # um job 'rodando' sem término bloqueia a cota do inquilino (cota_jobs_simultaneos) e a
        # chave da réplica: se o teste falhar no meio, devolve o job antes de sair
        if pego is not None and str(pego["id"]) == str(jid) and not terminou:
            try:
                with _cur_worker(con) as cur:
                    cur.execute(
                        "SELECT plat.job_devolver(%s, 'teste-sync-esri', 'teste interrompido', true, 0, 0, NULL)",
                        (str(jid),))
                con.commit()
            except Exception:  # noqa: BLE001 — limpeza não pode esconder o erro original
                con.rollback()
        con.close()

    concluido = sessao_a.get(status_url).json()
    assert concluido["jobStatus"] == "esriJobSucceeded", concluido
    assert concluido["status"] == "Completed", concluido
    assert "/pacote" in concluido["resultUrl"], concluido
    # e a réplica ficou pronta: o pacote baixa pelo caminho Esri
    rid = concluido["resultUrl"].rsplit("/", 2)[-2]
    assert rid == j["replicaID"]
    pacote = sessao_a.get(_svc(camada["id"], f"/replicas/{rid}/pacote"))
    # GeoPackage é contentor SQLite: a mágica do arquivo é "SQLite format 3", não a de ZIP
    assert pacote.status_code == 200 and pacote.content[:15] == b"SQLite format 3", pacote.status_code


# ================================================================ cláusula 8 (refutação)
# "réplicas até o teto declarado por usuário"
def test_create_replica_acima_do_teto_do_usuario_e_413(sessao_a, fabrica, contexto_a, conexao_plat_app):
    from app import limites

    camada = _camada(fabrica, contexto_a)
    criadas: list[str] = []
    try:
        for _ in range(limites.REPLICA_POR_USUARIO):
            _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=criadas,
                                **{"async": True}, replicaName=f"zt-teto-{uuid.uuid4()}")
        r = sessao_a.post(_svc(camada["id"], "/createReplica"),
                          json={"layers": ["0"], "async": True})
        assert r.status_code == 413, r.text
        assert "replicas_demais" in r.json()["error"]["message"], r.text
    finally:
        for rid in criadas:
            sessao_a.delete(f"/api/replicas/{rid}")
        # o job pendente de cada createReplica assíncrono sobrevive à réplica (não há FK): sem esta
        # limpeza a fila acumula 20 jobs por execução e o teste do job assíncrono passa a devolver
        # lixo em vez do próprio job (job_pegar devolve sempre o mais velho)
        with conexao_plat_app.cursor(cursor_factory=CursorSchemaAmbiente) as cur:
            cur.execute("DELETE FROM plat.job WHERE tipo = 'replicas.criar' AND estado = 'pendente' "
                        "AND parametros->>'replica_id' = ANY(%s::text[])", (criadas,))
        conexao_plat_app.commit()


# ================================================================ medida
# "tempo medido" — createReplica síncrono de 200 feições, com a carga da máquina registrada ao lado
@pytest.mark.lento
def test_medida_create_replica_de_200_feicoes(sessao_a, fabrica, contexto_a, replicas_criadas, tmp_path, medida):
    if os.getloadavg()[0] > 8.0:
        pytest.skip(f"carga de 1 min = {os.getloadavg()[0]:.2f} passou de 8: número sob disputa não prova nada")
    camada = _camada(fabrica, contexto_a)
    _adicionar(sessao_a, camada["id"], [
        {"atributos": {"nome": f"m{i}", "grupo": "par" if i % 2 == 0 else "impar"},
         "geometria": _ponto(-46.5 + i / 10000, -23.5 + i / 10000 % 1)}
        for i in range(200)
    ])
    inicio = time.monotonic()
    j = _criar_replica_esri(sessao_a, camada["id"], ["0"], registrar=replicas_criadas,
                            replicaName="zt-esri-medida")
    segundos = time.monotonic() - inicio
    pacote = sessao_a.get(j["URL"].replace("http://testserver", ""))
    assert pacote.status_code == 200, pacote.text

    gravar = medida("L2-04-k-sync-replicas-esri")
    comando = (f"pytest tests/api/test_sync_esri.py::test_medida_create_replica_de_200_feicoes "
               f"[carga_1min={os.getloadavg()[0]:.2f}; ram_livre_gb="
               f"{(os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')) / 2**30:.1f}; "
               f"medido_em={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}]")
    gravar("esri_create_replica_200f_segundos", round(segundos, 3), "s", comando)
    gravar("esri_create_replica_200f_bytes", len(pacote.content), "bytes", comando)
    assert segundos < 30, segundos
