"""Os dois CHAMADORES credenciados do item L6-02-a-modelo-conexao-e-seguranca, no nível deles.

O bloqueio registrado no item dizia duas coisas: (a) `buscar_seguro` reenviava a credencial em
redirecionamento para outra origem — provado e consertado em `tests/unit/test_conexao_credencial_redirect.py`
e em `tests/adversario/test_g5_adversario.py`; (b) `testar`/`saude` "vazam o Bearer da casa" — que é a mesma
falha vista de onde a credencial nasce. O laudo do conserto (handoff T3, seção 7) admitia a lacuna: "a prova é
no nível de `buscar_seguro`; não montei o cenário fim a fim". Este arquivo fecha o lado do JOB
(`conexoes.saude_verificar`, `app/conexao/tarefas.py`), que decifra a credencial do inquilino e a entrega a
`buscar_seguro`; o lado da ROTA (`POST /api/conexoes/{id}/testar`) está em
`tests/api/test_conexoes_credencial_saltos.py`.

Tudo offline e determinístico: `socket.getaddrinfo` e `cliente_pinado` trocados por `monkeypatch`, contexto de
job de mentira, nenhum socket e nenhum banco.

As guardas de regressão do fim do arquivo são `xfail(strict=True)` DE PROPÓSITO: elas afirmam o comportamento
VULNERÁVEL. Enquanto o conserto estiver de pé elas falham (xfail = esperado); se alguém desfizer o conserto
elas passam (XPASS) e a suíte fica vermelha.
"""

import contextlib
import socket

import httpx
import pytest

from app.conexao import credencial as credencial_mod
from app.conexao import seguranca as s
from app.conexao import tarefas
from app.settings import settings

_MAPA = {"host-a.teste": "8.8.8.8", "host-b.teste": "9.9.9.9"}
SEGREDO = "segredo-de-teste-nao-e-real-XYZ789"


def _gai(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (_MAPA.get(host, host), port))]


class _Resposta:
    def __init__(self, status, headers):
        self.status_code, self.headers = status, headers

    def iter_bytes(self):
        return iter(())


class _Fluxo:
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


class _Cursor:
    """Cursor de mentira: devolve as candidatas na primeira consulta e engole o registro de saúde."""

    def __init__(self, candidatas, sql_vistos):
        self._candidatas, self._sql = candidatas, sql_vistos
        self._ultimo = None

    def execute(self, sql, params=None):
        self._sql.append((sql, params))
        self._ultimo = sql

    def fetchall(self):
        return self._candidatas if "candidatas" in (self._ultimo or "") else []

    def fetchone(self):
        return None


class _Ctx:
    def __init__(self, candidatas):
        self.candidatas, self.sql, self.progresso_visto = candidatas, [], []

    @contextlib.contextmanager
    def db(self):
        yield _Cursor(self.candidatas, self.sql)

    def verificar(self):
        return None

    def progresso(self, pct, msg=""):
        self.progresso_visto.append((pct, msg))


@pytest.fixture
def rodar_saude(monkeypatch):
    """`f(url, rotas) -> (retorno, registro)` — roda o job de saúde com UMA conexão credenciada."""

    def _f(url: str, rotas: dict[str, str]):
        registro: list[tuple[str, dict[str, str]]] = []
        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        monkeypatch.setattr(s, "cliente_pinado", lambda validada, **_: _Cliente(rotas, registro))
        cifrada = credencial_mod.cifrar(SEGREDO, settings.PLAT_SECRET)
        ctx = _Ctx([{"id": "00000000-0000-0000-0000-000000000001", "url": url, "credencial_cifrada": cifrada}])
        retorno = tarefas.conexoes_saude_verificar(ctx, limite=10)
        return retorno, registro, ctx

    return _f


def _autorizacoes(registro):
    return [h.get("Authorization") for _, h in registro]


# --------------------------------------------------------- o job: mesma origem mantém, outra origem retira
def test_job_saude_manda_a_credencial_para_a_origem_cadastrada(rodar_saude):
    _, registro, _ = rodar_saude("http://host-a.teste/capabilities", {})
    assert [u for u, _ in registro] == ["http://host-a.teste/capabilities"]
    assert _autorizacoes(registro) == [f"Bearer {SEGREDO}"]


def test_job_saude_nao_leva_a_credencial_para_host_de_redirecionamento(rodar_saude):
    retorno, registro, _ = rodar_saude(
        "http://host-a.teste/capabilities", {"http://host-a.teste/capabilities": "http://host-b.teste/coleta"},
    )
    assert [u for u, _ in registro] == ["http://host-a.teste/capabilities", "http://host-b.teste/coleta"]
    enviados_ao_b = registro[1][1]
    assert "Authorization" not in enviados_ao_b
    # varredura por TEXTO, não inspeção visual: o segredo não aparece em nenhum cabeçalho mandado ao host B
    assert SEGREDO not in repr(enviados_ao_b)
    assert retorno == {"candidatas": 1, "ok": 1, "erro": 0}


def test_job_saude_nao_escreve_a_credencial_em_nenhum_sql_nem_no_retorno(rodar_saude):
    retorno, registro, ctx = rodar_saude(
        "http://host-a.teste/x", {"http://host-a.teste/x": "http://host-b.teste/y"},
    )
    assert SEGREDO not in repr(retorno)
    assert SEGREDO not in repr(ctx.sql)          # nada de credencial em consulta (o log de consulta lenta a veria)
    assert SEGREDO not in repr(ctx.progresso_visto)
    assert SEGREDO not in repr(registro[1][1])


def test_job_saude_mantem_a_credencial_em_redirecionamento_da_mesma_origem(rodar_saude):
    """`Location` relativo dentro da mesma origem é o caso comum de GetCapabilities: a credencial fica."""
    _, registro, _ = rodar_saude(
        "http://host-a.teste/a", {"http://host-a.teste/a": "/b"},
    )
    assert [u for u, _ in registro] == ["http://host-a.teste/a", "http://host-a.teste/b"]
    assert _autorizacoes(registro) == [f"Bearer {SEGREDO}"] * 2


# ------------------------------------------------------------------------ guardas de regressão (ver docstring)
@pytest.mark.xfail(strict=True, reason="furo G5-1 fechado: mudar de host tem de retirar a credencial")
def test_regressao_credencial_atravessa_mudanca_de_host(monkeypatch):
    registro: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    monkeypatch.setattr(
        s, "cliente_pinado",
        lambda v, **_: _Cliente({"http://host-a.teste/": "http://host-b.teste/"}, registro),
    )
    s.buscar_seguro("http://host-a.teste/", cabecalhos={"Authorization": f"Bearer {SEGREDO}"})
    assert registro[1][1].get("Authorization") == f"Bearer {SEGREDO}"


@pytest.mark.xfail(strict=True, reason="furo fechado: mudar de porta na mesma máquina tambem retira")
def test_regressao_credencial_atravessa_mudanca_de_porta(monkeypatch):
    registro: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    monkeypatch.setattr(
        s, "cliente_pinado",
        lambda v, **_: _Cliente({"http://host-a.teste/": "http://host-a.teste:8443/x"}, registro),
    )
    s.buscar_seguro("http://host-a.teste/", cabecalhos={"Authorization": f"Bearer {SEGREDO}"})
    assert registro[1][1].get("Authorization") == f"Bearer {SEGREDO}"


@pytest.mark.xfail(strict=True, reason="furo fechado: a retirada e definitiva, voltar a origem nao devolve")
def test_regressao_credencial_volta_ao_retornar_a_origem_inicial(monkeypatch):
    registro: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    monkeypatch.setattr(
        s, "cliente_pinado",
        lambda v, **_: _Cliente(
            {"http://host-a.teste/1": "http://host-b.teste/2", "http://host-b.teste/2": "http://host-a.teste/3"},
            registro,
        ),
    )
    s.buscar_seguro("http://host-a.teste/1", cabecalhos={"Authorization": f"Bearer {SEGREDO}"})
    assert registro[2][1].get("Authorization") == f"Bearer {SEGREDO}"


@pytest.mark.xfail(strict=True, reason="furo fechado: o job de saude nao leva o Bearer da casa para fora")
def test_regressao_job_saude_leva_a_credencial_para_outro_host(rodar_saude):
    _, registro, _ = rodar_saude(
        "http://host-a.teste/x", {"http://host-a.teste/x": "http://host-b.teste/y"},
    )
    assert registro[1][1].get("Authorization") == f"Bearer {SEGREDO}"


@pytest.mark.xfail(strict=True, reason="furo fechado: app/garage.py nao segue Location com Authorization")
def test_regressao_garage_segue_redirecionamento_com_authorization():
    """O outro caminho da casa que monta `Authorization` e usava `requests` com redirecionamento automático."""
    import inspect

    from app import garage

    fonte = inspect.getsource(garage)
    assert "allow_redirects=False" not in fonte
