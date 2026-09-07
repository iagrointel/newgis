#!/usr/bin/env python3
"""Corpo do serviço systemd DE TESTE usado para provar a rotação de segredo (item L7-19-segredos-e-
certificados) sem tocar plat-api/plat-worker/nginx/postgres de produção — proibido neste item. Não é
parte do produto: só existe para o `scripts/segredo_rotacionar.py --provar` criar, medir e apagar.

Reproduz a MESMA forma de leitura de segredo que a produção usa (`LoadCredential=` do systemd,
`$CREDENTIALS_DIRECTORY/<nome>`) e, quando `PLAT_TESTE_DSN_CRED` aponta para um credential com um DSN
completo, também reproduz a mesma prova de "a senha antiga não autentica mais" que
`app/db.py`/`plat_worker` fazem: uma conexão psycopg2 de verdade a cada `/saude`.

Ativação por SOQUETE (`Sockets=` na unidade .socket companheira, `systemd-socket-activate`/`LISTEN_FDS`):
o kernel segura a fila de conexões novas enquanto o processo reinicia, então uma janela de restart não
vira "connection refused" nem 5xx — é a técnica MEDIDA aqui para a cláusula "o serviço não cai" do
portão. Sem `LISTEN_FDS` no ambiente (uso manual, fora de systemd) cai para bind comum."""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import socket
import socketserver
import sys
import time


def _sha256_prefixo(caminho: str) -> str | None:
    try:
        valor = open(caminho, encoding="utf-8").read().strip()
    except OSError:
        return None
    if not valor:
        return None
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16]


def _testar_dsn(dsn: str) -> tuple[bool, str]:
    import psycopg2

    try:
        con = psycopg2.connect(dsn, connect_timeout=3)
        try:
            with con.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            con.close()
        return True, "ok"
    except Exception as e:  # noqa: BLE001 — a mensagem de erro do psycopg2 nunca cita a senha em si
        return False, type(e).__name__


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "plat-teste-segredo/1"

    def log_message(self, fmt, *args):  # silencioso: o hammer de medição já conta os códigos
        pass

    def do_GET(self):
        if self.path == "/admin":
            self._admin()
            return
        if self.path != "/saude":
            self.send_response(404)
            self.end_headers()
            return
        cred_dir = os.environ.get("CREDENTIALS_DIRECTORY", "")
        nomes = [n for n in os.environ.get("PLAT_TESTE_CREDS", "").split(",") if n]
        corpo: dict = {"status": "ok", "pid": os.getpid(), "hashes": {}}
        for nome in nomes:
            corpo["hashes"][nome] = _sha256_prefixo(os.path.join(cred_dir, nome)) if cred_dir else None

        dsn_cred = os.environ.get("PLAT_TESTE_DSN_CRED", "")
        if dsn_cred and cred_dir:
            caminho = os.path.join(cred_dir, dsn_cred)
            try:
                dsn = open(caminho, encoding="utf-8").read().strip()
            except OSError:
                dsn = ""
            if dsn:
                ok, motivo = _testar_dsn(dsn)
                corpo["banco"] = "ok" if ok else "falhou"
                corpo["banco_motivo"] = motivo
                if not ok:
                    corpo["status"] = "erro"
            else:
                corpo["banco"] = "sem_credential"
                corpo["status"] = "erro"

        payload = json.dumps(corpo).encode("utf-8")
        self.send_response(200 if corpo["status"] == "ok" else 500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


    def _admin(self) -> None:
        """Simula a Admin API de um serviço protegido por token estático (Garage, item L7-19): exige
        `Authorization: Bearer <token>` batendo com o credential nomeado por `PLAT_TESTE_TOKEN_CRED`.
        Prova a mesma cláusula do resto do arquivo — token antigo para de autenticar, token novo
        funciona — sem precisar do Garage de verdade."""
        cred_dir = os.environ.get("CREDENTIALS_DIRECTORY", "")
        nome = os.environ.get("PLAT_TESTE_TOKEN_CRED", "")
        esperado = None
        if nome and cred_dir:
            try:
                esperado = open(os.path.join(cred_dir, nome), encoding="utf-8").read().strip()
            except OSError:
                esperado = None
        recebido = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if esperado and recebido and recebido == esperado:
            payload = json.dumps({"status": "autorizado"}).encode("utf-8")
            self.send_response(200)
        else:
            payload = json.dumps({"status": "nao_autorizado"}).encode("utf-8")
            self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ServidorSoquete(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Como HTTPServer, mas com `bind_and_activate=False` quando o soquete já vem do systemd (LISTEN_FDS)."""

    allow_reuse_address = True


def _soquete_do_systemd() -> socket.socket | None:
    pid = os.environ.get("LISTEN_PID")
    nfds = int(os.environ.get("LISTEN_FDS", "0") or "0")
    if not pid or int(pid) != os.getpid() or nfds < 1:
        return None
    # FD 3 é o primeiro soquete passado (SD_LISTEN_FDS_START); esta unidade de teste declara Sockets=
    # com um único soquete, então é sempre o 3.
    return socket.socket(fileno=3)


def main() -> None:
    porta = int(os.environ.get("PLAT_TESTE_PORTA", "8199"))
    soquete_systemd = _soquete_do_systemd()
    if soquete_systemd is not None:
        servidor = ServidorSoquete(("", 0), Handler, bind_and_activate=False)
        servidor.socket = soquete_systemd
        origem = "systemd (LISTEN_FDS, socket activation)"
    else:
        servidor = ServidorSoquete(("127.0.0.1", porta), Handler)
        origem = f"bind direto :{porta} (fora do systemd)"
    sys.stderr.write(f"plat-teste-segredo: pid={os.getpid()} origem={origem} hora={time.time()}\n")
    sys.stderr.flush()
    servidor.serve_forever()


if __name__ == "__main__":
    main()
