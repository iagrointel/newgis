"""Medição em escala REAL do item L4-01-b-topologia-derivada (marcador `lento`: fora do pytest do dia a dia).

É a cláusula central do portão: `POST /api/rede/{id}/topologia/habilitar` constrói a topologia da rede da
cooperativa de teste — os 44.268 trechos de MT + 29.244 de BT + 26.581 ramais + 5.481 transformadores +
60.549 postes do arquivo BDGD (schema `certaja`, ativo da casa, somente leitura) — em tempo medido, e a
contagem de nós/arestas/órfãos/sem-nó gravada em `plat.rede_topo_resumo` é conferida CONTRA O ARQUIVO
(SSDMT × CTMT × UNTRMT), por um contador INDEPENDENTE (`tests/dados/carga_bdgd.py`: Python puro sobre o wkt
cru, nunca reconsultando as tabelas que o construtor gravou).

⛔ Exige o GRANT de leitura do ativo para o papel da trilha (registrado no handoff do item):
  GRANT USAGE ON SCHEMA certaja TO <papel>; GRANT SELECT ON certaja.ssdmt, ssdbt, ramlig, trafo, ponnot,
  ctmt, eqtrmt TO <papel>;

Tudo que este teste mede vai para `tests/medidas/L4-01-b-topologia-derivada.json` (reescreve o arquivo a
cada rodada — ele é o registro vivo da medição, não um cache).

⛔ FRONTEIRA DECLARADA (achada ao medir, não um defeito de código): `certaja.ramlig` tem os 26.581
registros do arquivo, mas 0 de 26.581 têm a coluna `wkt` preenchida (ver docstring de
`tests/dados/carga_bdgd.py`). O ramal de ligação não tem geometria armazenada nesta extração BDGD —
carregá-lo como aresta exigiria fabricar uma linha que o arquivo não tem. Este teste mede a topologia
geométrica sobre o que TEM geometria real (MT + BT + transformador + poste = 139.542 elementos) e
confere separadamente que ramlig existe no arquivo (26.581) mas contribui ZERO arestas geométricas —
essa contagem zero é a prova da fronteira, não uma falha.
"""

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
from tests.dados import carga_bdgd

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-01-b-topologia-derivada.json"


def _conectar(env, tenant_id, usuario_id):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        # is_local=false (sessão, não transação): a medição dá COMMIT depois da carga e as conferências
        # seguintes continuam precisando do contexto de RLS
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "medida-l401b"),
        )
    return con


@pytest.mark.lento
def test_medida_topologia_escala_real(cred, env):
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    ids = ids_por_slug(con)
    con.close()
    tenant_id = ids["demo"]
    usuario_id = eu["id"]

    # 1) a rede do inquilino de teste, com o pacote eletrica-br importado (mesmo caminho dos testes rápidos)
    r = cliente.post("/api/rede", json={"nome": "zt-medida-topo-real", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    medida = {"rede_id": rid, "clausulas": {}, "avisos": []}
    con = None
    try:
        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text

        # 2) a carga do arquivo BDGD nas camadas de rede (RLS valendo: a carga vai como o inquilino)
        con = _conectar(env, tenant_id, usuario_id)
        try:
            with con.cursor() as cur:
                cron = carga_bdgd.carregar(cur, tenant_id, rid)
                arquivo = carga_bdgd.contagens_arquivo(cur)
            con.commit()
        except Exception:
            con.rollback()
            raise

        assert arquivo["ssdmt"] == 44_268 and arquivo["ssdbt"] == 29_244, arquivo
        assert arquivo["ramlig"] == 26_581 and arquivo["trafo"] == 5_481 and arquivo["ponnot"] == 60_549, arquivo
        # ramlig fica de fora desta lista: 0 dos 26.581 registros têm wkt (fronteira declarada acima),
        # logo a carga geométrica dele é 0 arestas — não os 26.581 do arquivo.
        for rotulo, esperado in (("ssdmt", 44_268), ("ssdbt", 29_244),
                                 ("trafo", 5_481), ("ponnot", 60_549)):
            assert cron[rotulo]["linhas"] == esperado, (rotulo, cron[rotulo])
        assert cron["ramlig"]["linhas"] == 0, cron["ramlig"]
        medida["carga"] = cron
        medida["arquivo"] = arquivo
        medida["clausulas"]["ramlig_sem_geometria"] = {
            "prova": f"{arquivo['ramlig']} registros no arquivo, {cron['ramlig']['linhas']} com geometria "
                     "(wkt nulo em 100%) -> 0 arestas carregadas, fronteira do ativo, não fabricado",
            "ok": True}

        # 3) A CLÁUSULA: habilitar pela API, em tempo medido (duracao_ms medido no servidor, por
        # perf_counter dentro do construtor — não inclui rede nem fila do cliente)
        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        medida["habilitar_http_segundos"] = round(time.perf_counter() - t0, 3)
        assert r.status_code == 201, r.text[:2000]
        resumo = r.json()
        medida["resumo"] = resumo

        # ramlig fica de fora da soma: 0 arestas geométricas (fronteira declarada acima). A cláusula
        # central do portão (contagem de arestas == arquivo) vale sobre o que TEM geometria real.
        total_linhas = arquivo["ssdmt"] + arquivo["ssdbt"]
        assert resumo["arestas"] == total_linhas, resumo
        medida["clausulas"]["arestas_igual_arquivo"] = {
            "prova": f"resumo.arestas {resumo['arestas']} == ssdmt+ssdbt {total_linhas} "
                     f"(ramlig fica fora: {arquivo['ramlig']} no arquivo, 0 com geometria)", "ok": True}

        # 4) conferência contra o arquivo, por caminho independente
        with con.cursor() as cur:
            # 4a) arestas por grupo == contagens do arquivo (SSDMT, SSDBT uma a uma; RAMLIG == 0)
            cur.execute(
                "SELECT g.codigo, count(*) AS n FROM plat.rede_topo_aresta a "
                "JOIN plat.rede_grupo g ON g.id = a.grupo_id WHERE a.rede_id = %s::uuid GROUP BY 1",
                (rid,))
            por_grupo = {r["codigo"]: r["n"] for r in cur.fetchall()}
        esperado_grupo = {"trecho_de_media_tensao": arquivo["ssdmt"],
                          "trecho_de_baixa_tensao": arquivo["ssdbt"]}
        assert por_grupo == esperado_grupo, (por_grupo, esperado_grupo)
        assert "ramal_de_ligacao" not in por_grupo, por_grupo  # 0 arestas -> nem aparece no GROUP BY
        medida["arestas_por_grupo"] = por_grupo

        # 4b) os 60.549 postes (sem_terminal) deram ZERO nó
        with con.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_topo_no n WHERE n.rede_id = %s::uuid AND n.papel = 'terminal' "
                "AND n.tipo_id = (SELECT tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
                " WHERE tp.rede_id = %s::uuid AND g.codigo = 'ponto_notavel' AND tp.codigo = 1)",
                (rid, rid))
            nos_poste = cur.fetchone()["n"]
        assert nos_poste == 0, nos_poste
        medida["clausulas"]["postes_zero_no"] = {"prova": f"{arquivo['ponnot']} postes -> {nos_poste} nós",
                                                 "ok": True}

        # 4c) MT: nós, fins de linha (grau 1) e componentes por alimentador — construído x arquivo
        t0 = time.perf_counter()
        with con.cursor() as cur:
            esperado = carga_bdgd.esperado_mt(cur, resumo["tolerancia_m"])
        medida["esperado_mt_segundos"] = round(time.perf_counter() - t0, 3)
        with con.cursor() as cur:
            cur.execute(
                "SELECT a.no_origem_id::text AS o, a.no_destino_id::text AS d, a.atributos->>'ctmt' AS ctmt "
                "FROM plat.rede_topo_aresta a JOIN plat.rede_grupo g ON g.id = a.grupo_id "
                "WHERE a.rede_id = %s::uuid AND g.codigo = 'trecho_de_media_tensao' "
                "AND a.no_origem_id IS NOT NULL",
                (rid,))
            arestas_mt = cur.fetchall()

        grau = {}
        pai = {}

        def achar(x):
            pai.setdefault(x, x)
            while pai[x] != x:
                pai[x] = pai[pai[x]]
                x = pai[x]
            return x

        nos_mt = set()
        for a in arestas_mt:
            nos_mt.add(a["o"])
            nos_mt.add(a["d"])
            grau[a["o"]] = grau.get(a["o"], 0) + 1
            grau[a["d"]] = grau.get(a["d"], 0) + 1
            ra, rb = achar(a["o"]), achar(a["d"])
            if ra != rb:
                pai[rb] = ra
        fins_topo = sum(1 for n in nos_mt if grau[n] == 1)
        medida["mt"] = {
            "arquivo": {"nos": esperado["nos"], "fins_de_linha_grau1": esperado["fins_de_linha_grau1"],
                        "alimentadores": esperado["alimentadores"]},
            "construido": {"nos": len(nos_mt), "fins_de_linha_grau1": fins_topo},
        }
        assert len(nos_mt) == esperado["nos"], (len(nos_mt), esperado["nos"])
        delta_fins = abs(fins_topo - esperado["fins_de_linha_grau1"])
        medida["clausulas"]["fins_de_linha_mt"] = {
            "prova": f"grau 1 na topologia {fins_topo} x esperado pelo arquivo {esperado['fins_de_linha_grau1']} "
                     f"(delta {delta_fins}; o contador independente usa equiretangular local, o construtor usa "
                     "ST_DWithin geodésico — divergência só pode vir de par de pontas a ~0,05 m exatos)",
            "ok": delta_fins == 0}
        assert delta_fins == 0, medida["clausulas"]["fins_de_linha_mt"]

        # componentes por alimentador: a junção SSDMT x CTMT — todo alimentador do arquivo tem de dar UMA
        # componente conexa na topologia (rede radial); o que divergir é medido e declarado, nunca escondido
        comp_topo = {}
        por_ctmt_topo = {}
        for a in arestas_mt:
            por_ctmt_topo.setdefault(a["ctmt"], []).append((a["o"], a["d"]))
        for ctmt, arestas in por_ctmt_topo.items():
            p2 = {}

            def achar2(x, p2=p2):  # p2 como argumento padrão: evita B023 (closure sobre variável de laço)
                p2.setdefault(x, x)
                while p2[x] != x:
                    p2[x] = p2[p2[x]]
                    x = p2[x]
                return x

            nos2 = set()
            for o, d in arestas:
                nos2.add(o)
                nos2.add(d)
                ro, rd = achar2(o), achar2(d)
                if ro != rd:
                    p2[rd] = ro
            comp_topo[ctmt] = len({achar2(n) for n in nos2})
        divergentes = {c: {"arquivo": esperado["componentes_por_ctmt"].get(c), "topologia": t}
                       for c, t in comp_topo.items()
                       if esperado["componentes_por_ctmt"].get(c) != t}
        medida["mt"]["componentes_por_ctmt_arquivo"] = esperado["componentes_por_ctmt"]
        medida["mt"]["componentes_por_ctmt_topologia"] = comp_topo
        medida["mt"]["componentes_divergentes"] = divergentes
        assert not divergentes, divergentes
        medida["clausulas"]["componentes_por_ctmt"] = {
            "prova": f"{len(comp_topo)} alimentadores, componentes idênticas arquivo x topologia", "ok": True}

        # 4d) UNTRMT: terminais de ALTA órfãos na topologia == transformadores sem ponta de MT no arquivo
        with con.cursor() as cur:
            orfaos_alta_esperados = carga_bdgd.esperado_orfaos_alta(cur, resumo["tolerancia_m"])
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_topo_no n "
                "WHERE n.rede_id = %s::uuid AND n.papel = 'terminal' AND n.terminal_num = 1 "
                "AND NOT EXISTS (SELECT 1 FROM plat.rede_topo_aresta a "
                " WHERE a.no_origem_id = n.id OR a.no_destino_id = n.id)",
                (rid,))
            orfaos_alta_topo = cur.fetchone()["n"]
        medida["mt"]["orfaos_alta"] = {"arquivo": orfaos_alta_esperados, "topologia": orfaos_alta_topo}
        medida["clausulas"]["orfaos_alta_untrmt"] = {
            "prova": f"terminais de alta órfãos: topologia {orfaos_alta_topo} x arquivo {orfaos_alta_esperados}",
            "ok": orfaos_alta_topo == orfaos_alta_esperados}
        assert orfaos_alta_topo == orfaos_alta_esperados

        # 5) o resumo gravado no banco é exatamente o que a API devolveu (plat.rede_topo_resumo é a ficha
        # da construção — cláusula "contagem gravada em plat.rede_topo_resumo")
        with con.cursor() as cur:
            cur.execute(
                "SELECT nos, arestas, nos_orfaos, arestas_sem_no, duracao_ms, tolerancia_m "
                "FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rid,))
            gravado = cur.fetchone()
        assert gravado["nos"] == resumo["nos"] and gravado["arestas"] == resumo["arestas"]
        assert gravado["nos_orfaos"] == resumo["nos_orfaos"]
        assert gravado["arestas_sem_no"] == resumo["arestas_sem_no"]
        assert gravado["duracao_ms"] == resumo["duracao_ms"]
        medida["clausulas"]["resumo_gravado"] = {
            "prova": f"rede_topo_resumo: nós {gravado['nos']}, arestas {gravado['arestas']}, "
                     f"órfãos {gravado['nos_orfaos']}, sem nó {gravado['arestas_sem_no']}, "
                     f"{gravado['duracao_ms']} ms", "ok": True}

        medida["ok"] = all(c["ok"] for c in medida["clausulas"].values())
    finally:
        cliente.delete(f"/api/rede/{rid}", timeout=600)
        if con is not None:
            con.close()

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    registro = {
        "item": "L4-01-b-topologia-derivada",
        "assinado_por": "redes+dados+backend+testador (trilha il401btopol)",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "maquina": "PostgreSQL 16 em iagro_sat; base própria da trilha "
                   f"({os.environ.get('PLAT_SCHEMA', '?')}); fonte = schema certaja (BDGD, ativo da casa, "
                   "somente leitura); outras sessões da casa na mesma máquina",
        "medidas": medida,
        "comando": "venv/bin/pytest tests/api/test_rede_topologia_medida.py -m lento -q "
                   "(exige GRANT de leitura em certaja.* para o papel da trilha — ver docstring)",
    }
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert medida["ok"], medida["clausulas"]
