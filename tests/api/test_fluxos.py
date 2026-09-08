"""API de gestão da fonte de fluxo (item L2-14-a-ingestao-de-fluxos): `/api/fluxos`.

Prova aqui: vocabulário fechado de tipo, validação da config por tipo (inclusive a recusa de SSRF na
entrada, não só na hora de conectar), esquema de destino GERADO do mapeamento, pausa e retomada, leitura e
expurgo dos eventos gravados, e o isolamento entre inquilinos (a fonte de B é 404 para A).
"""

import secrets

import pytest

from tests.api.conftest import PREFIXO_TESTE

MAPEAMENTO = {
    "campo_tempo": {"caminho": "ts", "tipo": "iso", "fuso": "America/Sao_Paulo"},
    "campo_rastro": "placa",
    "geometria": {"modo": "lonlat", "lon": "lon", "lat": "lat"},
    "campos": [{"caminho": "velocidade", "coluna": "velocidade", "tipo": "numero"}],
}


@pytest.fixture
def limpar(sessao_a):
    criadas = []
    yield criadas
    for fid in criadas:
        sessao_a.delete(f"/api/fluxos/{fid}")


def _criar(sessao, sufixo="", **extra):
    corpo = {"tipo": "http", "nome": f"{PREFIXO_TESTE}-fluxo-{sufixo or secrets.token_hex(3)}",
             "mapeamento": MAPEAMENTO}
    corpo.update(extra)
    return sessao.post("/api/fluxos", json=corpo)


def test_criar_com_esquema_de_destino_gerado(sessao_a, limpar):
    r = _criar(sessao_a, filtro="$velocidade > 40")
    assert r.status_code == 201, r.text
    fonte = r.json()
    limpar.append(fonte["id"])
    assert fonte["estado"] == "ativa"
    assert fonte["limite_eventos_s"] == 1000
    assert fonte["tem_credencial"] is False
    por_nome = {c["nome"]: c for c in fonte["esquema_destino"]}
    assert por_nome["velocidade"]["tipo"] == "numero"
    assert por_nome["tempo_evento"]["origem"] == "ts"
    assert por_nome["geom"]["tipo"] == "geometria"
    # tipo receptor traz o endereço para onde o remetente manda o evento
    assert fonte["endereco_receptor"].endswith(f"/fluxo/{fonte['id']}/eventos")
    assert fonte["metrica"]["recebidos"] == 0


def test_tipo_fora_do_vocabulario_e_422(sessao_a):
    assert _criar(sessao_a, tipo="kafka").status_code == 422


def test_nome_repetido_e_409(sessao_a, limpar):
    nome = f"{PREFIXO_TESTE}-fluxo-{secrets.token_hex(3)}"
    r = sessao_a.post("/api/fluxos", json={"tipo": "http", "nome": nome})
    limpar.append(r.json()["id"])
    assert sessao_a.post("/api/fluxos", json={"tipo": "http", "nome": nome.upper()}).status_code == 409


def test_config_de_mqtt_para_endereco_interno_e_recusada_na_entrada(sessao_a):
    """A defesa de SSRF do L6-02-a vale para MQTT, que nem HTTP fala: o que importa é o IP do host."""
    r = _criar(sessao_a, tipo="mqtt",
               config={"host": "127.0.0.1", "porta": 8155, "topico": "frota/#", "tls": False})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "url_insegura"


def test_config_de_sondagem_para_metadado_de_nuvem_e_recusada(sessao_a):
    r = _criar(sessao_a, tipo="sondagem", config={"url": "http://169.254.169.254/latest/meta-data/"})
    assert r.status_code == 422 and r.json()["erro"] == "url_insegura"


def test_config_de_websocket_cliente_exige_esquema_ws(sessao_a):
    r = _criar(sessao_a, tipo="websocket_cliente", config={"url": "https://exemplo.invalido/ws"})
    assert r.status_code == 422 and r.json()["erro"] == "url_insegura"


def test_config_sem_campo_obrigatorio_e_422(sessao_a):
    r = _criar(sessao_a, tipo="mqtt", config={"porta": 8883})
    assert r.status_code == 422 and r.json()["erro"] == "config_campo_obrigatorio"


def test_intervalo_de_sondagem_abaixo_do_minimo_e_422(sessao_a):
    r = _criar(sessao_a, tipo="sondagem",
               config={"url": "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35", "intervalo_s": 1})
    assert r.status_code == 422 and r.json()["erro"] == "config_fora_da_faixa"


def test_mapeamento_com_fuso_desconhecido_e_422(sessao_a):
    r = _criar(sessao_a, mapeamento={"campo_tempo": {"caminho": "ts", "tipo": "iso", "fuso": "Marte/Olimpo"}})
    assert r.status_code == 422 and r.json()["erro"] == "fuso_desconhecido"


def test_filtro_que_nao_compila_e_422(sessao_a):
    r = _criar(sessao_a, filtro="$velocidade >")
    assert r.status_code == 422 and r.json()["erro"] == "filtro_invalido"


def test_pausar_e_retomar(sessao_a, limpar):
    fonte = _criar(sessao_a).json()
    limpar.append(fonte["id"])
    r = sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"estado": "pausada"})
    assert r.status_code == 200 and r.json()["estado"] == "pausada"
    r = sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"estado": "ativa"})
    assert r.json()["estado"] == "ativa"


def test_editar_mapeamento_regera_o_esquema_de_destino(sessao_a, limpar):
    fonte = _criar(sessao_a).json()
    limpar.append(fonte["id"])
    r = sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"mapeamento": {
        "campo_tempo": {"caminho": "quando", "tipo": "epoch_ms"},
        "campos": [{"caminho": "temp", "coluna": "temperatura", "tipo": "numero"}]}})
    assert r.status_code == 200
    nomes = [c["nome"] for c in r.json()["esquema_destino"]]
    assert "temperatura" in nomes and "velocidade" not in nomes
    assert "geom" not in nomes  # mapeamento novo não declara geometria


def test_credencial_nunca_volta_na_resposta(sessao_a, limpar):
    fonte = _criar(sessao_a, credencial="senha-de-teste-do-broker").json()
    limpar.append(fonte["id"])
    assert fonte["tem_credencial"] is True
    assert "senha-de-teste-do-broker" not in str(sessao_a.get(f"/api/fluxos/{fonte['id']}").json())
    r = sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"remover_credencial": True})
    assert r.json()["tem_credencial"] is False


def test_simular_aplica_mapeamento_e_filtro_sem_gravar(sessao_a, limpar):
    fonte = _criar(sessao_a, filtro="$velocidade > 40").json()
    limpar.append(fonte["id"])
    r = sessao_a.post(f"/api/fluxos/{fonte['id']}/simular",
                      json={"ts": "2026-01-15T09:00:00", "placa": "AAA0A00", "lon": -46.6, "lat": -23.5,
                            "velocidade": 50})
    assert r.status_code == 200, r.text
    assert r.json()["aceito"] is True
    assert r.json()["tempo_evento"].startswith("2026-01-15T12:00:00")   # o fuso foi aplicado
    r = sessao_a.post(f"/api/fluxos/{fonte['id']}/simular",
                      json={"ts": "2026-01-15T09:00:00", "lon": 0, "lat": 0, "velocidade": 10})
    assert r.json() == {"aceito": False, "motivo": "filtro"} | {k: v for k, v in r.json().items()
                                                                if k not in ("aceito", "motivo")}
    assert r.json()["aceito"] is False and r.json()["motivo"] == "filtro"
    r = sessao_a.post(f"/api/fluxos/{fonte['id']}/simular", json={"ts": "não é data"})
    assert r.json()["aceito"] is False and r.json()["motivo"] == "tempo_invalido"
    assert sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["total"] == 0


def test_fonte_de_b_e_404_para_a(sessao_a, sessao_b):
    r = _criar(sessao_b)
    assert r.status_code == 201, r.text
    fonte = r.json()
    try:
        for pedido in (
            lambda: sessao_a.get(f"/api/fluxos/{fonte['id']}"),
            lambda: sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"nome": "invadida"}),
            lambda: sessao_a.delete(f"/api/fluxos/{fonte['id']}"),
            lambda: sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos"),
            lambda: sessao_a.post(f"/api/fluxos/{fonte['id']}/simular", json={"ts": "2026-01-01T00:00:00Z"}),
        ):
            assert pedido().status_code == 404
        assert fonte["id"] not in [f["id"] for f in sessao_a.get("/api/fluxos").json()["itens"]]
    finally:
        sessao_b.delete(f"/api/fluxos/{fonte['id']}")


def test_apagar_fonte_expurga_os_eventos(sessao_a, conexao_plat_app):
    """Não há chave estrangeira do evento para a fonte (custo por linha no lote): o expurgo é da rota, e
    é isso que este teste prova — sem ele, apagar a fonte deixaria evento órfão no banco."""
    from tests.api.test_rls import contexto, ids_por_slug

    r = _criar(sessao_a)
    assert r.status_code == 201, r.text
    fonte = r.json()
    tenant_a = ids_por_slug(conexao_plat_app)["demo"]
    with conexao_plat_app as con:
        cur = con.cursor()
        contexto(con, tenant_a, 0, "plat-fluxo")
        cur.execute(
            "INSERT INTO plat.fluxo_evento(tenant_id, fonte_id, rastro_id, tempo_evento, atributos) "
            "VALUES (%s, %s::uuid, 'AAA0A00', now(), '{}'::jsonb)", (tenant_a, fonte["id"]))
        con.commit()
    assert sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["total"] == 1
    assert sessao_a.delete(f"/api/fluxos/{fonte['id']}").status_code == 204
    tenant_a = ids_por_slug(conexao_plat_app)["demo"]
    with conexao_plat_app as con:
        cur = con.cursor()
        contexto(con, tenant_a, 0, "plat-fluxo")
        cur.execute("SELECT count(*) AS n FROM plat.fluxo_evento WHERE fonte_id = %s::uuid", (fonte["id"],))
        assert cur.fetchone()["n"] == 0


def test_expurgo_por_corte_de_tempo(sessao_a, conexao_plat_app, limpar):
    from tests.api.test_rls import contexto, ids_por_slug

    r = _criar(sessao_a)
    assert r.status_code == 201, r.text
    fonte = r.json()
    limpar.append(fonte["id"])
    tenant_a = ids_por_slug(conexao_plat_app)["demo"]
    with conexao_plat_app as con:
        cur = con.cursor()
        contexto(con, tenant_a, 0, "plat-fluxo")
        for quando in ("2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z"):
            cur.execute(
                "INSERT INTO plat.fluxo_evento(tenant_id, fonte_id, tempo_evento, recebido_em, atributos) "
                "VALUES (%s, %s::uuid, %s::timestamptz, %s::timestamptz, '{}'::jsonb)",
                (tenant_a, fonte["id"], quando, quando))
        con.commit()
    assert sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["total"] == 2
    r = sessao_a.delete(f"/api/fluxos/{fonte['id']}/eventos?antes_de=2026-03-01T00:00:00Z")
    assert r.status_code == 200 and r.json()["apagados"] == 1
    assert sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["total"] == 1


def test_leitura_por_rastro_e_janela(sessao_a, conexao_plat_app, limpar):
    from tests.api.test_rls import contexto, ids_por_slug

    r = _criar(sessao_a)
    assert r.status_code == 201, r.text
    fonte = r.json()
    limpar.append(fonte["id"])
    tenant_a = ids_por_slug(conexao_plat_app)["demo"]
    with conexao_plat_app as con:
        cur = con.cursor()
        contexto(con, tenant_a, 0, "plat-fluxo")
        for placa in ("AAA0A00", "BBB0B00"):
            cur.execute(
                "INSERT INTO plat.fluxo_evento(tenant_id, fonte_id, rastro_id, tempo_evento, recebido_em, "
                "geom, atributos) VALUES (%s, %s::uuid, %s, now(), now(), "
                "ST_SetSRID(ST_MakePoint(-46.6, -23.5), 4326), '{\"velocidade\": 42}'::jsonb)",
                (tenant_a, fonte["id"], placa))
        con.commit()
    todos = sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()
    assert todos["total"] == 2
    assert round(todos["itens"][0]["lon"], 4) == -46.6
    assert todos["itens"][0]["atributos"]["velocidade"] == 42
    um = sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos?rastro=AAA0A00").json()
    assert um["total"] == 1 and um["itens"][0]["rastro_id"] == "AAA0A00"
    assert sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos?desde=2099-01-01T00:00:00Z").json()["total"] == 0
    assert sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos?desde=ontem").status_code == 422


def test_id_que_nao_e_uuid_e_404(sessao_a):
    assert sessao_a.get("/api/fluxos/nao-e-uuid").status_code == 404
