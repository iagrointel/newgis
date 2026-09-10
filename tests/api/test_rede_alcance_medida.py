"""Medida do ALCANCE do traçado no ativo de referência (item L4-01-f-alcance-do-tracado-rede-real).

Cláusulas do portão medidas aqui:
  1. pelo menos 95 % dos transformadores de CADA alimentador alcançados a jusante do controlador;
  2. os órfãos que sobram, listados por classe, com contagem, distância e exemplo;
  3. nenhum laço novo no tier de média tensão.

Como as três são medidas na MESMA carga, duas vezes: uma com a tolerância declarada por par de tipos (o
conserto deste item) e outra com essa declaração apagada (o estado anterior). A comparação é o resultado —
alcance sobe, número de laços não. Sem o "antes" no mesmo dado, "não fabricou laço" não seria uma medida.

⛔ O ativo vem de `PLAT_REDE_REFERENCIA_ESQUEMA`; sem a variável a medida é pulada com essa razão.
⛔ O recorte é por ORÇAMENTO DE RELÓGIO, declarado: os alimentadores entram em ordem crescente de número de
trechos até `ORCAMENTO_TRECHOS`. Quantos entraram, e quantos transformadores, fica gravado na medida — a
cláusula vale para os alimentadores medidos, não para os 16 do arquivo.
⛔ O código do alimentador traz a sigla da distribuidora: no arquivo de medidas os alimentadores aparecem
numerados por tamanho, nunca pelo código.

Saída: `tests/medidas/L4-01-f-alcance-do-tracado-rede-real.json`."""

import json
import os
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE, entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados.carga_bdgd import esquema

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-01-f-alcance-do-tracado-rede-real.json"
ORCAMENTO_TRECHOS = 12_000   # o que cabe no relógio de uma rodada com DUAS construções de topologia
ALVO_ALCANCE = 0.95
TOLERANCIA_M = 0.05          # a tolerância padrão do produto: não muda: quem muda é a do par de tipos


def _carga_maquina() -> dict:
    livre = None
    try:
        with open("/proc/meminfo") as f:
            for linha in f:
                if linha.startswith("MemAvailable"):
                    livre = round(int(linha.split()[1]) / 1024 / 1024, 2)
    except OSError:
        pass
    return {"carga_1min": round(os.getloadavg()[0], 2), "ram_livre_gb": livre,
            "medido_em": time.strftime("%Y-%m-%dT%H:%M:%S")}


def _conectar(env, tenant_id, usuario_id):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "medida-l401f"),
        )
    return con


def _tipo(cur, rede_id: str, grupo: str, codigo: int) -> str:
    cur.execute(
        "SELECT tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s AND tp.codigo = %s",
        (rede_id, grupo, codigo),
    )
    return str(cur.fetchone()["id"])


def _escolher_alimentadores(cur) -> list[dict]:
    """Alimentadores com transformador, em ordem crescente de trechos, até o orçamento de relógio."""
    esq = esquema()
    cur.execute(
        f"SELECT s.ctmt, count(*) AS trechos, "
        f"       (SELECT count(*) FROM {esq}.trafo t WHERE t.ctmt = s.ctmt) AS trafos, "
        f"       (SELECT coalesce(sum(t.pot_nom), 0) FROM {esq}.trafo t WHERE t.ctmt = s.ctmt) AS kva "
        f"FROM {esq}.ssdmt s WHERE s.wkt IS NOT NULL GROUP BY 1 ORDER BY 2"
    )
    escolhidos, soma = [], 0
    for r in cur.fetchall():
        if r["trafos"] == 0:
            continue
        if soma + r["trechos"] > ORCAMENTO_TRECHOS and escolhidos:
            break
        escolhidos.append(dict(r))
        soma += r["trechos"]
    if not escolhidos:
        pytest.skip("o ativo de referência não tem alimentador com transformador")
    return escolhidos


def _carregar(cur, tenant_id: int, rede_id: str, ctmts: list[str]) -> dict:
    """Mesmo recorte de `test_rede_config_tracado_medida`, para vários alimentadores: trechos de média
    tensão e transformadores. Baixa tensão, ramal e poste ficam de fora — o alcance que este item mede é o
    do tier de média tensão, e carregar o resto só gastaria relógio."""
    esq = esquema()
    cron = {}
    fase = ("(CASE WHEN fas_con ILIKE '%%A%%' THEN 1 ELSE 0 END) + "
            "(CASE WHEN fas_con ILIKE '%%B%%' THEN 2 ELSE 0 END) + "
            "(CASE WHEN fas_con ILIKE '%%C%%' THEN 4 ELSE 0 END)")

    def rodar(rotulo, sql, params):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        cron[rotulo] = {"linhas": cur.fetchone()["n"], "segundos": round(time.perf_counter() - t0, 3)}

    rodar("ssdmt", f"""
        WITH carga AS (
          INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos)
          SELECT %s, %s::uuid, %s::uuid, ST_GeometryN(ST_GeomFromText(wkt, 4326), 1), {fase},
                 jsonb_build_object('cod_id', cod_id, 'ctmt', ctmt, 'sub', sub, 'fas_con', fas_con,
                                    'comp', comp)
          FROM {esq}.ssdmt WHERE wkt IS NOT NULL AND ctmt = ANY(%s)
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "trecho_de_media_tensao", 1), ctmts))

    rodar("trafo", f"""
        WITH carga AS (
          INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos)
          SELECT %s, %s::uuid, %s::uuid, ST_SetSRID(ST_MakePoint(x, y), 4326),
                 jsonb_build_object('cod_id', cod_id, 'pot_nom', pot_nom, 'ctmt', ctmt)
          FROM {esq}.trafo WHERE ctmt = ANY(%s)
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "transformador_de_distribuicao", 1), ctmts))
    return cron


def _apagar_tolerancia_do_par(env, tenant_id, usuario_id, rede_id) -> int:
    con = _conectar(env, tenant_id, usuario_id)
    try:
        with con.cursor() as cur:
            cur.execute("UPDATE plat.rede_regra SET tolerancia_m = NULL WHERE rede_id = %s::uuid", (rede_id,))
            n = cur.rowcount
        con.commit()
        return n
    finally:
        con.close()


def _nova_rede(cliente, sufixo: str) -> str:
    r = cliente.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-alcance-{sufixo}",
                                        "disciplina": "eletrica", "tolerancia_m": TOLERANCIA_M})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    from app.rede_utilidades import instalados

    r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                     headers={"Content-Type": "application/json"}, timeout=300)
    assert r.status_code == 201, r.text
    return rid


def _medir_alimentador(cliente, env, tenant_id, usuario_id, al: dict, ordem: int,
                       com_tolerancia_do_par: bool) -> dict:
    """Mede UM alimentador na SUA PRÓPRIA rede. Separado de propósito: com vários alimentadores carregados
    juntos, as geometrias de saída da subestação se encostam, a malha de média tensão ganha laço e o traçado
    passa a recusar arbitrar sentido — o que se mede aqui é o alcance DENTRO do alimentador. O efeito da
    carga conjunta fica medido à parte, em `observacao_carga_conjunta`."""
    rid = _nova_rede(cliente, f"{ordem}-{'par' if com_tolerancia_do_par else 'rede'}")
    linha = {"alimentador": ordem, "trechos_no_arquivo": al["trechos"], "trafos_no_arquivo": al["trafos"],
             "kva_no_arquivo": round(float(al["kva"]), 2)}
    try:
        if not com_tolerancia_do_par:
            _apagar_tolerancia_do_par(env, tenant_id, usuario_id, rid)
        con = _conectar(env, tenant_id, usuario_id)
        try:
            with con.cursor() as cur:
                _carregar(cur, tenant_id, rid, [al["ctmt"]])
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=900)
        assert r.status_code == 201, r.text
        resumo = r.json()
        linha["topologia"] = {"nos": resumo["nos"], "arestas": resumo["arestas"],
                              "nos_orfaos": resumo["nos_orfaos"],
                              "segundos": round(time.perf_counter() - t0, 2)}

        r = cliente.post(f"/api/rede/{rid}/controladores/importar", timeout=900)
        assert r.status_code == 200, r.text
        r = cliente.get(f"/api/rede/{rid}/controladores?limite=200")
        assert r.status_code == 200, r.text
        cab = next((c for c in r.json()["itens"] if c["tier"] == "media_tensao"), None)

        r = cliente.post(f"/api/rede/{rid}/tracar", json={"tipo": "lacos"}, timeout=900)
        assert r.status_code == 200, r.text
        linha["lacos_na_media_tensao"] = r.json()["contagem"]

        r = cliente.get(f"/api/rede/{rid}/topologia/diagnostico?limiar_m=1.0&exemplos=1")
        assert r.status_code == 200, r.text
        linha["classes_de_orfao"] = r.json()["classes"]

        if cab is None:
            linha["estado"] = "sem_controlador"
            return linha
        r = cliente.get(f"/api/rede/{rid}/config_tracado?limite=100")
        assert r.status_code == 200, r.text
        config_id = {c["codigo"]: c for c in r.json()["itens"]}["kva_a_jusante"]["id"]
        r = cliente.post(f"/api/rede/{rid}/tracar", timeout=900, json={
            "config_id": config_id, "pontos_partida": [{"lon": cab["lon"], "lat": cab["lat"]}]})
        assert r.status_code == 200, r.text
        saida = r.json()
        linha["direcao"] = saida.get("direcao")
        if saida.get("direcao") == "indeterminado":
            linha["estado"] = "indeterminado"
            linha["motivo"] = saida.get("motivo")
            return linha
        ids = [e["feicao_id"] for e in saida["elementos"]]
        con = _conectar(env, tenant_id, usuario_id)
        try:
            with con.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n, coalesce(sum((atributos->>'pot_nom')::double precision), 0) AS kva "
                    "FROM plat.rede_feicao_ponto WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[]) "
                    "AND atributos ? 'pot_nom'", (rid, ids))
                achou = cur.fetchone()
        finally:
            con.close()
        linha["trafos_alcancados"] = achou["n"]
        linha["kva_alcancado"] = round(float(achou["kva"]), 2)
        linha["alcance_pct"] = round(100.0 * achou["n"] / al["trafos"], 2) if al["trafos"] else None
        linha["estado"] = "medido"
        return linha
    finally:
        cliente.delete(f"/api/rede/{rid}")


def _resumir(linhas: list[dict]) -> dict:
    medidos = [x for x in linhas if x["estado"] == "medido"]
    return {
        "alimentadores": linhas,
        "alimentadores_medidos": len(medidos),
        "alimentadores_indeterminados": sum(1 for x in linhas if x["estado"] == "indeterminado"),
        "trafos_no_arquivo": sum(x["trafos_no_arquivo"] for x in medidos),
        "trafos_alcancados": sum(x["trafos_alcancados"] for x in medidos),
        "pior_alcance_pct": min([x["alcance_pct"] for x in medidos], default=None),
        "alimentadores_acima_do_alvo": sum(1 for x in medidos if x["alcance_pct"] >= ALVO_ALCANCE * 100),
        "lacos_na_media_tensao": sum(x["lacos_na_media_tensao"] for x in linhas),
        "nos_orfaos": sum(x["topologia"]["nos_orfaos"] for x in linhas if "topologia" in x),
        "classes_de_orfao": sorted({c["classe"] for x in linhas for c in x.get("classes_de_orfao", [])}),
    }


def _alcance(cliente, env, tenant_id, usuario_id, rid, alimentadores, config_id) -> dict:
    """Constrói a topologia, marca os controladores, traça a jusante de cada alimentador e conta quantos
    transformadores DAQUELE alimentador o traçado alcançou. Devolve tudo que a medida grava."""
    t0 = time.perf_counter()
    r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=900)
    assert r.status_code == 201, r.text
    topologia = {**r.json(), "segundos": round(time.perf_counter() - t0, 1)}

    r = cliente.post(f"/api/rede/{rid}/controladores/importar", timeout=900)
    assert r.status_code == 200, r.text
    controladores = r.json()

    r = cliente.get(f"/api/rede/{rid}/controladores?limite=200")
    assert r.status_code == 200, r.text
    por_nome = {c["nome"]: c for c in r.json()["itens"] if c["tier"] == "media_tensao"}

    con = _conectar(env, tenant_id, usuario_id)
    resultados = []
    try:
        for i, al in enumerate(alimentadores, start=1):
            cab = por_nome.get(al["ctmt"])
            linha = {"alimentador": i, "trechos_no_arquivo": al["trechos"],
                     "trafos_no_arquivo": al["trafos"], "controlador": bool(cab)}
            if cab is None:
                linha["estado"] = "sem_controlador"
                resultados.append(linha)
                continue
            t1 = time.perf_counter()
            r = cliente.post(f"/api/rede/{rid}/tracar", timeout=900, json={
                "config_id": config_id, "pontos_partida": [{"lon": cab["lon"], "lat": cab["lat"]}]})
            assert r.status_code == 200, r.text
            saida = r.json()
            linha["segundos"] = round(time.perf_counter() - t1, 2)
            linha["direcao"] = saida.get("direcao")
            if saida.get("direcao") == "indeterminado":
                linha["estado"] = "indeterminado"
                linha["motivo"] = saida.get("motivo")
                resultados.append(linha)
                continue
            ids = [e["feicao_id"] for e in saida["elementos"]]
            with con.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n, coalesce(sum((atributos->>'pot_nom')::double precision), 0) AS kva "
                    "FROM plat.rede_feicao_ponto WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[]) "
                    "AND atributos->>'ctmt' = %s AND atributos ? 'pot_nom'",
                    (rid, ids, al["ctmt"]))
                achou = cur.fetchone()
            linha["trafos_alcancados"] = achou["n"]
            linha["kva_alcancado"] = round(float(achou["kva"]), 2)
            linha["kva_no_arquivo"] = round(float(al["kva"]), 2)
            linha["alcance_pct"] = round(100.0 * achou["n"] / al["trafos"], 2) if al["trafos"] else None
            linha["estado"] = "medido"
            resultados.append(linha)
    finally:
        con.close()

    r = cliente.post(f"/api/rede/{rid}/tracar", json={"tipo": "lacos"}, timeout=900)
    assert r.status_code == 200, r.text
    lacos = r.json()["contagem"]

    r = cliente.get(f"/api/rede/{rid}/topologia/diagnostico?limiar_m=1.0&exemplos=1")
    assert r.status_code == 200, r.text
    diag = r.json()

    medidos = [x for x in resultados if x["estado"] == "medido"]
    return {
        "topologia": topologia, "controladores": controladores, "alimentadores": resultados,
        "lacos_no_tier_de_media_tensao": lacos,
        "diagnostico": {"nos_orfaos": diag["nos_orfaos"], "classes": diag["classes"]},
        "alimentadores_medidos": len(medidos),
        "alimentadores_indeterminados": sum(1 for x in resultados if x["estado"] == "indeterminado"),
        "trafos_no_arquivo": sum(x["trafos_no_arquivo"] for x in medidos),
        "trafos_alcancados": sum(x["trafos_alcancados"] for x in medidos),
        "pior_alcance_pct": min([x["alcance_pct"] for x in medidos], default=None),
        "alimentadores_acima_do_alvo": sum(1 for x in medidos if x["alcance_pct"] >= ALVO_ALCANCE * 100),
    }


@pytest.mark.lento
def test_medida_alcance_por_alimentador_no_ativo_de_referencia(cred, env):
    if not esquema():
        pytest.skip("sem PLAT_REDE_REFERENCIA_ESQUEMA: esta medida precisa do ativo de referência da casa")
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    ids = ids_por_slug(con)
    con.close()
    tenant_id, usuario_id = ids["demo"], eu["id"]

    medida = {"item": "L4-01-f-alcance-do-tracado-rede-real", "maquina": _carga_maquina(),
              "orcamento_trechos": ORCAMENTO_TRECHOS, "alvo_alcance_pct": ALVO_ALCANCE * 100,
              "tolerancia_da_rede_m": TOLERANCIA_M, "clausulas": {}, "avisos": []}
    rid = None
    try:
        r = cliente.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-medida-alcance",
                                            "disciplina": "eletrica", "tolerancia_m": TOLERANCIA_M})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        medida["rede_id"] = rid

        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text

        con = _conectar(env, tenant_id, usuario_id)
        try:
            with con.cursor() as cur:
                alimentadores = _escolher_alimentadores(cur)
                cron = _carregar(cur, tenant_id, rid, [a["ctmt"] for a in alimentadores])
                cur.execute("SELECT max(tolerancia_m) AS t FROM plat.rede_regra WHERE rede_id = %s::uuid",
                            (rid,))
                medida["tolerancia_do_par_m"] = float(cur.fetchone()["t"])
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        medida["carga"] = cron
        medida["alimentadores_no_recorte"] = len(alimentadores)
        medida["trechos_no_recorte"] = sum(a["trechos"] for a in alimentadores)
        medida["trafos_no_recorte"] = sum(a["trafos"] for a in alimentadores)

        r = cliente.get(f"/api/rede/{rid}/config_tracado?limite=100")
        assert r.status_code == 200, r.text
        configs = {c["codigo"]: c for c in r.json()["itens"]}
        assert "kva_a_jusante" in configs, sorted(configs)
        config_id = configs["kva_a_jusante"]["id"]

        # 1. a cláusula: cada alimentador na sua própria rede, com e sem a tolerância do par
        medida["com_tolerancia_do_par"] = _resumir([
            _medir_alimentador(cliente, env, tenant_id, usuario_id, al, i, True)
            for i, al in enumerate(alimentadores, start=1)])
        medida["sem_tolerancia_do_par"] = _resumir([
            _medir_alimentador(cliente, env, tenant_id, usuario_id, al, i, False)
            for i, al in enumerate(alimentadores, start=1)])

        # 2. a observação: os mesmos alimentadores carregados JUNTOS, na rede única criada acima
        conjunta = _alcance(cliente, env, tenant_id, usuario_id, rid, alimentadores, config_id)
        medida["observacao_carga_conjunta"] = {
            "por_que": "com vários alimentadores na mesma rede as geometrias de saída da subestação se "
                       "encostam, a malha ganha laço e o traçado recusa arbitrar sentido",
            "topologia": conjunta["topologia"],
            "lacos_no_tier_de_media_tensao": conjunta["lacos_no_tier_de_media_tensao"],
            "alimentadores_medidos": conjunta["alimentadores_medidos"],
            "alimentadores_indeterminados": conjunta["alimentadores_indeterminados"],
            "trafos_alcancados": conjunta["trafos_alcancados"],
            "trafos_no_arquivo": conjunta["trafos_no_arquivo"],
            "diagnostico": conjunta["diagnostico"],
        }

        depois, antes = medida["com_tolerancia_do_par"], medida["sem_tolerancia_do_par"]
        medida["clausulas"]["alcance_95_por_alimentador"] = {
            "alvo_pct": ALVO_ALCANCE * 100,
            "alimentadores_medidos": depois["alimentadores_medidos"],
            "alimentadores_acima_do_alvo": depois["alimentadores_acima_do_alvo"],
            "pior_alcance_pct": depois["pior_alcance_pct"],
            "trafos_alcancados": depois["trafos_alcancados"],
            "trafos_no_arquivo": depois["trafos_no_arquivo"],
            "antes_pior_alcance_pct": antes["pior_alcance_pct"],
            "antes_trafos_alcancados": antes["trafos_alcancados"],
            "antes_alimentadores_acima_do_alvo": antes["alimentadores_acima_do_alvo"],
        }
        medida["clausulas"]["sem_laco_novo_na_media_tensao"] = {
            "lacos_antes": antes["lacos_na_media_tensao"],
            "lacos_depois": depois["lacos_na_media_tensao"],
            "por_alimentador_antes": [x["lacos_na_media_tensao"] for x in antes["alimentadores"]],
            "por_alimentador_depois": [x["lacos_na_media_tensao"] for x in depois["alimentadores"]],
        }
        medida["clausulas"]["orfaos_por_classe"] = {
            "nos_orfaos_depois": depois["nos_orfaos"], "nos_orfaos_antes": antes["nos_orfaos"],
            "classes_depois": depois["classes_de_orfao"], "classes_antes": antes["classes_de_orfao"],
        }

        assert depois["alimentadores_medidos"] > 0, medida
        for atual, anterior in zip(depois["alimentadores"], antes["alimentadores"], strict=True):
            assert atual["lacos_na_media_tensao"] <= anterior["lacos_na_media_tensao"], (
                "a tolerância por par de tipos não pode fabricar laço na média tensão", atual, anterior)
        for x in depois["alimentadores"]:
            for c in x.get("classes_de_orfao", []):
                assert c["exemplos"], (x["alimentador"], c)
        fracos = [x for x in depois["alimentadores"]
                  if x["estado"] == "medido" and x["alcance_pct"] < ALVO_ALCANCE * 100]
        assert not fracos, f"alimentadores abaixo de {ALVO_ALCANCE * 100:.0f} % de alcance: {fracos}"
    finally:
        MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
        MEDIDAS.write_text(json.dumps(medida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if rid:
            cliente.delete(f"/api/rede/{rid}")
