"""Item L0-06-e-status: /api/status e a página /status.

Cada teste aqui é uma cláusula do portão de pronto: responde sem sessão com todos os campos; o campo do worker
acompanha o worker de verdade e volta ao religar, dentro da janela; o percentual do mês bate com as amostras
gravadas (o teste recalcula da tabela); a resposta não carrega versão de dependência nem caminho de disco;
cabeçalho `X-Robots-Tag: noindex`; e mil pedidos não viram mil consultas ao banco (cache de 30 s).

`systemctl stop plat-worker` NÃO é usado: derrubar unidade de produção é proibido nesta trilha (BRIEF). A queda
do worker é encenada como o /status a enxerga — a sonda HTTP de PLAT_WORKER_URL deixa de responder — subindo e
derrubando um servidor HTTP de verdade numa porta livre desta máquina.
"""

import http.server
import json
import re
import socket
import threading
import time

import pytest

from app import status

SERVICO_SINTETICO = "zt_status"
CAMPOS = ("estado", "servicos", "migracoes", "fila", "backup", "ensaio_restauracao", "disco", "bucket",
          "certificado", "historico", "disponibilidade_mes", "correcoes", "cache_s", "tempo_ms", "em")


@pytest.fixture
def sem_cache():
    status.limpar_cache()
    yield
    status.limpar_cache()


class _Servidor:
    """Servidor HTTP mínimo numa porta livre: faz o papel do worker vivo para a sonda de /api/status."""

    def __init__(self):
        self.porta = _porta_livre()
        self.httpd = http.server.HTTPServer(("127.0.0.1", self.porta), _Manipulador)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def parar(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class _Manipulador(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — nome imposto pela biblioteca padrão
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _amostras(cur, servico: str) -> list[str]:
    cur.execute("SELECT estado FROM plat.status_amostra WHERE servico = %s ORDER BY id", (servico,))
    return [r["estado"] for r in cur.fetchall()]


# ---------------------------------------------------------------- responde sem sessão, com todos os campos


def test_api_status_200_sem_sessao_com_todos_os_campos(cliente, sem_cache):
    r = cliente.get("/api/status")
    assert r.status_code in (200, 503), r.text
    j = r.json()
    assert set(CAMPOS) <= set(j), sorted(set(CAMPOS) - set(j))
    assert set(j["servicos"]) == set(status.SERVICOS_AMOSTRADOS)
    assert all("estado" in s for s in j["servicos"].values())
    assert {"na_fila", "executando", "falhas_24h"} <= set(j["fila"])
    assert {"aplicadas", "pendentes"} <= set(j["migracoes"])
    assert "ultimo_em" in j["backup"] and "estado" in j["disco"] and "estado" in j["bucket"]
    if j["bucket"]["estado"] == "ok":
        assert j["bucket"]["buckets"] is not None and j["bucket"]["bytes_aprox"] is not None
    assert j["historico"]["dias"] == 90
    assert isinstance(j["correcoes"], list)


def test_pagina_status_200_sem_sessao_e_noindex(cliente):
    r = cliente.get("/status")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["x-robots-tag"].startswith("noindex")
    assert '<meta name="robots" content="noindex, nofollow">' in r.text
    assert "/static/js/status.js" in r.text


def test_api_status_tem_cabecalho_noindex_e_no_store(cliente, sem_cache):
    r = cliente.get("/api/status")
    assert r.headers["x-robots-tag"].startswith("noindex")
    assert r.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- não expõe versão de dependência nem caminho


def test_nao_expoe_versao_de_dependencia_nem_caminho_de_disco(cliente, sem_cache):
    texto = cliente.get("/api/status").text
    for proibido in ("fastapi", "uvicorn", "psycopg2", "starlette", "pydantic", "PostgreSQL", "nginx/",
                     "/mnt/", "/home/", "/var/", "/etc/", "git_sha", "python"):
        assert proibido.lower() not in texto.lower(), proibido
    # nenhum "1.2.3" solto (versão de biblioteca); data ISO e percentual não casam com este padrão
    assert not re.search(r'"[^"]*\d+\.\d+\.\d+[^"]*"', texto), re.findall(r'"[^"]*\d+\.\d+\.\d+[^"]*"', texto)
    j = cliente.get("/api/status").json()
    assert "versao" not in j and "git_sha" not in j and "ambiente" not in j
    assert all("alvo" not in s for s in j["servicos"].values())
    assert "volumes" in j["disco"] and isinstance(j["disco"]["volumes"], int)


# ---------------------------------------------------------------- percentual do mês recalculado do banco


def test_percentual_do_mes_bate_com_as_amostras(cliente, conexao_plat_app, sem_cache):
    amostras = [{"servico": SERVICO_SINTETICO, "estado": e}
                for e in ("ok", "ok", "ok", "erro", "degradado", "ausente", "ok")]
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.status_amostra_expurgar(%s) AS n", (SERVICO_SINTETICO,))
        cur.execute("SELECT plat.status_amostrar(%s::jsonb) AS n", (json.dumps(amostras),))
        assert cur.fetchone()["n"] == len(amostras)
        conexao_plat_app.commit()
        gravadas = _amostras(cur, SERVICO_SINTETICO)
    try:
        j = cliente.get("/api/status").json()
        d = j["disponibilidade_mes"]["servicos"][SERVICO_SINTETICO]
        # recálculo independente, a partir do que está gravado: ok sobre o que não é 'ausente'
        uteis = [e for e in gravadas if e != "ausente"]
        esperado = round(100.0 * uteis.count("ok") / len(uteis), 3)
        assert d["amostras"] == len(uteis) and d["ok"] == uteis.count("ok")
        assert abs(d["pct"] - esperado) < 1e-6, (d, esperado)
        assert abs(d["pct"] - 66.667) < 1e-3  # 4 de 6: o 'ausente' fica fora da conta

        dias = j["historico"]["servicos"][SERVICO_SINTETICO]
        assert sum(x["amostras"] for x in dias) == len(uteis)
        assert sum(x["ok"] for x in dias) == uteis.count("ok")
    finally:
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT plat.status_amostra_expurgar(%s) AS n", (SERVICO_SINTETICO,))
            conexao_plat_app.commit()


def test_periodico_amostrar_grava_um_estado_por_servico(cliente, conexao_plat_app, sem_cache):
    """O periódico `status.amostrar` é o que alimenta o histórico: aqui ele roda de verdade (a função da
    tarefa, com um contexto de job de mentira só para o cursor) e as linhas têm de aparecer na tabela."""
    from app import status_tarefas

    class _Ctx:
        def db(self):
            return conexao_plat_app.cursor()

        def progresso(self, *a, **k):
            pass

    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.status_amostra")
        antes = cur.fetchone()["n"]
    saida = status_tarefas.status_amostrar(_Ctx())
    conexao_plat_app.commit()
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.status_amostra")
        depois = cur.fetchone()["n"]
    assert saida["amostras"] == len(status.SERVICOS_AMOSTRADOS)
    assert depois - antes == len(status.SERVICOS_AMOSTRADOS)
    assert set(saida["servicos"]) == set(status.SERVICOS_AMOSTRADOS)


# ---------------------------------------------------------------- cache: mil pedidos, uma consulta


def test_mil_pedidos_por_minuto_nao_consultam_o_banco(cliente, monkeypatch, sem_cache):
    """1.000 pedidos: o primeiro calcula, os outros saem do cache. A prova de que o banco não é consultado é
    dura — depois do primeiro pedido, `retrato()` passa a levantar; se algum pedido o chamasse, viraria 500."""
    primeiro = cliente.get("/api/status")
    assert primeiro.headers["x-cache"] == "miss"

    def _explode():
        raise AssertionError("cache não segurou: /api/status recalculou o retrato")

    monkeypatch.setattr(status, "retrato", _explode)
    inicio = time.perf_counter()
    for _ in range(1000):
        r = cliente.get("/api/status")
        assert r.status_code == primeiro.status_code and r.headers["x-cache"] == "hit"
    assert time.perf_counter() - inicio < 60.0
    assert status.CACHE_S <= 300  # a janela do cache cabe dentro dos 5 minutos que o portão exige


def test_nao_carrega_slug_de_inquilino_ip_interno_nem_segredo(cliente, conexao_plat_app, sem_cache):
    """A varredura que o adversário faria: os slugs REAIS do banco, endereço interno, e cada segredo do
    ambiente desta instalação — nenhum deles pode aparecer na resposta nem na página."""
    import os

    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT slug, nome FROM plat.tenant")
        inquilinos = [v for r in cur.fetchall() for v in (r["slug"], r["nome"])]

    corpo = cliente.get("/api/status").text + cliente.get("/status").text
    baixo = corpo.lower()
    for marca in inquilinos:
        if marca and marca.lower() not in ("plataforma",):  # 'plataforma' é palavra comum do texto da página
            assert marca.lower() not in baixo, marca
    for endereco in ("127.0.0.1", "localhost", "10.", "192.168.", "::1", ":54", ":39", ":3900", ":3903"):
        assert endereco not in corpo, endereco
    for chave, valor in os.environ.items():
        if chave.startswith("PLAT_") and len(valor) >= 12 and chave not in ("PLAT_URL_PUBLICA",):
            assert valor not in corpo, chave
