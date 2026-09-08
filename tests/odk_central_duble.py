"""Dublê HTTP da API do ODK Central (item L2-07-e-odk-central-ponte).

Por que um dublê e não o Central de verdade: o Central se instala por docker (docs.getodk.org/central-install)
e nesta máquina docker não sobe; o disco está em 96 % e uma pilha de contêineres do Central (node + postgres +
nginx + enketo) não caberia. A decisão está no ADR do item, com o que ela NÃO prova.

O que o dublê é: um servidor HTTP falso montado em cima de `httpx.MockTransport`, respondendo aos MESMOS
caminhos, parâmetros e formas de resposta que a documentação do Central publica (versão lida em 2026-09-08):

  POST /v1/projects/{p}/forms?publish=true                 -> {projectId, xmlFormId, name, version, hash, ...}
  GET  /v1/projects/{p}/forms/{xmlFormId}                  -> o mesmo objeto
  GET  /v1/projects/{p}/forms/{xmlFormId}.svc/Submissions  -> {@odata.context, @odata.count, value: [...]}
  GET  /v1/.../submissions/{instanceId}/attachments        -> [{name, exists}]
  GET  /v1/.../submissions/{instanceId}/attachments/{nome} -> os bytes
  GET  /v1/projects/{p}/datasets/{nome}/entities           -> [{uuid, currentVersion: {label, data}}]

O caminho de rede continua REAL até o transporte: `instalar()` troca só `socket.getaddrinfo` (para o nome do
dublê resolver num IP público) e `app.conexao.seguranca.cliente_pinado` (para o transporte ser o dublê). Toda a
validação de SSRF de `validar_url` roda de verdade — é por isso que apontar a conexão para um host interno
continua sendo bloqueado nos testes, e não por um `if` do dublê."""

from __future__ import annotations

import json
import socket
import struct
import zlib
from urllib.parse import parse_qs, urlsplit

import httpx

HOST = "central.odk.teste"
URL_BASE = f"https://{HOST}"
IP_PUBLICO = "8.8.8.8"  # mesmo truque de tests/api/test_conexoes_credencial_saltos.py: nome -> IP não privado
TOKEN = "zt-odk-token-de-teste"


def png(cor: tuple[int, int, int]) -> bytes:
    """PNG 1x1 de verdade (a varredura de conteúdo usa libmagic: byte mágico falso é recusado). Cor diferente
    = bytes diferentes = sha256 diferente, que é o que o teste de anexo precisa."""
    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes([0, *cor]))
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", ihdr) + bloco(b"IDAT", idat) + bloco(b"IEND", b"")


class CentralDuble:
    def __init__(self, projeto: int = 7, token: str = TOKEN):
        self.projeto = projeto
        self.token = token
        self.formularios: dict[str, dict] = {}
        self.envios: list[dict] = []
        self.anexos: dict[tuple[str, str], bytes] = {}  # (instanceId, nome) -> bytes
        self.entidades: dict[str, list[dict]] = {}
        self.chamadas: list[tuple[str, str]] = []       # (método, caminho+consulta), na ordem
        self.corpo_publicado: bytes | None = None
        self.cabecalhos_publicacao: dict[str, str] = {}
        self.resposta_crua: bytes | None = None         # força um corpo que não é JSON
        self.status_forcado: int | None = None          # força um status (401, 500, ...)

    # -------------------------------------------------------------- montagem do estado
    def semear_envios(self, n: int, *, com_foto: bool = True, prefixo: str = "uuid:zt-odk-") -> None:
        for i in range(n):
            iid = f"{prefixo}{i:03d}"
            linha = {
                "__id": iid,
                "__system": {"submissionDate": f"2026-09-0{i % 9 + 1}T10:00:00.000Z", "submitterId": 5,
                             "reviewState": None, "deletedAt": None},
                "inicio": "2026-09-01T09:55:00.000Z", "fim": "2026-09-01T10:00:00.000Z",
                "ponto": f"P-{i:03d}",
                "local": {"type": "Point", "coordinates": [-46.6 - i / 1000, -23.5 - i / 1000]},
                "detalhe": {"arvores": i, "estado_ponto": "bom" if i % 2 == 0 else "ruim"},
                "amostras": [{"codigo_a": f"A{i}-1", "peso_a": 1.5}, {"codigo_a": f"A{i}-2", "peso_a": 2.5}],
                "meta": {"instanceID": iid},
            }
            if com_foto:
                nome = f"foto-{i:03d}.png"
                linha["foto"] = nome
                self.anexos[(iid, nome)] = png((i * 7 % 256, 128, 32))
            self.envios.append(linha)

    def semear_entidades(self, dataset: str, linhas: list[dict]) -> None:
        self.entidades[dataset] = [
            {"uuid": u, "createdAt": "2026-09-01T00:00:00.000Z", "deletedAt": None, "creatorId": 1,
             "currentVersion": {"label": rotulo, "current": True, "version": 1, "data": dados}}
            for u, rotulo, dados in linhas
        ]

    # -------------------------------------------------------------- transporte
    def responder(self, pedido: httpx.Request) -> httpx.Response:
        partes = urlsplit(str(pedido.url))
        caminho, consulta = partes.path, parse_qs(partes.query)
        self.chamadas.append((pedido.method, partes.path + (("?" + partes.query) if partes.query else "")))
        if self.status_forcado:
            return self._json({"message": "forçado pelo teste"}, self.status_forcado)
        if self.resposta_crua is not None:
            return httpx.Response(200, content=self.resposta_crua, headers={"content-type": "application/json"})
        if pedido.headers.get("authorization") != f"Bearer {self.token}":
            return self._json({"code": 401.2, "message": "Could not authenticate with the provided credentials."},
                              401)
        pre = f"/v1/projects/{self.projeto}"
        if pedido.method == "POST" and caminho == f"{pre}/forms":
            return self._publicar(pedido, consulta)
        if caminho.startswith(f"{pre}/datasets/") and caminho.endswith("/entities"):
            nome = caminho[len(f"{pre}/datasets/"):-len("/entities")]
            if nome not in self.entidades:
                return self._json({"code": 404.1, "message": "Could not find the resource."}, 404)
            return self._json(self.entidades[nome])
        if caminho.startswith(f"{pre}/forms/"):
            resto = caminho[len(f"{pre}/forms/"):]
            if resto in self.formularios:
                return self._json(self.formularios[resto])
            if ".svc/Submissions" in resto:
                return self._envios(resto.split(".svc/")[0], consulta)
            if "/submissions/" in resto:
                return self._anexo(resto)
        return self._json({"code": 404.1, "message": "Could not find the resource."}, 404)

    def _publicar(self, pedido: httpx.Request, consulta: dict) -> httpx.Response:
        if consulta.get("publish") != ["true"]:
            return self._json({"code": 400.2, "message": "publish=true é o que a ponte usa"}, 400)
        self.corpo_publicado = pedido.content
        self.cabecalhos_publicacao = {k.lower(): v for k, v in pedido.headers.items()}
        form_id = pedido.headers.get("x-xlsform-formid-fallback") or "formulario"
        registro = {"projectId": self.projeto, "xmlFormId": form_id, "name": "Coleta de campo (ODK)",
                    "version": "2026090701", "hash": "51a93eab3a1974dbffc4c7913fa5a16a", "state": "open",
                    "publishedAt": "2026-09-08T00:00:00.000Z", "createdAt": "2026-09-08T00:00:00.000Z"}
        self.formularios[form_id] = registro
        return self._json(registro)

    def _envios(self, form_id: str, consulta: dict) -> httpx.Response:
        if form_id not in self.formularios:
            return self._json({"code": 404.1, "message": "Could not find the resource."}, 404)
        top = int(consulta.get("$top", ["250"])[0])
        skip = int(consulta.get("$skip", ["0"])[0])
        pagina = self.envios[skip: skip + top]
        corpo = {"@odata.context": f"{URL_BASE}/v1/projects/{self.projeto}/forms/{form_id}.svc/$metadata#Submissions",
                 "value": pagina}
        if consulta.get("$count") == ["true"]:
            corpo["@odata.count"] = len(self.envios)
        return self._json(corpo)

    def _anexo(self, resto: str) -> httpx.Response:
        form_id, _, cauda = resto.partition("/submissions/")
        if form_id not in self.formularios:
            return self._json({"code": 404.1, "message": "Could not find the resource."}, 404)
        iid, _, cauda = cauda.partition("/attachments")
        from urllib.parse import unquote

        iid = unquote(iid)
        if cauda in ("", "/"):
            nomes = sorted(n for (i, n) in self.anexos if i == iid)
            return self._json([{"name": n, "exists": True} for n in nomes])
        bruto = self.anexos.get((iid, unquote(cauda.lstrip("/"))))
        if bruto is None:
            return self._json({"code": 404.1, "message": "Could not find the resource."}, 404)
        return httpx.Response(200, content=bruto, headers={"content-type": "image/png"})

    @staticmethod
    def _json(corpo, status: int = 200) -> httpx.Response:
        return httpx.Response(status, content=json.dumps(corpo).encode("utf-8"),
                              headers={"content-type": "application/json"})


def instalar(monkeypatch, duble: CentralDuble, *, host: str = HOST) -> None:
    """Troca só o DNS e o transporte; `validar_url` (SSRF) continua rodando de verdade."""
    from app.conexao import seguranca

    def _gai(nome, porta, *a, **kw):
        if nome == host:
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (IP_PUBLICO, porta))]
        return socket.getaddrinfo(nome, porta, *a, **kw)

    real = socket.getaddrinfo
    monkeypatch.setattr(socket, "getaddrinfo", lambda n, p, *a, **k: _gai(n, p, *a, **k) if n == host
                        else real(n, p, *a, **k))
    monkeypatch.setattr(seguranca, "cliente_pinado",
                        lambda validada, **kw: httpx.Client(transport=httpx.MockTransport(duble.responder),
                                                            follow_redirects=False))
