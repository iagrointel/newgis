"""Bomba TCP → socket unix (stdlib pura, nenhum import da aplicação): roda DENTRO da rede de
nomes (netns) do contêiner vigia do gateway, por `nsenter`, e entrega as conexões dos notebooks
ao uvicorn do gateway, que escuta num socket unix no sistema de arquivos DO HOST — o processo
bomba é da máquina, só a sua REDE é a do contêiner.

Por que tudo isso: o firewall desta máquina derruba todo o tráfego contêiner → host (ufw INPUT
DROP, medido no item L2-16-b), então o contêiner do notebook não alcança a API da plataforma
por TCP do host de jeito nenhum. Em vez de abrir o firewall (máquina partilhada com produção),
a API é servida num socket unix (uvicorn --uds) e este processo entrega a rede interna.

Uso: python -m app.notebooks.rele <caminho do socket unix> <porta TCP>
"""

import socket
import socketserver
import sys
import threading

TAM = 65536


class Trata(socketserver.BaseRequestHandler):
    """Uma conexão TCP de um notebook ↔ uma conexão unix do uvicorn do gateway; bomba nos dois
    sentidos até um lado fechar (meio-fechamento respeitado com shutdown(SHUT_WR))."""

    def handle(self):  # noqa: D102 — protocolo trivial, documentado na classe
        uds = self.server.caminho_uds
        par = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            par.connect(uds)
        except OSError:
            corpo = (b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\n"
                     b"Content-Length: 30\r\nConnection: close\r\n\r\ngateway do notebook indisponivel\n")
            try:
                self.request.sendall(corpo)
            except OSError:
                pass
            return

        def bomba(origem, destino):
            try:
                while True:
                    dado = origem.recv(TAM)
                    if not dado:
                        break
                    destino.sendall(dado)
            except OSError:
                pass
            finally:
                try:
                    destino.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        ida = threading.Thread(target=bomba, args=(self.request, par), daemon=True)
        ida.start()
        bomba(par, self.request)
        ida.join(timeout=30)


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    if len(sys.argv) != 3:
        print("uso: python -m app.notebooks.rele <caminho do socket unix> <porta TCP>", file=sys.stderr)
        raise SystemExit(2)
    uds, porta = sys.argv[1], int(sys.argv[2])
    servidor = Servidor(("0.0.0.0", porta), Trata)
    servidor.caminho_uds = uds
    servidor.serve_forever()


if __name__ == "__main__":
    main()
