"""IdP OIDC sintético que reproduz o formato documentado do Login Único gov.br (item L0-08-c-govbr; roteiro
técnico público, acesso.gov.br/roteiro-tecnico/iniciarintegracao.html): descoberta, JWKS, `/authorize` (sem tela:
redireciona na hora com `code`+`state` para o cidadão escolhido), `/token` (id_token RS256 com `sub` = CPF, `amr`,
`reliability_info` {level, reliabilities} quando o escopo `govbr_confiabilidades_idtoken` foi pedido) e a API de
confiabilidades (`/confiabilidades/v3/contas/{cpf}/niveis` e `/confiabilidades`, `response-type=ids`). Um segundo
issuer (`/outro`) com chave própria serve à refutação: id_token assinado por ele com nível 'gold' dentro tem de
ser recusado pelo adaptador. Chaves geradas na hora (nada de chave privada no repositório). Só para teste."""

from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

from joserfc import jwt
from joserfc.jwk import RSAKey

CIDADAOS = {
    # cpf sintético: dados; todos fictícios (formato do roteiro)
    "11111111111": {"name": "Cidadã Ouro", "email": "ouro@exemplo.test", "level": "gold",
                    "reliabilities": [{"id": "801", "updatedAt": "2025-07-02T14:17:16.001-0300"},
                                      {"id": "701", "updatedAt": "2025-07-02T14:17:16.001-0300"}],
                    "amr": ["passwd", "mfa", "otp_offline"]},
    "22222222222": {"name": "Cidadão Prata", "email": "prata@exemplo.test", "level": "silver",
                    "reliabilities": [{"id": "602", "updatedAt": "2025-07-02T14:17:16.001-0300"}],
                    "amr": ["passwd"]},
    "33333333333": {"name": "Cidadã Bronze", "email": "bronze@exemplo.test", "level": "bronze",
                    "reliabilities": [{"id": "201", "updatedAt": "2025-07-02T14:17:16.001-0300"}],
                    "amr": ["passwd"]},
    "44444444444": {"name": "Cidadão Sem Escopo", "email": None, "level": "silver",
                    "reliabilities": [{"id": "401", "updatedAt": "2025-07-02T14:17:16.001-0300"}],
                    "amr": ["passwd"], "sem_reliability_no_token": True},
}
NIVEL_API = {"bronze": "1 (Bronze)", "silver": "2 (Prata)", "gold": "3 (Ouro)"}


class IdpGovBrFalso:
    """Servidor HTTP em thread; `issuer` = http://127.0.0.1:<porta>; `issuer_outro` = .../outro."""

    def __init__(self, porta: int = 0):
        self.chave = RSAKey.generate_key(2048, {"kid": "govbr-teste-1"})
        self.chave_outro = RSAKey.generate_key(2048, {"kid": "outro-issuer-1"})
        self.codigos: dict[str, dict] = {}
        self.tokens: dict[str, str] = {}  # access_token -> cpf
        self.cidadao_atual = "11111111111"
        self.forjar_outro_issuer = False
        self.chamadas_api: list[str] = []
        self.servidor = ThreadingHTTPServer(("127.0.0.1", porta), self._handler())
        self.porta = self.servidor.server_address[1]
        self.issuer = f"http://127.0.0.1:{self.porta}"
        self.issuer_outro = f"{self.issuer}/outro"
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    def iniciar(self) -> IdpGovBrFalso:
        self.thread.start()
        return self

    def parar(self) -> None:
        self.servidor.shutdown()
        self.servidor.server_close()

    # ---------------------------------------------------------------- tokens
    def _id_token(self, cpf: str, client_id: str, nonce: str, escopos: str) -> str:
        c = CIDADAOS[cpf]
        agora = int(time.time())
        forjado = self.forjar_outro_issuer
        claims = {
            "iss": self.issuer_outro if forjado else self.issuer,
            "sub": cpf,
            "aud": client_id,
            "exp": agora + 300,
            "iat": agora,
            "auth_time": agora,
            "nonce": nonce,
            "name": c["name"],
            "amr": c["amr"],
            "email_verified": bool(c["email"]),
            "phone_number": "99999999999",
            "phone_number_verified": True,
            "picture": f"{self.issuer}/userinfo/picture",
        }
        if c["email"]:
            claims["email"] = c["email"]
        if ("govbr_confiabilidades_idtoken" in escopos and not c.get("sem_reliability_no_token")) or forjado:
            claims["reliability_info"] = {
                "level": "gold" if forjado else c["level"], "reliabilities": c["reliabilities"],
            }
        chave = self.chave_outro if forjado else self.chave
        return jwt.encode({"alg": "RS256", "kid": chave.kid}, claims, chave)

    def _handler(self):
        idp = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *_a):  # silencioso
                return

            def _json(self, corpo, status=200):
                dados = json.dumps(corpo).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_GET(self):  # noqa: N802
                u = urlsplit(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                caminho = u.path
                if caminho == "/.well-known/openid-configuration":
                    return self._json({
                        "issuer": idp.issuer,
                        "authorization_endpoint": f"{idp.issuer}/authorize",
                        "token_endpoint": f"{idp.issuer}/token",
                        "jwks_uri": f"{idp.issuer}/jwk",
                        "userinfo_endpoint": f"{idp.issuer}/userinfo",
                        "end_session_endpoint": f"{idp.issuer}/logout",
                        "id_token_signing_alg_values_supported": ["RS256"],
                        "scopes_supported": ["openid", "email", "profile", "govbr_confiabilidades",
                                             "govbr_confiabilidades_idtoken"],
                    })
                if caminho == "/outro/.well-known/openid-configuration":
                    return self._json({
                        "issuer": idp.issuer_outro,
                        "authorization_endpoint": f"{idp.issuer_outro}/authorize",
                        "token_endpoint": f"{idp.issuer_outro}/token",
                        "jwks_uri": f"{idp.issuer_outro}/jwk",
                    })
                if caminho == "/jwk":
                    return self._json({"keys": [idp.chave.as_dict(private=False)]})
                if caminho == "/outro/jwk":
                    return self._json({"keys": [idp.chave_outro.as_dict(private=False)]})
                if caminho == "/authorize":
                    if q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
                        return self._json({"error": "invalid_request", "error_description": "PKCE S256"}, 400)
                    codigo = secrets.token_urlsafe(24)
                    idp.codigos[codigo] = {
                        "cpf": q.get("cpf") or idp.cidadao_atual, "client_id": q.get("client_id", ""),
                        "nonce": q.get("nonce", ""), "scope": q.get("scope", ""),
                        "redirect_uri": q.get("redirect_uri", ""),
                        "code_challenge": q["code_challenge"],
                    }
                    volta = urlencode({"code": codigo, "state": q.get("state", "")})
                    destino = q.get("redirect_uri", "") + "?" + volta
                    self.send_response(302)
                    self.send_header("Location", destino)
                    self.end_headers()
                    return None
                if caminho.startswith("/confiabilidades/v3/contas/"):
                    partes = caminho.split("/")
                    cpf, recurso = partes[4], partes[5] if len(partes) > 5 else ""
                    auth = self.headers.get("Authorization", "")
                    token = auth[7:] if auth.startswith("Bearer ") else ""
                    if idp.tokens.get(token) != cpf:
                        return self._json({"erro": "token invalido ou de outro cidadão"}, 401)
                    idp.chamadas_api.append(caminho)
                    c = CIDADAOS[cpf]
                    if recurso == "niveis":
                        ordem = ["bronze", "silver", "gold"]
                        ate = ordem.index(c["level"])
                        niveis = [
                            {"id": NIVEL_API[n], "dataAtualizacao": "2025-07-02 14:17:16"} for n in ordem[: ate + 1]
                        ]
                        return self._json(niveis)
                    if recurso == "confiabilidades":
                        selos = [{"id": s["id"], "dataAtualizacao": "2025-07-02 14:17:16"} for s in c["reliabilities"]]
                        return self._json(selos)
                self._json({"erro": "rota inexistente"}, 404)
                return None

            def do_POST(self):  # noqa: N802
                u = urlsplit(self.path)
                n = int(self.headers.get("Content-Length", "0") or 0)
                corpo = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8")).items()}
                if u.path in ("/token", "/outro/token"):
                    cod = idp.codigos.pop(corpo.get("code", ""), None)
                    if cod is None or corpo.get("grant_type") != "authorization_code":
                        return self._json({"error": "invalid_grant"}, 400)
                    import base64
                    import hashlib

                    esperado = base64.urlsafe_b64encode(
                        hashlib.sha256(corpo.get("code_verifier", "").encode("ascii")).digest()
                    ).decode("ascii").rstrip("=")
                    if esperado != cod["code_challenge"]:
                        return self._json({"error": "invalid_grant", "error_description": "code_verifier"}, 400)
                    access = "at-" + secrets.token_urlsafe(24)
                    idp.tokens[access] = cod["cpf"]
                    return self._json({
                        "access_token": access, "token_type": "Bearer", "expires_in": 3600,
                        "id_token": idp._id_token(cod["cpf"], cod["client_id"], cod["nonce"], cod["scope"]),
                        "scope": cod["scope"],
                    })
                self._json({"erro": "rota inexistente"}, 404)
                return None

        return H
