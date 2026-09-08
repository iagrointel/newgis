"""Medida da cláusula de escala do item L4-04-c-unificar-subrede (marcador `lento`).

A cláusula do portão: *a subrede derivada bate com a do arquivo em ≥ 95 % dos CTMT da cooperativa de teste*.
Aqui as duas leituras são construídas de forma independente sobre a MESMA rede real e comparadas:

  * a DERIVADA nasce do controlador marcado por `controladores.marcar_da_importacao` (terminal do
    equipamento de saída quando o arquivo o traz; nó de cabeça quando não traz);
  * a DECLARADA nasce dos campos `SUB`/`CTMT` que as feições carregam do arquivo.

RECORTE DECLARADO: a carga é a BDGD da cooperativa de teste (schema em `PLAT_REDE_REFERENCIA_ESQUEMA`,
ativo da casa, somente leitura), restrita aos alimentadores de `QUANTOS_ALIMENTADORES` — não é dado
sintético, é o mesmo arquivo com um recorte nomeado, pelo mesmo motivo do item irmão L4-04-b (a topologia
da rede inteira levou 600 s medidos e o teto de uma rodada do semáforo é 600 s). Quem citar o número tem
de citar o recorte junto.

⛔ Sem a variável de ambiente o teste PULA com a razão: nesta máquina o ativo pode não existir, e inventar
um número seria pior que não ter número.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.rede_utilidades import controladores, reconciliacao
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd

ITEM = "L4-04-c-unificar-subrede"
MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / f"{ITEM}.json"
TAXA_MINIMA = 0.95
QUANTOS_ALIMENTADORES = 3
CARGA_MAXIMA_PARA_MEDIR = 8.0  # 12 núcleos; acima disso o número mede a casa, não o produto


def _carga_da_maquina() -> dict:
    livre_gb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("MemAvailable:"):
                    livre_gb = round(int(linha.split()[1]) / 1024 / 1024, 2)
                    break
    except OSError:
        livre_gb = None
    return {"carga_1min": round(os.getloadavg()[0], 2), "ram_livre_gb": livre_gb,
            "medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


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


@pytest.mark.lento
@pytest.mark.skipif(not carga_bdgd.esquema(),
                    reason="sem PLAT_REDE_REFERENCIA_ESQUEMA: a medida exige a BDGD real da cooperativa "
                           "de teste carregada num schema do iagro_sat (ativo da casa, só leitura)")
def test_medida_reconciliacao_na_cooperativa(cred, env):
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    usuario_id = cliente.get("/api/eu").json()["id"]

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)["demo"]
    con.close()

    r = cliente.post("/api/rede", json={"nome": "zt-medida-unifica", "disciplina": "eletrica"})
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
        with con.cursor() as cur:
            cur.execute(
                f"SELECT ctmt, count(*) AS n FROM {carga_bdgd.exigir_esquema()}.ssdmt "
                "WHERE ctmt IS NOT NULL AND wkt IS NOT NULL GROUP BY 1 ORDER BY n DESC, ctmt LIMIT %s",
                (QUANTOS_ALIMENTADORES,),
            )
            escolhidos = [r2["ctmt"] for r2 in cur.fetchall()]
            assert len(escolhidos) == QUANTOS_ALIMENTADORES, escolhidos
            cron = carga_bdgd.carregar(cur, tenant_id, rid, ctmts=escolhidos, com_postes=False)
            cur.execute(f"SELECT count(DISTINCT ctmt) AS n FROM {carga_bdgd.exigir_esquema()}.ssdmt "
                        "WHERE ctmt = ANY(%s) AND wkt IS NOT NULL", (escolhidos,))
            ctmts_no_arquivo = cur.fetchone()["n"]
        con.commit()
        # o CÓDIGO do alimentador não entra no arquivo de medida: é identificador do cadastro de um
        # parceiro e este repositório é público. O que a medida precisa é do TAMANHO do recorte.
        medida["recorte"] = {"quantos_alimentadores": len(escolhidos),
                             "ctmts_no_arquivo_no_recorte": ctmts_no_arquivo,
                             "postes": "fora (0 nó de topologia)"}
        medida["carga_bdgd"] = cron

        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        assert r.status_code == 201, r.text[:2000]

        antes = _carga_da_maquina()
        t0 = time.perf_counter()
        with con.cursor() as cur:
            contagem = controladores.marcar_da_importacao(cur, tenant_id, rid, usuario_id)
        con.commit()
        segundos = round(time.perf_counter() - t0, 3)
        medida["importacao"] = {k: v for k, v in contagem.items()
                                if k not in ("declarado", "reconciliacao")}
        medida["declarado"] = contagem["declarado"]
        medida["reconciliacao"] = contagem["reconciliacao"]
        medida["tempo"] = {"segundos": segundos, **antes}

        alim = contagem["reconciliacao"]["alimentadores"]
        taxa = alim["taxa"]
        medida["clausulas"]["subrede_derivada_bate_com_a_do_arquivo"] = {
            "prova": f"{alim['com_equivalente']} de {alim['declaradas']} alimentadores declarados pelo "
                     f"arquivo têm subrede derivada de mesmo nome no tier de média tensão = {taxa} "
                     f"(alvo {TAXA_MINIMA}); recorte de {QUANTOS_ALIMENTADORES} alimentadores da "
                     f"cooperativa de teste; carga da máquina {antes['carga_1min']}, "
                     f"{antes['ram_livre_gb']} GB de RAM livre",
            "ok": taxa is not None and taxa >= TAXA_MINIMA}

        # a mesma reconciliação rodada de novo não muda o número (idempotente)
        with con.cursor() as cur:
            de_novo = reconciliacao.reconciliar(cur, rid)
        con.commit()
        medida["clausulas"]["reconciliacao_idempotente"] = {
            "prova": f"segunda passagem: {de_novo['alimentadores']} (igual à primeira)",
            "ok": de_novo["alimentadores"]["com_equivalente"] == alim["com_equivalente"]}

        if antes["carga_1min"] > CARGA_MAXIMA_PARA_MEDIR:
            medida["avisos"].append(
                f"carga {antes['carga_1min']} acima de {CARGA_MAXIMA_PARA_MEDIR}: o TEMPO ao lado mede a "
                "máquina cheia, não o produto; a taxa de reconciliação não depende de tempo")
        medida["ok"] = all(c["ok"] for c in medida["clausulas"].values())
    finally:
        cliente.delete(f"/api/rede/{rid}", timeout=600)
        if con is not None:
            con.close()

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    registro = {
        "item": ITEM,
        "assinado_por": "construtor+fila (trilha il404cunifi)",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "maquina": "PostgreSQL 16 em iagro_sat; base própria da trilha "
                   f"({os.environ.get('PLAT_SCHEMA', '?')}); fonte = BDGD da cooperativa de teste (ativo "
                   "da casa, somente leitura); outras sessões da casa na mesma máquina",
        "medidas": medida,
        "comando": "bash laco/roda_teste.sh tests/api/test_rede_subrede_unificada_medida.py -m lento -q",
    }
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert medida["ok"], medida["clausulas"]
