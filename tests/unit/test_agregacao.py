"""Unitários do motor de agregação (item L2-06-e-estatisticas-servidor), sem banco: só a montagem do
pedido e a tradução `outStatistics` -> pedido canônico."""

import pytest

from app.estatistica import agregacao as agr


def test_montar_pedido_simples():
    p = agr.montar_pedido({"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "sum"}]})
    assert p.grupos == ["categoria"]
    assert p.estatisticas[0].nome_saida() == "sum_valor"


def test_montar_pedido_percentil_fora_da_faixa_reprova():
    with pytest.raises(agr.ErroAgregacao):
        agr.montar_pedido({"estatisticas": [{"campo": "valor", "tipo": "percentile", "percentil": 150}]})


def test_montar_pedido_estatistica_invalida_reprova():
    with pytest.raises(agr.ErroAgregacao):
        agr.montar_pedido({"estatisticas": [{"campo": "valor", "tipo": "mediana"}]})


def test_montar_pedido_50_estatisticas_reprova():
    stats = [{"campo": "valor", "tipo": "sum", "alias": f"s{i}"} for i in range(51)]
    with pytest.raises(agr.ErroAgregacao):
        agr.montar_pedido({"estatisticas": stats})


def test_montar_pedido_identificador_malicioso_reprova():
    with pytest.raises(agr.ErroAgregacao):
        agr.montar_pedido({"grupos": ["categoria; DROP TABLE x"]})


def test_montar_pedido_limite_acima_do_teto_reprova():
    with pytest.raises(agr.ErroAgregacao):
        agr.montar_pedido({"grupos": ["c"], "limite": agr.LIMITE_GRUPOS + 1})


def test_construir_sql_grupo_por_geometria_reprova():
    """refutação do item: agrupar por campo de geometria — 'geom' nunca está em `colunas` (a rota
    remove `geom`/`tenant_id` de `_colunas` antes de chegar aqui), então cai no mesmo erro de campo
    inexistente que qualquer nome fora do esquema."""
    p = agr.montar_pedido({"grupos": ["geom"]})
    with pytest.raises(agr.ErroAgregacao) as exc:
        agr.construir_sql("plat_trabalho", "zt_x", p, {"id": "integer", "valor": "numeric"})
    assert exc.value.codigo == "campo_inexistente"


def test_traduzir_outstatistics_para_pedido_canonico():
    q = {
        "outStatistics": [
            {"statisticType": "sum", "onStatisticField": "valor", "outStatisticFieldName": "total"},
            {"statisticType": "count", "onStatisticField": "id", "outStatisticFieldName": "n"},
        ],
        "groupByFieldsForStatistics": "categoria",
        "orderByFields": "categoria DESC",
    }
    corpo = agr.traduzir_outstatistics(q)
    assert corpo["grupos"] == ["categoria"]
    assert corpo["ordenacao"] == "-categoria"
    p = agr.montar_pedido(corpo)
    nomes = {e.nome_saida() for e in p.estatisticas}
    assert nomes == {"total", "n"}


def test_traduzir_outstatistics_tipo_desconhecido_reprova():
    with pytest.raises(agr.ErroAgregacao):
        agr.traduzir_outstatistics({"outStatistics": [{"statisticType": "esriMedianaX", "onStatisticField": "v"}]})


def test_construir_sql_faixa_data_usa_date_trunc_e_fuso():
    p = agr.montar_pedido({"faixa_data": {"campo": "quando", "granularidade": "mes", "fuso": "America/Sao_Paulo"}})
    sql_montado = agr.construir_sql(
        "plat_trabalho", "zt_x", p, {"quando": "timestamp with time zone"}
    )
    assert "date_trunc('month'" in sql_montado.sql
    # 2 na expressão do SELECT + 2 na do GROUP BY (mesma expressão reconstruída)
    assert sql_montado.params.count("America/Sao_Paulo") == 4
