"""Servidor MQTT 3.1.1 mínimo, em processo, para o teste da fonte de fluxo do tipo `mqtt` (item
L2-14-a-ingestao-de-fluxos).

Por que existe: o portão pede "fonte MQTT (broker de teste em contêiner, ou público registrado)". Contêiner
está fora — o disco desta máquina está a 96 % e a regra da corrida proíbe serviço novo em disco; broker
público não serve de prova (indisponibilidade dele reprovaria o nosso código, e mandar dado de teste para
fora da casa é o que não se faz). O que fica é a terceira forma de ter um broker: falar o protocolo. Este
arquivo é um SERVIDOR de verdade no fio — os bytes que ele lê e escreve são os do MQTT 3.1.1 —, e é contra
ele que `app/fluxo/mqtt.py` é exercido.

Não é simulação do nosso cliente: ele não conhece nenhuma estrutura de `app.fluxo`, só o protocolo. O que
ele NÃO faz (declarado): QoS 2, sessão persistente, retenção, última vontade, autenticação real (guarda o
usuário e a senha recebidos para o teste conferir) e curinga de tópico com `+`.
"""

from __future__ import annotations

import socket
import struct
import threading


def _tamanho(n: int) -> bytes:
    saida = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n:
            b |= 0x80
        saida.append(b)
        if not n:
            return bytes(saida)


def _texto(valor: str) -> bytes:
    bruto = valor.encode("utf-8")
    return struct.pack("!H", len(bruto)) + bruto


class BrokerDeTeste:
    """`with BrokerDeTeste() as b: ...` — `b.porta`, `b.publicar(topico, carga)`, `b.derrubar()`."""

    def __init__(self, host: str = "127.0.0.1", recusar_connack: int = 0):
        self._servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._servidor.bind((host, 0))
        self._servidor.listen(8)
        self._servidor.settimeout(0.5)
        self.host, self.porta = self._servidor.getsockname()
        self.recusar_connack = recusar_connack
        self.clientes: list[socket.socket] = []
        self.assinaturas: list[str] = []
        self.credenciais: list[tuple[str, str]] = []
        self.conexoes = 0
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._aceitar, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self.parar()

    # -------------------------------------------------------------- laço
    def _aceitar(self):
        while not self._parar.is_set():
            try:
                cliente, _ = self._servidor.accept()
            except (TimeoutError, OSError):
                continue
            self.conexoes += 1
            threading.Thread(target=self._atender, args=(cliente,), daemon=True).start()

    def _atender(self, cliente: socket.socket):
        cliente.settimeout(0.5)
        try:
            while not self._parar.is_set():
                pacote = self._ler(cliente)
                if pacote is None:
                    continue
                if pacote is False:
                    return
                tipo, corpo = pacote
                if tipo == 1:  # CONNECT
                    self._connect(cliente, corpo)
                elif tipo == 8:  # SUBSCRIBE
                    identificador = struct.unpack("!H", corpo[:2])[0]
                    n = struct.unpack("!H", corpo[2:4])[0]
                    self.assinaturas.append(corpo[4:4 + n].decode("utf-8"))
                    cliente.sendall(bytes([0x90, 3]) + struct.pack("!H", identificador) + bytes([0]))
                elif tipo == 12:  # PINGREQ
                    cliente.sendall(bytes([0xD0, 0]))
                elif tipo == 14:  # DISCONNECT
                    return
        except OSError:
            return
        finally:
            if cliente in self.clientes:
                self.clientes.remove(cliente)
            try:
                cliente.close()
            except OSError:
                pass

    def _connect(self, cliente: socket.socket, corpo: bytes) -> None:
        # protocolo(2+4) + nível(1) + bandeiras(1) + keepalive(2) = 10 bytes antes do payload
        bandeiras = corpo[7]
        pos = 10
        pos = self._pular_texto(corpo, pos)  # id do cliente
        usuario = senha = ""
        if bandeiras & 0x80:
            usuario, pos = self._ler_texto(corpo, pos)
        if bandeiras & 0x40:
            senha, pos = self._ler_texto(corpo, pos)
        self.credenciais.append((usuario, senha))
        cliente.sendall(bytes([0x20, 2, 0, self.recusar_connack]))
        if not self.recusar_connack:
            self.clientes.append(cliente)

    @staticmethod
    def _ler_texto(corpo: bytes, pos: int) -> tuple[str, int]:
        n = struct.unpack("!H", corpo[pos:pos + 2])[0]
        return corpo[pos + 2:pos + 2 + n].decode("utf-8", "replace"), pos + 2 + n

    @classmethod
    def _pular_texto(cls, corpo: bytes, pos: int) -> int:
        return cls._ler_texto(corpo, pos)[1]

    @staticmethod
    def _ler(cliente: socket.socket):
        """None = sem dado agora; False = conexão fechada; (tipo, corpo) = um pacote."""
        try:
            cabecalho = cliente.recv(1)
        except TimeoutError:
            return None
        if not cabecalho:
            return False
        multiplicador, tamanho = 1, 0
        while True:
            b = cliente.recv(1)
            if not b:
                return False
            tamanho += (b[0] & 0x7F) * multiplicador
            if not b[0] & 0x80:
                break
            multiplicador *= 128
        corpo = b""
        while len(corpo) < tamanho:
            pedaco = cliente.recv(tamanho - len(corpo))
            if not pedaco:
                return False
            corpo += pedaco
        return cabecalho[0] >> 4, corpo

    # -------------------------------------------------------------- publicação
    def publicar(self, topico: str, carga: bytes, *, qos: int = 0, identificador: int = 1) -> int:
        corpo = _texto(topico) + (struct.pack("!H", identificador) if qos else b"") + carga
        pacote = bytes([0x30 | (qos << 1)]) + _tamanho(len(corpo)) + corpo
        enviados = 0
        for cliente in list(self.clientes):
            try:
                cliente.sendall(pacote)
                enviados += 1
            except OSError:
                self.clientes.remove(cliente)
        return enviados

    def derrubar(self) -> None:
        """Fecha as conexões abertas sem parar o servidor: é como se o broker caísse e voltasse."""
        for cliente in list(self.clientes):
            try:
                cliente.shutdown(socket.SHUT_RDWR)
                cliente.close()
            except OSError:
                pass
        self.clientes.clear()

    def parar(self) -> None:
        self._parar.set()
        self.derrubar()
        try:
            self._servidor.close()
        except OSError:
            pass
        self._thread.join(timeout=2)

    def esperar_assinatura(self, timeout: float = 5.0) -> bool:
        import time

        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self.assinaturas and self.clientes:
                return True
            time.sleep(0.02)
        return False
