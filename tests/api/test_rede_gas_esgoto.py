"""Gás e esgoto pela API (item L4-05-e-gas-e-esgoto).

Cláusulas do portão provadas aqui:
1. importação do esquema TEKSI: um GeoPackage com as duas camadas do projeto entra por
   `POST /api/rede/{id}/teksi` e vira feição no vocabulário do pacote `esgoto-teksi`
   (`test_importa_geopackage_teksi_com_as_200_feicoes`);
2. rede sintética de 200 elementos com cotas, jusante calculado pela cota concordando com a direção declarada
   em 100 % dos trechos (`test_escoamento_concorda_em_100_por_cento_dos_99_trechos`);
3. gás com o regulador como controlador de tier de pressão, inclusive a emenda entre tiers sem regulador
   (`test_gas_com_regulador_entre_tiers_passa` e `test_gas_acusa_regulador_que_eleva_pressao_e_emenda_sem_ele`).

Refutação do item ("adversário inverte a cota de um trecho e confere que o sistema marca contrafluxo como
erro, não muda a direção em silêncio") em `test_adversario_inverte_a_cota_e_nada_e_corrigido_em_silencio`."""

import pytest

from app.rede_utilidades import instalados
from tests.api.conftest import PREFIXO_TESTE
from tests.dados import gerar_esgoto

LON, LAT = -46.7000, -23.6000


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, limpar, disciplina, pacote, sufixo):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-{sufixo}", "disciplina": disciplina})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto(pacote),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _importar_teksi(sessao, rid, tmp_path):
    arquivo = tmp_path / "teksi.gpkg"
    gerar_esgoto.escrever_geopackage(arquivo)
    r = sessao.post(f"/api/rede/{rid}/teksi", content=arquivo.read_bytes(),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return r.json()


def _escoamento(sessao, rid):
    r = sessao.get(f"/api/rede/{rid}/esgoto/escoamento")
    assert r.status_code == 200, r.text
    return r.json()


def _linhas(sessao, rid):
    r = sessao.get(f"/api/rede/{rid}/feicoes/linhas", params={"limite": 500})
    assert r.status_code == 200, r.text
    return r.json()["itens"]


def test_importa_geopackage_teksi_com_as_200_feicoes(sessao_a, limpar_redes, tmp_path):
    rid = _criar_rede(sessao_a, limpar_redes, "esgoto", "esgoto-teksi", "teksi")
    resultado = _importar_teksi(sessao_a, rid, tmp_path)
    assert resultado["contagens"] == {"estruturas_lidas": 101, "trechos_lidos": 99, "ignoradas": 0}
    assert resultado["gravadas"] == {"pontos": 101, "linhas": 99}
    assert resultado["recusadas"] == []
    assert len(resultado["sha256"]) == 64
    # o importador diz em voz alta o que não sabe (subtipo), em vez de escolher em silêncio
    assert any(a["aviso"] == "tipo_padrao_do_grupo" for a in resultado["avisos"])
    r = sessao_a.get(f"/api/rede/{rid}")
    assert r.status_code == 200, r.text


def test_escoamento_concorda_em_100_por_cento_dos_99_trechos(sessao_a, limpar_redes, tmp_path):
    rid = _criar_rede(sessao_a, limpar_redes, "esgoto", "esgoto-teksi", "escoa")
    _importar_teksi(sessao_a, rid, tmp_path)
    conf = _escoamento(sessao_a, rid)
    assert conf["total"] == 99
    assert conf["conferidos"] == 99
    assert conf["conformes"] == 99
    assert conf["percentual_concordancia"] == 100.0
    assert conf["problemas"] == []
    assert conf["com_testemunha_nas_estruturas"] == 99
    assert conf["alterou_a_rede"] is False


def test_adversario_inverte_a_cota_e_nada_e_corrigido_em_silencio(sessao_a, limpar_redes, tmp_path):
    rid = _criar_rede(sessao_a, limpar_redes, "esgoto", "esgoto-teksi", "refuta")
    _importar_teksi(sessao_a, rid, tmp_path)
    alvo = _linhas(sessao_a, rid)[0]
    antes = next(item for item in _linhas(sessao_a, rid) if item["id"] == alvo["id"])
    invertidos = dict(antes["atributos"])
    invertidos["cota_montante"], invertidos["cota_jusante"] = (
        antes["atributos"]["cota_jusante"], antes["atributos"]["cota_montante"])
    r = sessao_a.post(f"/api/rede/{rid}/feicoes/linhas/applyEdits",
                      json={"updates": [{"attributes": {"id": alvo["id"], "atributos": invertidos}}]})
    assert r.status_code == 200, r.text
    assert r.json()["updateResults"][0]["success"] is True

    conf = _escoamento(sessao_a, rid)
    contrafluxo = [p for p in conf["problemas"] if p["erro"] == "contrafluxo"]
    assert len(contrafluxo) == 1, conf["problemas"]
    assert contrafluxo[0]["feicao_id"] == alvo["id"]
    assert contrafluxo[0]["sentido_por_cota"] == "jusante_para_montante"
    assert contrafluxo[0]["cota_jusante"] > contrafluxo[0]["cota_montante"]
    assert conf["conformes"] == 98
    assert conf["percentual_concordancia"] < 100.0
    assert conf["alterou_a_rede"] is False

    depois = next(item for item in _linhas(sessao_a, rid) if item["id"] == alvo["id"])
    assert depois["atributos"]["cota_montante"] == invertidos["cota_montante"]
    assert depois["atributos"]["cota_jusante"] == invertidos["cota_jusante"]
    assert depois["atributos"]["no_montante"] == antes["atributos"]["no_montante"]
    assert depois["atributos"]["no_jusante"] == antes["atributos"]["no_jusante"]
    # conferir de novo não muda nada: a conferência é leitura pura
    assert _escoamento(sessao_a, rid)["conformes"] == 98


def test_recalque_fica_fora_da_conta_e_trecho_sem_cota_e_acusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, limpar_redes, "esgoto", "esgoto-teksi", "bordas")
    adds = [
        {"attributes": {"grupo": "coletor", "tipo_codigo": 5,
                        "atributos": {"identificador": "REC-1", "cota_montante": 700.0,
                                      "cota_jusante": 706.0}},
         "geometry": {"paths": [[[LON, LAT], [LON + 0.001, LAT]]]}},
        {"attributes": {"grupo": "coletor", "tipo_codigo": 1,
                        "atributos": {"identificador": "SEM-COTA"}},
         "geometry": {"paths": [[[LON, LAT + 0.002], [LON + 0.001, LAT + 0.002]]]}},
    ]
    r = sessao_a.post(f"/api/rede/{rid}/feicoes/linhas/applyEdits", json={"adds": adds})
    assert r.status_code == 200, r.text
    assert all(x["success"] for x in r.json()["addResults"]), r.text

    conf = _escoamento(sessao_a, rid)
    assert conf["total"] == 2
    assert conf["sob_pressao"] == 1  # a linha de recalque sobe de propósito e não é conferida pela gravidade
    assert conf["conferidos"] == 0
    assert conf["percentual_concordancia"] is None
    assert [p["erro"] for p in conf["problemas"]] == ["cota_ausente"]


def _rede_gas_com_dois_tiers(sessao, limpar, sufixo, com_regulador, tier_montante="alta_pressao",
                             tier_jusante="media_pressao", lon=LON, lat=LAT):
    rid = _criar_rede(sessao, limpar, "gas", "gas-br", sufixo)
    adds = [
        {"attributes": {"grupo": "tubulacao_de_gas", "tipo_codigo": 2,
                        "atributos": {"identificador": "ALTA-1"}},
         "geometry": {"paths": [[[lon - 0.001, lat], [lon, lat]]]}},
        {"attributes": {"grupo": "tubulacao_de_gas", "tipo_codigo": 3,
                        "atributos": {"identificador": "MEDIA-1"}},
         "geometry": {"paths": [[[lon, lat], [lon + 0.001, lat]]]}},
    ]
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas/applyEdits", json={"adds": adds})
    assert r.status_code == 200, r.text
    assert all(x["success"] for x in r.json()["addResults"]), r.text
    if com_regulador:
        r = sessao.post(f"/api/rede/{rid}/feicoes/pontos/applyEdits", json={"adds": [
            {"attributes": {"grupo": "regulador", "tipo_codigo": 2,
                            "atributos": {"identificador": "REG-1", "tier_montante": tier_montante,
                                          "tier_jusante": tier_jusante}},
             "geometry": {"x": lon, "y": lat}},
        ]})
        assert r.status_code == 200, r.text
        assert all(x["success"] for x in r.json()["addResults"]), r.text
    return rid


def _pressao(sessao, rid):
    r = sessao.get(f"/api/rede/{rid}/gas/pressao")
    assert r.status_code == 200, r.text
    return r.json()


def test_gas_com_regulador_entre_tiers_passa(sessao_a, limpar_redes):
    rid = _rede_gas_com_dois_tiers(sessao_a, limpar_redes, "gas-ok", com_regulador=True)
    conf = _pressao(sessao_a, rid)
    assert conf["controladores"] == 1
    assert conf["controladores_conformes"] == 1
    assert conf["transicoes_sem_regulador"] == 0
    assert conf["problemas"] == []
    assert [t["codigo"] for t in conf["tiers"]] == ["transporte", "alta_pressao", "media_pressao",
                                                    "baixa_pressao"]
    assert conf["alterou_a_rede"] is False


def test_gas_acusa_regulador_que_eleva_pressao_e_emenda_sem_ele(sessao_a, limpar_redes):
    # regulador declarado ao contrário: recebe em média e entrega em alta
    rid = _rede_gas_com_dois_tiers(sessao_a, limpar_redes, "gas-sobe", com_regulador=True,
                                   tier_montante="media_pressao", tier_jusante="alta_pressao")
    conf = _pressao(sessao_a, rid)
    assert [p["erro"] for p in conf["problemas"]] == ["regulador_eleva_pressao"]
    assert conf["controladores_conformes"] == 0

    # duas tubulações de tiers diferentes emendadas sem controlador nenhum ao lado
    rid2 = _rede_gas_com_dois_tiers(sessao_a, limpar_redes, "gas-sem-reg", com_regulador=False)
    conf2 = _pressao(sessao_a, rid2)
    assert conf2["controladores"] == 0
    assert conf2["transicoes_sem_regulador"] == 1
    assert conf2["problemas"][0]["erro"] == "transicao_sem_regulador"
    assert {conf2["problemas"][0]["tier_montante"], conf2["problemas"][0]["tier_jusante"]} == {
        "alta_pressao", "media_pressao"}


def test_teksi_sem_pacote_recusa_dizendo_o_que_falta(sessao_a, limpar_redes, tmp_path):
    r = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-teksi-sem-pacote", "disciplina": "esgoto"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar_redes.append(rid)
    arquivo = tmp_path / "teksi.gpkg"
    gerar_esgoto.escrever_geopackage(arquivo)
    r = sessao_a.post(f"/api/rede/{rid}/teksi", content=arquivo.read_bytes(),
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "pacote_ausente"


def test_teksi_com_arquivo_que_nao_e_geopackage_recusa_com_422(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, limpar_redes, "esgoto", "esgoto-teksi", "teksi-lixo")
    r = sessao_a.post(f"/api/rede/{rid}/teksi", content=b"isto nao e um geopackage",
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] in ("nao_e_geopackage", "arquivo_ilegivel")


def test_rede_de_outro_inquilino_nao_aparece_em_nenhuma_das_tres_rotas(sessao_a, sessao_b, tmp_path):
    r = sessao_b.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-gas-esgoto-b", "disciplina": "esgoto"})
    assert r.status_code == 201, r.text
    rid_b = r.json()["id"]
    try:
        assert sessao_a.get(f"/api/rede/{rid_b}/esgoto/escoamento").status_code == 404
        assert sessao_a.get(f"/api/rede/{rid_b}/gas/pressao").status_code == 404
        arquivo = tmp_path / "teksi.gpkg"
        gerar_esgoto.escrever_geopackage(arquivo)
        r = sessao_a.post(f"/api/rede/{rid_b}/teksi", content=arquivo.read_bytes(),
                          headers={"Content-Type": "application/json"})
        assert r.status_code == 404, r.text
    finally:
        sessao_b.delete(f"/api/rede/{rid_b}")
