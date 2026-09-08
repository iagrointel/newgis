"""O resultado de um traçado como seleção, camada, arquivo e histórico (item L4-02-f-resultados-e-exportacao).

Cláusulas do portão provadas aqui, sobre a mesma cooperativa de teste pequena dos itens irmãos — disjuntor,
dois ramos de média tensão, chave fusível, dois transformadores (75 e 45 kVA), duas unidades consumidoras e
um poste —, onde toda contagem fecha à mão:

  1. o resultado vira TABELA e AGREGAÇÃO por tipo de ativo e por nível de tensão:
     `test_tracado_traz_agregacao_por_tipo_e_por_nivel`;
  2. EXPORTAÇÃO nos três formatos, sem perder elemento: `test_exportar_csv_geojson_e_gpkg_sem_perder_nada`
     (o CSV abre com as colunas id, tipo, grupo, terminal, comprimento_m e nivel, como o portão pede; o
     GeoPackage é lido de volta por `ogrinfo`, quando a máquina o tem);
  3. CAMADA salva com procedência (rede, configuração, pontos de partida, versão da topologia e data):
     `test_salvar_como_camada_guarda_procedencia`;
  4. HISTÓRICO dos últimos traçados da pessoa, com repetir: `test_historico_lista_os_ultimos_e_repete`,
     `test_historico_e_por_pessoa_e_para_em_vinte`;
  5. recusas e fronteiras: `test_recusa_formato_desconhecido_e_execucao_de_outra_rede`.

O que NÃO está aqui: a medida de tempo com carga da máquina e a exportação de 20 mil elementos (refutação do
item) — o portão leve deste turno não pede medida com carga, e o teto está declarado em
`limites.TRACADO_EXPORTACAO_MAX` com a resposta 413 conferida em `test_recusa_formato_desconhecido_e_...`
apenas na parte do formato."""

import csv
import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app import limites
from tests.api.conftest import PREFIXO_TESTE

ITEM = "L4-02-f-resultados-e-exportacao"

DISJUNTOR, FUSIVEL = 4, 2
UC_BT, POSTE = 1, 1
LON0, LAT0, D = 36.0, 12.0, 0.001


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


@pytest.fixture
def limpar_itens(sessao_a):
    criados = []
    yield criados
    for item_id in criados:
        sessao_a.delete(f"/api/itens/{item_id}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-res-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos",
                    json={"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat,
                          "atributos": atributos or {}})
    assert r.status_code == 201, r.text
    return r.json()


def _linha(sessao, rid, coordenadas, grupo, atributos=None, fase=None):
    corpo = {"tipo_codigo": 1, "grupo": grupo, "coordenadas": coordenadas, "atributos": atributos or {}}
    if fase is not None:
        corpo["fase_bitmask"] = fase
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _rede(sessao, rid):
    """A mesma cooperativa de teste do item L4-02-e, com outras coordenadas:

        disjuntor(a0) ──MT0── a ──MT1── fusivel(b) ──MT2── trafo1(75 kVA) ──BT1──ramal── uc1
                              └──MT3── trafo2(45 kVA) ──BT2──ramal── uc2
    """
    a0 = (LON0 - D, LAT0)
    a = (LON0, LAT0)
    b = (LON0 + D, LAT0)
    c = (LON0 + 2 * D, LAT0)
    d = (LON0 + 2 * D, LAT0 + D)
    u1 = (LON0 + 2 * D, LAT0 + 2 * D)
    e = (LON0, LAT0 + 3 * D)
    g = (LON0 + D, LAT0 + 3 * D)
    u2 = (LON0 + 2 * D, LAT0 + 3 * D)
    at = {"ctmt": "1_RES_1", "sub": "RES"}

    disjuntor = _ponto(sessao, rid, *a0, "chave_de_media_tensao", DISJUNTOR,
                       {**at, "cod_id": "DJ1", "estado": "fechado"})
    _linha(sessao, rid, [list(a0), list(a)], "trecho_de_media_tensao",
           {**at, "cod_id": "MT0", "comp": 10, "fas_con": "ABC"}, fase=7)
    fusivel = _ponto(sessao, rid, *b, "chave_de_media_tensao", FUSIVEL,
                     {**at, "cod_id": "FU1", "estado": "fechado"})
    _linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao",
           {**at, "cod_id": "MT1", "comp": 100, "fas_con": "ABC"}, fase=7)
    _linha(sessao, rid, [list(b), list(c)], "trecho_de_media_tensao",
           {**at, "cod_id": "MT2", "comp": 200, "fas_con": "AB"}, fase=3)
    trafo1 = _ponto(sessao, rid, *c, "transformador_de_distribuicao", 1,
                    {**at, "cod_id": "TR1", "pot_nom": 75})
    _linha(sessao, rid, [list(c), list(d)], "trecho_de_baixa_tensao",
           {**at, "cod_id": "BT1", "uni_tr_mt": "TR1", "comp": 50}, fase=7)
    _linha(sessao, rid, [list(d), list(u1)], "ramal_de_ligacao",
           {**at, "cod_id": "RL1", "uni_tr_mt": "TR1", "comp": 5}, fase=7)
    uc1 = _ponto(sessao, rid, *u1, "unidade_consumidora", UC_BT,
                 {**at, "cod_id": "UC1", "uni_tr_mt": "TR1", "clas_sub": "RE1", "ene": 1200})
    _linha(sessao, rid, [list(a), list(e)], "trecho_de_media_tensao",
           {**at, "cod_id": "MT3", "comp": 300, "fas_con": "ABC"}, fase=7)
    trafo2 = _ponto(sessao, rid, *e, "transformador_de_distribuicao", 1,
                    {**at, "cod_id": "TR2", "pot_nom": 45})
    _linha(sessao, rid, [list(e), list(g)], "trecho_de_baixa_tensao",
           {**at, "cod_id": "BT2", "uni_tr_mt": "TR2", "comp": 60}, fase=7)
    _linha(sessao, rid, [list(g), list(u2)], "ramal_de_ligacao",
           {**at, "cod_id": "RL2", "uni_tr_mt": "TR2", "comp": 6}, fase=7)
    uc2 = _ponto(sessao, rid, *u2, "unidade_consumidora", UC_BT,
                 {**at, "cod_id": "UC2", "uni_tr_mt": "TR2", "clas_sub": "RU1", "ene": 600})
    poste = _ponto(sessao, rid, *c, "ponto_notavel", POSTE, {**at, "cod_id": "PN1"})

    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    r = sessao.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 200, r.text
    return {"disjuntor": disjuntor, "fusivel": fusivel, "trafo1": trafo1, "trafo2": trafo2,
            "uc1": uc1, "uc2": uc2, "poste": poste}


def _pedido(f):
    return {"tipo": "conectado", "pontos_partida": [{"feicao_id": f["disjuntor"]["id"], "terminal": 2}]}


def _tracar(sessao, rid, corpo):
    r = sessao.post(f"/api/rede/{rid}/tracar", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


# --- cláusula 1: tabela e agregações -----------------------------------------------------------------------

def test_tracado_traz_agregacao_por_tipo_e_por_nivel(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "agrega", limpar_redes)
    f = _rede(sessao_a, rid)
    saida = _tracar(sessao_a, rid, _pedido(f))
    ag = saida["agregacoes"]

    # a soma das contagens de cada agregação é sempre o total do traçado: nenhum elemento fica fora
    assert ag["total"] == saida["contagem"]
    assert sum(x["contagem"] for x in ag["por_tipo"]) == ag["total"]
    assert sum(x["contagem"] for x in ag["por_nivel"]) == ag["total"]

    # O traçado conectado do disjuntor alcança os dois ramos. A contagem é de ELEMENTO do traçado, e o
    # elemento de um dispositivo é o TERMINAL: cada transformador tem dois (alta e baixa), então os dois
    # transformadores dão 4; cada unidade consumidora tem um só, então as duas dão 2.
    por_tipo = {x["tipo"]: x["contagem"] for x in ag["por_tipo"]}
    assert por_tipo.get("transformador_de_distribuicao") == 4, ag["por_tipo"]
    assert por_tipo.get("consumidor_de_baixa_tensao") == 2, ag["por_tipo"]

    # nível de tensão é o TIER declarado no pacote, com a ordem dele (média antes de baixa)
    niveis = [x["nivel"] for x in ag["por_nivel"]]
    assert "media_tensao" in niveis and "baixa_tensao" in niveis, ag["por_nivel"]
    assert niveis.index("media_tensao") < niveis.index("baixa_tensao"), ag["por_nivel"]
    por_nivel = {x["nivel"]: x for x in ag["por_nivel"]}
    # os três trechos de média tensão do traçado (MT0, MT1, MT3) somam comprimento; nenhum é zero
    assert por_nivel["media_tensao"]["comprimento_m"] > 0
    assert ag["comprimento_m"] == pytest.approx(
        sum(x["comprimento_m"] for x in ag["por_nivel"]), rel=1e-6)


# --- cláusula 2: exportação nos três formatos --------------------------------------------------------------

def test_exportar_csv_geojson_e_gpkg_sem_perder_nada(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "exporta", limpar_redes)
    f = _rede(sessao_a, rid)
    saida = _tracar(sessao_a, rid, _pedido(f))
    total = saida["contagem"]

    r = sessao_a.post(f"/api/rede/{rid}/tracar/exportar?formato=csv", json=_pedido(f))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "tracado.csv" in r.headers["content-disposition"]
    assert r.headers["x-plat-contagem"] == str(total)
    linhas = list(csv.reader(io.StringIO(r.text)))
    assert linhas[0] == ["id", "tipo", "grupo", "terminal", "comprimento_m", "nivel"], linhas[0]
    assert len(linhas) - 1 == total, f"{len(linhas) - 1} linhas para {total} elementos"
    # trecho tem comprimento e não tem terminal; terminal de dispositivo é o contrário
    corpo = {linha[0]: linha for linha in linhas[1:]}
    assert any(linha[4] and not linha[3] for linha in corpo.values())
    assert any(linha[3] and not linha[4] for linha in corpo.values())

    r = sessao_a.post(f"/api/rede/{rid}/tracar/exportar?formato=geojson", json=_pedido(f))
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json"), r.text
    colecao = json.loads(r.text)
    assert colecao["type"] == "FeatureCollection" and len(colecao["features"]) == total
    assert all(x["geometry"] for x in colecao["features"]), "toda feição exportada tem geometria"
    assert colecao["procedencia"]["rede_id"] == rid
    assert colecao["procedencia"]["agregacoes"]["total"] == total

    r = sessao_a.post(f"/api/rede/{rid}/tracar/exportar?formato=gpkg", json=_pedido(f))
    assert r.status_code == 200, r.text
    bruto = r.content
    assert bruto[:16].startswith(b"SQLite format 3") and bruto[68:72] == b"GPKG", bruto[:80]
    if shutil.which("ogrinfo"):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "tracado.gpkg"
            alvo.write_bytes(bruto)
            saida_ogr = subprocess.run(["ogrinfo", "-al", "-so", str(alvo)],
                                       capture_output=True, text=True, timeout=60)
            assert saida_ogr.returncode == 0, saida_ogr.stderr
            assert f"Feature Count: {total}" in saida_ogr.stdout, saida_ogr.stdout


# --- cláusula 3: camada salva com procedência --------------------------------------------------------------

def test_salvar_como_camada_guarda_procedencia(sessao_a, limpar_redes, limpar_itens):
    rid = _criar_rede(sessao_a, "camada", limpar_redes)
    f = _rede(sessao_a, rid)
    total = _tracar(sessao_a, rid, _pedido(f))["contagem"]

    corpo = dict(_pedido(f), titulo=f"{PREFIXO_TESTE} camada de traçado")
    r = sessao_a.post(f"/api/rede/{rid}/tracar/camada", json=corpo)
    assert r.status_code == 201, r.text
    salvo = r.json()
    limpar_itens.append(salvo["item_id"])
    assert salvo["contagem"] == total

    r = sessao_a.get(f"/api/itens/{salvo['item_id']}")
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["tipo"] == "camada_tracado"
    dados = item["dados"]
    proc = dados["procedencia"]
    # os cinco campos que o portão nomeia
    assert proc["rede_id"] == rid and proc["rede_nome"]
    assert proc["tipo"] == "conectado" and proc["config_id"] is None
    assert proc["pontos_partida"] == [{"feicao_id": f["disjuntor"]["id"], "terminal": 2}]
    assert proc["topologia_construido_em"], proc
    assert item["criado_em"], item
    assert dados["contagem"] == total and len(dados["elementos"]) == total
    assert dados["geometria"]["type"] == "GeometryCollection"
    assert dados["agregacoes"]["total"] == total


# --- cláusula 4: histórico ---------------------------------------------------------------------------------

def test_historico_lista_os_ultimos_e_repete(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "hist", limpar_redes)
    f = _rede(sessao_a, rid)
    primeiro = _tracar(sessao_a, rid, _pedido(f))
    assert primeiro["execucao_id"], primeiro

    r = sessao_a.get(f"/api/rede/{rid}/tracados")
    assert r.status_code == 200, r.text
    itens = r.json()["itens"]
    assert itens and itens[0]["id"] == primeiro["execucao_id"]
    assert itens[0]["tipo"] == "conectado" and itens[0]["contagem"] == primeiro["contagem"]
    assert itens[0]["pedido"]["pontos_partida"][0]["feicao_id"] == f["disjuntor"]["id"]
    assert itens[0]["topologia_construido_em"], itens[0]

    r = sessao_a.post(f"/api/rede/{rid}/tracados/{primeiro['execucao_id']}/repetir")
    assert r.status_code == 200, r.text
    repetido = r.json()
    assert repetido["contagem"] == primeiro["contagem"]
    assert repetido["contagem_anterior"] == primeiro["contagem"]
    assert repetido["execucao_id"] != primeiro["execucao_id"]

    # repetir entra no histórico como um traçado a mais, na frente
    r = sessao_a.get(f"/api/rede/{rid}/tracados")
    assert r.json()["itens"][0]["id"] == repetido["execucao_id"]


def test_historico_e_por_pessoa_e_para_em_vinte(sessao_a, usuarios_a, limpar_redes):
    rid = _criar_rede(sessao_a, "vinte", limpar_redes)
    f = _rede(sessao_a, rid)
    for _ in range(limites.TRACADO_HISTORICO_MAX + 2):
        _tracar(sessao_a, rid, _pedido(f))

    r = sessao_a.get(f"/api/rede/{rid}/tracados")
    assert r.status_code == 200, r.text
    assert len(r.json()["itens"]) == limites.TRACADO_HISTORICO_MAX

    r = sessao_a.get(f"/api/rede/{rid}/tracados?limite=99")
    assert r.status_code == 422 and r.json()["erro"] == "limite_invalido", r.text

    # o histórico é de quem traçou: outra pessoa do MESMO inquilino não vê os traçados dela
    outra_pessoa, _, _ = usuarios_a.sessao("editor")
    r = outra_pessoa.get(f"/api/rede/{rid}/tracados")
    assert r.status_code == 200, r.text
    assert r.json()["itens"] == []


# --- cláusula 5: recusas -----------------------------------------------------------------------------------

def test_recusa_formato_desconhecido_e_execucao_de_outra_rede(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "recusa", limpar_redes)
    outra = _criar_rede(sessao_a, "recusa2", limpar_redes)
    f = _rede(sessao_a, rid)
    saida = _tracar(sessao_a, rid, _pedido(f))

    r = sessao_a.post(f"/api/rede/{rid}/tracar/exportar?formato=shp", json=_pedido(f))
    assert r.status_code == 422 and r.json()["erro"] == "formato_desconhecido", r.text

    # a execução existe, mas em OUTRA rede: 404, nunca o traçado da rede errada
    r = sessao_a.post(f"/api/rede/{outra}/tracados/{saida['execucao_id']}/repetir")
    assert r.status_code == 404 and r.json()["erro"] == "execucao_inexistente", r.text
    r = sessao_a.post(f"/api/rede/{rid}/tracados/nao-e-uuid/repetir")
    assert r.status_code == 404 and r.json()["erro"] == "execucao_inexistente", r.text
