"""Servidor de mentira que responde como um Portal for ArcGIS / ArcGIS Online
(apoio do item L2-08-a-leitor-portal-inventario).

Por que existe: o portão do item pede a prova contra um Portal de teste, e a credencial do portal do parceiro
é decisão do dono (D20), ainda em aberto — ver `tests/migracao/PORTAL_DE_TESTE.md`. Em vez de apontar a
suíte para uma organização pública de terceiro sem autorização, este servidor devolve as respostas gravadas
de `respostas/portal.json`, no formato documentado publicamente pela Esri (a procedência de cada campo está
no cabeçalho de `respostas/gerar.py`).

Ele escuta no IP PÚBLICO desta máquina, nunca em 127.0.0.1 — o leitor passa por `app.conexao.seguranca`, que
recusa loopback, e um servidor de teste em loopback provaria só que a defesa de SSRF funciona. É o mesmo
recurso que `tests/unit/test_conexao_seguranca.py` já usa.

Modos que o teste liga (todos desligados por padrão):
  `falhar_apos=N`      corta a conexão sem resposta a partir do N-ésimo pedido (falha de rede no meio)
  `limite_ate=N`       responde 429 com Retry-After nos N primeiros pedidos (limite de uso do portal)
  `nao_e_portal=True`  responde HTML em tudo (URL que não é Portal)
  `itens_sinteticos=N` ignora o acervo gravado e gera N itens simples (teste de paginação em massa)
  `token_exigido=tok`  recusa (erro 499 no corpo, como o portal faz) todo pedido sem o cabeçalho certo
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

RESPOSTAS = Path(__file__).resolve().parent / "respostas" / "portal.json"
BASE_SERVICO_GRAVADA = "https://sig-de-teste-interno.invalido/server/rest/services"


def acervo() -> dict:
    return json.loads(RESPOSTAS.read_text(encoding="utf-8"))


def ip_publico() -> str | None:
    """IP global IPv4 desta máquina (o mesmo truque de tests/unit/test_conexao_seguranca.py)."""
    import ipaddress

    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_global:
            return str(ip)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("198.51.100.1", 53))
        ip = ipaddress.ip_address(s.getsockname()[0])
        return str(ip) if ip.is_global else None
    except OSError:
        return None
    finally:
        s.close()


class _Manipulador(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------ utilidades
    def log_message(self, *a):  # silêncio: a suíte já tem saída demais
        pass

    def _responder(self, dado, status: int = 200, tipo: str = "application/json", cabecalhos=None):
        corpo = dado if isinstance(dado, bytes) else json.dumps(dado, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for chave, valor in (cabecalhos or {}).items():
            self.send_header(chave, valor)
        self.end_headers()
        self.wfile.write(corpo)

    def _erro_portal(self, codigo: int, mensagem: str):
        """O Portal responde HTTP 200 com o erro no corpo — este servidor faz igual, de propósito."""
        self._responder({"error": {"code": codigo, "message": mensagem, "details": []}})

    @property
    def cfg(self) -> dict:
        return self.server.cfg

    def _base(self) -> str:
        return f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"

    def _reescrever(self, obj):
        """Troca a URL gravada do serviço pela URL deste servidor, para que a contagem de feições seja lida
        de verdade e não caia em host inexistente."""
        if isinstance(obj, str):
            return obj.replace(BASE_SERVICO_GRAVADA, f"{self._base()}/server/rest/services")
        if isinstance(obj, list):
            return [self._reescrever(o) for o in obj]
        if isinstance(obj, dict):
            return {k: self._reescrever(v) for k, v in obj.items()}
        return obj

    # ------------------------------------------------------------------ ciclo
    def do_POST(self):
        self.do_GET(corpo_lido=True)

    def do_GET(self, corpo_lido: bool = False):
        if corpo_lido:
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho:
                self.rfile.read(tamanho)

        self.server.pedidos += 1
        n = self.server.pedidos

        falhar = self.cfg.get("falhar_apos")
        if falhar and n >= falhar:
            # corte de rede: fecha o socket sem resposta nenhuma
            self.close_connection = True
            try:
                self.connection.close()
            except OSError:
                pass
            return

        limite = self.cfg.get("limite_ate") or 0
        if n <= limite:
            self.server.recusas_429 += 1
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        partes = urlsplit(self.path)
        caminho = partes.path.rstrip("/") or "/"
        consulta = {k: v[0] for k, v in parse_qs(partes.query).items()}

        if self.cfg.get("nao_e_portal"):
            self._responder(b"<html><body>isto aqui nao e um Portal</body></html>", tipo="text/html")
            return

        token = None
        autorizacao = self.headers.get("X-Esri-Authorization") or ""
        if autorizacao.lower().startswith("bearer "):
            token = autorizacao[7:]
        self.server.tokens_na_query.extend(
            v for k, v in consulta.items() if k == "token"
        )  # se algum dia o leitor puser token na query, o teste vê

        exigido = self.cfg.get("token_exigido")
        if exigido and caminho != "/sharing/rest/generateToken" and token != exigido:
            self._erro_portal(499, "Token Required")
            return

        try:
            self._rotear(caminho, consulta)
        except BrokenPipeError:
            pass

    # ------------------------------------------------------------------ rotas
    def _rotear(self, caminho: str, consulta: dict):
        a = self.server.acervo
        org = a["org_id"]

        if caminho == "/sharing/rest":
            return self._responder(a["raiz"])
        if caminho == "/sharing/rest/generateToken":
            return self._responder(
                {"token": self.cfg.get("token_emitido", "tok-de-mentira"), "expires": 9_999_999_999_000, "ssl": True}
            )
        if caminho == "/sharing/rest/portals/self":
            return self._responder(a["self"])
        if caminho == "/sharing/rest/search":
            return self._responder(self._buscar(consulta))
        if caminho == f"/sharing/rest/portals/{org}/groups":
            return self._responder(
                {"total": len(a["grupos"]), "start": 1, "num": len(a["grupos"]), "nextStart": -1, "groups": a["grupos"]}
            )
        if caminho == f"/sharing/rest/portals/{org}/users":
            return self._responder(
                {
                    "total": len(a["usuarios"]),
                    "start": 1,
                    "num": len(a["usuarios"]),
                    "nextStart": -1,
                    "users": a["usuarios"],
                }
            )
        if caminho.startswith("/sharing/rest/community/groups/") and caminho.endswith("/users"):
            grupo_id = caminho.split("/")[-2]
            return self._responder(a["membros"].get(grupo_id, {"owner": None, "admins": [], "users": []}))
        if caminho.startswith("/sharing/rest/content/items/"):
            return self._item(caminho, consulta)
        if "/server/rest/services/" in caminho:
            return self._servico(caminho, consulta)
        return self._erro_portal(400, f"caminho desconhecido: {caminho}")

    def _indice_de_itens(self) -> list[dict]:
        sinteticos = self.cfg.get("itens_sinteticos") or 0
        if sinteticos:
            if not self.server.sinteticos:
                self.server.sinteticos = [
                    {
                        "id": f"{i:032x}",
                        "owner": "ana.tec",
                        "title": f"Item sintético {i}",
                        "type": "CSV",
                        "typeKeywords": ["CSV"],
                        "created": 1_700_000_000_000,
                        "modified": 1_700_000_000_000,
                        "lastViewed": 1_700_000_000_000,
                        "url": None,
                        "size": 100 + i,
                        "numViews": i,
                    }
                    for i in range(1, sinteticos + 1)
                ]
            return self.server.sinteticos
        return self.server.acervo["itens"]

    def _buscar(self, consulta: dict) -> dict:
        itens = self._indice_de_itens()
        inicio = max(1, int(consulta.get("start") or 1))
        num = min(100, max(1, int(consulta.get("num") or 10)))
        fatia = itens[inicio - 1 : inicio - 1 + num]
        proxima = inicio + num
        return {
            "query": consulta.get("q", ""),
            "total": len(itens),
            "start": inicio,
            "num": len(fatia),
            "nextStart": proxima if proxima <= len(itens) else -1,
            "results": self._reescrever(fatia),
        }

    def _item(self, caminho: str, consulta: dict):
        resto = caminho[len("/sharing/rest/content/items/") :]
        partes = resto.split("/")
        item_id = partes[0]
        a = self.server.acervo
        item = next((i for i in self._indice_de_itens() if i["id"] == item_id), None)
        if item is None:
            return self._erro_portal(400, "Item does not exist or is inaccessible.")
        if len(partes) == 1:
            return self._responder(self._reescrever(item))
        if partes[1] == "data":
            dado = a["dados"].get(item_id)
            if dado is None:
                return self._responder(b"", tipo="application/octet-stream")
            return self._responder(self._reescrever(dado))
        if partes[1] == "resources":
            recursos = (
                [{"resource": "info.json", "created": 1_700_000_000_000, "size": 12}]
                if item["type"] in ("Web Map", "Form")
                else []
            )
            return self._responder(
                {"total": len(recursos), "start": 1, "num": len(recursos), "nextStart": -1, "resources": recursos}
            )
        if partes[1] == "relatedItems":
            relacao = consulta.get("relationshipType", "")
            ligados = []
            if relacao == "Map2Service" and item["type"] == "Web Map":
                dado = a["dados"].get(item_id) or {}
                ligados = [{"id": c["itemId"]} for c in dado.get("operationalLayers", []) if c.get("itemId")]
            return self._responder({"total": len(ligados), "relatedItems": ligados})
        return self._erro_portal(400, f"subcaminho desconhecido: {partes[1:]}")

    def _servico(self, caminho: str, consulta: dict):
        a = self.server.acervo
        if caminho.startswith("/server/rest/services/publico/"):
            return self._servico_publico(caminho[len("/server/rest/services/publico") :], consulta)
        chave = BASE_SERVICO_GRAVADA + caminho.split("/server/rest/services", 1)[1]
        if chave in a["servicos"]:
            descricao = dict(a["servicos"][chave])
            descricao.pop("contagens", None)
            return self._responder(descricao)
        if caminho.endswith("/query"):
            sem_query = caminho[: -len("/query")]
            camada = sem_query.rsplit("/", 1)[-1]
            servico = BASE_SERVICO_GRAVADA + sem_query.rsplit("/", 1)[0].split("/server/rest/services", 1)[1]
            contagens = (a["servicos"].get(servico) or {}).get("contagens") or {}
            if camada not in contagens:
                return self._erro_portal(400, "Invalid or missing input parameters.")
            if consulta.get("returnCountOnly") != "true":
                return self._erro_portal(400, "este servidor de teste só responde returnCountOnly=true")
            return self._responder({"count": contagens[camada]})
        return self._erro_portal(400, f"serviço desconhecido: {caminho}")

    # ------------------------------------------------------------------ serviço público gravado (item L2-08-b):
    # /server/rest/services/publico/FeatureServer[/{id}[/query | /{oid}/attachments[/{aid}]]] a partir de
    # tests/migracao/respostas/publicas/servico_publico.json (URL e data no próprio arquivo)
    def _servico_publico(self, resto: str, consulta: dict):
        import base64

        g = self.server.publico
        partes = [p for p in resto.split("/") if p]
        if not partes or partes[0] != "FeatureServer":
            return self._erro_portal(400, f"serviço desconhecido: {resto}")
        if len(partes) == 1:
            return self._responder(g["raiz"])
        camada = partes[1]
        if camada not in g["camadas"]:
            return self._erro_portal(400, "Invalid or missing input parameters.")
        if len(partes) == 2:
            return self._responder(g["camadas"][camada])
        if partes[2] == "query":
            paginas = g["paginas"][camada]
            feicoes = [f for p in paginas for f in p["features"]]
            if consulta.get("returnCountOnly") == "true":
                return self._responder({"count": len(feicoes)})  # a gravação é uma amostra: a contagem é dela
            oid = g["camadas"][camada]["objectIdField"]
            if consulta.get("returnIdsOnly") == "true":
                return self._responder({"objectIdFieldName": oid, "objectIds": [f["attributes"][oid] for f in feicoes]})
            if consulta.get("objectIds"):
                pedidos = {int(x) for x in consulta["objectIds"].split(",") if x.strip()}
                fatia = [f for f in feicoes if int(f["attributes"][oid]) in pedidos]
                return self._responder(
                    {
                        **{k: v for k, v in paginas[0].items() if k != "features"},
                        "features": fatia,
                        "exceededTransferLimit": False,
                    }
                )
            deslocamento = int(consulta.get("resultOffset") or 0)
            tamanho = int(consulta.get("resultRecordCount") or 10)
            fatia = feicoes[deslocamento : deslocamento + tamanho]
            return self._responder(
                {
                    **{k: v for k, v in paginas[0].items() if k != "features"},
                    "features": fatia,
                    "exceededTransferLimit": deslocamento + tamanho < len(feicoes),
                }
            )
        if len(partes) >= 4 and partes[3] == "attachments":
            anexos = (g["anexos"].get(camada) or {}).get(partes[2]) or {"attachmentInfos": [], "bytes": {}}
            if len(partes) == 4:
                return self._responder({"attachmentInfos": anexos["attachmentInfos"]})
            b64 = anexos["bytes"].get(partes[4])
            if b64 is None:
                return self._erro_portal(400, "anexo inexistente")
            tipo = next(
                (a["contentType"] for a in anexos["attachmentInfos"] if str(a["id"]) == partes[4]),
                "application/octet-stream",
            )
            return self._responder(base64.b64decode(b64), tipo=tipo)
        return self._erro_portal(400, f"serviço desconhecido: {resto}")


class PortalFalso:
    """Contexto: `with PortalFalso(itens_sinteticos=...) as portal: portal.base`."""

    def __init__(self, **cfg):
        self.cfg = cfg
        self.servidor = None
        self.thread = None

    def __enter__(self) -> PortalFalso:
        ip = ip_publico()
        if ip is None:
            raise RuntimeError(
                "máquina sem IP público: o servidor de mentira não pode escutar em loopback "
                "(a defesa de SSRF do L6-02-a recusaria antes de qualquer leitura)"
            )
        self.servidor = http.server.ThreadingHTTPServer((ip, 0), _Manipulador)
        self.servidor.cfg = self.cfg
        self.servidor.acervo = acervo()
        self.servidor.publico = json.loads(
            (RESPOSTAS.parent / "publicas" / "servico_publico.json").read_text(encoding="utf-8")
        )
        self.servidor.pedidos = 0
        self.servidor.recusas_429 = 0
        self.servidor.tokens_na_query = []
        self.servidor.sinteticos = []
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.servidor.shutdown()
        self.thread.join(timeout=5)
        self.servidor.server_close()
        return False

    @property
    def base(self) -> str:
        return f"http://{self.servidor.server_address[0]}:{self.servidor.server_address[1]}"

    @property
    def pedidos(self) -> int:
        return self.servidor.pedidos

    @property
    def tokens_na_query(self) -> list:
        return self.servidor.tokens_na_query

    def configurar(self, **cfg) -> None:
        """Muda o modo com o servidor no ar (ex.: tirar a falha de rede antes da segunda tentativa)."""
        self.servidor.cfg.update(cfg)
