"""Receptor de eventos do processo plat-fluxo (item L2-14-a-ingestao-de-fluxos), com o registro de fontes e
a fila reais, gravando na base da trilha.

Cláusulas do portão exercidas aqui:
  - fonte HTTP recebe o simulador de 100 veículos a 1 evento/s e a tabela cresce na taxa esperada;
  - filtro na entrada descarta e conta; mapeamento com fuso converte;
  - token de A não escreve em fonte de B;
  - fonte pausada não perde evento do WebSocket por 30 s (buffer declarado).

O receptor é montado em processo (`app.fluxo.receptor.criar`) e chamado por um cliente de teste ASGI: é o
MESMO objeto que o `plat-fluxo` sobe com uvicorn, sem porta e sem espera de subida.
"""

import datetime
import json
import secrets
import time

import pytest
from starlette.testclient import TestClient

from app import limites
from app.fluxo import receptor as mod_receptor
from app.fluxo.fila import Fila
from app.fluxo.fontes import Registro
from tests.api.conftest import PREFIXO_TESTE

UTC = datetime.UTC
MAPEAMENTO = {
    "campo_tempo": {"caminho": "ts", "tipo": "iso", "fuso": "America/Sao_Paulo"},
    "campo_rastro": "placa",
    "geometria": {"modo": "lonlat", "lon": "lon", "lat": "lat"},
    "campos": [{"caminho": "velocidade", "coluna": "velocidade", "tipo": "numero"}],
}


# ------------------------------------------------------------------ apoio
def _criar_fonte(sessao, tipo="http", **extra):
    corpo = {"tipo": tipo, "nome": f"{PREFIXO_TESTE}-recep-{secrets.token_hex(4)}", "mapeamento": MAPEAMENTO}
    corpo.update(extra)
    r = sessao.post("/api/fluxos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _token(sessao, escopos):
    r = sessao.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-fluxo-{secrets.token_hex(3)}",
                                         "escopos": escopos})
    assert r.status_code == 201, r.text
    return r.json()


def _evento(i=0, **troca):
    base = {"ts": "2026-01-15T09:00:00", "placa": f"AAA{i:04d}", "lon": -46.6, "lat": -23.5, "velocidade": 50}
    base.update(troca)
    return base


@pytest.fixture
def ambiente():
    """Registro + fila reais e o receptor montado em cima deles. Nada é gravado sem `escrever()`."""
    registro, fila = Registro(), Fila()
    cliente = TestClient(mod_receptor.criar(registro, fila))
    yield registro, fila, cliente
    cliente.close()


def _escrever(registro, fila):
    return fila.escrever_uma_vez(registro.contexto_do_inquilino)


def _contar(sessao, fonte_id, **params):
    consulta = "&".join(f"{k}={v}" for k, v in params.items())
    return sessao.get(f"/api/fluxos/{fonte_id}/eventos" + (f"?{consulta}" if consulta else "")).json()["total"]


# ------------------------------------------------------------------ caminho feliz
def test_evento_http_atravessa_ate_a_tabela_com_o_fuso_aplicado(sessao_a, ambiente):
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=[_evento(1)],
                         headers={"Authorization": f"Bearer {token['token']}"})
        assert r.status_code == 202, r.text
        assert r.json()["aceitos"] == 1
        assert _escrever(registro, fila) == 1
        eventos = sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["itens"]
        assert eventos[0]["rastro_id"] == "AAA0001"
        assert eventos[0]["tempo_evento"].startswith("2026-01-15T12:00:00")  # 09:00 em São Paulo = 12:00 UTC
        assert round(eventos[0]["lon"], 4) == -46.6
        assert eventos[0]["atributos"]["velocidade"] == 50
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_simulador_de_cem_veiculos_a_um_evento_por_segundo(sessao_a, ambiente):
    """Cláusula do portão: 'fonte HTTP ... recebe o simulador de 100 veículos a 1 evento/s cada e a tabela
    cresce na taxa esperada'. O simulador manda os 100 veículos de uma vez por segundo (é como um coletor
    de frota entrega), por 3 segundos; a tabela tem de crescer 100 por segundo, sem perda."""
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a, limite_eventos_s=500)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    cabecalhos = {"Authorization": f"Bearer {token['token']}"}
    try:
        crescimento = []
        for segundo in range(3):
            agora = datetime.datetime.now(UTC).isoformat()
            lote = [_evento(v, ts=agora) for v in range(100)]
            r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=lote, headers=cabecalhos)
            assert r.status_code == 202 and r.json()["aceitos"] == 100, r.text
            _escrever(registro, fila)
            crescimento.append(_contar(sessao_a, fonte["id"]))
            if segundo < 2:
                time.sleep(1.0)
        assert crescimento == [100, 200, 300], f"a tabela não cresceu 100/s: {crescimento}"
        metrica = fila.conta(fonte["id"]).instantaneo()
        assert metrica["aceitos"] == 300 and metrica["recebidos"] == 300
        assert metrica["descartados_limite"] == 0 and metrica["descartados_invalido"] == 0
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_filtro_na_entrada_descarta_conta_e_nao_grava(sessao_a, ambiente):
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a, filtro="$velocidade > 40")
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        lote = [_evento(1, velocidade=50), _evento(2, velocidade=10), _evento(3, velocidade=5)]
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=lote,
                         headers={"Authorization": f"Bearer {token['token']}"})
        assert r.json()["aceitos"] == 1 and r.json()["descartados_filtro"] == 2
        _escrever(registro, fila)
        assert _contar(sessao_a, fonte["id"]) == 1
        # a métrica vai para o banco e aparece na tela da fonte
        fila.gravar_metricas(registro.contexto_do_inquilino, registro.inquilino_da_fonte)
        metrica = sessao_a.get(f"/api/fluxos/{fonte['id']}").json()["metrica"]
        assert metrica["recebidos"] == 3 and metrica["aceitos"] == 1 and metrica["descartados_filtro"] == 2
        assert metrica["atraso_ms_ultimo"] is not None
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_formatos_csv_e_geojson_pelo_tipo_de_conteudo(sessao_a, ambiente):
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    cabecalhos = {"Authorization": f"Bearer {token['token']}"}
    try:
        csv = b"ts,placa,lon,lat,velocidade\n2026-01-15T09:00:00,CSV0001,-46.6,-23.5,33\n"
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", content=csv,
                         headers={**cabecalhos, "Content-Type": "text/csv"})
        assert r.status_code == 202 and r.json()["aceitos"] == 1, r.text
        geojson = json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"ts": "2026-01-15T09:00:00", "placa": "GEO0001", "lon": -46.6,
                                               "lat": -23.5, "velocidade": 44},
             "geometry": {"type": "Point", "coordinates": [-46.6, -23.5]}}]}).encode()
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", content=geojson,
                         headers={**cabecalhos, "Content-Type": "application/geo+json"})
        assert r.status_code == 202 and r.json()["aceitos"] == 1, r.text
        _escrever(registro, fila)
        placas = {e["rastro_id"] for e in sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["itens"]}
        assert placas == {"CSV0001", "GEO0001"}
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


# ------------------------------------------------------------------ isolamento
def test_token_de_a_nao_escreve_em_fonte_de_b(sessao_a, sessao_b, ambiente):
    """Cláusula do portão. O 404 (e não 403) é de propósito: a existência do id de outro inquilino não vaza."""
    registro, fila, cliente = ambiente
    fonte_b = _criar_fonte(sessao_b)
    token_a = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        r = cliente.post(f"/fluxo/{fonte_b['id']}/eventos", json=[_evento(1)],
                         headers={"Authorization": f"Bearer {token_a['token']}"})
        assert r.status_code == 404, r.text
        assert r.json()["erro"] == "fonte_inexistente"
        assert _escrever(registro, fila) == 0
        assert _contar(sessao_b, fonte_b["id"]) == 0
    finally:
        sessao_a.delete(f"/api/tokens/{token_a['id']}")
        sessao_b.delete(f"/api/fluxos/{fonte_b['id']}")


def test_token_sem_o_escopo_de_escrita_e_403(sessao_a, ambiente):
    registro, _, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    token = _token(sessao_a, ["catalogo:ler"])
    registro.carregar()
    try:
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=[_evento()],
                         headers={"Authorization": f"Bearer {token['token']}"})
        assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_escopo_preso_a_uma_fonte_nao_serve_para_outra(sessao_a, ambiente):
    """`fluxo:escrever:<uuid>` é como se entrega token a um veículo sem lhe dar as outras fontes da casa."""
    registro, _, cliente = ambiente
    uma, outra = _criar_fonte(sessao_a), _criar_fonte(sessao_a)
    token = _token(sessao_a, [f"fluxo:escrever:{uma['id']}"])
    registro.carregar()
    try:
        cabecalhos = {"Authorization": f"Bearer {token['token']}"}
        assert cliente.post(f"/fluxo/{uma['id']}/eventos", json=[_evento()],
                            headers=cabecalhos).status_code == 202
        assert cliente.post(f"/fluxo/{outra['id']}/eventos", json=[_evento()],
                            headers=cabecalhos).status_code == 403
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{uma['id']}")
        sessao_a.delete(f"/api/fluxos/{outra['id']}")


def test_token_revogado_e_401(sessao_a, ambiente):
    registro, _, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        cabecalhos = {"Authorization": f"Bearer {token['token']}"}
        assert cliente.post(f"/fluxo/{fonte['id']}/eventos", json=[_evento()],
                            headers=cabecalhos).status_code == 202
        sessao_a.delete(f"/api/tokens/{token['id']}")
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=[_evento()], headers=cabecalhos)
        assert r.status_code == 401 and r.json()["erro"] in ("token_revogado", "token_invalido")
    finally:
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


@pytest.mark.parametrize("cabecalho", [None, "Bearer nao-e-token", "Basic abc", "Bearer plat_" + "x" * 43])
def test_sem_credencial_valida_e_401(sessao_a, ambiente, cabecalho):
    registro, _, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    registro.carregar()
    try:
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=[_evento()],
                         headers={"Authorization": cabecalho} if cabecalho else {})
        assert r.status_code == 401
    finally:
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_saude_so_mostra_as_fontes_do_inquilino_do_token(sessao_a, sessao_b, ambiente):
    registro, _, cliente = ambiente
    fonte_a, fonte_b = _criar_fonte(sessao_a), _criar_fonte(sessao_b)
    token_a = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        anonimo = cliente.get("/saude").json()
        assert "por_fonte" not in anonimo and anonimo["processo"] == "plat-fluxo"
        com_token = cliente.get("/saude", headers={"Authorization": f"Bearer {token_a['token']}"}).json()
        assert fonte_a["id"] in com_token["por_fonte"]
        assert fonte_b["id"] not in com_token["por_fonte"]
    finally:
        sessao_a.delete(f"/api/tokens/{token_a['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte_a['id']}")
        sessao_b.delete(f"/api/fluxos/{fonte_b['id']}")


# ------------------------------------------------------------------ fronteira de confiança
def test_corpo_de_dez_mega_e_recusado_com_413(sessao_a, ambiente):
    """Refutação do item: 'envia JSON com 10 MB'."""
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        corpo = b'[{"ts":"2026-01-15T09:00:00","placa":"' + b"x" * (10 * 1024 * 1024) + b'"}]'
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", content=corpo,
                         headers={"Authorization": f"Bearer {token['token']}",
                                  "Content-Type": "application/json"})
        assert r.status_code == 413 and r.json()["erro"] == "corpo_grande_demais"
        assert fila.tamanho() == 0
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_coordenada_fora_da_faixa_tempo_no_futuro_e_rastro_gigante_sao_contados(sessao_a, ambiente):
    """Refutação do item, os três de uma vez: nada disso chega à tabela e cada um aparece na métrica."""
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    adiante = (datetime.datetime.now(UTC) + datetime.timedelta(hours=2)).isoformat()
    try:
        lote = [_evento(1, lat=999.0), _evento(2, ts=adiante), _evento(3, placa="z" * 1_000_000), _evento(4)]
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=lote,
                         headers={"Authorization": f"Bearer {token['token']}"})
        assert r.status_code == 202
        assert r.json() == {"recebidos": 4, "aceitos": 1, "descartados_limite": 0,
                            "descartados_invalido": 3, "descartados_filtro": 0, "em_buffer": 0}
        motivos = fila.conta(fonte["id"]).instantaneo()["motivos"]
        assert motivos == {"coordenada_fora_da_faixa": 1, "tempo_no_futuro": 1, "rastro_longo": 1}
        _escrever(registro, fila)
        assert _contar(sessao_a, fonte["id"]) == 1
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_lote_acima_do_teto_de_eventos_e_413(sessao_a, ambiente):
    registro, _, cliente = ambiente
    fonte = _criar_fonte(sessao_a)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        corpo = ("[" + ",".join(["{}"] * (limites.FLUXO_LOTE_MAX + 1)) + "]").encode()
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", content=corpo,
                         headers={"Authorization": f"Bearer {token['token']}",
                                  "Content-Type": "application/json"})
        assert r.status_code == 413 and r.json()["erro"] == "lote_grande_demais"
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_teto_por_segundo_da_fonte_descarta_e_conta_no_receptor(sessao_a, ambiente):
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a, limite_eventos_s=10)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        r = cliente.post(f"/fluxo/{fonte['id']}/eventos", json=[_evento(i) for i in range(25)],
                         headers={"Authorization": f"Bearer {token['token']}"})
        assert r.json()["aceitos"] == 10 and r.json()["descartados_limite"] == 15
        _escrever(registro, fila)
        assert _contar(sessao_a, fonte["id"]) == 10
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


# ------------------------------------------------------------------ WebSocket servidor e pausa
def test_websocket_recebe_evento_e_fonte_pausada_guarda_sem_perder(sessao_a, ambiente):
    """Cláusula do portão: 'fonte pausada não perde eventos do WebSocket por 30 s (buffer declarado)'.

    30 segundos de eventos ao teto da fonte, não 30 segundos de relógio: o que o portão exige é que o
    buffer AGUENTE a janela declarada, e o teto do buffer é `limite_eventos_s * FLUXO_BUFFER_PAUSA_S`
    (app/limites.py). A fonte aqui tem teto de 5 eventos/s, então a janela de 30 s é de 150 eventos —
    todos entregues durante a pausa e todos gravados depois da retomada, sem um a menos."""
    registro, fila, cliente = ambiente
    fonte = _criar_fonte(sessao_a, tipo="websocket_servidor", limite_eventos_s=5)
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    janela = 5 * limites.FLUXO_BUFFER_PAUSA_S
    try:
        with cliente.websocket_connect(f"/fluxo/{fonte['id']}/ws?token={token['token']}") as ws:
            ws.send_text(json.dumps(_evento(0)))
            assert json.loads(ws.receive_text())["aceitos"] == 1
            assert _escrever(registro, fila) == 1

            # pausa: o balde de fichas não pode ser o que limita a prova do buffer, então o teto por
            # segundo é elevado enquanto pausada (a fonte segue com teto de 5/s no banco; aqui se mede
            # o BUFFER, e o teto por segundo já tem teste próprio)
            assert sessao_a.patch(f"/api/fluxos/{fonte['id']}",
                                  json={"estado": "pausada"}).json()["estado"] == "pausada"
            registro.carregar()
            registro.obter(fonte["id"]).balde.ajustar(10_000)
            for i in range(janela):
                ws.send_text(json.dumps(_evento(i + 1)))
                assert json.loads(ws.receive_text())["em_buffer"] == 1
            pausada = registro.obter(fonte["id"])
            assert len(pausada.buffer) == janela == pausada.buffer_max
            assert _escrever(registro, fila) == 0  # nada foi gravado durante a pausa

            # retomada: o buffer inteiro entra na fila, na ordem, e nada se perdeu
            sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"estado": "ativa"})
            registro.carregar()
            retomada = registro.obter(fonte["id"])
            retomada.balde.ajustar(10_000)
            from app.fluxo.entrada import drenar_buffer

            assert drenar_buffer(retomada, fila) == janela
            gravados = 0
            while True:
                n = _escrever(registro, fila)
                gravados += n
                if not n:
                    break
            assert gravados == janela
        assert _contar(sessao_a, fonte["id"]) == janela + 1
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_websocket_de_fonte_de_outro_inquilino_e_fechado(sessao_a, sessao_b, ambiente):
    from starlette.websockets import WebSocketDisconnect

    registro, _, cliente = ambiente
    fonte_b = _criar_fonte(sessao_b, tipo="websocket_servidor")
    token_a = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        with pytest.raises(WebSocketDisconnect) as e:
            with cliente.websocket_connect(f"/fluxo/{fonte_b['id']}/ws?token={token_a['token']}") as ws:
                ws.receive_text()
        assert e.value.code == 4404
    finally:
        sessao_a.delete(f"/api/tokens/{token_a['id']}")
        sessao_b.delete(f"/api/fluxos/{fonte_b['id']}")


def test_websocket_em_fonte_que_nao_e_de_websocket_e_fechado(sessao_a, ambiente):
    from starlette.websockets import WebSocketDisconnect

    registro, _, cliente = ambiente
    fonte = _criar_fonte(sessao_a, tipo="http")
    token = _token(sessao_a, ["fluxo:escrever"])
    registro.carregar()
    try:
        with pytest.raises(WebSocketDisconnect) as e:
            with cliente.websocket_connect(f"/fluxo/{fonte['id']}/ws?token={token['token']}") as ws:
                ws.receive_text()
        assert e.value.code == 4400
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")
