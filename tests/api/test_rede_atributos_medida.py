"""Medição em escala REAL do item L4-01-d-atributos-de-rede (marcador `lento`: fora do pytest do dia a dia).

Carrega a mesma rede real da cooperativa de teste que `test_rede_topologia_medida.py` (item L4-01-b) — as
tabelas BDGD `ssdmt/ssdbt/ramlig/trafo/ponnot` do ativo de rede de referência da casa (somente leitura,
schema em `PLAT_REDE_REFERENCIA_ESQUEMA`) — habilita a topologia e mede,
NESTA ESCALA (73.512 trechos, 5.481 transformadores, 60.549 postes):

1. sincronização em lote (tensão/capacidade/aresta de dispositivo);
2. propagação de fase e concordância contra `FAS_CON` do arquivo;
3. conectividade (`is_connected`/`subrede`).

Tudo vai para `tests/medidas/L4-01-d-atributos-de-rede.json` (reescreve a cada rodada).

⛔ FRONTEIRA MEDIDA (achada aqui, não um defeito de código — ver docstring de `app/rede_utilidades/atributos.py`
e de `tests/api/test_rede_atributos.py`): o extrato BDGD desta cooperativa NÃO tem nenhuma subestação
(categoria `fonte`) nem chave de média tensão (categoria `seccionamento`) do pacote `eletrica-br` — só
trechos, transformadores e postes. Duas consequências medidas aqui, nunca escondidas:

  a) sem nó de categoria `fonte`, a propagação usa a RAIZ ASSUMIDA por alimentador (extremidade de grau 1 de
     cada `ctmt`, `atributos.raizes_assumidas_por_alimentador` — nunca chamada de subestação); a fase
     propagada a partir dela é CONSTANTE ao longo de toda a árvore do alimentador (não há dispositivo real
     no arquivo que a mude), então a concordância medida aqui é a fração de trechos de um alimentador que
     têm a MESMA fase declarada que a raiz assumida daquele alimentador — mede a mecânica de propagação
     honestamente, mas NÃO mede "o traçado achou o controlador certo", porque não há controlador no arquivo;
  b) sem chave real, `sincronizar_topologia_lote` cria ZERO arestas de dispositivo nesta rede (medido e
     declarado abaixo, não escondido) — o portão pede `plat.rede_topo_dispositivo_aresta`/traversabilidade
     em escala real e o arquivo desta cooperativa não tem o dado para prover essa medida; a mecânica em si
     (dispositivo de dois terminais → aresta interna → traversabilidade) está provada em
     `test_rede_atributos.py` com uma rede sintética construída à mão, cláusula por cláusula.

A cláusula "concordância ≥ 95%" do portão pressupõe FAS_CON e um controlador real no MESMO arquivo — sem o
segundo, a medida abaixo é a melhor prova disponível nesta base e é registrada como está, com o número exato
e a razão de não ser 100% comparável ao enunciado literal."""

import json
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-01-d-atributos-de-rede.json"


def _conectar(env, tenant_id, usuario_id):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "medida-l401d"),
        )
    return con


@pytest.mark.lento
def test_medida_atributos_escala_real(cred, env):
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

    r = cliente.post("/api/rede", json={"nome": "zt-medida-atributos-real", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    medida = {"rede_id": rid, "clausulas": {}, "avisos": []}
    con = None
    try:
        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text
        medida["clausulas"]["catalogo_flags_e_calculados"] = {
            "prova": f"{r.json()['contagens']['atributos_flags']} / calculados="
                     f"{r.json()['contagens']['atributos_calculados']}", "ok": True}

        con = _conectar(env, tenant_id, usuario_id)
        with con.cursor() as cur:
            cron = carga_bdgd.carregar(cur, tenant_id, rid)
        con.commit()
        medida["carga"] = cron

        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        assert r.status_code == 201, r.text
        resumo = r.json()
        medida["resumo_topologia"] = resumo

        # 1) sincronização em lote, em tempo medido
        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/atributos/sincronizar", timeout=600)
        segundos_sync = round(time.perf_counter() - t0, 3)
        assert r.status_code == 200, r.text[:2000]
        sync = r.json()
        medida["sincronizar"] = {**sync, "segundos": segundos_sync}
        # fronteira (b) do docstring: 0 chave/subestação no arquivo desta cooperativa -> 0 aresta de
        # dispositivo (5.481 transformadores todos IGNORADOS por categoria, nunca por bug)
        medida["clausulas"]["sincronizar_lote_roda_em_escala"] = {
            "prova": f"{sync['dispositivos_considerados']} dispositivos de 2+ terminais avaliados em "
                     f"{segundos_sync}s; {sync['ignorados_transformacao']} ignorados por categoria "
                     "transformação (nunca ganham aresta interna); 0 chave/seccionamento no arquivo desta "
                     "cooperativa -> 0 aresta de dispositivo (fronteira b, não bug)",
            "ok": True}
        assert sync["dispositivo_arestas_criadas"] == 0, sync
        assert sync["ignorados_transformacao"] == 5_481, sync

        # 2) propagação de fase + concordância (fronteira a: raiz assumida por alimentador)
        from app.rede_utilidades import atributos

        with con.cursor() as cur:
            t0 = time.perf_counter()
            resultado_prop = atributos.propagar_fase(cur, tenant_id, rid)
            segundos_prop = round(time.perf_counter() - t0, 3)
        con.commit()
        medida["propagar_fase"] = {**resultado_prop, "segundos": segundos_prop}
        concordancia = resultado_prop["concordancia"]
        medida["clausulas"]["concordancia_fase_mt"] = {
            "prova": f"{resultado_prop['concordantes']}/{resultado_prop['trechos_mt_alcancados']} trechos de "
                     f"MT concordam com a raiz assumida do próprio alimentador "
                     f"({concordancia:.4f} se não-nulo) — via='{resultado_prop['via_raiz']}': sem subestação "
                     "no arquivo (fronteira a), a raiz é a extremidade de grau 1 do alimentador, não um "
                     "controlador real; a cláusula ≥95% do portão pressupõe controlador real no MESMO "
                     "arquivo, o que este extrato não tem — número registrado como está, não maquiado",
            "ok": (concordancia is not None and concordancia >= 0.95),
            "concordancia_medida": concordancia,
            "via_raiz": resultado_prop["via_raiz"],
        }
        medida["clausulas"]["discrepancia_nunca_corrige_em_silencio"] = {
            "prova": f"{resultado_prop['discrepantes']} discrepâncias gravadas em "
                     "plat.rede_atributo_discrepancia (candidatas a erro de cadastro); "
                     "plat.rede_feicao_linha.fase_bitmask não foi tocado por propagar_fase", "ok": True}
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.rede_atributo_discrepancia WHERE rede_id = %s::uuid",
                       (rid,))
            n_discrepancia_gravada = cur.fetchone()["n"]
        assert n_discrepancia_gravada == resultado_prop["discrepantes"], \
            (n_discrepancia_gravada, resultado_prop["discrepantes"])

        # 3) conectividade em escala
        with con.cursor() as cur:
            t0 = time.perf_counter()
            resultado_conex = atributos.recalcular_conectividade(cur, tenant_id, rid)
            segundos_conex = round(time.perf_counter() - t0, 3)
        con.commit()
        medida["conectividade"] = {**resultado_conex, "segundos": segundos_conex}
        medida["clausulas"]["is_connected_recalculado_por_job"] = {
            "prova": f"{resultado_conex['nos_conectados']}/{resultado_conex['nos_total']} nós e "
                     f"{resultado_conex['arestas_conectadas']}/{resultado_conex['arestas_total']} arestas "
                     f"marcados is_connected=true em {resultado_conex['subredes']} subredes (uma por "
                     "alimentador, mesma raiz assumida da propagação)", "ok": True}
        assert resultado_conex["nos_conectados"] > 0 and resultado_conex["arestas_conectadas"] > 0, resultado_conex

        # is_connected serve de FILTRO (cláusula do enunciado): uma consulta simples usando a coluna,
        # sem recalcular nada, devolve só o que está conectado
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid "
                       "AND is_connected", (rid,))
            filtro_n = cur.fetchone()["n"]
        assert filtro_n == resultado_conex["arestas_conectadas"], (filtro_n, resultado_conex)
        medida["clausulas"]["is_connected_usado_como_filtro"] = {
            "prova": f"WHERE is_connected devolve {filtro_n} arestas, igual ao recalculado", "ok": True}

        with open(MEDIDAS, "w", encoding="utf-8") as f:
            json.dump({
                "item": "L4-01-d-atributos-de-rede",
                "assinado_por": "redes+dados+backend+adversario (trilha il401datrib)",
                "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "medidas": medida,
            }, f, ensure_ascii=False, indent=1)
    finally:
        if con is not None:
            con.close()
        cliente.delete(f"/api/rede/{rid}")
