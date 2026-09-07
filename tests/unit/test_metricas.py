"""app/metricas.py (item L7-06-a-metricas-exporters): contrato de cardinalidade e ausência de segredo/token
no texto exposto. Testes de integração (rota /metrics de verdade, contra a API) ficam em tests/api/test_metricas_rota.py."""

import re

from app import metricas

FAMILIAS_ESPERADAS = {
    "plat_http_requests_total",
    "plat_http_request_duracao_segundos",
    "plat_tiles_requisicoes_total",
    "plat_jobs_processados_total",
    "plat_jobs_fila",
    "plat_jobs_workers_vivos",
}


class _RotaFalsa:
    def __init__(self, path):
        self.path = path


class _RequestFalso:
    """Só o suficiente de starlette.Request para exercitar rota_para_metrica: scope com/sem 'route'."""

    def __init__(self, rota_path=None):
        self.scope = {"route": _RotaFalsa(rota_path)} if rota_path else {}


def _registro_vazio():
    """REGISTRO é módulo-global (contadores acumulam entre testes do mesmo processo pytest — normal em
    Prometheus). Os testes daqui conferem DELTA e forma, nunca valor absoluto."""
    return metricas.expor()[0].decode("utf-8")


def test_rota_para_metrica_usa_o_padrao_da_rota_nunca_o_caminho_literal():
    r = _RequestFalso("/api/jobs/{job_id}")
    assert metricas.rota_para_metrica(r) == "/api/jobs/{job_id}"


def test_rota_para_metrica_sem_rota_casada_cai_no_rotulo_fixo():
    assert metricas.rota_para_metrica(_RequestFalso(None)) == "outro"


def test_expor_devolve_content_type_prometheus_e_todas_as_familias():
    # prometheus_client só emite uma família se ALGUMA combinação de rótulo já foi observada (Counter/
    # Histogram vazios não geram nem HELP/TYPE) — este teste é o que garante que, depois de UM uso de
    # cada instrumento, as 6 famílias do portão aparecem juntas; import de app.saude é o que registra o
    # coletor de fila (plat.fila_estado(), só a API o registra, nunca o worker — ver metricas.py).
    import app.saude  # noqa: F401 — registra o coletor de fila em metricas.REGISTRO como efeito de import

    metricas.registrar_requisicao("/_teste_familias", 200, 100098, 0.01)
    metricas.registrar_tile("cog_autorizar", "autorizado")
    metricas.registrar_job_processado("prova.progresso", "concluido")
    corpo, tipo = metricas.expor()
    assert tipo.startswith("text/plain")
    texto = corpo.decode("utf-8")
    # text_string_to_metric_families reporta o nome da família SEM o sufixo "_total"/"_bucket" (convenção
    # do parser para Counter/Histogram) — conferir a linha "# TYPE <nome> ..." literal evita esse ruído e
    # prova exatamente o que o portão pede ("`curl :8150/metrics` ... devolve 200 com as famílias listadas").
    for nome in FAMILIAS_ESPERADAS:
        assert f"# TYPE {nome} " in texto, f"família ausente de /metrics: {nome}"


def test_registrar_requisicao_rotula_por_tenant_id_nunca_por_token():
    """Contrato estrutural: a assinatura de registrar_requisicao não aceita token nenhum — não há como
    um chamador vazar token_id nesta função, mesmo por engano."""
    import inspect

    parametros = set(inspect.signature(metricas.registrar_requisicao).parameters)
    assert "token" not in parametros and "token_id" not in parametros
    assert {"rota", "status", "tenant_id", "duracao_s"} == parametros


def test_cardinalidade_nao_cresce_com_numero_de_chamadas_so_com_numero_de_combinacoes():
    """50 inquilinos sintéticos (tenant_id 100000..100049) x 1 rota x 1 status: exatamente 50 séries NOVAS,
    não importa quantas vezes cada combinação é observada (a refutação real, com token de verdade passando
    pela API/middleware, está em tests/api/test_metricas_rota.py::test_refutacao_500_tokens...)."""
    antes = {
        linha.split("{", 1)[1].rsplit("}", 1)[0]
        for linha in _registro_vazio().splitlines()
        if linha.startswith("plat_http_requests_total{")
    }
    rota = "/_teste_cardinalidade_unico_da_suite"
    for _rodada in range(3):  # repete: não deve criar série nova, só incrementar as mesmas 50
        for tid in range(100000, 100050):
            metricas.registrar_requisicao(rota, 200, tid, 0.01)
    depois = {
        linha.split("{", 1)[1].rsplit("}", 1)[0]
        for linha in _registro_vazio().splitlines()
        if linha.startswith("plat_http_requests_total{")
    }
    novas = depois - antes
    assert len(novas) == 50, f"esperava 50 séries novas (uma por inquilino sintético), achou {len(novas)}"
    for serie in novas:
        assert f'rota="{rota}"' in serie and 'status="200"' in serie
        m = re.search(r'tenant="(\d+)"', serie)
        assert m and 100000 <= int(m.group(1)) <= 100049


def test_um_token_de_verdade_gerado_como_o_do_produto_nunca_aparece_no_corpo_exposto():
    """Token real (mesmo formato de app/auth/rotas_tokens.py: 'plat_' + token_urlsafe(32)) registrado
    só como uma STRING QUALQUER no processo (nunca passado a metricas.py — a função não aceita token,
    teste estrutural acima) não pode aparecer no corpo exposto por coincidência de algum f-string solto."""
    import secrets

    token_de_prova = "plat_" + secrets.token_urlsafe(32)
    metricas.registrar_requisicao("/_teste_token_nao_vaza", 200, 100099, 0.01)
    assert token_de_prova not in _registro_vazio()


# ---------------------------------------------------------------- item L7-06-b-alertas: novas famílias


def test_dias_restantes_certificado_curto_da_negativo_ou_perto_de_zero(tmp_path):
    """openssl gera um certificado autoassinado válido por 1 dia (86400 s); a função devolve um número
    de dias positivo bem menor que qualquer limiar de alerta razoável (14 d do portão)."""
    import subprocess

    cert = tmp_path / "curto.pem"
    chave = tmp_path / "curto.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(chave), "-out", str(cert),
         "-days", "1", "-nodes", "-subj", "/CN=teste-alertas-il706balert"],
        check=True, capture_output=True,
    )
    dias = metricas._dias_restantes_certificado(str(cert))
    assert dias is not None
    assert 0 < dias <= 1.01


def test_dias_restantes_certificado_arquivo_ausente_devolve_none():
    assert metricas._dias_restantes_certificado("/caminho/que/nao/existe.pem") is None
