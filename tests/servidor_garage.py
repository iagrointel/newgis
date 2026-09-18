"""Garage de mentira para testes: S3 path-style e Admin API v2 em memória, num único porto 127.0.0.1.

Por que ele existe: o caminho "arquivo por URL vira camada" (item L6-02-h) grava o arquivo baixado com
`objetos.guardar` e a ingestão o lê de volta com `objetos.ler` — os dois falam S3/Admin com o Garage
(item L0-11). O Garage de trilhas (`plataforma-garage-trilhas.service`) não existe em toda máquina onde a
suíte roda; sem um substituto, o teste ponta a ponta do L6-02-h não roda nessas máquinas. O duble cobre
EXATAMENTE o contrato que o caminho usa:

  S3:    PUT/GET/HEAD/DELETE de objeto (path-style, /<balde>/<chave>); a assinatura SigV4 é ignorada —
         ela é prova do L0-11 contra o Garage real, não deste item.
  Admin: ListBuckets/CreateBucket, ListKeys/CreateKey, AllowBucketKey, UpdateBucket (cota) e
         GetBucketInfo — o que `objetos.garantir_bucket` chama.

O que ele NÃO faz, de propósito: multipart, ListObjects, Range, GetKeyInfo, endpoint web e verificação da assinatura
SigV4 em si — ela é prova do L0-11 contra o Garage real, não deste duble. O que ele EXIGE, desde o item
L2-03-e-anexos: cabeçalho `Authorization` presente (assinada ou não) em todo acesso S3 e `Bearer` qualquer
na Admin API — o Garage real devolve 403 AccessDenied ao acesso ANÔNIMO (MEDIDO na instância v2.3.0, ver
ADR 0006 seção 3 e o docstring de `definir_web`: "GET/LIST anônimos no endpoint S3 continuam 403"), e é essa
recusa que o portão do L2-03-e prova para a "URL direta do Garage". A API sempre assina (ClienteS3/ClienteAdmin),
logo quem passa pela aplicação não nota a exigência.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socket
import socketserver
import threading
import urllib.parse


class GarageDuble:
    """Uso: `with GarageDuble() as g: ... g.url`. Buckets/chaves/objetos vivem só em memória."""

    def __init__(self):
        self.baldes: dict[str, dict] = {}   # alias -> {"id", "objetos": {chave: (bytes, content_type)}}
        self.chaves: dict[str, dict] = {}   # nome  -> {"accessKeyId", "secretAccessKey"}
        self._trava = threading.Lock()
        duble = self

        class Manipulador(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _responder(self, status: int, corpo: bytes = b"", cabecalhos: dict | None = None):
                self.send_response(status)
                enviados = set()
                for k, v in (cabecalhos or {}).items():
                    self.send_header(k, v)
                    enviados.add(k.lower())
                if "content-length" not in enviados:  # o HEAD declara o tamanho do OBJETO, não o do corpo
                    self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                if corpo:
                    self.wfile.write(corpo)

            def _json(self, status: int, doc):
                self._responder(status, json.dumps(doc).encode("utf-8"),
                                {"Content-Type": "application/json"})

            def _corpo(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def _nao_achado(self):
                corpo = b"<Error><Code>NoSuchKey</Code><Message>nao existe</Message></Error>"
                self._responder(404, corpo, {"Content-Type": "application/xml"})

            def _proibido_anonimo(self):
                # MEDIDO no Garage real v2.3.0 (ADR 0006): acesso sem Authorization = 403 AccessDenied.
                corpo = b"<Error><Code>AccessDenied</Code><Message>Access Denied.</Message></Error>"
                self._responder(403, corpo, {"Content-Type": "application/xml"})

            # ------------------------------------------------------------ S3 path-style
            def _s3(self, metodo: str):
                if not self.headers.get("Authorization"):
                    self._proibido_anonimo()
                    return
                partes = urllib.parse.unquote(self.path.split("?")[0]).lstrip("/").split("/", 1)
                balde = partes[0]
                chave = partes[1] if len(partes) > 1 else ""
                with duble._trava:
                    # balde desconhecido é criado no acesso: a linha de plat.arquivo_bucket sobrevive na
                    # base de teste entre duas rodadas da suíte, mas o duble em memória não — sem isto, a
                    # 2ª rodada em diante falhava com 404 no PUT de um balde que a base dizia existir.
                    b = duble.baldes.setdefault(
                        balde, {"id": f"b-{balde}", "objetos": {}, "cota_bytes": 0, "cota_objetos": None})
                    objetos = b["objetos"]
                    if metodo == "PUT":
                        corpo = self._corpo()
                        etag = hashlib.md5(corpo).hexdigest()  # noqa: S324 — ETag de mentira, não é segurança
                        objetos[chave] = (corpo, self.headers.get("Content-Type") or "application/octet-stream")
                        self._responder(200, b"", {"ETag": f'"{etag}"'})
                    elif metodo == "GET":
                        if chave not in objetos:
                            self._nao_achado()
                            return
                        dados, tipo = objetos[chave]
                        self._responder(200, dados, {"Content-Type": tipo,
                                                     "ETag": f'"{hashlib.md5(dados).hexdigest()}"'})  # noqa: S324
                    elif metodo == "HEAD":
                        if chave not in objetos:
                            self._nao_achado()
                            return
                        dados, tipo = objetos[chave]
                        self._responder(200, b"", {"Content-Type": tipo, "Content-Length": str(len(dados)),
                                                   "ETag": f'"{hashlib.md5(dados).hexdigest()}"'})  # noqa: S324
                    elif metodo == "DELETE":
                        existia = objetos.pop(chave, None) is not None
                        self._responder(204 if existia else 204, b"")
                    else:
                        self._responder(405, b"")

            # ------------------------------------------------------------ Admin API v2 (JSON)
            def _admin_get(self, caminho: str, query: dict):
                if caminho == "/v2/ListBuckets":
                    with duble._trava:
                        self._json(200, [{"id": b["id"], "globalAliases": [alias], "keys": []}
                                         for alias, b in duble.baldes.items()])
                elif caminho == "/v2/ListKeys":
                    with duble._trava:
                        self._json(200, [{"id": c["accessKeyId"], "name": nome}
                                         for nome, c in duble.chaves.items()])
                elif caminho == "/v2/GetBucketInfo":
                    with duble._trava:
                        b = next((x for x in duble.baldes.values() if x["id"] == query.get("id")), None)
                        if b is None:
                            self._json(404, {"error": "balde inexistente"})
                            return
                        self._json(200, {"id": b["id"], "keys": [], "websiteAccess": None,
                                         "bytes": sum(len(d) for d, _ in b["objetos"].values()),
                                         "objects": len(b["objetos"]),
                                         "quotas": {"maxSize": b["cota_bytes"], "maxObjects": b["cota_objetos"]}})
                else:
                    self._json(404, {"error": f"admin desconhecido: {caminho}"})

            def _admin_post(self, caminho: str, query: dict):
                doc = json.loads(self._corpo() or b"{}")
                with duble._trava:
                    if caminho == "/v2/CreateBucket":
                        alias = doc["globalAlias"]
                        b = duble.baldes.setdefault(
                            alias, {"id": f"b-{alias}", "objetos": {},
                                    "cota_bytes": 0, "cota_objetos": None})
                        self._json(200, {"id": b["id"], "globalAliases": [alias], "keys": []})
                    elif caminho == "/v2/CreateKey":
                        nome = doc["name"]
                        c = duble.chaves.setdefault(
                            nome, {"accessKeyId": "GK" + hashlib.sha256(nome.encode()).hexdigest()[:16],
                                   "secretAccessKey": "segredo-de-teste-" + nome})
                        self._json(200, {"accessKeyId": c["accessKeyId"],
                                         "secretAccessKey": c["secretAccessKey"], "name": nome})
                    elif caminho == "/v2/AllowBucketKey":
                        self._json(200, {"id": doc.get("bucketId")})
                    elif caminho == "/v2/UpdateBucket":
                        b = next((x for x in duble.baldes.values() if x["id"] == query.get("id")), None)
                        if b is not None:
                            cotas = doc.get("quotas") or {}
                            b["cota_bytes"] = int(cotas.get("maxSize") or 0)
                            b["cota_objetos"] = cotas.get("maxObjects")
                        self._json(200, {"id": query.get("id")})
                    else:
                        self._json(404, {"error": f"admin desconhecido: {caminho}"})

            def do_GET(self):  # noqa: N802 — nome exigido pela BaseHTTPRequestHandler
                caminho, _, qs = self.path.partition("?")
                if caminho.startswith("/v2/"):
                    if not self.headers.get("Authorization", "").startswith("Bearer "):
                        self._json(403, {"error": "AccessDenied"})
                        return
                    self._admin_get(caminho, {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()})
                else:
                    self._s3("GET")

            def do_HEAD(self):  # noqa: N802
                self._s3("HEAD")

            def do_PUT(self):  # noqa: N802
                self._s3("PUT")

            def do_DELETE(self):  # noqa: N802
                self._s3("DELETE")

            def do_POST(self):  # noqa: N802
                caminho, _, qs = self.path.partition("?")
                if caminho.startswith("/v2/"):
                    if not self.headers.get("Authorization", "").startswith("Bearer "):
                        self._json(403, {"error": "AccessDenied"})
                        return
                    self._admin_post(caminho, {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()})
                else:
                    self._responder(405, b"")

            def log_message(self, *args):  # silencia o log do http.server na saída do pytest
                return

        class Servidor(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

            def handle_error(self, request, client_address):  # a sonda do __enter__ fecha sem ler; silencia
                return

        self._servidor = Servidor(("127.0.0.1", 0), Manipulador)
        self.porta = self._servidor.server_address[1]
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    def __enter__(self) -> GarageDuble:
        self._thread.start()
        with socket.create_connection(("127.0.0.1", self.porta), timeout=5):
            pass
        return self

    def __exit__(self, *exc):
        self._servidor.shutdown()
        self._servidor.server_close()
        self._thread.join(timeout=5)


if __name__ == "__main__":
    # auto-checagem mínima: sobe, cria balde/chave pelo cliente admin real, grava e lê um objeto pelo S3 real
    from app.garage import ClienteAdmin, ClienteS3

    with GarageDuble() as g:
        admin = ClienteAdmin(g.url, "token-qualquer")
        balde = admin.criar_bucket("t-plat-demo")
        rw = admin.criar_chave("t-plat-demo-rw")
        admin.permitir(balde["id"], rw["accessKeyId"], ler=True, escrever=True, dono=True)
        admin.definir_cota(balde["id"], 1000, 10)
        cli = ClienteS3(g.url, rw["accessKeyId"], rw["secretAccessKey"])
        assert cli.head("t-plat-demo", "classe/x.bin") is None
        cli.put("t-plat-demo", "classe/x.bin", b"conteudo", "application/octet-stream")
        assert cli.get("t-plat-demo", "classe/x.bin") == b"conteudo"
        assert cli.head("t-plat-demo", "classe/x.bin").tamanho == 8
        assert cli.delete("t-plat-demo", "classe/x.bin") is True
        assert cli.head("t-plat-demo", "classe/x.bin") is None
        try:
            cli.get("t-plat-demo", "classe/x.bin")
            raise AssertionError("GET de objeto apagado devia dar FileNotFoundError")
        except FileNotFoundError:
            pass
        assert admin.info_bucket(balde["id"])["quotas"]["maxSize"] == 1000
        # acesso ANÔNIMO (sem Authorization) é recusado como no Garage real (item L2-03-e)
        import urllib.request
        for url in (f"{g.url}/t-plat-demo/classe/x.bin", f"{g.url}/v2/ListBuckets"):
            try:
                urllib.request.urlopen(url, timeout=5)
                raise AssertionError(f"anonimo devia dar 403: {url}")
            except urllib.error.HTTPError as e:
                assert e.code == 403, (url, e.code)
    print("servidor_garage: auto-checagem ok")
