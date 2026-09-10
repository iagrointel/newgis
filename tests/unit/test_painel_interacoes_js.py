"""Interações do painel em node (item L2-06-c-acoes-seletores-filtros-cruzados) — o MESMO teste roda o
runner `tests/app/executar_painel_js.mjs`, que importa o BARRAMENTO REAL do L5-07 (`web/js/app/barramento.js`)
e o adaptador REAL (`web/js/paineis/interacoes.js`) sem dublê nenhum: latência gatilho→ação com 10.000
feições (cláusula 6 do portão, p95 <= 100 ms), refutação de ciclo A→B→A (corte em uma volta), seleção de
5.000 feições e estado na URL. Também grava `tests/medidas/L2-06-c-acoes-seletores-filtros-cruzados.json`
(só com `PLAT_GRAVAR_MEDIDAS=1`)."""

import datetime
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "app" / "executar_painel_js.mjs"
LIMITE_P95_MS = 100.0  # cláusula literal do portão do item


def _rodar() -> dict:
    r = subprocess.run(
        ["node", str(RUNNER)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        check=True,
    )
    return json.loads(r.stdout)


def test_interacoes_do_painel_no_node(medida):
    saida = _rodar()
    lat = saida["latencia"]
    cic = saida["ciclo"]
    sel = saida["selecao5000"]
    url = saida["url"]
    emb = saida["embrulhar"]

    # cláusula 6: p95 gatilho→ação <= 100 ms com 10.000 feições carregadas nos alvos
    assert lat["disparos_medidos"] == 200, "nem todo disparo foi medido pelo barramento"
    assert lat["p95_ms"] is not None and lat["p95_ms"] <= LIMITE_P95_MS, (
        f"p95 {lat['p95_ms']} ms > {LIMITE_P95_MS} ms"
    )
    # o filtro do seletor chegou aos alvos da mesma fonte e o alvo de fonte DIFERENTE recebeu o in
    assert lat["filtro_no_alvo_aplicado"] == {
        "op": "=",
        "args": [{"property": "categoria"}, "agua"],
    }
    assert lat["alvo_d_recebeu_in"], "relação por atributo não virou in-list no alvo de outra fonte"

    # refutação: A→B→A não recursa (cada mensagem roda no máximo uma vez por volta)
    assert cic["terminou_sem_laco"] and cic["disparos"] == 200
    assert cic["cortes_ciclo_cortado"] >= 1, "o ciclo A→B→A rodou sem o aviso de corte"
    assert cic["voltas_com_mais_de_uma_mensagem"] == 0, "uma volta executou a mesma mensagem duas vezes"

    # refutação: seleção de 5.000 em vista com 10.000
    assert sel["selecao_5000_aceita"] and sel["selecionadas"] == 5000
    assert sel["in_deduplicado"], "o in-list da relação por atributo não casou com os valores da seleção"

    # cláusula 5 (funções puras): estado das vistas → URL → vistas novas
    assert url["nome_do_parametro"] == ["v.v:el1", "v.v:el2"]
    assert url["vistas_aplicadas"] == 2
    assert url["filtro_restaurado_igual"] and url["selecao_restaurada_igual"]

    # a forma de feição que as relações leem, para cada tipo de resultado do servidor
    assert emb["linhas_com_geometria"] and emb["serie_id_e_a_chave"]
    assert emb["categorias_id_e_a_categoria"] and emb["feicao_unica"]
    assert emb["numero_nao_carrega_feicao"]

    grava = medida("L2-06-c-acoes-seletores-filtros-cruzados")
    carga_1min = os.getloadavg()[0]
    ram_livre_gb = next(
        (int(linha.split()[1]) / (1024 * 1024)
         for linha in open("/proc/meminfo", encoding="ascii") if linha.startswith("MemAvailable:")),
        None,
    )
    medido_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contexto = f"carga_1min={carga_1min:.2f}, ram_livre_gb={ram_livre_gb}, medido_em={medido_em}"
    grava("carga_1min", round(carga_1min, 2), "load",
          f"os.getloadavg()[0] no momento da medição ({medido_em})")
    grava("ram_livre_gb", ram_livre_gb, "GB",
          "MemAvailable de /proc/meminfo no momento da medição")
    grava("medido_em", medido_em, "data UTC", "carimbo da medição de latência deste arquivo")
    grava("latencia_p95_gatilho_acao_10k_ms", round(lat["p95_ms"], 3), "ms",
          "tests/app/executar_painel_js.mjs: 200 disparos de filtro_mudou do seletor com 10.000 feições "
          "nas 4 vistas alvo (3 da mesma fonte + 1 por atributo); p95 de barramento.medidas — portão "
          f"<= 100 ms ({contexto})")
    grava("latencia_max_gatilho_acao_10k_ms", round(lat["max_ms"], 3), "ms",
          "mesma série do p95, o disparo mais lento dos 200")
    grava("latencia_p95_pior_caso_atributo_10k_ms", round(lat["pior_caso_atributo_10k_p95_ms"], 3), "ms",
          "pior caso adversarial (50 disparos): a ORIGEM tem as 10.000 feições e o filtro é avaliado em "
          "memória feição a feição (caminho que o painel real não usa — ele filtra em SQL no servidor)")
    grava("ciclo_ab_ba_cortes_por_200_disparos", cic["cortes_ciclo_cortado"], "avisos",
          "A filtra B e B filtra A: um ciclo_cortado por disparo (a mensagem re-dispachada pelo causador é "
          "cortada em 1 volta); 200 disparos terminam")
    grava("selecao_5000_gatilho_ms", round(sel["ms_gatilho_para_acao"], 3), "ms",
          "definirSelecao(5000 ids) + disparar selecao_mudou com ação por atributo; in-list sai "
          "deduplicado (5000 ids → valores distintos da seleção)")
    grava("parametros_url_por_vista", len(url["nome_do_parametro"]), "parâmetros",
          "estadoDasVistas → paramsDoEstado → estadoDosParams → aplicarEstado ida e volta; nome do "
          "parâmetro v.v:<id do elemento> (prefixo v. do L5-07 + id de vista v:<id>)")
