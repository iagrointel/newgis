"""Conserto do achado G5-1 do adversário (item L6-02-a-modelo-conexao-e-seguranca; ADR 0012, seção
"credencial nunca atravessa mudança de origem"): `app.conexao.seguranca.buscar_seguro` reenviava
`Authorization: Bearer <credencial decifrada>` em salto de redirecionamento para outra origem. Os dois
chamadores credenciados — `POST /api/conexoes/{id}/testar` (`app/conexao/rotas.py`) e o periódico
`conexoes.saude_verificar` (`app/conexao/tarefas.py`) — decifram a credencial do inquilino antes de chamar,
então um destino com redirecionamento aberto exfiltrava a credencial para um servidor de terceiro.

Regra conferida aqui, salto a salto: o cabeçalho de credencial só vale para a ORIGEM que o inquilino
cadastrou (esquema + host + porta, RFC 6454). Muda qualquer uma das três, a credencial sai. E a retirada é
DEFINITIVA: se a cadeia voltar à origem inicial, a credencial não volta junto — quem escolheu o desvio foi o
servidor de destino, não o inquilino (`requests` faz o mesmo: uma vez apagado o cabeçalho no
`rebuild_auth`, ele não é remontado nos saltos seguintes).

Tudo offline e determinístico: `socket.getaddrinfo` e `cliente_pinado` são substituídos por
`monkeypatch`; nenhum teste aqui abre socket, toca banco ou depende de rede.
"""

import socket

import httpx
import pytest

from app.conexao import seguranca as s

# hostnames de teste que resolvem para IPs PÚBLICOS distintos (todos passam na validação de SSRF, senão o
# teste provaria a recusa por IP interno, não a retirada da credencial)
_MAPA = {"host-a.teste": "8.8.8.8", "host-b.teste": "9.9.9.9", "host-c.teste": "1.1.1.1"}
CREDENCIAL = "Bearer CREDENCIAL-DA-CASA"


def _getaddrinfo_fixo(host, port, *a, **kw):
    ip = _MAPA.get(host, host)
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]


class _Resposta:
    def __init__(self, status: int, headers: httpx.Headers):
        self.status_code = status
        self.headers = headers

    def iter_bytes(self):
        return iter(())


class _Fluxo:
    """Contexto devolvido por `cliente.stream(...)`: registra (url, cabeçalhos) e responde conforme a rota."""

    def __init__(self, rotas, registro, url, headers):
        self._rotas, self._registro, self._url, self._headers = rotas, registro, url, headers

    def __enter__(self):
        self._registro.append((self._url, dict(self._headers)))
        destino = self._rotas.get(self._url)
        if destino is None:
            return _Resposta(200, httpx.Headers({}))
        return _Resposta(302, httpx.Headers({"location": destino}))

    def __exit__(self, *a):
        return False


class _Cliente:
    def __init__(self, rotas, registro):
        self._rotas, self._registro = rotas, registro

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, metodo, url, headers=None):
        return _Fluxo(self._rotas, self._registro, url, headers or {})


@pytest.fixture
def percorrer(monkeypatch):
    """Devolve `f(url_inicial, rotas, **kw) -> (resultado, registro)`, onde `rotas` é
    `{url: destino_do_302}` e `registro` é a lista de (url, cabeçalhos) realmente enviados, salto a salto."""

    def _f(url_inicial: str, rotas: dict[str, str], **kw):
        registro: list[tuple[str, dict[str, str]]] = []
        monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo_fixo)
        monkeypatch.setattr(s, "cliente_pinado", lambda validada, **_: _Cliente(rotas, registro))
        resultado = s.buscar_seguro(url_inicial, **kw)
        return resultado, registro

    return _f


def _autorizacoes(registro) -> list[str | None]:
    return [h.get("Authorization") for _, h in registro]


# ------------------------------------------------------------------ mudança de host
def test_muda_de_host_retira_a_credencial(percorrer):
    resultado, registro = percorrer(
        "http://host-a.teste/", {"http://host-a.teste/": "http://host-b.teste/"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert [u for u, _ in registro] == ["http://host-a.teste/", "http://host-b.teste/"]
    assert _autorizacoes(registro) == [CREDENCIAL, None]
    assert resultado.credencial_retirada is True


# ------------------------------------------------------------------ mudança de porta no MESMO host
def test_muda_de_porta_no_mesmo_host_retira_a_credencial(percorrer):
    _, registro = percorrer(
        "http://host-a.teste/", {"http://host-a.teste/": "http://host-a.teste:8443/x"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert [u for u, _ in registro] == ["http://host-a.teste/", "http://host-a.teste:8443/x"]
    assert _autorizacoes(registro) == [CREDENCIAL, None]


def test_porta_explicita_igual_a_padrao_e_a_mesma_origem(percorrer):
    """`https://h/` e `https://h:443/` são a MESMA origem — retirar aqui seria quebrar redirecionamento
    legítimo de serviço que normaliza a URL."""
    _, registro = percorrer(
        "https://host-a.teste/", {"https://host-a.teste/": "https://host-a.teste:443/capabilities"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert _autorizacoes(registro) == [CREDENCIAL, CREDENCIAL]


# ------------------------------------------------------------------ rebaixamento de esquema
def test_https_para_http_no_mesmo_host_retira_a_credencial(percorrer):
    """Mesmo host e mesma máquina, mas o segredo passaria a viajar em claro: sai."""
    resultado, registro = percorrer(
        "https://host-a.teste/", {"https://host-a.teste/": "http://host-a.teste/"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert _autorizacoes(registro) == [CREDENCIAL, None]
    assert resultado.credencial_retirada is True


# ------------------------------------------------------------------ cadeia de dois redirecionamentos
def test_cadeia_de_dois_saltos_nao_recupera_a_credencial(percorrer):
    resultado, registro = percorrer(
        "http://host-a.teste/",
        {"http://host-a.teste/": "http://host-b.teste/", "http://host-b.teste/": "http://host-c.teste/"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert [u for u, _ in registro] == [
        "http://host-a.teste/", "http://host-b.teste/", "http://host-c.teste/",
    ]
    assert _autorizacoes(registro) == [CREDENCIAL, None, None]
    assert resultado.saltos == 2


# ------------------------------------------------------------------ volta ao host original (decisão registrada)
def test_volta_a_origem_inicial_nao_devolve_a_credencial(percorrer):
    """DECISÃO (ADR 0012): a→b→a NÃO recupera a credencial. Ela poderia voltar sem vazamento direto, mas
    quem desenhou o desvio foi o servidor de destino; devolver o segredo depois de passar por terceiro dá a
    ele um caminho para pedir a repetição da requisição autenticada quando quiser. Mesma escolha de
    `requests` (`rebuild_auth` apaga o cabeçalho e não o remonta nos saltos seguintes)."""
    resultado, registro = percorrer(
        "http://host-a.teste/inicio",
        {"http://host-a.teste/inicio": "http://host-b.teste/", "http://host-b.teste/": "http://host-a.teste/fim"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert [u for u, _ in registro] == [
        "http://host-a.teste/inicio", "http://host-b.teste/", "http://host-a.teste/fim",
    ]
    assert _autorizacoes(registro) == [CREDENCIAL, None, None]
    assert resultado.credencial_retirada is True


def test_http_para_https_tambem_retira_a_credencial(percorrer):
    """DIVERGÊNCIA DELIBERADA de `requests` e `httpx`: as duas abrem exceção para o salto de subida
    `http://h/` → `https://h/` em porta padrão e MANTÊM a credencial (compatibilidade com versões antigas,
    comentada na fonte de `requests.Session.should_strip_auth`). Aqui não: mudou o esquema, a credencial sai.
    Custo conhecido e aceito: uma conexão cadastrada com `http://` num serviço que redireciona para `https://`
    passa a ser testada sem credencial e pode devolver 401 — o `credencial_retirada=True` no resultado diz por
    quê, e o conserto de operação é cadastrar a URL `https://`, que é a que nunca manda o segredo em claro."""
    resultado, registro = percorrer(
        "http://host-a.teste/", {"http://host-a.teste/": "https://host-a.teste/"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert _autorizacoes(registro) == [CREDENCIAL, None]
    assert resultado.credencial_retirada is True


# ------------------------------------------------------------------ mesma origem: a credencial SEGUE
def test_mesma_origem_mantem_a_credencial(percorrer):
    """Controle negativo: caminho diferente na MESMA origem (inclusive `Location` relativo, como fazem
    GetCapabilities e catálogo STAC) é redirecionamento legítimo e o teste de saúde precisa continuar
    autenticado — senão o conserto vira uma quebra de funcionalidade disfarçada."""
    resultado, registro = percorrer(
        "https://host-a.teste/wms", {"https://host-a.teste/wms": "/wms/1.3.0?request=GetCapabilities"},
        cabecalhos={"Authorization": CREDENCIAL},
    )
    assert [u for u, _ in registro] == [
        "https://host-a.teste/wms", "https://host-a.teste/wms/1.3.0?request=GetCapabilities",
    ]
    assert _autorizacoes(registro) == [CREDENCIAL, CREDENCIAL]
    assert resultado.credencial_retirada is False
    assert resultado.ok is True


# ------------------------------------------------------------------ os outros cabeçalhos de segredo
def test_cookie_proxy_authorization_e_cabecalho_secreto_declarado_saem_juntos(percorrer):
    _, registro = percorrer(
        "http://host-a.teste/", {"http://host-a.teste/": "http://host-b.teste/"},
        cabecalhos={
            "Authorization": CREDENCIAL,
            "Cookie": "sessao=abc",
            "Proxy-Authorization": "Basic xyz",
            "X-Api-Key": "CHAVE-DO-INQUILINO",
            "Accept": "application/json",
            "User-Agent": "plat/1.0",
        },
        cabecalhos_secretos=["X-Api-Key"],
    )
    _, primeiro = registro[0]
    _, segundo = registro[1]
    assert primeiro["X-Api-Key"] == "CHAVE-DO-INQUILINO"
    assert set(segundo) == {"Accept", "User-Agent"}, segundo
    assert "CREDENCIAL-DA-CASA" not in repr(segundo)


def test_nome_do_cabecalho_secreto_nao_diferencia_maiuscula(percorrer):
    """Nome de cabeçalho HTTP é insensível a caixa: `authorization` minúsculo tem de sair igual."""
    _, registro = percorrer(
        "http://host-a.teste/", {"http://host-a.teste/": "http://host-b.teste/"},
        cabecalhos={"authorization": CREDENCIAL, "x-api-key": "K"}, cabecalhos_secretos=["X-API-KEY"],
    )
    assert registro[1][1] == {}


# ------------------------------------------------------------------ sem credencial nenhuma
def test_sem_credencial_a_marca_fica_falsa(percorrer):
    """Conexão pública (sem credencial cadastrada) que redireciona para outro host não tem nada a retirar —
    a marca não pode ficar ligada à toa, senão o chamador lê "credencial retirada" onde nunca houve uma."""
    resultado, registro = percorrer(
        "http://host-a.teste/", {"http://host-a.teste/": "http://host-b.teste/"},
        cabecalhos={"Accept": "application/json"},
    )
    assert registro[1][1] == {"Accept": "application/json"}
    assert resultado.credencial_retirada is False


def test_dicionario_do_chamador_nao_e_alterado(percorrer):
    """A rota reusa o dicionário depois da chamada (log, novo teste): `buscar_seguro` copia, nunca mexe."""
    cabecalhos = {"Authorization": CREDENCIAL}
    percorrer("http://host-a.teste/", {"http://host-a.teste/": "http://host-b.teste/"}, cabecalhos=cabecalhos)
    assert cabecalhos == {"Authorization": CREDENCIAL}
