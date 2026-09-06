"""Servidor SMTP de CAPTURA em stdlib puro (asyncio), porta local (item L0-07-d-smtp-convites): `aiosmtpd`
está AUSENTE desta máquina, então o portão pede exatamente isto — um mock TCP simples que fala o suficiente
do protocolo (EHLO, MAIL FROM, RCPT TO, DATA, QUIT) para receber o que `smtplib` (o cliente real de
`app/correio/cliente.py`) envia. Roda numa thread própria com seu próprio laço de eventos, porta 127.0.0.1
efêmera: tanto o processo de teste (chamada síncrona) quanto o `plat-worker` REAL (processo systemd
separado, que de fato processa o job `correio.enviar`) conseguem falar com ele por TCP no mesmo host.
Sem AUTH: os testes configuram o SMTP do inquilino SEM usuário/senha, então `cliente.enviar` nunca chama
`SMTP.login` contra este mock (ele não entende AUTH)."""

import asyncio
import threading
from email import message_from_string, policy


class Mensagem:
    """`dados` é a mensagem RFC 822 CRUA (cabeçalhos + corpo) tal como chegou pela fio; `assunto`/`corpo`
    decodificam de verdade (`email.message_from_string` + `get_content()`) — texto em português força
    `Content-Transfer-Encoding: quoted-printable` (acentos) ou `base64`, e o link do convite/redefinição
    pode nascer QUEBRADO NO MEIO por causa da dobra de linha do quoted-printable em 76 colunas (achado
    desta verificação: ler a mensagem crua como string ingênua rompe o token no meio). Um cliente de
    e-mail de verdade decodifica isso do jeito certo (é para isso que o MIME existe); o mock tinha que
    decodificar do mesmo jeito para não acusar um bug que não existe do lado do produto."""

    def __init__(self, mail_from: str, rcpt_to: list[str], dados: str):
        self.mail_from = mail_from
        self.rcpt_to = rcpt_to
        self.dados = dados
        self._msg = message_from_string(dados, policy=policy.default)

    @property
    def assunto(self) -> str:
        return str(self._msg.get("Subject", ""))

    @property
    def corpo(self) -> str:
        if self._msg.is_multipart():
            for parte in self._msg.walk():
                if parte.get_content_type() == "text/plain":
                    return parte.get_content()
            return ""
        return self._msg.get_content()


class ServidorSMTPCaptura:
    """Uso: `with ServidorSMTPCaptura() as s: ...; s.esperar(1); s.mensagens`. `esperar(n, timeout)` bloqueia
    até `n` mensagens chegarem ou o tempo esgotar (o worker real roda em outro processo; a entrega não é
    instantânea)."""

    def __init__(self):
        self.mensagens: list[Mensagem] = []
        self._trava = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.base_events.Server | None = None
        self._thread: threading.Thread | None = None
        self.porta: int = 0

    def __enter__(self):
        self.iniciar()
        return self

    def __exit__(self, *exc):
        self.parar()

    def iniciar(self) -> None:
        pronto = threading.Event()

        def alvo():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)

            async def montar():
                server = await asyncio.start_server(self._atender, "127.0.0.1", 0)
                self._server = server
                self.porta = server.sockets[0].getsockname()[1]
                pronto.set()

            loop.run_until_complete(montar())
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(self._server.wait_closed())
                loop.close()

        self._thread = threading.Thread(target=alvo, daemon=True)
        self._thread.start()
        assert pronto.wait(5), "servidor de captura SMTP não subiu em 5 s"

    def parar(self) -> None:
        if self._loop is None:
            return

        def fechar():
            self._server.close()
            self._loop.stop()

        self._loop.call_soon_threadsafe(fechar)
        self._thread.join(timeout=5)
        self._loop = None

    async def _ler_linha(self, leitor: asyncio.StreamReader) -> str:
        linha = await leitor.readline()
        return linha.decode("utf-8", "replace").rstrip("\r\n")

    async def _atender(self, leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        escritor.write(b"220 localhost plat-teste ESMTP\r\n")
        await escritor.drain()
        mail_from = None
        rcpt_to: list[str] = []
        try:
            while True:
                linha = await self._ler_linha(leitor)
                if not linha:
                    break
                comando = linha[:4].upper()
                if comando in ("EHLO", "HELO"):
                    escritor.write(b"250-localhost\r\n250-AUTH LOGIN PLAIN\r\n250 HELP\r\n")
                elif comando == "AUTH":
                    # aceita qualquer usuário/senha (o mock não autentica de verdade; existe só para o
                    # cliente real completar o handshake e provar que a senha nunca é logada em lugar
                    # nenhum do lado do PLAT, não para validar credencial)
                    partes = linha.split()
                    mecanismo = partes[1].upper() if len(partes) > 1 else ""
                    if mecanismo == "LOGIN":
                        escritor.write(b"334 VXNlcm5hbWU6\r\n")  # "Username:"
                        await escritor.drain()
                        await self._ler_linha(leitor)
                        escritor.write(b"334 UGFzc3dvcmQ6\r\n")  # "Password:"
                        await escritor.drain()
                        await self._ler_linha(leitor)
                        escritor.write(b"235 Authentication successful\r\n")
                    elif mecanismo == "PLAIN":
                        if len(partes) < 3:
                            await self._ler_linha(leitor)
                        escritor.write(b"235 Authentication successful\r\n")
                    else:
                        escritor.write(b"504 Unrecognized authentication type\r\n")
                elif comando == "MAIL":
                    mail_from = linha.split(":", 1)[-1].strip()
                    escritor.write(b"250 OK\r\n")
                elif comando == "RCPT":
                    rcpt_to.append(linha.split(":", 1)[-1].strip())
                    escritor.write(b"250 OK\r\n")
                elif comando == "DATA":
                    escritor.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    await escritor.drain()
                    linhas_dados = []
                    while True:
                        dl = await self._ler_linha(leitor)
                        if dl == ".":
                            break
                        linhas_dados.append(dl[1:] if dl.startswith("..") else dl)
                    dados = "\n".join(linhas_dados)
                    with self._trava:
                        self.mensagens.append(Mensagem(mail_from or "", list(rcpt_to), dados))
                    mail_from, rcpt_to = None, []
                    escritor.write(b"250 OK: queued\r\n")
                elif comando == "RSET":
                    mail_from, rcpt_to = None, []
                    escritor.write(b"250 OK\r\n")
                elif comando == "QUIT":
                    escritor.write(b"221 Bye\r\n")
                    await escritor.drain()
                    break
                else:
                    escritor.write(b"500 Command not recognized\r\n")
                await escritor.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            escritor.close()

    def esperar(self, n: int, timeout: float = 20.0) -> bool:
        import time

        fim = time.monotonic() + timeout
        while time.monotonic() < fim:
            with self._trava:
                if len(self.mensagens) >= n:
                    return True
            time.sleep(0.1)
        return False
