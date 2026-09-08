"""Medição da cláusula do kVA em dado REAL (item L4-02-e-configuracoes-de-tracado, marcador `lento`).

A cláusula do portão: a função "Σ kVA a jusante" de um alimentador (CTMT) tem de dar a soma de POT_NOM dos
transformadores (UNTRMT) daquele alimentador NO ARQUIVO. Aqui os dois lados são medidos por caminhos
independentes:

  * o lado da plataforma: um traçado a jusante do controlador do alimentador, com a configuração
    `kva_a_jusante` que vem pronta no pacote elétrica-BR;
  * o lado do arquivo: `tests/dados/carga_bdgd_uc.esperado_por_ctmt`, que só lê as tabelas do ativo de
    referência da casa e nunca consulta `plat.*`.

⛔ O nome do schema do ativo vem de `PLAT_REDE_REFERENCIA_ESQUEMA`; sem a variável a medição é pulada.
⛔ É UM alimentador, o de menor número de trechos que tenha transformador — construir a topologia da
cooperativa inteira levou 600 s no item L4-01-b, mais que o relógio de uma rodada.
⛔ A diferença entre os dois lados, quando existe, é achado e fica gravada: o arquivo declara a filiação de
cada transformador ao alimentador pelo campo `ctmt`, e o traçado anda pela topologia. Transformador que o
cadastro filia ao alimentador mas cuja geometria não se liga à rede dele não é alcançado — e isso é a
diferença entre o retrato do cadastro e o que a rede conduz, não um erro da função.

Tudo que este teste mede vai para `tests/medidas/L4-02-e-configuracoes-de-tracado.json`."""

import json
import os
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE, entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd_uc
from tests.dados.carga_bdgd import esquema

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-02-e-configuracoes-de-tracado.json"
TOLERANCIA_M = 0.05   # a tolerancia padrao do produto. MEDIDO em 08/09: com 1,0 m os nos orfaos caem de
                      # 47 para 22, mas a folga funde vertices vizinhos e o grafo ganha LACO — o tracado a
                      # jusante passa a responder `indeterminado` e a soma deixa de existir. Alargar a
                      # tolerancia nao e conserto: troca falta de alcance por falta de sentido.
TRAFOS_MINIMOS = 20   # a soma de um alimentador de um transformador só não prova a função


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
            (str(tenant_id), str(usuario_id), "medida-l402e"),
        )
    return con


def _tipo(cur, rede_id: str, grupo: str, codigo: int) -> str:
    cur.execute(
        "SELECT tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s AND tp.codigo = %s",
        (rede_id, grupo, codigo),
    )
    return str(cur.fetchone()["id"])


def _escolher_alimentador(cur) -> str:
    """O alimentador de MENOR número de trechos entre os que têm ao menos `TRAFOS_MINIMOS` transformadores:
    grande o bastante para a soma dizer alguma coisa (um alimentador de um transformador só provaria pouco) e
    pequeno o bastante para caber no orçamento de relógio de uma trilha. Se nenhum chega ao mínimo, cai para
    o que tem mais transformadores, e o número fica gravado na medida."""
    esq = esquema()
    cur.execute(
        "SELECT ctmt, trechos, trafos FROM ("
        f"  SELECT s.ctmt, count(*) AS trechos, "
        f"         (SELECT count(*) FROM {esq}.trafo t WHERE t.ctmt = s.ctmt) AS trafos "
        f"  FROM {esq}.ssdmt s GROUP BY 1"
        ") c WHERE trafos > 0 ORDER BY (trafos >= %s) DESC, trechos ASC, trafos DESC LIMIT 1",
        (TRAFOS_MINIMOS,),
    )
    linha = cur.fetchone()
    if linha is None:
        pytest.skip("o ativo de referência não tem alimentador com transformador")
    return linha["ctmt"]


def _carregar_um_alimentador(cur, tenant_id: int, rede_id: str, ctmt: str) -> dict:
    """Mesma carga de `carga_bdgd_uc`, recortada a UM alimentador: trechos de média tensão e transformadores."""
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
          FROM {esq}.ssdmt WHERE wkt IS NOT NULL AND ctmt = %s
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "trecho_de_media_tensao", 1), ctmt))

    rodar("trafo", f"""
        WITH carga AS (
          INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos)
          SELECT %s, %s::uuid, %s::uuid, ST_SetSRID(ST_MakePoint(x, y), 4326),
                 jsonb_build_object('cod_id', cod_id, 'pot_nom', pot_nom, 'ctmt', ctmt)
          FROM {esq}.trafo WHERE ctmt = %s
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "transformador_de_distribuicao", 1), ctmt))
    return cron


@pytest.mark.lento
def test_medida_kva_a_jusante_contra_o_arquivo(cred, env):
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    ids = ids_por_slug(con)
    con.close()
    tenant_id, usuario_id = ids["demo"], eu["id"]

    r = cliente.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-medida-cfg", "disciplina": "eletrica",
                                        "tolerancia_m": TOLERANCIA_M})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    medida = {"item": "L4-02-e-configuracoes-de-tracado", "rede_id": rid, "maquina": _carga_maquina(),
              "clausulas": {}, "avisos": []}
    con = None
    try:
        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text
        medida["configuracoes_instaladas_com_o_pacote"] = r.json()["contagens"].get(
            "configuracoes_de_tracado")

        con = _conectar(env, tenant_id, usuario_id)
        try:
            with con.cursor() as cur:
                ctmt = _escolher_alimentador(cur)
                declarado = carga_bdgd_uc.esperado_por_ctmt(cur)[ctmt]
                cron = _carregar_um_alimentador(cur, tenant_id, rid, ctmt)
            con.commit()
        except Exception:
            con.rollback()
            raise
        # o código do alimentador traz a sigla da distribuidora: fica fora do arquivo de medidas
        medida["alimentador"] = {"trechos_no_arquivo": declarado["ssdmt"],
                                 "trafos_no_arquivo": declarado["trafos"],
                                 "kva_no_arquivo": declarado["kva"]}
        medida["carga"] = cron

        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=900)
        assert r.status_code == 201, r.text
        medida["topologia"] = {**r.json(), "segundos": round(time.perf_counter() - t0, 1)}
        r = cliente.post(f"/api/rede/{rid}/controladores/importar", timeout=900)
        assert r.status_code == 200, r.text
        medida["controladores"] = r.json()

        r = cliente.get(f"/api/rede/{rid}/controladores?limite=50")
        assert r.status_code == 200, r.text
        mt = [c for c in r.json()["itens"] if c["tier"] == "media_tensao"]
        assert mt, r.json()
        cabeca = mt[0]
        medida["controlador"] = {"origem": cabeca["origem"], "tier": cabeca["tier"]}

        r = cliente.get(f"/api/rede/{rid}/config_tracado?limite=100")
        assert r.status_code == 200, r.text
        configs = {c["codigo"]: c for c in r.json()["itens"]}
        assert "kva_a_jusante" in configs, sorted(configs)

        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/tracar", timeout=900, json={
            "config_id": configs["kva_a_jusante"]["id"],
            "pontos_partida": [{"lon": cabeca["lon"], "lat": cabeca["lat"]}]})
        assert r.status_code == 200, r.text
        saida = r.json()
        medida["tracado"] = {"segundos": round(time.perf_counter() - t0, 1),
                             "direcao": saida.get("direcao"), "motivo": saida.get("motivo"),
                             "contagem": saida["contagem"], "duracao_ms": saida["duracao_ms"]}

        if saida.get("direcao") == "indeterminado":
            medida["clausulas"]["kva_a_jusante"] = {
                "estado": "nao_medida",
                "razao": f"o traçado a jusante deste alimentador é indeterminado ({saida.get('motivo')}): "
                         "com laço na malha o produto recusa arbitrar sentido, e a soma não é comparável",
            }
            pytest.skip("traçado a jusante indeterminado neste alimentador: medida registrada como pendente")

        kva = next(f for f in saida["funcoes"] if f["codigo"] == "kva_instalado")
        alcancados = kva["elementos_considerados"]
        medida["clausulas"]["kva_a_jusante"] = {
            "kva_da_funcao": kva["valor"], "kva_do_arquivo": declarado["kva"],
            "trafos_alcancados": alcancados, "trafos_do_arquivo": declarado["trafos"],
            "diferenca_pct": (round(100.0 * ((kva["valor"] or 0.0) - declarado["kva"]) / declarado["kva"], 3)
                              if declarado["kva"] else None),
        }
        # a função soma o que ela alcançou: a conferência dura é que a soma dos trafos ALCANÇADOS é
        # exatamente a soma de POT_NOM daqueles mesmos trafos no arquivo.
        with _conectar(env, tenant_id, usuario_id) as con2, con2.cursor() as cur:
            ids_alcancados = [e["feicao_id"] for e in saida["elementos"]]
            cur.execute(
                "SELECT sum((atributos->>'pot_nom')::double precision) AS kva, count(*) AS n "
                "FROM plat.rede_feicao_ponto WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])",
                (rid, ids_alcancados))
            confere = cur.fetchone()
        assert confere["n"] == alcancados, (confere["n"], alcancados)
        assert kva["valor"] == pytest.approx(float(confere["kva"])), (kva["valor"], confere["kva"])
        medida["clausulas"]["kva_a_jusante"]["estado"] = (
            "igual_ao_arquivo" if alcancados == declarado["trafos"] else "parcial_alcancado_pela_topologia")
        if alcancados != declarado["trafos"]:
            medida["avisos"].append(
                f"{declarado['trafos'] - alcancados} de {declarado['trafos']} transformadores que o cadastro "
                "filia a este alimentador não são alcançados pela topologia: o cadastro filia por campo, o "
                "traçado anda pela rede")
    finally:
        if con is not None:
            con.close()
        MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
        MEDIDAS.write_text(json.dumps(medida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cliente.delete(f"/api/rede/{rid}")
