"""Medição em escala REAL do item L4-04-c-sumarios-por-subrede (marcador `lento`).

É a cláusula central do portão: para a cooperativa de teste, o quilômetro de média tensão de cada
alimentador tem de bater com a soma do comprimento que o arquivo declara (± 0,1 %) e o número de unidades
consumidoras de baixa tensão tem de ser a contagem do arquivo, nos 20 alimentadores — conferido contra as
tabelas do ativo de referência por um caminho INDEPENDENTE (`tests/dados/carga_bdgd_uc.py`, que só lê o
schema do arquivo e nunca `plat.*`).

Vai junto a conferência que o adversário pediu: nenhuma unidade consumidora contada em dois alimentadores.
A soma das unidades dos 20 sumários tem de ser exatamente o total do arquivo.

⛔ O nome do schema do ativo vem de `PLAT_REDE_REFERENCIA_ESQUEMA`; sem a variável a medição é pulada.
⛔ Esta medição NÃO constrói a topologia (600 s medidos no item L4-01-b, contra 10 min de relógio da
rodada). As subredes dos 20 alimentadores são registradas direto em `plat.rede_subrede`, que é o que o
sumário consome; sem controlador, a coluna do tronco fica nula com `tronco_origem='sem_controlador'` — o
tronco medido pela topologia está provado no teste rápido `test_rede_subredes_resumo.py`.

Tudo que este teste mede vai para `tests/medidas/L4-04-c-sumarios-por-subrede.json`."""

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd_uc

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-04-c-sumarios-por-subrede.json"
TOLERANCIA_KM_PCT = 0.1


def _conectar(env, tenant_id, usuario_id):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "medida-l404c"),
        )
    return con


def _registrar_subredes(cur, tenant_id: int, rede_id: str) -> int:
    """Uma subrede por alimentador do arquivo, no tier de média tensão — o mesmo nome que
    `controladores.marcar_da_importacao` daria (o código do alimentador), sem exigir a topologia."""
    cur.execute(
        "SELECT id FROM plat.rede_tier WHERE rede_id = %s::uuid AND codigo = 'media_tensao'", (rede_id,))
    tier_id = str(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO plat.rede_subrede(tenant_id, rede_id, tier_id, nome) "
        "SELECT %s, %s::uuid, %s::uuid, f.atributos->>'ctmt' FROM plat.rede_feicao_linha f "
        "WHERE f.rede_id = %s::uuid AND f.atributos->>'ctmt' IS NOT NULL "
        "GROUP BY f.atributos->>'ctmt' "
        "ON CONFLICT (rede_id, tier_id, nome) DO NOTHING",
        (tenant_id, rede_id, tier_id, rede_id),
    )
    cur.execute("SELECT count(*) AS n FROM plat.rede_subrede WHERE rede_id = %s::uuid", (rede_id,))
    return cur.fetchone()["n"]


@pytest.mark.lento
def test_medida_sumario_por_subrede_escala_real(cred, env):
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    ids = ids_por_slug(con)
    con.close()
    tenant_id, usuario_id = ids["demo"], eu["id"]

    r = cliente.post("/api/rede", json={"nome": "zt-medida-resumo-real", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    medida = {"rede_id": rid, "clausulas": {}, "avisos": []}
    con = None
    try:
        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text

        con = _conectar(env, tenant_id, usuario_id)
        try:
            with con.cursor() as cur:
                cron = carga_bdgd_uc.carregar_media_tensao_e_trafos(cur, tenant_id, rid)
                cron.update(carga_bdgd_uc.carregar_consumo_e_geracao(cur, tenant_id, rid))
                arquivo = carga_bdgd_uc.totais_arquivo(cur)
                declarados = carga_bdgd_uc.esperado_por_ctmt(cur)
                subredes = _registrar_subredes(cur, tenant_id, rid)
            con.commit()
        except Exception:
            con.rollback()
            raise

        medida["carga"] = cron
        medida["arquivo"] = arquivo
        # Um dos alimentadores declarados na camada CTMT não tem NENHUM trecho de média tensão no
        # arquivo (medido: 21 linhas em CTMT, 20 códigos distintos em SSDMT). Sem trecho não há subrede a
        # registrar nem o que somar; fica anotado, não escondido.
        sem_trecho = sorted(c for c, v in declarados.items() if v["ssdmt"] == 0)
        esperado = {c: v for c, v in declarados.items() if v["ssdmt"] > 0}
        medida["subredes_registradas"] = subredes
        medida["alimentadores_declarados_sem_trecho"] = sem_trecho
        medida["avisos"].append(
            f"{len(sem_trecho)} alimentador(es) da camada CTMT sem trecho de média tensão no arquivo: "
            f"{', '.join(sem_trecho) if sem_trecho else 'nenhum'}")
        assert subredes == len(esperado) == 20, (subredes, len(esperado), arquivo)
        for rotulo in ("ssdmt", "trafo", "ucbt", "ugbt"):
            assert cron[rotulo]["linhas"] == arquivo[rotulo], (rotulo, cron[rotulo], arquivo[rotulo])

        # A CLÁUSULA: o cálculo pela API, em tempo medido
        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/subredes/resumos/calcular", timeout=1800)
        medida["calcular_http_segundos"] = round(time.perf_counter() - t0, 3)
        assert r.status_code == 200, r.text[:2000]
        contagem = r.json()
        medida["calculo"] = contagem
        assert contagem["calculadas"] == 20, contagem

        r = cliente.get(f"/api/rede/{rid}/subredes/resumos", params={"limite": 100}, timeout=300)
        assert r.status_code == 200, r.text[:2000]
        tabela = r.json()
        linhas = {i["subrede"]: i for i in tabela["itens"]}
        assert set(linhas) == set(esperado), (sorted(linhas), sorted(esperado))

        # 1) km de média tensão por alimentador = soma do comprimento declarado, dentro de 0,1 %
        piores, por_ctmt = [], {}
        for ctmt, alvo in esperado.items():
            calculado_m = (linhas[ctmt]["km_por_nivel"].get("trecho_de_media_tensao") or 0.0) * 1000.0
            declarado_m = alvo["comp_m"]
            desvio = abs(calculado_m - declarado_m) / declarado_m * 100.0 if declarado_m else 0.0
            por_ctmt[ctmt] = {"arquivo_comp_m": round(declarado_m, 3),
                              "sumario_m": round(calculado_m, 3), "desvio_pct": round(desvio, 6),
                              "arquivo_ucbt": alvo["ucbt"], "sumario_ucs": linhas[ctmt]["ucs"]}
            if desvio > TOLERANCIA_KM_PCT:
                piores.append(por_ctmt[ctmt])
        medida["por_ctmt"] = por_ctmt
        medida["clausulas"]["km_mt_por_ctmt"] = {
            "prova": f"20 alimentadores; maior desvio "
                     f"{max(v['desvio_pct'] for v in por_ctmt.values()):.6f} % contra a soma de COMP do "
                     f"arquivo (tolerância {TOLERANCIA_KM_PCT} %)",
            "ok": not piores}
        assert not piores, piores

        # 2) unidades consumidoras de baixa tensão por alimentador = contagem do arquivo
        divergentes = {c: (v["arquivo_ucbt"], v["sumario_ucs"]) for c, v in por_ctmt.items()
                       if v["arquivo_ucbt"] != v["sumario_ucs"]}
        medida["clausulas"]["ucbt_por_ctmt"] = {
            "prova": f"20 alimentadores, contagem idêntica ao arquivo; divergentes: {len(divergentes)}",
            "ok": not divergentes}
        assert not divergentes, divergentes

        # 3) refutação do adversário: nenhuma unidade consumidora contada em dois alimentadores
        soma_ucs = sum(i["ucs"] for i in tabela["itens"])
        medida["clausulas"]["sem_uc_em_dois_alimentadores"] = {
            "prova": f"soma das unidades dos 20 sumários = {soma_ucs}; total no arquivo = "
                     f"{arquivo['ucbt']} (dupla contagem apareceria como soma maior)",
            "ok": soma_ucs == arquivo["ucbt"]}
        assert soma_ucs == arquivo["ucbt"], (soma_ucs, arquivo["ucbt"])

        # 4) as demais grandezas do sumário, conferidas contra o arquivo do mesmo modo
        outras = {}
        for ctmt, alvo in esperado.items():
            linha = linhas[ctmt]
            outras[ctmt] = {
                "trafos": (alvo["trafos"], linha["trafos"]),
                "kva": (round(alvo["kva"], 3), round(linha["kva_instalado"] or 0.0, 3)),
                "ugbt": (alvo["ugbt"], linha["gd_unidades"]),
                "energia": (round(alvo["ene"], 3), round(linha["energia_anual_kwh"] or 0.0, 3)),
            }
        erradas = {c: v for c, v in outras.items()
                   if any(abs(a - b) > 0.01 if isinstance(a, float) else a != b for a, b in v.values())}
        medida["clausulas"]["trafos_kva_gd_energia"] = {
            "prova": f"transformadores, kVA, gerações e energia anual conferidos nos 20 alimentadores; "
                     f"divergentes: {len(erradas)}",
            "ok": not erradas}
        assert not erradas, erradas

        # 5) divergência entre o comprimento declarado e o da geometria: medida e guardada, não escondida
        medida["divergencia_declarado_geometria_pct"] = {
            c: round(linhas[c]["divergencia_pct"], 4) for c in sorted(linhas)}

        # 6) exportação CSV: uma linha por subrede, com o mesmo número
        r = cliente.get(f"/api/rede/{rid}/subredes/resumos",
                        params={"formato": "csv", "limite": 100}, timeout=300)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), r.status_code
        linhas_csv = [linha for linha in r.text.split("\n") if linha]
        medida["clausulas"]["csv"] = {
            "prova": f"{len(linhas_csv) - 1} linhas de dado + cabeçalho, {len(tabela['colunas'])} colunas",
            "ok": len(linhas_csv) == 21}
        assert len(linhas_csv) == 21, len(linhas_csv)

        medida["ok"] = all(c["ok"] for c in medida["clausulas"].values())
    finally:
        cliente.delete(f"/api/rede/{rid}", timeout=600)
        if con is not None:
            con.close()

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    registro = {
        "item": "L4-04-c-sumarios-por-subrede",
        "assinado_por": "redes+backend+testador (trilha il404csumar)",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "maquina": "PostgreSQL 16 em iagro_sat; base própria da trilha "
                   f"({os.environ.get('PLAT_SCHEMA', '?')}); fonte = schema do ativo de rede de "
                   "referência (BDGD, ativo da casa, somente leitura); outras sessões da casa na mesma "
                   "máquina",
        "medidas": medida,
        "comando": "bash /home/dev/plataforma/laco/roda_teste.sh "
                   "tests/api/test_rede_subredes_resumo_medida.py -m lento -q "
                   "(exige PLAT_REDE_REFERENCIA_ESQUEMA e GRANT de leitura no schema do ativo)",
    }
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert medida["ok"], medida["clausulas"]
