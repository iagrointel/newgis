"""Cliente SMTP de biblioteca padrão (`smtplib`/`email.message`), sem dependência nova. `enviar()` nunca
recebe a senha em claro do chamador guardada em lugar nenhum além do argumento local da função — e nunca a
grava em log: qualquer exceção de `smtplib` é convertida para `ErroSMTP` com uma mensagem legível que cita
host/porta/código, jamais o argumento `senha` (conferido por `tests/unit/test_correio_cliente.py::
test_senha_nunca_aparece_na_mensagem_de_erro`, que grava a saída de log inteira e faz grep pela senha)."""

import smtplib
import socket
from email.message import EmailMessage
from email.utils import formataddr

from app import limites
from app.correio.config import ConfigSMTP


class ErroSMTP(RuntimeError):
    """Mensagem sempre segura para log e para o corpo HTTP: nunca inclui usuário/senha."""


def _remetente_formatado(cfg: ConfigSMTP) -> str:
    return formataddr((cfg.rotulo, cfg.remetente)) if cfg.rotulo else cfg.remetente


def montar_mensagem(cfg: ConfigSMTP, destinatario: str, assunto: str, texto: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = assunto[: limites.SMTP_ASSUNTO_MAX]
    msg["From"] = _remetente_formatado(cfg)
    msg["To"] = destinatario
    msg.set_content(texto[: limites.SMTP_TEXTO_MAX])
    return msg


def enviar(cfg: ConfigSMTP, senha: str | None, destinatario: str, assunto: str, texto: str,
           timeout: float = limites.SMTP_ENVIAR_TIMEOUT_S) -> None:
    """Conecta, autentica se houver usuário, envia e fecha. Levanta `ErroSMTP` com mensagem legível (host,
    porta, motivo) em qualquer falha de rede/protocolo/autenticação — nunca a senha."""
    msg = montar_mensagem(cfg, destinatario, assunto, texto)
    try:
        if cfg.porta == 465:  # SMTPS: TLS desde o primeiro byte, nunca STARTTLS depois
            servidor = smtplib.SMTP_SSL(cfg.host, cfg.porta, timeout=timeout)
        else:
            servidor = smtplib.SMTP(cfg.host, cfg.porta, timeout=timeout)
        with servidor:
            servidor.ehlo()
            if cfg.tls and cfg.porta != 465:
                servidor.starttls()
                servidor.ehlo()
            if cfg.usuario:
                servidor.login(cfg.usuario, senha or "")
            servidor.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise ErroSMTP(f"autenticação recusada por {cfg.host}:{cfg.porta} (código {e.smtp_code})") from e
    except smtplib.SMTPConnectError as e:
        raise ErroSMTP(f"não conectou a {cfg.host}:{cfg.porta} (código {e.smtp_code})") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise ErroSMTP(f"destinatário recusado por {cfg.host}:{cfg.porta}: {destinatario}") from e
    except smtplib.SMTPHeloError as e:
        raise ErroSMTP(f"servidor {cfg.host}:{cfg.porta} recusou o EHLO/HELO") from e
    except smtplib.SMTPNotSupportedError as e:
        raise ErroSMTP(f"{cfg.host}:{cfg.porta} não oferece o recurso pedido (STARTTLS/AUTH): {e}") from e
    except smtplib.SMTPException as e:
        raise ErroSMTP(f"falha SMTP em {cfg.host}:{cfg.porta}: {type(e).__name__}") from e
    except (socket.timeout, TimeoutError) as e:
        raise ErroSMTP(f"tempo esgotado ao falar com {cfg.host}:{cfg.porta} ({timeout:.0f} s)") from e
    except (socket.gaierror, ConnectionRefusedError, OSError) as e:
        raise ErroSMTP(f"não foi possível conectar a {cfg.host}:{cfg.porta}: {type(e).__name__}") from e
