"""Rota GET /metrics (item L7-06-a-metricas-exporters): as famílias do portão, cardinalidade com 50
inquilinos sintéticos e a refutação do adversário — 500 tokens não podem aumentar a cardinalidade além do
número de INQUILINOS de verdade, e nenhum token pode aparecer no corpo exposto."""

import re
import secrets

import pytest

from tests.api.conftest import InquilinoTemporario, com_token

FAMILIAS = (
    "plat_http_requests_total",
    "plat_http_request_duracao_segundos",
    "plat_tiles_requisicoes_total",
    "plat_jobs_processados_total",
    "plat_jobs_fila",
    "plat_jobs_workers_vivos",
)


def _series(texto: str, nome_metrica: str) -> list[str]:
    prefixo = f"{nome_metrica}{{"
    return [linha[len(prefixo) - 1 :].split("}", 1)[0] for linha in texto.splitlines() if linha.startswith(prefixo)]


def _tenants_de(series_labels: list[str], rota: str, status: str = "200") -> set[str]:
    alvo = [s for s in series_labels if f'rota="{rota}"' in s and f'status="{status}"' in s]
    return {m.group(1) for s in alvo if (m := re.search(r'tenant="(-?\d+)"', s))}


def test_metrics_200_texto_prometheus_com_as_familias_do_portao(cliente):
    r = cliente.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    for nome in FAMILIAS:
        assert f"# TYPE {nome} " in r.text, f"família ausente: {nome}"
    # não passa por app.auth.middleware.gera_log (SEM_LOG_ACESSO) nem entra em plat.log_acesso
    assert "no-store" in r.headers.get("cache-control", "")


def test_metrics_nao_exige_autenticacao(cliente):
    """A porta 8150 só escuta em 127.0.0.1 (plat-api.service): o Prometheus da casa é quem chama, sem
    sessão nem token — exigir auth aqui quebraria o scrape."""
    assert cliente.get("/metrics").status_code == 200


@pytest.fixture(scope="module")
def cinquenta_inquilinos(sessao_plat):
    inqs = [InquilinoTemporario(sessao_plat) for _ in range(50)]
    yield inqs
    for inq in inqs:
        inq.apagar()


def test_cardinalidade_50_inquilinos_sinteticos_uma_serie_por_inquilino(cliente, cinquenta_inquilinos):
    rota_alvo = "/api/eu"
    for inq in cinquenta_inquilinos:
        assert inq.admin.get(rota_alvo).status_code == 200
    texto = cliente.get("/metrics").text
    total_series = len(_series(texto, "plat_http_requests_total"))
    assert total_series <= 5000, f"cardinalidade de plat_http_requests_total = {total_series} (portão: <= 5000)"
    tenants = _tenants_de(_series(texto, "plat_http_requests_total"), rota_alvo)
    novos = {inq.id for inq in cinquenta_inquilinos}
    assert novos <= {int(t) for t in tenants}, "faltam inquilinos sintéticos na métrica"


def test_refutacao_500_tokens_nao_aumenta_cardinalidade_alem_dos_inquilinos_de_verdade(cliente, sessao_plat):
    """Refutação do item: cria 500 tokens (10 inquilinos x 50 tokens) e faz 1 pedido com CADA UM. A
    contagem de séries de plat_http_requests_total para a rota alvo só pode crescer pelo número de
    INQUILINOS novos (10), nunca pelo número de tokens (500) — e nenhum dos 500 valores de token pode
    aparecer no corpo de /metrics."""
    rota_alvo = "/api/eu"
    antes = _tenants_de(_series(cliente.get("/metrics").text, "plat_http_requests_total"), rota_alvo)

    inquilinos = [InquilinoTemporario(sessao_plat) for _ in range(10)]
    try:
        tokens = []  # só para a checagem final de "nenhum token vaza"; cada um é APAGADO após o uso
        # (o produto limita 20 tokens ATIVOS por usuário — política de segurança correta e alheia a este
        # item; 500 pedidos com 500 tokens DIFERENTES não exige 500 tokens vivos ao mesmo tempo)
        for inq in inquilinos:
            for _ in range(50):
                r = inq.admin.post(
                    "/api/tokens", json={"nome": f"zt-carga-{secrets.token_hex(4)}", "escopos": ["admin:inquilino"]}
                )
                assert r.status_code == 201, r.text
                tok = r.json()
                assert com_token(cliente, tok["token"], "GET", rota_alvo).status_code == 200
                tokens.append(tok["token"])
                assert inq.admin.delete(f"/api/tokens/{tok['id']}").status_code == 204
        assert len(tokens) == 500

        texto_depois = cliente.get("/metrics").text
        depois = _tenants_de(_series(texto_depois, "plat_http_requests_total"), rota_alvo)
        novos = depois - antes
        # 10 inquilinos NOVOS (os 50 tokens de cada um caem na MESMA série, por tenant_id — nunca por token)
        assert len(novos) == 10, f"esperava 10 inquilinos novos na métrica, achou {len(novos)} — token virou rótulo?"
        for token_de_prova in tokens:
            assert token_de_prova not in texto_depois, "token apareceu no corpo de /metrics"
        # "procura métrica que devolve número fixo": plat_jobs_fila reflete o banco de verdade, não um
        # valor hardcoded — cria 1 job e confere que o gauge de pendentes sobe exatamente 1
        fila_antes = _fila_pendente(cliente)
        r = inquilinos[0].admin.post(
            "/api/jobs", json={"tipo": "prova.progresso", "parametros": {"duracao_s": 0, "passos": 1}}
        )
        assert r.status_code == 201, r.text
        fila_depois = _fila_pendente(cliente)
        assert fila_depois == fila_antes + 1, (fila_antes, fila_depois)
    finally:
        for inq in inquilinos:
            inq.apagar()


def _fila_pendente(cliente) -> int:
    texto = cliente.get("/metrics").text
    for linha in texto.splitlines():
        if linha.startswith('plat_jobs_fila{estado="pendente"}'):
            return int(float(linha.rsplit(" ", 1)[1]))
    raise AssertionError("plat_jobs_fila{estado=\"pendente\"} ausente de /metrics")
