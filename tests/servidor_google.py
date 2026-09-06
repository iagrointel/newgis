"""Servidor de prova dos DOIS protocolos do Google Sheets (item L6-02-i-google-sheets).

Por que ele existe: o item tem duas portas de entrada — a planilha publicada (exportação CSV sem credencial)
e a planilha privada (conta de serviço -> JWT RS256 -> access token -> exportação CSV com Bearer). Provar as
duas contra o Google de verdade exigiria uma conta Google da casa, que não existe (registrado como pendente
nas medidas do item, nunca como feito). O que dá para provar de verdade AQUI é o protocolo inteiro, e é o
que este servidor faz:

  * HTTPS de verdade no IP PÚBLICO da máquina (a defesa de SSRF continua ligada e recusaria `localhost`;
    `validar_conta_servico` exige `token_uri` https, então HTTP simples não basta). O certificado é de uma
    CA de teste gerada na hora; o bundle `SSL_CERT_FILE` que o worker e o processo do teste recebem é a CA
    de teste MAIS as CAs do sistema — nenhuma verificação é desligada, só se acrescenta uma raiz.
  * `GET /spreadsheets/d/<id>/export?format=csv` e `GET /spreadsheets/d/e/<pac>/pub?output=csv&single=true`:
    a planilha pública responde sem cabeçalho; a privada só responde com `Authorization: Bearer <token>`
    emitido por este servidor (senão 401, como o Google).
  * `POST /oauth2/token`: fluxo `urn:ietf:params:oauth:grant-type:jwt-bearer` da RFC 7523 de verdade — a
    assinatura RS256 do JWT é VERIFICADA com a chave pública da conta de serviço de teste, e iss/aud/scope/
    exp são conferidos. Só então sai um access token. `revogar()` faz o endpoint responder `invalid_grant`,
    que é exatamente o que o Google devolve quando a conta é desativada — a refutação do item.

Cada requisição fica registrada em `pedidos`/`trocas` para o teste afirmar (a) que a planilha privada nunca
foi buscada sem token, (b) que a pública nunca recebeu credencial e (c) que a troca de token aconteceu com
assinatura válida.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import http.server
import ipaddress
import json
import socket
import socketserver
import ssl
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from tests.servidor_arquivo import ip_publico

ESCOPO_PLANILHAS = "https://www.googleapis.com/auth/spreadsheets.readonly"
GRANT_JWT_BEARER = "urn:ietf:params:oauth:grant-type:jwt-bearer"


def _b64url_decodificar(trecho: str) -> bytes:
    return base64.urlsafe_b64decode(trecho + "=" * (-len(trecho) % 4))


def _escrever_pem(destino: Path, *blocos: bytes) -> None:
    destino.write_bytes(b"".join(blocos))
    destino.chmod(0o600)


class ServidorGoogle:
    """Uso: `with ServidorGoogle() as g: g.publicar_publica(id_, csv); g.conta_servico_json()`."""

    def __init__(self):
        self.host = ip_publico()
        self.pedidos: list[dict] = []          # GETs de exportação: caminho, query e cabeçalhos
        self.trocas: list[dict] = []           # POSTs de token: claims do JWT, assinatura válida, desfecho
        self.tokens: dict[str, float] = {}     # access token -> validade (epoch)
        self._revogada = False

        # conta de serviço de teste: chave RSA própria, gerada na hora, e-mail único por rodada
        self._chave_conta = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.client_email = f"conta-teste-{uuid.uuid4().hex[:12]}@projeto-teste.iam.gserviceaccount.com"
        self.private_key_id = uuid.uuid4().hex

        # planilhas: caminho -> {"corpo": bytes, "exige_token": bool}
        self._planilhas: dict[str, dict] = {}

        self._diretorio = Path(tempfile.mkdtemp(prefix="servidor_google_"))
        self._montar_tls()
        self._montar_servidor()

    # ------------------------------------------------------------------ TLS (CA de teste + cert do IP)
    def _montar_tls(self) -> None:
        agora = datetime.datetime.now(datetime.UTC)
        ca_chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA de teste L6-02-i")])
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_nome).issuer_name(ca_nome)
            .public_key(ca_chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - datetime.timedelta(hours=1))
            .not_valid_after(agora + datetime.timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False, content_commitment=False, key_encipherment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                    encipher_only=False, decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_chave, hashes.SHA256())
        )
        srv_chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        srv_cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, self.host)]))
            .issuer_name(ca_nome)
            .public_key(srv_chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - datetime.timedelta(hours=1))
            .not_valid_after(agora + datetime.timedelta(days=2))
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(self.host))]),
                critical=False,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True, content_commitment=False, key_encipherment=True,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                    encipher_only=False, decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_chave, hashes.SHA256())
        )
        ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
        _escrever_pem(
            self._diretorio / "servidor.pem",
            srv_cert.public_bytes(serialization.Encoding.PEM),
            srv_chave.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ),
        )
        # bundle = CA de teste + as CAs do sistema: quem roda com SSL_CERT_FILE apontando para ele continua
        # verificando o Google de verdade (a medida de alcance roda no mesmo processo) E o servidor de prova.
        raizes_sistema = b""
        padrao = ssl.get_default_verify_paths()
        if padrao.cafile and Path(padrao.cafile).exists():
            raizes_sistema = Path(padrao.cafile).read_bytes()
        self.bundle = self._diretorio / "bundle.pem"
        _escrever_pem(self.bundle, ca_pem, b"\n", raizes_sistema)
        self.tem_raizes_sistema = bool(raizes_sistema)

    # ------------------------------------------------------------------ servidor HTTPS
    def _montar_servidor(self) -> None:
        pai = self

        class Manipulador(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _responder(self, status: int, corpo: bytes = b"", cabecalhos: dict | None = None):
                self.send_response(status)
                for k, v in (cabecalhos or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                if corpo:
                    self.wfile.write(corpo)

            def do_GET(self):  # noqa: N802 — nome exigido pela BaseHTTPRequestHandler
                partes = urlsplit(self.path)
                planilha = pai._planilhas.get(partes.path)
                if planilha is None:
                    self._responder(404, b"planilha desconhecida", {"Content-Type": "text/plain"})
                    return
                cabecalhos = {k.lower(): v for k, v in self.headers.items()}
                pai.pedidos.append({"caminho": partes.path, "query": partes.query, "cabecalhos": cabecalhos})
                if planilha["exige_token"]:
                    autorizacao = cabecalhos.get("authorization", "")
                    token = autorizacao[7:] if autorizacao.startswith("Bearer ") else ""
                    if not token or pai.tokens.get(token, 0) < time.time():
                        corpo = json.dumps({"error": {"code": 401, "message": "Request is missing required "
                                            "authentication credential."}}).encode("utf-8")
                        self._responder(401, corpo, {"Content-Type": "application/json"})
                        return
                etag = '"' + hashlib.sha256(planilha["corpo"]).hexdigest()[:32] + '"'
                if self.headers.get("If-None-Match") == etag:
                    self._responder(304, b"", {"ETag": etag})
                    return
                self._responder(200, planilha["corpo"], {"Content-Type": "text/csv", "ETag": etag})

            def do_POST(self):  # noqa: N802 — nome exigido pela BaseHTTPRequestHandler
                if urlsplit(self.path).path != "/oauth2/token":
                    self._responder(404, b"desconhecido", {"Content-Type": "text/plain"})
                    return
                tamanho = int(self.headers.get("Content-Length") or 0)
                forma = parse_qs(self.rfile.read(tamanho).decode("utf-8"))
                assertion = (forma.get("assertion") or [""])[0]
                grant = (forma.get("grant_type") or [""])[0]
                registro = {"grant": grant, "assinatura_valida": False, "claims": None, "desfecho": ""}
                pai.trocas.append(registro)

                def recusa(codigo: str):
                    registro["desfecho"] = codigo
                    corpo = json.dumps({"error": codigo}).encode("utf-8")
                    self._responder(400, corpo, {"Content-Type": "application/json"})

                if grant != GRANT_JWT_BEARER:
                    recusa("unsupported_grant_type")
                    return
                try:
                    cab_b64, pay_b64, ass_b64 = assertion.split(".")
                    claims = json.loads(_b64url_decodificar(pay_b64))
                    registro["claims"] = claims
                    pai._chave_conta.public_key().verify(
                        _b64url_decodificar(ass_b64), f"{cab_b64}.{pay_b64}".encode("ascii"),
                        padding.PKCS1v15(), hashes.SHA256(),
                    )
                    registro["assinatura_valida"] = True
                except (ValueError, KeyError, json.JSONDecodeError):
                    recusa("invalid_grant")
                    return
                if (claims.get("iss") != pai.client_email or claims.get("aud") != pai.token_uri
                        or ESCOPO_PLANILHAS not in str(claims.get("scope", ""))
                        or int(claims.get("exp", 0)) < time.time()):
                    recusa("invalid_grant")
                    return
                if pai._revogada:
                    # conta desativada no console: o Google responde exatamente isto
                    recusa("invalid_grant")
                    return
                token = f"ya29.teste-{uuid.uuid4().hex}"
                pai.tokens[token] = time.time() + 3600
                registro["desfecho"] = "concedido"
                corpo = json.dumps({"access_token": token, "expires_in": 3600,
                                    "token_type": "Bearer"}).encode("utf-8")
                self._responder(200, corpo, {"Content-Type": "application/json"})

            def log_message(self, *args):  # silencia o log do http.server na saída do pytest
                return

        class Servidor(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._servidor = Servidor(("0.0.0.0", 0), Manipulador)  # noqa: S104 — o teste precisa do IP público
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.load_cert_chain(str(self._diretorio / "servidor.pem"))
        self._servidor.socket = contexto.wrap_socket(self._servidor.socket, server_side=True)
        self.porta = self._servidor.server_address[1]
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)

    # ------------------------------------------------------------------ interface pública
    def __enter__(self) -> ServidorGoogle:
        self._thread.start()
        with socket.create_connection((self.host, self.porta), timeout=5):
            pass
        return self

    def __exit__(self, *exc):
        self._servidor.shutdown()
        self._servidor.server_close()
        self._thread.join(timeout=5)

    @property
    def base(self) -> str:
        return f"https://{self.host}:{self.porta}"

    @property
    def token_uri(self) -> str:
        return f"{self.base}/oauth2/token"

    def publicar_publica(self, id_planilha: str, corpo_csv: bytes) -> str:
        """Planilha publicada na web: exportação CSV sem credencial. Devolve a URL de EDIÇÃO (a forma que o
        usuário cola; a plataforma é quem normaliza para a forma de exportação)."""
        self._planilhas[f"/spreadsheets/d/{id_planilha}/export"] = {"corpo": corpo_csv, "exige_token": False}
        return f"{self.base}/spreadsheets/d/{id_planilha}/edit"

    def publicar_pacote_publicado(self, id_pacote: str, corpo_csv: bytes) -> str:
        """A outra forma pública: 'Arquivo > Publicar na web', que o Google serve por /pub?output=csv."""
        self._planilhas[f"/spreadsheets/d/e/{id_pacote}/pub"] = {"corpo": corpo_csv, "exige_token": False}
        return f"{self.base}/spreadsheets/d/e/{id_pacote}/pubhtml"

    def publicar_privada(self, id_planilha: str, corpo_csv: bytes) -> str:
        """Planilha privada compartilhada com a conta de serviço: exportação só com Bearer válido."""
        self._planilhas[f"/spreadsheets/d/{id_planilha}/export"] = {"corpo": corpo_csv, "exige_token": True}
        return f"{self.base}/spreadsheets/d/{id_planilha}/edit"

    def trocar_corpo(self, id_planilha: str, corpo_csv: bytes) -> None:
        self._planilhas[f"/spreadsheets/d/{id_planilha}/export"]["corpo"] = corpo_csv

    def conta_servico_json(self) -> str:
        """O JSON no formato exato do console do Google (campos que `validar_conta_servico` exige)."""
        pem = self._chave_conta.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode("ascii")
        return json.dumps({
            "type": "service_account",
            "project_id": "projeto-teste-l602i",
            "private_key_id": self.private_key_id,
            "private_key": pem,
            "client_email": self.client_email,
            "client_id": "100000000000000000001",
            "token_uri": self.token_uri,
        })

    def revogar(self) -> None:
        self._revogada = True

    def reativar(self) -> None:
        self._revogada = False

    def autorizacoes_da(self, id_planilha: str) -> list[str | None]:
        """Cabeçalho Authorization de cada GET na exportação desta planilha (None quando ausente)."""
        prefixo = f"/spreadsheets/d/{id_planilha}/export"
        return [p["cabecalhos"].get("authorization") for p in self.pedidos if p["caminho"] == prefixo]
