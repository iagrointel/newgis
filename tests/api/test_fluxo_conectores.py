"""Conectores ATIVOS da fonte de fluxo (item L2-14-a-ingestao-de-fluxos): MQTT e sondagem de URL, com o
registro, a fila e o banco da trilha.

Cláusulas do portão exercidas aqui:
  - "fonte MQTT (broker de teste ...) recebe o simulador de 100 veículos a 1 evento/s cada e a tabela cresce
    na taxa esperada";
  - da refutação: "derruba o broker e confere reconexão".

O broker é o servidor de `tests/apoio/broker_mqtt.py` — MQTT 3.1.1 no fio, em processo, sem contêiner e sem
serviço em disco (o disco desta máquina está a 96 % e a corrida proíbe serviço novo). A fonte é criada com
host público de verdade (a defesa de SSRF recusa 127.0.0.1) e o endereço do broker de teste é injetado na
config em memória, DEPOIS da validação — o que se mede aqui é o conector, não a validação, que tem teste
próprio em tests/api/test_fluxos.py.
"""

import datetime
import json
import secrets
import threading
import time

import pytest

from app.fluxo.conectores import Conector
from app.fluxo.fila import Fila
from app.fluxo.fontes import Registro
from tests.api.conftest import PREFIXO_TESTE
from tests.apoio.broker_mqtt import BrokerDeTeste

UTC = datetime.UTC
# host público de verdade, dado aberto federal (o mesmo que o teste de conexão do L6-02-a usa): passa pela
# defesa de SSRF na criação da fonte. O conector é apontado para o broker de teste depois disso.
HOST_PUBLICO = "servicodados.ibge.gov.br"
MAPEAMENTO = {
    "campo_tempo": {"caminho": "ts", "tipo": "iso"},
    "campo_rastro": "placa",
    "geometria": {"modo": "lonlat", "lon": "lon", "lat": "lat"},
    "campos": [{"caminho": "velocidade", "coluna": "velocidade", "tipo": "numero"}],
}


def _criar_fonte_mqtt(sessao, **extra):
    corpo = {
        "tipo": "mqtt", "nome": f"{PREFIXO_TESTE}-mqtt-{secrets.token_hex(4)}", "mapeamento": MAPEAMENTO,
        "config": {"host": HOST_PUBLICO, "porta": 8883, "topico": "frota/#", "tls": True},
        "limite_eventos_s": 500,
    }
    corpo.update(extra)
    r = sessao.post("/api/fluxos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _conector_no_broker(fonte, registro, fila, broker):
    conector = Conector(registro.obter(fonte["id"]), registro, fila)
    conector.config = {"host": broker.host, "porta": broker.porta, "topico": "frota/#", "tls": False,
                       "qos": 0, "cliente_id": "teste", "usuario": ""}
    return conector


def _esperar(condicao, timeout=15.0, passo=0.05):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(passo)
    return False


@pytest.fixture
def ambiente():
    registro, fila = Registro(), Fila()
    yield registro, fila


def test_mqtt_simulador_de_cem_veiculos_a_um_evento_por_segundo(sessao_a, ambiente):
    """Cláusula do portão, pelo caminho do MQTT: 100 veículos publicam 1 evento/s cada, por 3 segundos; a
    tabela cresce 100 por segundo e a métrica da fonte não acusa perda."""
    registro, fila = ambiente
    fonte = _criar_fonte_mqtt(sessao_a)
    registro.carregar()
    try:
        with BrokerDeTeste() as broker:
            conector = _conector_no_broker(fonte, registro, fila, broker)
            conector.start()
            try:
                assert broker.esperar_assinatura(), "o conector não assinou o tópico"
                crescimento = []
                for segundo in range(3):
                    agora = datetime.datetime.now(UTC).isoformat()
                    for veiculo in range(100):
                        broker.publicar("frota/a", json.dumps(
                            {"ts": agora, "placa": f"AAA{veiculo:04d}", "lon": -46.6, "lat": -23.5,
                             "velocidade": 50}).encode())
                    alvo = 100 * (segundo + 1)
                    assert _esperar(lambda: fila.conta(fonte["id"]).instantaneo()["aceitos"] >= alvo), (
                        f"só {fila.conta(fonte['id']).instantaneo()['aceitos']} de {alvo} eventos chegaram")
                    while fila.escrever_uma_vez(registro.contexto_do_inquilino):
                        pass
                    crescimento.append(
                        sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos?limite=1").json()["total"])
                    if segundo < 2:
                        time.sleep(1.0)
                assert crescimento == [100, 200, 300], f"a tabela não cresceu 100/s: {crescimento}"
                metrica = fila.conta(fonte["id"]).instantaneo()
                assert metrica["aceitos"] == 300 and metrica["descartados_invalido"] == 0
                assert metrica["descartados_limite"] == 0
            finally:
                conector.parar()
                conector.join(timeout=5)
    finally:
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_queda_do_broker_e_reconexao(sessao_a, ambiente):
    """Refutação do item: 'derruba o broker e confere reconexão'. O broker continua de pé (a porta não muda)
    e as conexões abertas são cortadas — é o que acontece quando o broker reinicia. O conector tem de voltar
    sozinho, assinar de novo e voltar a entregar evento, sem intervenção e sem thread morta."""
    registro, fila = ambiente
    fonte = _criar_fonte_mqtt(sessao_a)
    registro.carregar()
    try:
        with BrokerDeTeste() as broker:
            conector = _conector_no_broker(fonte, registro, fila, broker)
            conector.start()
            try:
                assert broker.esperar_assinatura()
                broker.publicar("frota/a", json.dumps(
                    {"ts": datetime.datetime.now(UTC).isoformat(), "placa": "ANTES01",
                     "lon": -46.6, "lat": -23.5, "velocidade": 10}).encode())
                assert _esperar(lambda: fila.conta(fonte["id"]).instantaneo()["aceitos"] == 1)

                conexoes_antes = broker.conexoes
                broker.derrubar()
                assert _esperar(lambda: broker.conexoes > conexoes_antes and broker.clientes,
                                timeout=30), "o conector não reconectou depois da queda do broker"
                assert _esperar(lambda: len(broker.assinaturas) >= 2), "reconectou sem reassinar o tópico"

                broker.publicar("frota/a", json.dumps(
                    {"ts": datetime.datetime.now(UTC).isoformat(), "placa": "DEPOIS1",
                     "lon": -46.6, "lat": -23.5, "velocidade": 20}).encode())
                assert _esperar(lambda: fila.conta(fonte["id"]).instantaneo()["aceitos"] == 2), (
                    "reconectou mas não voltou a entregar evento")
                assert conector.is_alive(), "a thread do conector morreu na queda"
                assert conector.tentativas >= 1  # a queda foi registrada como falha, não engolida
                while fila.escrever_uma_vez(registro.contexto_do_inquilino):
                    pass
                placas = {e["rastro_id"] for e in
                          sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["itens"]}
                assert placas == {"ANTES01", "DEPOIS1"}
            finally:
                conector.parar()
                conector.join(timeout=10)
    finally:
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_carga_mqtt_invalida_e_contada_e_nao_derruba_o_conector(sessao_a, ambiente):
    registro, fila = ambiente
    fonte = _criar_fonte_mqtt(sessao_a)
    registro.carregar()
    try:
        with BrokerDeTeste() as broker:
            conector = _conector_no_broker(fonte, registro, fila, broker)
            conector.start()
            try:
                assert broker.esperar_assinatura()
                broker.publicar("frota/a", b"isto nao e json")
                broker.publicar("frota/a", json.dumps(
                    {"ts": datetime.datetime.now(UTC).isoformat(), "placa": "BOA0001",
                     "lon": -46.6, "lat": -23.5, "velocidade": 30}).encode())
                assert _esperar(lambda: fila.conta(fonte["id"]).instantaneo()["aceitos"] == 1)
                assert fila.conta(fonte["id"]).instantaneo()["motivos"].get("json_invalido") == 1
                assert conector.is_alive()
            finally:
                conector.parar()
                conector.join(timeout=5)
    finally:
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_topico_entra_no_registro_e_pode_ser_filtrado(sessao_a, ambiente):
    """O tópico da publicação vira campo do registro (`topico`), o que deixa uma fonte assinar `frota/#` e
    separar os veículos por tópico no mapeamento."""
    registro, fila = ambiente
    fonte = _criar_fonte_mqtt(sessao_a, mapeamento={
        "campo_tempo": {"caminho": "ts", "tipo": "iso"},
        "campos": [{"caminho": "topico", "coluna": "topico", "tipo": "texto"}]})
    registro.carregar()
    try:
        with BrokerDeTeste() as broker:
            conector = _conector_no_broker(fonte, registro, fila, broker)
            conector.start()
            try:
                assert broker.esperar_assinatura()
                broker.publicar("frota/norte", json.dumps(
                    {"ts": datetime.datetime.now(UTC).isoformat()}).encode())
                assert _esperar(lambda: fila.conta(fonte["id"]).instantaneo()["aceitos"] == 1)
                while fila.escrever_uma_vez(registro.contexto_do_inquilino):
                    pass
                itens = sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["itens"]
                assert itens[0]["atributos"]["topico"] == "frota/norte"
            finally:
                conector.parar()
                conector.join(timeout=5)
    finally:
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


def test_fonte_pausada_continua_conectada_e_guarda_no_buffer(sessao_a, ambiente):
    """Desconectar na pausa perderia o que chega. O conector segue assinado e o evento vai para o buffer."""
    registro, fila = ambiente
    fonte = _criar_fonte_mqtt(sessao_a)
    registro.carregar()
    try:
        with BrokerDeTeste() as broker:
            conector = _conector_no_broker(fonte, registro, fila, broker)
            conector.start()
            try:
                assert broker.esperar_assinatura()
                sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"estado": "pausada"})
                registro.carregar()
                broker.publicar("frota/a", json.dumps(
                    {"ts": datetime.datetime.now(UTC).isoformat(), "placa": "PAUSA01",
                     "lon": -46.6, "lat": -23.5, "velocidade": 5}).encode())
                assert _esperar(lambda: len(registro.obter(fonte["id"]).buffer) == 1)
                assert fila.tamanho() == 0 and broker.clientes, "a pausa não pode derrubar a conexão"

                sessao_a.patch(f"/api/fluxos/{fonte['id']}", json={"estado": "ativa"})
                registro.carregar()
                from app.fluxo.entrada import drenar_buffer

                assert drenar_buffer(registro.obter(fonte["id"]), fila) == 1
                while fila.escrever_uma_vez(registro.contexto_do_inquilino):
                    pass
                itens = sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["itens"]
                assert [e["rastro_id"] for e in itens] == ["PAUSA01"]
            finally:
                conector.parar()
                conector.join(timeout=5)
    finally:
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")


# ------------------------------------------------------------------ sondagem de URL
def _servidor_http(respostas: list, ip: str):
    """Servidor HTTP no IP PÚBLICO desta máquina (a defesa de SSRF recusa loopback, e é assim que o teste do
    L6-02-a já faz). Devolve (servidor, thread, contador de pedidos)."""
    import http.server

    pedidos = {"n": 0}

    class Manipulador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            corpo = respostas[min(pedidos["n"], len(respostas) - 1)]
            pedidos["n"] += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    servidor = http.server.HTTPServer((ip, 0), Manipulador)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor, thread, pedidos


def _ip_publico():
    import ipaddress
    import subprocess

    try:
        saida = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"],
                               capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) >= 4:
            ip = partes[3].split("/")[0]
            try:
                if ipaddress.ip_address(ip).is_global:
                    return ip
            except ValueError:
                continue
    return None


@pytest.mark.lento
def test_sondagem_le_a_url_e_o_campo_de_ultima_atualizacao_evita_repetir(sessao_a, ambiente):
    """A sondagem busca a URL no intervalo declarado; com `campo_atualizacao`, a segunda rodada só ingere o
    que tem valor MAIOR que o da anterior — sem isso a mesma lista entraria de novo a cada rodada."""
    ip = _ip_publico()
    if ip is None:
        pytest.skip("máquina sem IP público roteável (a defesa de SSRF recusa loopback)")
    registro, fila = ambiente
    primeira = json.dumps([{"ts": "2026-01-15T09:00:00+00:00", "placa": "SON0001", "lon": -46.6,
                            "lat": -23.5, "velocidade": 10, "atualizado": "2026-01-15T09:00:00"}]).encode()
    segunda = json.dumps([
        {"ts": "2026-01-15T09:00:00+00:00", "placa": "SON0001", "lon": -46.6, "lat": -23.5,
         "velocidade": 10, "atualizado": "2026-01-15T09:00:00"},
        {"ts": "2026-01-15T09:00:10+00:00", "placa": "SON0002", "lon": -46.6, "lat": -23.5,
         "velocidade": 20, "atualizado": "2026-01-15T09:00:10"},
    ]).encode()
    servidor, thread, pedidos = _servidor_http([primeira, segunda], ip)
    porta = servidor.server_address[1]
    fonte = None
    try:
        r = sessao_a.post("/api/fluxos", json={
            "tipo": "sondagem", "nome": f"{PREFIXO_TESTE}-sonda-{secrets.token_hex(4)}",
            "mapeamento": MAPEAMENTO,
            "config": {"url": f"http://{ip}:{porta}/", "intervalo_s": 5, "campo_atualizacao": "atualizado"},
        })
        assert r.status_code == 201, r.text
        fonte = r.json()
        registro.carregar()
        conector = Conector(registro.obter(fonte["id"]), registro, fila)
        conector.start()
        try:
            assert _esperar(lambda: fila.conta(fonte["id"]).instantaneo()["aceitos"] == 1, timeout=20)
            # a segunda rodada traz a lista inteira; só o registro novo entra
            assert _esperar(lambda: pedidos["n"] >= 2, timeout=30)
            assert _esperar(lambda: fila.conta(fonte["id"]).instantaneo()["aceitos"] == 2, timeout=20)
            time.sleep(0.5)
            assert fila.conta(fonte["id"]).instantaneo()["aceitos"] == 2, "o registro repetido entrou de novo"
            while fila.escrever_uma_vez(registro.contexto_do_inquilino):
                pass
            placas = {e["rastro_id"] for e in
                      sessao_a.get(f"/api/fluxos/{fonte['id']}/eventos").json()["itens"]}
            assert placas == {"SON0001", "SON0002"}
        finally:
            conector.parar()
            conector.join(timeout=10)
    finally:
        servidor.shutdown()
        thread.join(timeout=3)
        if fonte:
            sessao_a.delete(f"/api/fluxos/{fonte['id']}")
