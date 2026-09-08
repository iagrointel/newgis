"""Conectores ATIVOS do processo `plat-fluxo` (item L2-14-a-ingestao-de-fluxos): uma thread por fonte que
VAI BUSCAR o evento — `websocket_cliente`, `mqtt`, `sondagem` e `ais`.

Reconexão: espera que dobra a cada falha, de `FLUXO_RECONEXAO_MIN_S` até `FLUXO_RECONEXAO_MAX_S`, e volta ao
mínimo assim que a conexão se estabelece. É o que a refutação do item exige ("derruba o broker e confere
reconexão"): a queda vira uma linha no registro e uma nova tentativa, nunca uma thread morta em silêncio.

Fonte PAUSADA: o conector continua conectado e continua entregando ao `entrada.ingerir`, que guarda no
buffer de pausa. Desconectar na pausa seria perder o que chega — o oposto do que o portão pede.
"""

from __future__ import annotations

import json
import logging
import socket
import threading

from app import limites
from app.conexao import seguranca
from app.fluxo import ais as mod_ais
from app.fluxo import entrada
from app.fluxo import formato as mod_formato
from app.fluxo import mqtt as mod_mqtt
from app.fluxo.mapeamento import ler_caminho

log = logging.getLogger("plat.fluxo.conectores")


class Conector(threading.Thread):
    """Uma fonte ativa. `parar()` é cooperativo: fecha o soquete e o laço sai na volta seguinte."""

    def __init__(self, fonte, registro, fila, *, credencial: str = ""):
        super().__init__(name=f"fluxo-{fonte.tipo}-{fonte.id[:8]}", daemon=True)
        self.fonte_id = fonte.id
        self.tipo = fonte.tipo
        self.config = dict(fonte.config)
        self.credencial = credencial
        self._registro = registro
        self._fila = fila
        self._parar = threading.Event()
        self.tentativas = 0
        self.conexoes = 0
        self.ultimo_erro: str | None = None
        self._cliente = None

    # ------------------------------------------------------------ laço
    def fonte(self):
        return self._registro.obter(self.fonte_id)

    def parar(self) -> None:
        self._parar.set()
        cliente = self._cliente
        if cliente is not None:
            try:
                cliente.parar()
            except Exception:  # noqa: BLE001 — fechar soquete não pode levantar para o chamador
                log.debug("fluxo: falha ao fechar o cliente de %s", self.fonte_id, exc_info=True)

    def run(self) -> None:
        espera = limites.FLUXO_RECONEXAO_MIN_S
        while not self._parar.is_set():
            try:
                self.conexoes += 1
                self._uma_rodada()
                espera = limites.FLUXO_RECONEXAO_MIN_S
            except Exception as e:  # noqa: BLE001 — nenhuma falha de terceiro derruba o processo
                self.tentativas += 1
                self.ultimo_erro = f"{type(e).__name__}: {e}"
                log.warning("fluxo: fonte %s caiu (%s); nova tentativa em %.0f s",
                            self.fonte_id, self.ultimo_erro, espera)
            if self._parar.is_set():
                return
            self._parar.wait(timeout=espera)
            espera = min(espera * 2, limites.FLUXO_RECONEXAO_MAX_S)

    def _uma_rodada(self) -> None:
        if self.tipo == "mqtt":
            self._mqtt()
        elif self.tipo == "ais":
            self._ais()
        elif self.tipo == "sondagem":
            self._sondagem()
        elif self.tipo == "websocket_cliente":
            self._websocket()
        else:
            raise ValueError(f"tipo sem conector ativo: {self.tipo}")

    def entregar(self, registros: list) -> dict:
        fonte = self.fonte()
        if fonte is None:
            return {"recebidos": 0, "aceitos": 0}
        return entrada.ingerir(fonte, registros, self._fila)

    # ------------------------------------------------------------ MQTT
    def _mqtt(self) -> None:
        cliente = mod_mqtt.Cliente(
            self.config["host"], self.config["porta"], self.config["topico"],
            tls=self.config.get("tls", True),
            cliente_id=self.config.get("cliente_id") or f"plat-{self.fonte_id[:8]}",
            usuario=self.config.get("usuario", ""), senha=self.credencial,
            qos=self.config.get("qos", 0),
        )
        self._cliente = cliente
        try:
            cliente.conectar()
            cliente.escutar(lambda topico, carga: self._carga_mqtt(topico, carga))
        finally:
            self._cliente = None
            cliente.parar()

    def _carga_mqtt(self, topico: str, carga: bytes) -> None:
        try:
            registros = mod_formato.decodificar(carga, "json")
        except mod_formato.ErroFormato as e:
            self._fila.conta(self.fonte_id).somar_motivo(e.motivo)
            return
        for r in registros:
            if isinstance(r, dict):
                r.setdefault("topico", topico)
        self.entregar(registros)

    # ------------------------------------------------------------ AIS (NMEA por TCP)
    def _ais(self) -> None:
        remontador = mod_ais.Remontador()
        sock = socket.create_connection((self.config["host"], self.config["porta"]), timeout=30)
        self._cliente = _Fechavel(sock)
        try:
            resto = b""
            while not self._parar.is_set():
                try:
                    pedaco = sock.recv(8192)
                except TimeoutError:
                    continue
                if not pedaco:
                    raise ConnectionError("a fonte AIS fechou a conexão")
                resto += pedaco
                if len(resto) > limites.FLUXO_AIS_LINHA_MAX * 64:
                    resto = resto[-limites.FLUXO_AIS_LINHA_MAX:]
                linhas = resto.split(b"\n")
                resto = linhas.pop()
                lote = []
                for bruta in linhas:
                    if len(bruta) > limites.FLUXO_AIS_LINHA_MAX:
                        continue
                    evento = remontador.alimentar(bruta.decode("ascii", "ignore"))
                    if evento is not None:
                        lote.append(evento)
                if lote:
                    self.entregar(lote)
        finally:
            self._cliente = None
            sock.close()

    # ------------------------------------------------------------ sondagem de URL
    def _sondagem(self) -> None:
        """Uma rodada = uma busca; o intervalo é respeitado aqui dentro para a espera de reconexão não se
        confundir com o intervalo declarado. O campo de última atualização evita reingerir a mesma lista."""
        campo = self.config.get("campo_atualizacao") or ""
        caminho_lista = self.config.get("caminho_lista") or ""
        visto = None
        while not self._parar.is_set():
            resultado = seguranca.buscar_seguro(self.config["url"], guardar_corpo=True)
            if not resultado.ok:
                self.ultimo_erro = resultado.mensagem
                self._fila.conta(self.fonte_id).somar_motivo(f"sondagem:{resultado.mensagem}")
            else:
                try:
                    registros = mod_formato.decodificar(resultado.corpo, self.config.get("formato", "json"))
                except mod_formato.ErroFormato as e:
                    self._fila.conta(self.fonte_id).somar_motivo(e.motivo)
                    registros = []
                if caminho_lista and len(registros) == 1:
                    lista = ler_caminho(registros[0], caminho_lista)
                    registros = [r for r in lista if isinstance(r, dict)] if isinstance(lista, list) else []
                if campo:
                    novos, maior = [], visto
                    for r in registros:
                        valor = ler_caminho(r, campo) if isinstance(r, dict) else None
                        chave = str(valor) if valor is not None else None
                        if visto is None or (chave is not None and chave > visto):
                            novos.append(r)
                            if chave is not None and (maior is None or chave > maior):
                                maior = chave
                    registros, visto = novos, maior
                if registros:
                    self.entregar(registros)
            self._parar.wait(timeout=float(self.config.get("intervalo_s", 60)))

    # ------------------------------------------------------------ WebSocket cliente
    def _websocket(self) -> None:
        """Assinante de um WebSocket de terceiro. Usa `websockets` (já instalado nesta máquina, é o que o
        uvicorn usa para servir WebSocket) em modo síncrono — uma thread por fonte, como os demais."""
        from websockets.sync.client import connect

        cabecalhos = {}
        nome = self.config.get("cabecalho_credencial")
        if nome and self.credencial:
            cabecalhos[nome] = self.credencial
        with connect(self.config["url"], additional_headers=cabecalhos or None,
                     open_timeout=30, close_timeout=5) as ws:
            self._cliente = _Fechavel(ws)
            try:
                assinatura = self.config.get("assinatura")
                if assinatura:
                    ws.send(assinatura)
                while not self._parar.is_set():
                    try:
                        bruto = ws.recv(timeout=30)
                    except TimeoutError:
                        continue
                    dados = bruto if isinstance(bruto, bytes) else str(bruto).encode("utf-8")
                    try:
                        registros = mod_formato.decodificar(dados, "json")
                    except mod_formato.ErroFormato as e:
                        self._fila.conta(self.fonte_id).somar_motivo(e.motivo)
                        continue
                    self.entregar(registros)
            finally:
                self._cliente = None


class _Fechavel:
    """Adaptador mínimo: o `parar()` do conector fecha qualquer cliente pela mesma porta."""

    def __init__(self, alvo):
        self._alvo = alvo

    def parar(self) -> None:
        for metodo in ("close", "shutdown"):
            fechar = getattr(self._alvo, metodo, None)
            if fechar is None:
                continue
            try:
                fechar() if metodo == "close" else fechar(socket.SHUT_RDWR)
                return
            except OSError:
                return


def carga_json(dados: bytes) -> list:
    """Atalho usado pelos testes de conector: bytes → lista de registros, com o mesmo decodificador."""
    return mod_formato.decodificar(dados if isinstance(dados, bytes) else json.dumps(dados).encode(), "json")
