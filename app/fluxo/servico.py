"""Processo `plat-fluxo` (`python -m app.fluxo.servico`; unidade deploy/plat-fluxo.service; porta 8155).

Junta as quatro peças e nada mais:
  `fontes.Registro`  — as fontes em memória, recarregadas a cada `RECARGA_S`
  `fila.Fila`        — fila em memória + um lote por segundo no Postgres + métrica por fonte
  `receptor`         — a aplicação ASGI (HTTP, WebSocket servidor, /saude)
  `conectores`       — uma thread por fonte ATIVA (MQTT, WebSocket cliente, sondagem, AIS)

O supervisor de conectores roda no mesmo laço da recarga: fonte que aparece ganha thread, fonte que some ou
muda de configuração tem a thread parada e recriada. Fonte pausada mantém a thread (ver `conectores`).

Parada limpa por SIGTERM: para os conectores, para o laço de escrita e grava o que restou na fila.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading

import uvicorn

from app import limites
from app import log as plat_log
from app.conexao import credencial as mod_credencial
from app.db import Contexto
from app.fluxo import fila as mod_fila
from app.fluxo import fontes as mod_fontes
from app.fluxo import receptor as mod_receptor
from app.fluxo.conectores import Conector
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

log = logging.getLogger("plat.fluxo")


class Servico:
    def __init__(self):
        self.registro = mod_fontes.Registro()
        self.fila = mod_fila.Fila()
        self.conectores: dict[str, Conector] = {}
        self._parar = threading.Event()
        self.app = mod_receptor.criar(self.registro, self.fila)

    # ------------------------------------------------------------ conectores
    def _credencial(self, fonte_id: str, tenant_id: int) -> str:
        """Credencial cifrada da fonte (senha do broker MQTT, cabeçalho do WebSocket). Decifrada em memória
        na hora de conectar; nunca guardada no registro nem escrita em log."""
        from app import db

        try:
            with db.db(Contexto(tenant_id, 0, "plat-fluxo")) as cur:
                cur.execute("SELECT credencial_cifrada FROM plat.fluxo_fonte WHERE id = %s::uuid", (fonte_id,))
                r = cur.fetchone()
            if r is None or not r["credencial_cifrada"]:
                return ""
            return decifrar_com_rotacao(mod_credencial.decifrar, r["credencial_cifrada"],
                                        settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)
        except Exception:  # noqa: BLE001 — sem credencial o conector tenta sem ela e o broker recusa
            log.exception("fluxo: credencial da fonte %s não decifrada", fonte_id)
            return ""

    def _assinatura(self, fonte) -> tuple:
        """O que, mudando, obriga a refazer a conexão (a pausa NÃO entra: pausada segue conectada)."""
        return (fonte.tipo, tuple(sorted((k, str(v)) for k, v in fonte.config.items())))

    def sincronizar_conectores(self) -> None:
        vivas = {f.id: f for f in self.registro.todas() if f.tipo in mod_fontes.limites_tipos_ativos()}
        for fid, conector in list(self.conectores.items()):
            fonte = vivas.get(fid)
            if fonte is None or self._assinatura(fonte) != (conector.tipo, tuple(
                    sorted((k, str(v)) for k, v in conector.config.items()))):
                conector.parar()
                del self.conectores[fid]
        for fid, fonte in vivas.items():
            if fid in self.conectores and self.conectores[fid].is_alive():
                continue
            self.conectores.pop(fid, None)
            conector = Conector(fonte, self.registro, self.fila,
                                credencial=self._credencial(fid, fonte.tenant_id))
            self.conectores[fid] = conector
            conector.start()

    # ------------------------------------------------------------ laço
    def _laco_registro(self) -> None:
        while not self._parar.is_set():
            self.registro.carregar()
            for fonte in self.registro.todas():
                if fonte.ativa and fonte.buffer:
                    from app.fluxo.entrada import drenar_buffer

                    n = drenar_buffer(fonte, self.fila)
                    if n:
                        log.info("fluxo: fonte %s retomada; %d eventos do buffer entraram na fila", fonte.id, n)
            self.sincronizar_conectores()
            self._parar.wait(timeout=mod_fontes.RECARGA_S)

    def iniciar(self) -> None:
        self.registro.carregar()
        self.fila.iniciar(self.registro.contexto_do_inquilino, self.registro.inquilino_da_fonte)
        self.sincronizar_conectores()
        threading.Thread(target=self._laco_registro, name="fluxo-registro", daemon=True).start()

    def parar(self) -> None:
        self._parar.set()
        for conector in list(self.conectores.values()):
            conector.parar()
        self.conectores.clear()
        self.fila.parar()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="processo plat-fluxo: entrada de eventos em tempo real")
    p.add_argument("--porta", type=int, default=limites.FLUXO_PORTA)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args(argv)

    plat_log.configurar(settings.PLAT_LOG_NIVEL)
    servico = Servico()
    servico.iniciar()
    log.info("plat-fluxo em %s:%d com %d fonte(s)", args.host, args.porta, len(servico.registro.todas()))

    servidor = uvicorn.Server(uvicorn.Config(servico.app, host=args.host, port=args.porta,
                                             log_level=settings.PLAT_LOG_NIVEL.lower(), access_log=False))

    def encerrar(*_):
        servidor.should_exit = True

    signal.signal(signal.SIGTERM, encerrar)
    try:
        servidor.run()
    finally:
        servico.parar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
