"""Portão do item `L1-02-d-cache-nginx-cdn-e-bancada-de-carga` relido sobre a evidência commitada
(`tests/medidas/L1-02-d-cache-nginx-e-carga.json`).

Nasceu como adversário (linha L1, parte 2, turno 9) e derrubou a entrega anterior por três cláusulas
literais — frio abaixo de 15 tiles/s, bancada com um ponto só de conexão, página de status inexistente
— tudo admitido no próprio `nao_feito` da evidência velha. A trilha l102dca50db refez a medição de
ponta a ponta (bancada em `tests/carga/tiles.py`, pilha nginx de usuário + uvicorn por teste) e este
arquivo virou a GUARDA positiva: os mesmos três testes, agora sem xfail, mais a conferência das demais
cláusulas do portão sobre o JSON. Se alguém regredir a evidência (ou apagá-la num merge), isto falha.

Reprodução da medição: `PLAT_GRAVAR_MEDIDAS=1 bash /home/dev/plat-frota/laco/roda_teste.sh
tests/carga/test_l102d_bancada.py -q`. Esta guarda: `... roda_teste.sh
tests/unit/test_l1_adv2_cache_gate.py -q`."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEDIDA = ROOT / "tests" / "medidas" / "L1-02-d-cache-nginx-e-carga.json"


def _dados():
    return json.loads(MEDIDA.read_text(encoding="utf-8"))


def test_frio_uma_conexao_atende_o_portao():
    d = _dados()
    frio = d["carga"]["frio_1_conexao"]
    assert frio["passou"] is True, f"frio_1_conexao nao passou no proprio JSON de fechamento: {frio}"


def test_bancada_cobre_a_faixa_de_1_a_200_conexoes():
    d = _dados()
    texto_nao_feito = " ".join(d.get("nao_feito", []))
    assert "bancada de 1 a 200" not in texto_nao_feito, (
        f"a propria evidencia admite a bancada de 1-200 conexoes como NAO FEITA: {texto_nao_feito!r}"
    )
    quente = d["carga"]["quente"]
    conexoes = [n["conexoes"] for n in quente["niveis"]]
    assert conexoes[0] == 1 and conexoes[-1] == 200, conexoes
    assert quente["passou"] is True and quente["melhor"]["tiles_por_s"] >= 500, quente["melhor"]


def test_pagina_de_status_com_taxa_de_acerto_do_cache_existe():
    achados = []
    for caminho in (ROOT / "app").rglob("*.py"):
        texto = caminho.read_text(encoding="utf-8", errors="ignore").lower()
        if "acerto do cache" in texto or "taxa de acerto" in texto or "cache_hit_rate" in texto:
            achados.append(str(caminho.relative_to(ROOT)))
    assert achados, "nenhum arquivo em app/ implementa taxa de acerto de cache por dia"
    # a cláusula é PÁGINA: rota registrada e os dois arquivos da tela presentes
    from app.paginas import PAGINAS, WEB

    assert PAGINAS.get("/admin/cache") == "admin/cache.html"
    assert (WEB / "admin" / "cache.html").is_file()
    assert (WEB / "js" / "admin" / "cache.js").is_file()


def test_todas_as_clausulas_da_evidencia_passam():
    d = _dados()
    fases = {
        "quente": d["carga"]["quente"],
        "frio_1_conexao": d["carga"]["frio_1_conexao"],
        "proxy_cache_lock": d["cache"]["proxy_cache_lock"],
        "chave_com_parametros": d["chave_com_parametros"],
        "revogacao": d["revogacao"],
        "eviction": d["eviction"],
    }
    reprovadas = [nome for nome, fase in fases.items() if fase.get("passou") is not True]
    assert not reprovadas, f"clausulas reprovadas na evidencia commitada: {reprovadas}"
