"""Dicionário de unidades da BDGD: declarada × detectada (item L4-01-e-dicionario-unidades-bdgd).

O dicionário do pacote eletrica-br declarava COMP em quilômetro e ENE_SUM em megawatt-hora; o extrato de
referência da casa traz os dois em metro e em quilowatt-hora. Este arquivo prova, cláusula por cláusula do
portão, que a unidade passou a ser MEDIDA no arquivo, GRAVADA na auditoria da importação e LIDA de lá por
quem soma (sumário por subrede) e por quem exporta (OpenDSS):

1. `test_auditoria_lista_unidade_declarada_e_detectada_por_campo` — a auditoria da importação
   (`plat.rede_importacao.unidades`) lista, por campo numérico, a unidade declarada, a detectada e o fator;
2. `test_arquivo_em_metros_e_em_quilometros_dao_o_mesmo_comprimento` — dois arquivos iguais em tudo menos
   na unidade do COMP dão o MESMO comprimento em metros;
3. `test_refutacao_energia_em_mwh_e_em_kwh_dao_a_mesma_energia_anual` — a refutação exigida pelo item: dois
   arquivos iguais em tudo menos na unidade da energia dão a MESMA energia anual em quilowatt-hora;
4. `test_sumario_por_subrede_le_a_unidade_da_auditoria` — o sumário do item L4-04-c muda de resultado
   quando a auditoria diz que o arquivo está em quilômetro e megawatt-hora, e diz na própria linha de onde
   a unidade veio;
5. `test_exportador_opendss_le_a_unidade_da_auditoria` — o circuito exportado usa o fator da auditoria: a
   MESMA rede, exportada depois de uma importação que mediu megawatt-hora, tem carga mil vezes maior.

Os arquivos de teste são SINTÉTICOS (`tests/dados/gerar_bdgd_unidades.py`) porque a cláusula compara dois
arquivos que só diferem na unidade, e esse par não existe no extrato real — ele é construído. A geometria é
de verdade: o COMP escrito no arquivo é o comprimento geodésico medido do próprio segmento.
"""

# ruff: noqa: F811  (fixtures importadas de módulos irmãos: padrão do pytest neste repositório)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rede_utilidades import unidades as unidades_mod
from app.rede_utilidades.bdgd import importar
from tests.api.test_rede_modelo import rede_eletrica  # noqa: F401  (fixture reusada)
from tests.api.test_rede_opendss import _alimentador, _atualizar_tudo, _pasta
from tests.api.test_rede_opendss import _criar_rede as _criar_rede_dss
from tests.api.test_rede_subredes_resumo import _calcular, _criar_rede, _rede_bdgd, _tabela
from tests.api.test_rls import contexto
from tests.dados import gerar_bdgd_unidades as gerador

ITEM = "L4-01-e-dicionario-unidades-bdgd"
MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / f"{ITEM}.json"
CTMT_DSS = "ZT-DSS-1"


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _importar(con, tenant_id, usuario_id, rede_id, caminho) -> dict:
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        return importar(cur, tenant_id, rede_id, caminho)


def _importar_publicando(env, sessao, rede_id, caminho, apagar_consumidores: bool = False) -> dict:
    """Importa numa CONEXÃO PRÓPRIA e confirma a transação: os testes de sumário e de exportação leem pela
    API, que é outra conexão, e sem `commit` a auditoria não existiria para ela. A conexão é própria (e não
    a da fixture do modelo) porque confirmar a transação da fixture deixaria a rede dela no banco da trilha,
    e o nome de rede é único — isso quebrava a rodada seguinte. A rede destes testes é criada e apagada pela
    própria sessão da API, e `plat.rede_importacao` cai por cascata com ela."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import ids_por_slug

    eu = sessao.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
        with con.cursor() as cur:
            contexto(con, tenant_id, int(eu["id"]))
            if apagar_consumidores:
                cur.execute("DELETE FROM plat.rede_no WHERE rede_id = %s::uuid AND papel = 'consumidor'",
                            (rede_id,))
            resultado = importar(cur, tenant_id, rede_id, caminho)
        con.commit()
        return resultado
    finally:
        con.close()


def _soma_comprimento_mt(con, rede_id) -> float:
    with con.cursor() as cur:
        cur.execute(
            "SELECT sum(a.comprimento_m) AS m FROM plat.rede_aresta a "
            "JOIN plat.rede_tipo t ON t.id = a.tipo_id "
            "JOIN plat.rede_grupo g ON g.id = t.grupo_id "
            "WHERE a.rede_id = %s::uuid AND g.codigo = 'trecho_de_media_tensao'",
            (rede_id,),
        )
        return float(cur.fetchone()["m"] or 0.0)


def _energia_anual_kwh(con, rede_id) -> float:
    """Energia anual das unidades consumidoras da rede, convertida com o fator que a IMPORTAÇÃO mediu —
    o mesmo caminho que o sumário e o exportador usam."""
    with con.cursor() as cur:
        fator = unidades_mod.fatores_da_rede(cur, rede_id)["ene"]["fator_para_base"]
        cur.execute(
            "SELECT sum(v) AS total FROM plat.rede_no n, "
            "  LATERAL (SELECT sum((n.atributos ->> c)::double precision) AS v "
            "           FROM unnest(%s::text[]) AS c WHERE n.atributos ? c) s "
            "WHERE n.rede_id = %s::uuid AND n.papel = 'consumidor'",
            ([f"ENE_{m:02d}" for m in range(1, 13)], rede_id),
        )
        return float(cur.fetchone()["total"] or 0.0) * fator


# --- cláusula 1: a auditoria lista unidade declarada e detectada por campo, com fator --------------------


def test_auditoria_lista_unidade_declarada_e_detectada_por_campo(rede_eletrica, tmp_path):
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    caminho = gerador.escrever(tmp_path / "metros_kwh.gpkg", unidade_comp="m", unidade_ene="kWh")
    resultado = _importar(con, tenant_id, usuario_id, rede_id, caminho)

    unidades = resultado["unidades"]
    assert "SSDMT.COMP" in unidades and "UCBT_tab.ENE" in unidades, sorted(unidades)
    comp = unidades["SSDMT.COMP"]
    assert comp["familia"] == "comp" and comp["declarada"] == "km"
    assert comp["detectada"] == "metros" and comp["fator_para_base"] == 1.0 and comp["origem"] == "detectada"
    assert 0.99 <= comp["razao_comp_sobre_geodesico"] <= 1.01, comp
    ene = unidades["UCBT_tab.ENE"]
    assert ene["familia"] == "ene" and ene["declarada"] == "MWh"
    assert ene["detectada"] == "kWh" and ene["fator_para_base"] == 1.0 and ene["origem"] == "detectada"
    # as duas âncoras da ordem de grandeza são medidas, não supostas
    assert ene["por_potencia_instalada"] == "kWh" and ene["por_unidade_consumidora"] == "kWh", ene
    assert ene["kva_instalado"] == pytest.approx(gerador.TRAFOS * gerador.POT_NOM_KVA), ene

    # e o mesmo dicionário está na LINHA de auditoria, que é de onde os outros módulos leem
    with con.cursor() as cur:
        cur.execute("SELECT unidades FROM plat.rede_importacao WHERE id = %s::uuid",
                    (resultado["importacao_id"],))
        gravado = cur.fetchone()["unidades"]
    assert gravado["SSDMT.COMP"]["fator_para_base"] == 1.0
    assert gravado["UCBT_tab.ENE"]["detectada"] == "kWh"

    with con.cursor() as cur:
        fatores = unidades_mod.fatores_da_rede(cur, rede_id)
    assert fatores["comp"]["origem"] == "detectada" and fatores["comp"]["fator_para_base"] == 1.0
    assert fatores["ene"]["origem"] == "detectada" and fatores["ene"]["fator_para_base"] == 1.0


# --- cláusula 2: km e metros dão o mesmo comprimento -----------------------------------------------------


def test_arquivo_em_metros_e_em_quilometros_dao_o_mesmo_comprimento(rede_eletrica, tmp_path):
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    geodesico = sum(gerador.comprimento_geodesico_m(i) for i in range(gerador.TRECHOS))

    em_metros = gerador.escrever(tmp_path / "m.gpkg", unidade_comp="m", unidade_ene="kWh")
    r1 = _importar(con, tenant_id, usuario_id, rede_id, em_metros)
    soma_m = _soma_comprimento_mt(con, rede_id)

    # a mesma rede, apagada e recarregada do arquivo em quilômetro
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute("DELETE FROM plat.rede_aresta WHERE rede_id = %s::uuid", (rede_id,))
    em_km = gerador.escrever(tmp_path / "km.gpkg", unidade_comp="km", unidade_ene="kWh")
    r2 = _importar(con, tenant_id, usuario_id, rede_id, em_km)
    soma_km = _soma_comprimento_mt(con, rede_id)

    assert r1["unidades"]["SSDMT.COMP"]["detectada"] == "metros"
    assert r2["unidades"]["SSDMT.COMP"]["detectada"] == "quilometros"
    assert r2["unidades"]["SSDMT.COMP"]["fator_para_base"] == 1000.0
    assert soma_m == pytest.approx(soma_km, rel=1e-6), (soma_m, soma_km)
    assert soma_m == pytest.approx(geodesico, rel=1e-3), (soma_m, geodesico)


# --- cláusula 3 (refutação do item): MWh e kWh dão a mesma energia ---------------------------------------


def test_refutacao_energia_em_mwh_e_em_kwh_dao_a_mesma_energia_anual(rede_eletrica, tmp_path):
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    esperado = gerador.energia_anual_kwh()

    em_kwh = gerador.escrever(tmp_path / "kwh.gpkg", unidade_comp="m", unidade_ene="kWh")
    r1 = _importar(con, tenant_id, usuario_id, rede_id, em_kwh)
    energia_kwh = _energia_anual_kwh(con, rede_id)

    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute("DELETE FROM plat.rede_no WHERE rede_id = %s::uuid AND papel = 'consumidor'", (rede_id,))
    em_mwh = gerador.escrever(tmp_path / "mwh.gpkg", unidade_comp="m", unidade_ene="MWh")
    r2 = _importar(con, tenant_id, usuario_id, rede_id, em_mwh)
    energia_mwh = _energia_anual_kwh(con, rede_id)

    assert r1["unidades"]["UCBT_tab.ENE"]["detectada"] == "kWh"
    assert r2["unidades"]["UCBT_tab.ENE"]["detectada"] == "MWh"
    assert r2["unidades"]["UCBT_tab.ENE"]["fator_para_base"] == 1000.0
    assert energia_kwh == pytest.approx(esperado, rel=1e-6), (energia_kwh, esperado)
    assert energia_mwh == pytest.approx(esperado, rel=1e-6), (energia_mwh, esperado)


# --- cláusula 4: o sumário por subrede lê a unidade da auditoria -----------------------------------------


def test_sumario_por_subrede_le_a_unidade_da_auditoria(sessao_a, env, limpar_redes, tmp_path):
    rid = _criar_rede(sessao_a, "unidades", limpar_redes)
    _rede_bdgd(sessao_a, rid)

    # sem importação registrada a unidade NÃO foi medida: o valor entra como está no arquivo, e a linha diz
    _calcular(sessao_a, rid)
    linha = {i["subrede"]: i for i in _tabela(sessao_a, rid)["itens"]}["1_TST_1"]
    assert linha["unidades"]["comp"]["origem"] == "nao_medida", linha["unidades"]
    assert linha["unidades"]["comp"]["declarada_no_dicionario"] == "km"
    km_sem_medida, energia_sem_medida = linha["km_declarado"], linha["energia_anual_kwh"]

    # agora a MESMA rede recebe uma importação cujo arquivo está em quilômetro e megawatt-hora
    caminho = gerador.escrever(tmp_path / "km_mwh.gpkg", unidade_comp="km", unidade_ene="MWh")
    _importar_publicando(env, sessao_a, rid, caminho)
    _calcular(sessao_a, rid)
    linha2 = {i["subrede"]: i for i in _tabela(sessao_a, rid)["itens"]}["1_TST_1"]

    assert linha2["unidades"]["comp"]["origem"] == "detectada", linha2["unidades"]
    assert linha2["unidades"]["comp"]["unidade_do_arquivo"] == "km"
    assert linha2["unidades"]["ene"]["unidade_do_arquivo"] == "MWh"
    # o número muda porque a unidade do arquivo mudou — e é o único motivo pelo qual ele muda
    assert linha2["km_declarado"] == pytest.approx(km_sem_medida * 1000.0, rel=1e-9)
    assert linha2["energia_anual_kwh"] == pytest.approx(energia_sem_medida * 1000.0, rel=1e-9)


# --- cláusula 5: o exportador OpenDSS lê a unidade da auditoria ------------------------------------------


def test_exportador_opendss_le_a_unidade_da_auditoria(sessao_a, env, limpar_redes, tmp_path):
    rid = _criar_rede_dss(sessao_a, "unidades", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)

    def exportar() -> dict:
        # `jusante=true`: a unidade consumidora vive na subrede de BAIXA tensão, abaixo do transformador —
        # sem o jusante o circuito sai só com a média tensão e não teria carga nenhuma para comparar
        rota = f"/api/rede/{rid}/subrede/{CTMT_DSS}/exportar?formato=dss&jusante=true&ano=2024"
        arquivos = _pasta(sessao_a.get(rota))
        return {"resumo": json.loads(arquivos["resumo.json"]), "cargas": arquivos["Cargas.dss"]}

    def kw_da_primeira_carga(cargas: str) -> float:
        for linha in cargas.splitlines():
            if linha.startswith("New Load."):
                for pedaco in linha.split():
                    if pedaco.startswith("kw="):
                        return abs(float(pedaco[3:]))
        raise AssertionError(cargas)

    em_kwh = gerador.escrever(tmp_path / "dss_kwh.gpkg", unidade_comp="m", unidade_ene="kWh")
    _importar_publicando(env, sessao_a, rid, em_kwh)
    saida_kwh = exportar()
    assert saida_kwh["resumo"]["conferencia"]["cargas"] >= 1, saida_kwh["resumo"]
    assert saida_kwh["resumo"]["unidades"]["ene"]["unidade_do_arquivo"] == "kWh"
    assert saida_kwh["resumo"]["unidades"]["ene"]["origem"] == "detectada"

    em_mwh = gerador.escrever(tmp_path / "dss_mwh.gpkg", unidade_comp="m", unidade_ene="MWh")
    _importar_publicando(env, sessao_a, rid, em_mwh, apagar_consumidores=True)
    saida_mwh = exportar()
    assert saida_mwh["resumo"]["unidades"]["ene"]["unidade_do_arquivo"] == "MWh"

    kw_kwh = kw_da_primeira_carga(saida_kwh["cargas"])
    kw_mwh = kw_da_primeira_carga(saida_mwh["cargas"])
    # O arquivo do OpenDSS escreve `kw` com seis casas decimais. Com o arquivo em quilowatt-hora a carga
    # desta unidade consumidora é da ordem de 0,00014 kW, ou seja, a sexta casa É a precisão disponível: o
    # valor arredondado, multiplicado por mil, erra até 5e-4 kW. Por isso a comparação é por diferença
    # absoluta nesse tamanho — o que se está separando aqui é 1.000×, não a quarta casa.
    assert kw_mwh == pytest.approx(kw_kwh * 1000.0, abs=1e-3), (kw_kwh, kw_mwh)
    assert 900.0 < kw_mwh / kw_kwh < 1100.0, (kw_kwh, kw_mwh)

    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    MEDIDAS.write_text(json.dumps({
        "item": ITEM,
        "clausulas": {
            "auditoria_por_campo": "SSDMT.COMP e UCBT_tab.ENE com declarada, detectada e fator",
            "km_x_metros": "mesmo comprimento em metros nos dois arquivos",
            "mwh_x_kwh": "mesma energia anual em quilowatt-hora nos dois arquivos",
            "sumario_le_da_auditoria": "km_declarado e energia_anual_kwh mudam com a unidade medida",
            "exportador_le_da_auditoria": "carga do OpenDSS mil vezes maior com o arquivo em megawatt-hora",
        },
        "medido": {
            "kw_da_primeira_carga_arquivo_em_kwh": kw_kwh,
            "kw_da_primeira_carga_arquivo_em_mwh": kw_mwh,
            "energia_anual_do_arquivo_sintetico_kwh": gerador.energia_anual_kwh(),
            "comprimento_geodesico_total_m": round(
                sum(gerador.comprimento_geodesico_m(i) for i in range(gerador.TRECHOS)), 3),
        },
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
