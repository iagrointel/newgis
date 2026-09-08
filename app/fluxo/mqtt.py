"""Cliente MQTT 3.1.1 assinante, só o necessário para uma fonte de fluxo (item L2-14-a-ingestao-de-fluxos).

Por que escrito aqui e não com biblioteca: a casa não tem `paho-mqtt` instalado, o disco está no limite e a
regra da corrida proíbe dependência nova; o subconjunto que uma fonte assinante usa — CONNECT, CONNACK,
SUBSCRIBE, SUBACK, PUBLISH (QoS 0 e 1), PUBACK, PINGREQ/PINGRESP, DISCONNECT — cabe neste arquivo e é
exercido por teste contra um servidor que fala o mesmo protocolo. O que ficou DE FORA, de propósito:
QoS 2, sessão persistente, mensagem de última vontade, retenção, MQTT 5 e broker próprio (decisão D31, ainda
do dono) — está escrito em docs/PARIDADE.md.

Referência: especificação MQTT 3.1.1 (mqtt.org/mqtt-specification), seções 2 (formato do pacote de controle)
e 3 (pacotes). O cliente é assinante: nunca publica dado do inquilino no broker de terceiro.

TLS: `ssl.create_default_context()` — verificação de certificado e de nome ligadas, como em qualquer outro
cliente da casa. O host já passou pela defesa de SSRF em `app/fluxo/tipos.py` antes de virar config.
"""

from __future__ import annotations

import logging
import socket
import ssl
import struct

from app import limites

log = logging.getLogger("plat.fluxo.mqtt")

CONNECT, CONNACK, PUBLISH, PUBACK, SUBSCRIBE, SUBACK, PINGREQ, PINGRESP, DISCONNECT = (
    1, 2, 3, 4, 8, 9, 12, 13, 14)
CONNACK_MENSAGEM = {
    0: "ok", 1: "versão de protocolo recusada", 2: "identificador de cliente recusado",
    3: "servidor indisponível", 4: "usuário ou senha inválidos", 5: "não autorizado",
}


class ErroMQTT(Exception):
    pass


# ---------------------------------------------------------------- codificação
def codificar_tamanho(n: int) -> bytes:
    """Remaining Length: varint de até 4 bytes (seção 2.2.3 da especificação)."""
    if n < 0 or n > 268_435_455:
        raise ErroMQTT("tamanho de pacote fora da faixa do MQTT 3.1.1")
    saida = bytearray()
    while True:
        byte = n % 128
        n //= 128
        if n:
            byte |= 0x80
        saida.append(byte)
        if not n:
            return bytes(saida)


def decodificar_tamanho(ler_um_byte) -> int:
    multiplicador, valor = 1, 0
    for _ in range(4):
        byte = ler_um_byte()
        valor += (byte & 0x7F) * multiplicador
        if not byte & 0x80:
            return valor
        multiplicador *= 128
    raise ErroMQTT("Remaining Length com mais de 4 bytes")


def _texto(valor: str) -> bytes:
    bruto = valor.encode("utf-8")
    if len(bruto) > 65535:
        raise ErroMQTT("texto de mais de 65535 bytes no pacote")
    return struct.pack("!H", len(bruto)) + bruto


def pacote_connect(cliente_id: str, *, usuario: str = "", senha: str = "",
                   keepalive: int = limites.FLUXO_MQTT_KEEPALIVE_S) -> bytes:
    flags = 0x02  # sessão limpa
    payload = _texto(cliente_id)
    if usuario:
        flags |= 0x80
        payload += _texto(usuario)
        if senha:
            flags |= 0x40
            payload += _texto(senha)
    corpo = _texto("MQTT") + bytes([4, flags]) + struct.pack("!H", keepalive) + payload
    return bytes([CONNECT << 4]) + codificar_tamanho(len(corpo)) + corpo


def pacote_subscribe(identificador: int, topico: str, qos: int = 0) -> bytes:
    corpo = struct.pack("!H", identificador) + _texto(topico) + bytes([qos])
    return bytes([(SUBSCRIBE << 4) | 0x02]) + codificar_tamanho(len(corpo)) + corpo


def pacote_puback(identificador: int) -> bytes:
    return bytes([PUBACK << 4, 2]) + struct.pack("!H", identificador)


def pacote_pingreq() -> bytes:
    return bytes([PINGREQ << 4, 0])


def pacote_disconnect() -> bytes:
    return bytes([DISCONNECT << 4, 0])


def pacote_publish(topico: str, carga: bytes, *, qos: int = 0, identificador: int = 1) -> bytes:
    """Só o teste publica (o cliente da plataforma é assinante); fica aqui para os dois lados usarem o
    MESMO codificador — um erro de formato apareceria nos dois e o teste não provaria nada se cada lado
    tivesse a sua versão."""
    corpo = _texto(topico) + (struct.pack("!H", identificador) if qos else b"") + carga
    return bytes([(PUBLISH << 4) | (qos << 1)]) + codificar_tamanho(len(corpo)) + corpo


def ler_publish(corpo: bytes, qos: int) -> tuple[str, bytes, int | None]:
    """Corpo de um PUBLISH → (tópico, carga, identificador). Levanta ErroMQTT em corpo truncado."""
    if len(corpo) < 2:
        raise ErroMQTT("PUBLISH truncado")
    n = struct.unpack("!H", corpo[:2])[0]
    if len(corpo) < 2 + n:
        raise ErroMQTT("PUBLISH com tópico truncado")
    topico = corpo[2:2 + n].decode("utf-8", "replace")
    resto = corpo[2 + n:]
    identificador = None
    if qos:
        if len(resto) < 2:
            raise ErroMQTT("PUBLISH com QoS sem identificador")
        identificador = struct.unpack("!H", resto[:2])[0]
        resto = resto[2:]
    return topico, resto, identificador


# ---------------------------------------------------------------- cliente
class Cliente:
    """Assinante bloqueante de um tópico. `escutar(ao_receber)` só volta quando a conexão cai ou `parar()`
    é chamado; quem cuida da reconexão é `app/fluxo/conectores.py`."""

    def __init__(self, host: str, porta: int, topico: str, *, tls: bool = True, cliente_id: str = "plat",
                 usuario: str = "", senha: str = "", qos: int = 0, timeout_s: float = 30.0):
        self.host, self.porta, self.topico = host, porta, topico
        self.tls, self.cliente_id, self.usuario, self.senha, self.qos = tls, cliente_id, usuario, senha, qos
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None
        self._parar = False

    def conectar(self) -> None:
        bruto = socket.create_connection((self.host, self.porta), timeout=self.timeout_s)
        if self.tls:
            contexto = ssl.create_default_context()
            bruto = contexto.wrap_socket(bruto, server_hostname=self.host)
        self._sock = bruto
        self._enviar(pacote_connect(self.cliente_id, usuario=self.usuario, senha=self.senha))
        tipo, _, corpo = self._ler_pacote()
        if tipo != CONNACK or len(corpo) < 2:
            raise ErroMQTT("o servidor não respondeu CONNACK")
        codigo = corpo[1]
        if codigo != 0:
            raise ErroMQTT(f"CONNACK recusou a conexão: {CONNACK_MENSAGEM.get(codigo, codigo)}")
        self._enviar(pacote_subscribe(1, self.topico, self.qos))
        tipo, _, corpo = self._ler_pacote()
        if tipo != SUBACK:
            raise ErroMQTT("o servidor não respondeu SUBACK")
        if corpo[-1] == 0x80:
            raise ErroMQTT(f"assinatura do tópico {self.topico} recusada pelo servidor")

    def escutar(self, ao_receber) -> None:
        """`ao_receber(topico, carga_bytes)` por mensagem. PINGREQ a cada timeout de leitura sem tráfego."""
        assert self._sock is not None, "conectar() antes de escutar()"
        self._sock.settimeout(min(self.timeout_s, limites.FLUXO_MQTT_KEEPALIVE_S / 2))
        while not self._parar:
            try:
                tipo, bandeiras, corpo = self._ler_pacote()
            except TimeoutError:
                self._enviar(pacote_pingreq())
                continue
            except (OSError, ErroMQTT):
                # `parar()` fecha o soquete DEBAIXO desta leitura: parada pedida sai limpa, queda do
                # servidor continua subindo como erro (é o que faz o conector reconectar).
                if self._parar or self._sock is None:
                    return
                raise
            if tipo == PUBLISH:
                qos = (bandeiras >> 1) & 0x03
                topico, carga, identificador = ler_publish(corpo, qos)
                if qos == 1 and identificador is not None:
                    self._enviar(pacote_puback(identificador))
                ao_receber(topico, carga)
            elif tipo in (PINGRESP, PUBACK, SUBACK):
                continue
            elif tipo == DISCONNECT:
                return

    def parar(self) -> None:
        self._parar = True
        s, self._sock = self._sock, None
        if s is not None:
            try:
                s.sendall(pacote_disconnect())
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

    # ------------------------------------------------------------ soquete
    def _enviar(self, dados: bytes) -> None:
        if self._sock is None:
            raise ErroMQTT("soquete fechado")
        self._sock.sendall(dados)

    def _ler_exato(self, n: int) -> bytes:
        assert self._sock is not None
        pedacos, lido = [], 0
        while lido < n:
            pedaco = self._sock.recv(n - lido)
            if not pedaco:
                raise ErroMQTT("conexão fechada pelo servidor")
            pedacos.append(pedaco)
            lido += len(pedaco)
        return b"".join(pedacos)

    def _ler_pacote(self) -> tuple[int, int, bytes]:
        cabecalho = self._ler_exato(1)[0]
        tamanho = decodificar_tamanho(lambda: self._ler_exato(1)[0])
        if tamanho > limites.FLUXO_CORPO_MAX_BYTES:
            raise ErroMQTT(f"pacote de {tamanho} bytes acima do teto do receptor")
        return cabecalho >> 4, cabecalho & 0x0F, self._ler_exato(tamanho) if tamanho else b""
