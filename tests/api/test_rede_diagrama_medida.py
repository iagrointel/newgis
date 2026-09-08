"""Medição em escala REAL da cláusula de tempo do item L4-04-d-diagrama-esquematico (marcador `lento`: fora
do pytest do dia a dia).

Cláusula medida: **gerar o diagrama de UM alimentador da cooperativa de teste, a partir do traçado de
subrede, em ≤ 10 s**. Junto vão, sobre a MESMA rede real, as outras três cláusulas que só ganham sentido em
escala: os quatro layouts do portão terminam com ZERO par de nós a menos de 1 unidade; a regra
`reduzir_juncao_de_passagem` reduz o número de nós; e o grafo reduzido tem o mesmo número de componentes
conexos do grafo bruto.

RECORTE DECLARADO: a carga é a BDGD da cooperativa de teste (schema lido de
`PLAT_REDE_REFERENCIA_ESQUEMA`, ativo da casa, somente leitura), restrita a UM alimentador — o MAIOR do
arquivo, que é o pior caso. Quem citar o número tem de citar o recorte junto: é 1 dos 20 alimentadores, e o
tempo medido é o da GERAÇÃO do diagrama (recorte + grafo + regras + layout + gravação), não o da carga da
BDGD nem o da construção da topologia, que são etapas de outros itens e estão registradas ao lado.

⛔ Exige o GRANT de leitura do ativo para o papel da trilha (o `trilha_ambiente.sh` já dá). Sem a variável de
ambiente, o teste PULA com a razão escrita, nunca inventa número."""

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.rede_utilidades import diagrama, subredes
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd

ITEM = "L4-04-d-diagrama-esquematico"
MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / f"{ITEM}.json"
SEGUNDOS_MAXIMO = 10.0
LAYOUTS_DO_PORTAO = ("arvore_inteligente", "radial", "linha_principal", "geografico")
CARGA_MAXIMA_PARA_MEDIR = 8.0  # 12 núcleos; acima disso o número mede a casa, não o produto


def _conectar(env, tenant_id, usuario_id):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "medida-l404d"),
        )
    return con


def _carga_da_maquina() -> dict:
    carga_1min = os.getloadavg()[0]
    livre_gb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("MemAvailable:"):
                    livre_gb = round(int(linha.split()[1]) / 1024 / 1024, 2)
                    break
    except OSError:
        livre_gb = None
    return {"carga_1min": round(carga_1min, 2), "ram_livre_gb": livre_gb,
            "medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _maior_alimentador(cur) -> tuple[str, int]:
    """O alimentador com mais trechos de média tensão no arquivo — recorte determinístico e pior caso.
    Medir no menor daria um número bonito e sem valor."""
    cur.execute(
        f"SELECT ctmt, count(*) AS n FROM {carga_bdgd.exigir_esquema()}.ssdmt "
        "WHERE ctmt IS NOT NULL AND wkt IS NOT NULL GROUP BY 1 ORDER BY n DESC, ctmt LIMIT 1"
    )
    r = cur.fetchone()
    return r["ctmt"], r["n"]


@pytest.mark.lento
def test_medida_diagrama_de_um_alimentador_da_cooperativa(cred, env):
    if not carga_bdgd.esquema():
        pytest.skip("sem PLAT_REDE_REFERENCIA_ESQUEMA: a medida precisa da BDGD real da cooperativa")
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)["demo"]
    con.close()

    r = cliente.post("/api/rede", json={"nome": "zt-medida-diagrama", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    medida = {"rede_id": rid, "clausulas": {}, "avisos": []}
    con = None
    try:
        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text

        con = _conectar(env, tenant_id, eu["id"])
        with con.cursor() as cur:
            alimentador, trechos_no_arquivo = _maior_alimentador(cur)
            cron = carga_bdgd.carregar(cur, tenant_id, rid, ctmts=[alimentador], com_postes=False)
        con.commit()
        medida["recorte"] = {"alimentador": alimentador, "de_quantos_no_arquivo": 20,
                             "trechos_mt_no_arquivo": trechos_no_arquivo,
                             "postes": "fora (0 nó de topologia)"}
        medida["carga_bdgd"] = cron

        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        assert r.status_code == 201, r.text[:2000]
        medida["topologia"] = r.json()
        r = cliente.post(f"/api/rede/{rid}/controladores/importar", timeout=3600)
        assert r.status_code == 200, r.text[:2000]
        medida["importacao_de_controladores"] = r.json()

        # a subrede precisa estar atualizada: o diagrama é feito do que a atualização gravou
        with con.cursor() as cur:
            lote = subredes.atualizar_todas(cur, tenant_id, rid, todas=True, tier="media_tensao")
        con.commit()
        medida["atualizacao_da_subrede"] = {"candidatas": lote["candidatas"],
                                            "atualizadas": lote["atualizadas"],
                                            "elementos": lote["elementos"],
                                            "duracao_ms": lote["duracao_ms"]}
        assert lote["atualizadas"] >= 1, lote

        origem = {"tipo": "subrede", "subrede": alimentador, "tier": "media_tensao"}

        # --- cláusula 1: gerar o diagrama do alimentador em <= 10 s
        antes = _carga_da_maquina()
        with con.cursor() as cur:
            t0 = time.perf_counter()
            gerado = diagrama.gerar(cur, tenant_id, rid, "medida", origem, "basico", "arvore_inteligente")
            segundos = round(time.perf_counter() - t0, 3)
        con.commit()
        medida["geracao"] = {"segundos": segundos, "nos": gerado["resumo"]["nos"],
                             "arestas": gerado["resumo"]["arestas"],
                             "etapas_ms": gerado["resumo"]["duracao_ms"], **antes}
        medida["clausulas"]["gerar_um_alimentador_ate_10s"] = {
            "prova": f"diagrama do alimentador {alimentador} ({trechos_no_arquivo} trechos de média tensão no "
                     f"arquivo, 1 de 20): {gerado['resumo']['nos']} nós e {gerado['resumo']['arestas']} "
                     f"ligações gerados em {segundos} s (teto {SEGUNDOS_MAXIMO} s), com carga "
                     f"{antes['carga_1min']} e {antes['ram_livre_gb']} GB de RAM livre",
            "ok": segundos <= SEGUNDOS_MAXIMO}
        if antes["carga_1min"] > CARGA_MAXIMA_PARA_MEDIR:
            medida["avisos"].append(
                f"carga {antes['carga_1min']} acima de {CARGA_MAXIMA_PARA_MEDIR}: o tempo mede a máquina "
                "cheia, não o produto; o número fica registrado com a carga ao lado")

        # --- cláusula 2: os quatro layouts do portão, sem sobreposição, sobre a rede real
        por_layout = {}
        for layout in LAYOUTS_DO_PORTAO:
            carga = _carga_da_maquina()
            with con.cursor() as cur:
                t0 = time.perf_counter()
                r_layout = diagrama.reaplicar_layout(cur, rid, gerado["id"], layout)
                gasto = round(time.perf_counter() - t0, 3)
            con.commit()
            por_layout[layout] = {"segundos": gasto,
                                  "pares_sobrepostos": r_layout["resumo"]["pares_sobrepostos"],
                                  "menor_distancia_proxima": r_layout["resumo"]["menor_distancia_proxima"],
                                  **carga}
        medida["layouts"] = por_layout
        medida["clausulas"]["quatro_layouts_sem_sobreposicao"] = {
            "prova": "; ".join(
                f"{k}: {v['pares_sobrepostos']} par(es) a menos de 1 unidade em {v['segundos']} s"
                for k, v in por_layout.items()),
            "ok": all(v["pares_sobrepostos"] == 0 for v in por_layout.values())}

        # --- cláusulas 3 e 4: a redução encolhe o grafo e não parte a rede
        with con.cursor() as cur:
            diagrama.definir_modelo(cur, tenant_id, rid, "medida-reduz", "medida: só reduzir junção",
                                    [{"regra": "reduzir_juncao_de_passagem"}], "linha_principal")
            t0 = time.perf_counter()
            reduzido = diagrama.gerar(cur, tenant_id, rid, "medida reduzida", origem, "medida-reduz")
            segundos_reduzido = round(time.perf_counter() - t0, 3)
        con.commit()
        resumo = reduzido["resumo"]
        medida["reducao"] = {"segundos": segundos_reduzido, "bruto": resumo["bruto"],
                             "nos": resumo["nos"], "arestas": resumo["arestas"],
                             "componentes": resumo["componentes"], "regras": resumo["regras"]}
        medida["clausulas"]["reduzir_juncao_reduz_os_nos"] = {
            "prova": f"{resumo['bruto']['nos']} nós no grafo bruto e {resumo['nos']} depois da regra "
                     f"({resumo['regras'][0]['nos_removidos']} junções de passagem removidas)",
            "ok": resumo["nos"] < resumo["bruto"]["nos"]}
        medida["clausulas"]["reducao_preserva_a_conectividade"] = {
            "prova": f"{resumo['bruto']['componentes']} componente(s) conexo(s) no grafo bruto e "
                     f"{resumo['componentes']} no reduzido",
            "ok": resumo["componentes"] == resumo["bruto"]["componentes"]}

        medida["ok"] = all(c["ok"] for c in medida["clausulas"].values())
    finally:
        cliente.delete(f"/api/rede/{rid}", timeout=600)
        if con is not None:
            con.close()

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    registro = {
        "item": ITEM,
        "assinado_por": "redes+frontend+backend+cartografo+adversario (trilha il404ddiagr)",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "maquina": "PostgreSQL 16 em iagro_sat; base própria da trilha "
                   f"({os.environ.get('PLAT_SCHEMA', '?')}); fonte = BDGD da cooperativa de teste (ativo da "
                   "casa, somente leitura); outras sessões da casa na mesma máquina",
        "medidas": medida,
        "comando": "venv/bin/pytest tests/api/test_rede_diagrama_medida.py -m lento -q",
    }
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert medida["ok"], medida["clausulas"]
