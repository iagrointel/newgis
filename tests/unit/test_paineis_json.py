"""Item L7-06-d-paineis — o que dá para conferir nos arquivos de painel sem subir nada.

Os cinco painéis são ARQUIVO (`deploy/grafana/paineis/*.json`), provisionados por
`deploy/grafana/provisioning/`. Nunca editados pela interface: `allowUiUpdates: false` no provedor e
`editable: false` em cada painel. Estes testes seguram exatamente isso.
"""

import json
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
PAINEIS = RAIZ / "deploy/grafana/paineis"
PROV = RAIZ / "deploy/grafana/provisioning"
UID_FONTE = "plat-prometheus"
ESPERADOS = {"plat-visao-geral", "plat-por-inquilino", "plat-banco", "plat-objetos", "plat-backup"}


def arquivos() -> list[Path]:
    return sorted(PAINEIS.glob("*.json"))


def carregar(caminho: Path) -> dict:
    return json.loads(caminho.read_text())


def test_sao_cinco_e_o_nome_do_arquivo_e_o_uid():
    """O uid é a identidade do painel para o Grafana: é ele que faz subir 2× dar o MESMO painel em vez
    de dois. Amarrá-lo ao nome do arquivo tira a chance de duas cópias com uid trocado."""
    achados = {carregar(a)["uid"] for a in arquivos()}
    assert achados == ESPERADOS, achados
    for a in arquivos():
        assert carregar(a)["uid"] == a.stem, a


@pytest.mark.parametrize("caminho", arquivos(), ids=lambda p: p.stem)
def test_painel_e_de_arquivo_e_aponta_a_fonte_pelo_uid(caminho: Path):
    d = carregar(caminho)
    assert d["editable"] is False, "painel editável pela interface: o arquivo deixaria de ser a verdade"
    assert d["title"] and d["description"], "painel sem título ou sem o que ele diz"
    assert d["panels"], "painel sem nenhum quadro"
    for p in d["panels"]:
        assert p["datasource"]["uid"] == UID_FONTE, (p["title"], p["datasource"])
        assert p["targets"], f"quadro sem consulta: {p['title']}"
        for t in p["targets"]:
            assert t["datasource"]["uid"] == UID_FONTE, (p["title"], t)
            assert t["expr"].strip(), f"consulta vazia em {p['title']}"


def test_visao_geral_tem_as_dez_medidas_do_portao():
    """O portão nomeia dez: p95 por rota, ladrilhos/s, acerto de cache, fila, conexões, disco, RAM,
    5xx, usuários ativos em 24 h e jobs. Uma a menos e o painel deixou de responder à pergunta."""
    d = carregar(PAINEIS / "plat-visao-geral.json")
    assert len(d["panels"]) == 10, [p["title"] for p in d["panels"]]
    todas = " ".join(t["expr"] for p in d["panels"] for t in p["targets"])
    for pedaco in ("plat_http_request_duracao_segundos_bucket", "martin_tile_cache_requests_total",
                   "plat_jobs_fila", "pg_stat_activity_count", "node_filesystem_avail_bytes",
                   "node_memory_MemAvailable_bytes", 'status=~"5.."', "plat_usuarios_ativos_24h",
                   "plat_jobs_processados_total"):
        assert pedaco in todas, pedaco


def test_por_inquilino_tem_seletor_e_so_usa_id_opaco():
    """Regra binária do produto: rótulo de inquilino é `plat.tenant.id`, nunca o slug. Um seletor que
    listasse slug poria o nome do cliente na tela e na URL do painel."""
    d = carregar(PAINEIS / "plat-por-inquilino.json")
    variaveis = d["templating"]["list"]
    assert [v["name"] for v in variaveis] == ["inquilino"]
    assert variaveis[0]["query"]["query"] == 'label_values(plat_http_requests_total{tenant!="-"}, tenant)'
    # só o que vai para o Prometheus e para a URL do painel: consulta e seletor. A descrição do
    # painel fala das palavras proibidas de propósito, para explicar a regra a quem lê a tela.
    texto = json.dumps([t["expr"] for p in d["panels"] for t in p["targets"]]
                       + [v["query"]["query"] for v in variaveis])
    for proibido in ("slug", "d_demo", "bucket_alias", "token"):
        assert proibido not in texto, proibido


def test_nenhum_painel_expoe_texto_de_consulta_ou_nome_de_bucket():
    """Cardinalidade e sigilo: o painel do banco mostra queryid, não o texto da consulta (que pode
    trazer literal com dado do cliente); o de objetos mostra tenant_id, não o alias do bucket."""
    texto = json.dumps([t["expr"] for a in arquivos() for p in carregar(a)["panels"] for t in p["targets"]])
    for proibido in ("pg_stat_statements_query", "bucket_alias", "chave_rw", "application_name="):
        assert proibido not in texto, proibido


def test_provisionamento_recusa_edicao_pela_interface():
    prov = yaml.safe_load((PROV / "dashboards/plat.yml").read_text())["providers"][0]
    assert prov["allowUiUpdates"] is False
    assert prov["disableDeletion"] is False, "com deleção desabilitada o Grafana nem recria o apagado"
    assert prov["updateIntervalSeconds"] <= 60
    assert prov["options"]["path"] == "/var/lib/grafana/dashboards/plat"
    fonte = yaml.safe_load((PROV / "datasources/plat-prometheus.yml").read_text())["datasources"][0]
    assert fonte["uid"] == UID_FONTE and fonte["editable"] is False
