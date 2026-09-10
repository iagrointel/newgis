"""Cliente MQTT 3.1.1 da fonte de fluxo (item L2-14-a-ingestao-de-fluxos), exercido contra um servidor que
fala o protocolo de verdade (`tests/apoio/broker_mqtt.py`), nunca contra ele mesmo.

Cobre, do portão: "fonte MQTT ... recebe o simulador"; da refutação: "derruba o broker e confere reconexão".
"""

import json
import threading
import time

import pytest

from app.fluxo import mqtt
from tests.apoio.broker_mqtt import BrokerDeTeste


# ------------------------------------------------------------------ codificação (a parte pura)
@pytest.mark.parametrize("n,esperado", [(0, b"\x00"), (127, b"\x7f"), (128, b"\x80\x01"),
                                        (16_383, b"\xff\x7f"), (16_384, b"\x80\x80\x01")])
def test_tamanho_variavel_segue_a_especificacao(n, esperado):
    """Os quatro pontos de virada da tabela da seção 2.2.3 do MQTT 3.1.1."""
    assert mqtt.codificar_tamanho(n) == esperado
    fluxo = iter(esperado)
    assert mqtt.decodificar_tamanho(lambda: next(fluxo)) == n


def test_tamanho_acima_do_maximo_e_recusado():
    with pytest.raises(mqtt.ErroMQTT):
        mqtt.codificar_tamanho(268_435_456)


def test_connect_declara_mqtt_nivel_4_e_sessao_limpa():
    pacote = mqtt.pacote_connect("cli", usuario="u", senha="s", keepalive=60)
    assert pacote[0] >> 4 == mqtt.CONNECT
    assert pacote[2:8] == b"\x00\x04MQTT"
    assert pacote[8] == 4                      # nível do protocolo
    assert pacote[9] & 0x02                    # sessão limpa
    assert pacote[9] & 0xC0 == 0xC0            # usuário e senha presentes


def test_subscribe_leva_o_bit_reservado_0x02():
    """Sem o 0x02 no cabeçalho fixo o broker fecha a conexão (seção 3.8.1)."""
    assert mqtt.pacote_subscribe(1, "t/#", 1)[0] == 0x82


def test_publish_ida_e_volta_com_qos_1():
    pacote = mqtt.pacote_publish("frota/a", b'{"v":1}', qos=1, identificador=7)
    corpo = pacote[2:]
    topico, carga, identificador = mqtt.ler_publish(corpo, 1)
    assert (topico, carga, identificador) == ("frota/a", b'{"v":1}', 7)


def test_publish_truncado_levanta_erro_nomeado():
    with pytest.raises(mqtt.ErroMQTT):
        mqtt.ler_publish(b"\x00\x10abc", 0)


# ------------------------------------------------------------------ contra um servidor de verdade
def _assinante(broker, recebidas, pronto, **troca):
    cliente = mqtt.Cliente(broker.host, broker.porta, "frota/#", tls=False, cliente_id="teste", **troca)
    cliente.conectar()
    pronto.set()
    t = threading.Thread(target=lambda: cliente.escutar(lambda t_, c: recebidas.append((t_, c))), daemon=True)
    t.start()
    return cliente, t


def test_conecta_assina_e_recebe_publicacao():
    recebidas, pronto = [], threading.Event()
    with BrokerDeTeste() as broker:
        cliente, _ = _assinante(broker, recebidas, pronto)
        try:
            assert pronto.wait(5) and broker.esperar_assinatura()
            assert broker.assinaturas == ["frota/#"]
            broker.publicar("frota/a", json.dumps({"placa": "AAA0A00"}).encode())
            limite = time.monotonic() + 5
            while not recebidas and time.monotonic() < limite:
                time.sleep(0.02)
            assert recebidas and recebidas[0][0] == "frota/a"
            assert json.loads(recebidas[0][1])["placa"] == "AAA0A00"
        finally:
            cliente.parar()


def test_qos_1_e_confirmado_com_puback():
    recebidas, pronto = [], threading.Event()
    with BrokerDeTeste() as broker:
        cliente, _ = _assinante(broker, recebidas, pronto, qos=1)
        try:
            assert pronto.wait(5) and broker.esperar_assinatura()
            broker.publicar("frota/a", b'{"v":1}', qos=1, identificador=9)
            limite = time.monotonic() + 5
            while not recebidas and time.monotonic() < limite:
                time.sleep(0.02)
            assert recebidas == [("frota/a", b'{"v":1}')]
        finally:
            cliente.parar()


def test_usuario_e_senha_chegam_ao_servidor():
    with BrokerDeTeste() as broker:
        cliente = mqtt.Cliente(broker.host, broker.porta, "frota/#", tls=False,
                               usuario="sensor", senha="segredo-de-teste")
        cliente.conectar()
        cliente.parar()
        assert broker.credenciais == [("sensor", "segredo-de-teste")]


def test_connack_de_recusa_vira_erro_com_a_razao():
    with BrokerDeTeste(recusar_connack=5) as broker:
        cliente = mqtt.Cliente(broker.host, broker.porta, "frota/#", tls=False)
        with pytest.raises(mqtt.ErroMQTT) as e:
            cliente.conectar()
        assert "não autorizado" in str(e.value)


def test_queda_do_servidor_encerra_a_escuta_com_erro_e_nao_trava():
    """Metade da refutação: derrubado o broker, o laço de escuta SAI (é o que deixa o conector reconectar)
    em vez de ficar preso num soquete morto. A outra metade — a reconexão em si — está em
    tests/api/test_fluxo_conectores.py, onde o conector de verdade entra."""
    pronto = threading.Event()
    with BrokerDeTeste() as broker:
        cliente = mqtt.Cliente(broker.host, broker.porta, "frota/#", tls=False)
        cliente.conectar()
        erro = []

        def escutar():
            pronto.set()
            try:
                cliente.escutar(lambda t, c: None)
            except Exception as e:  # noqa: BLE001 — é o erro que se quer observar
                erro.append(type(e).__name__)

        t = threading.Thread(target=escutar, daemon=True)
        t.start()
        assert pronto.wait(5) and broker.esperar_assinatura()
        broker.derrubar()
        t.join(timeout=10)
        assert not t.is_alive(), "a escuta ficou presa depois de o servidor cair"
        assert erro, "a queda do servidor tem de virar erro, nunca laço silencioso"
