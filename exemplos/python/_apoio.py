# Apoio dos exemplos em Python: leitura das variáveis de ambiente e uma chamada HTTP sem dependência.
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ.get("PLAT_URL", "http://127.0.0.1:8153").rstrip("/")
CHAVE = os.environ.get("PLAT_CHAVE", "")


def chamar(caminho, metodo="GET", corpo=None, chave=None, tempo=30):
    """Devolve (status, cabecalhos, objeto). Não levanta em 4xx/5xx: o erro faz parte da resposta."""
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(URL + caminho, data=dados, method=metodo)
    pedido.add_header("Accept", "application/json")
    if dados is not None:
        pedido.add_header("Content-Type", "application/json")
    valor = CHAVE if chave is None else chave
    if valor:
        pedido.add_header("Authorization", "Bearer " + valor)
    try:
        with urllib.request.urlopen(pedido, timeout=tempo) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        texto = e.read()
        try:
            return e.code, dict(e.headers), json.loads(texto or b"null")
        except json.JSONDecodeError:
            return e.code, dict(e.headers), {"corpo_nao_json": texto.decode("utf-8", "replace")[:200]}


def exigir(condicao, mensagem):
    if not condicao:
        print("FALHOU: " + mensagem, file=sys.stderr)
        raise SystemExit(1)


def exigir_chave():
    exigir(CHAVE.startswith("plat_"), "defina PLAT_CHAVE com uma chave de API do plat (plat_...)")
