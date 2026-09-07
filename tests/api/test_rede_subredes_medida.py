"""Medição em escala REAL das duas cláusulas de escala do item L4-04-b-atualizar-e-exportar-subrede
(marcador `lento`: fora do pytest do dia a dia).

  * atualizar as subredes de média tensão da cooperativa de teste EM TEMPO MEDIDO, com a carga da máquina
    gravada ao lado do número;
  * o nome da subrede gravado em cada trecho de média tensão bate com o `CTMT` DO ARQUIVO em ≥ 99 %, e a
    diferença sai listada como candidata a erro de cadastro.

RECORTE DECLARADO: a carga é a BDGD da cooperativa de teste (schema lido de
`PLAT_REDE_REFERENCIA_ESQUEMA`, ativo da casa, somente leitura), mas
restrita aos ALIMENTADORES escolhidos em `ALIMENTADORES_MEDIDOS` — não é dado sintético, é o mesmo arquivo
com um recorte nomeado. O motivo é a janela do semáforo de testes: a construção da topologia da rede inteira
levou 600 s medidos no item L4-01-b, e o teto de uma rodada é 600 s. Quem citar este número tem de citar o
recorte junto: são 3 dos 20 alimentadores do arquivo.

⛔ O tier de BAIXA TENSÃO não é medido aqui. Na BDGD ele tem uma subrede por transformador de distribuição
(5.481 no arquivo inteiro), e cada atualização custa uma passada de componentes conexas sobre o grafo —
medir isso é outro item, e prometer o número sem medir seria invenção. O que se mede aqui é o tier de média
tensão, uma subrede por alimentador, que é o caso do portão.

⛔ Exige o GRANT de leitura do ativo para o papel da trilha (o `trilha_ambiente.sh` já dá):
  GRANT USAGE ON SCHEMA <esquema> TO <papel>; GRANT SELECT ON <esquema>.ssdmt, ssdbt, ... ao papel
"""

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.rede_utilidades import controladores, subredes
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd

ITEM = "L4-04-b-atualizar-e-exportar-subrede"
MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / f"{ITEM}.json"
CONCORDANCIA_MINIMA = 0.99
CARGA_MAXIMA_PARA_MEDIR = 8.0  # 12 núcleos; acima disso o número mede a casa, não o produto


def _conectar(env, tenant_id, usuario_id):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "medida-l404b"),
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


def _alimentadores(cur, quantos: int) -> list[str]:
    """Os `quantos` MAIORES alimentadores do arquivo (mais trechos de média tensão) — recorte determinístico
    e o pior caso que cabe na janela do semáforo. Medir nos menores daria um número bonito e sem valor."""
    cur.execute(
        f"SELECT ctmt, count(*) AS n FROM {carga_bdgd.exigir_esquema()}.ssdmt "
        "WHERE ctmt IS NOT NULL AND wkt IS NOT NULL "
        "GROUP BY 1 ORDER BY n DESC, ctmt LIMIT %s",
        (quantos,),
    )
    return [r["ctmt"] for r in cur.fetchall()]


@pytest.mark.lento
def test_medida_atualizar_subredes_da_cooperativa(cred, env):
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)["demo"]
    con.close()
    usuario_id = eu["id"]

    r = cliente.post("/api/rede", json={"nome": "zt-medida-subredes", "disciplina": "eletrica"})
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
            escolhidos = _alimentadores(cur, 3)
            assert len(escolhidos) == 3, escolhidos
            cron = carga_bdgd.carregar(cur, tenant_id, rid, ctmts=escolhidos, com_postes=False)
            cur.execute(f"SELECT count(*) AS n FROM {carga_bdgd.exigir_esquema()}.ssdmt "
                        "WHERE ctmt = ANY(%s) AND wkt IS NOT NULL",
                        (escolhidos,))
            mt_no_arquivo = cur.fetchone()["n"]
        con.commit()
        medida["recorte"] = {"alimentadores": escolhidos, "de_quantos_no_arquivo": 20,
                             "trechos_mt_no_arquivo": mt_no_arquivo, "postes": "fora (0 nó de topologia)"}
        medida["carga_bdgd"] = cron
        assert cron["ssdmt"]["linhas"] == mt_no_arquivo, (cron["ssdmt"], mt_no_arquivo)

        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        assert r.status_code == 201, r.text[:2000]
        medida["topologia"] = r.json()

        r = cliente.post(f"/api/rede/{rid}/controladores/importar", timeout=3600)
        assert r.status_code == 200, r.text[:2000]
        medida["importacao_de_controladores"] = r.json()

        # --- cláusula 1: atualizar todas as subredes de média tensão em tempo medido
        antes = _carga_da_maquina()
        with con.cursor() as cur:
            t0 = time.perf_counter()
            lote = subredes.atualizar_todas(cur, tenant_id, rid, todas=True, tier="media_tensao")
            segundos = round(time.perf_counter() - t0, 3)
        con.commit()
        medida["lote"] = {"segundos": segundos, "candidatas": lote["candidatas"],
                          "atualizadas": lote["atualizadas"], "recusadas": lote["recusadas"],
                          "elementos": lote["elementos"], **antes}
        # Recusa NÃO é falha do lote: a subrede sem controlador com nó na topologia continua suja e sai
        # nomeada, com o código do erro. O que o portão exige é que toda subrede CANDIDATA seja tratada e
        # que nenhuma fique em silêncio — por isso a soma tem de fechar.
        assert lote["atualizadas"] + len(lote["recusadas"]) == lote["candidatas"], lote
        assert lote["atualizadas"] >= 1, lote
        medida["clausulas"]["atualizar_todas_em_tempo_medido"] = {
            "prova": f"{lote['candidatas']} subredes de média tensão candidatas ({len(escolhidos)} de 20 "
                     f"alimentadores do arquivo): {lote['atualizadas']} atualizadas e "
                     f"{len(lote['recusadas'])} recusadas com motivo nomeado ({lote['recusadas']}), "
                     f"{lote['elementos']} elementos, em {segundos} s, com carga {antes['carga_1min']} e "
                     f"{antes['ram_livre_gb']} GB de RAM livre",
            "ok": lote["atualizadas"] + len(lote["recusadas"]) == lote["candidatas"]}
        if antes["carga_1min"] > CARGA_MAXIMA_PARA_MEDIR:
            medida["avisos"].append(
                f"carga {antes['carga_1min']} acima de {CARGA_MAXIMA_PARA_MEDIR}: o tempo mede a máquina "
                "cheia, não o produto; o número fica registrado com a carga ao lado")

        # --- cláusula 2: nome da subrede em cada trecho de MT == CTMT do arquivo em >= 99 %
        with con.cursor() as cur:
            conferencia = subredes.conferir(cur, rid, "ctmt", "trecho_de_media_tensao",
                                            tier="media_tensao", limite=200)
            tiers = controladores.listar_tiers(cur, rid)
        medida["conferencia"] = {k: v for k, v in conferencia.items() if k != "diferencas"}
        medida["conferencia"]["diferencas_amostra"] = conferencia["diferencas"][:20]
        medida["tiers"] = tiers
        concordancia = conferencia["concordancia"]
        medida["clausulas"]["nome_da_subrede_igual_ao_ctmt"] = {
            "prova": f"{conferencia['iguais']} de {conferencia['comparaveis']} trechos de média tensão com o "
                     f"nome da subrede igual ao CTMT do arquivo = {concordancia}; "
                     f"{conferencia['diferentes']} diferenças listadas como candidatas a erro de cadastro "
                     f"(nunca erro provado)",
            "ok": concordancia is not None and concordancia >= CONCORDANCIA_MINIMA}

        # --- exportação de uma subrede real: Σ elementos = o que a atualização gravou
        with con.cursor() as cur:
            exportado = subredes.exportar(cur, rid, escolhidos[0], "media_tensao")
        medida["exportacao"] = {
            "subrede": exportado["subrede"]["nome"], "elementos": len(exportado["elementos"]),
            "conectividade": len(exportado["conectividade"]),
            "comprimento_m": exportado["subrede"]["comprimento_m"],
            "resumo_elementos": exportado["resumo"]["elementos"]}
        medida["clausulas"]["exportacao_bate_com_o_resumo"] = {
            "prova": f"{len(exportado['elementos'])} elementos exportados == resumo "
                     f"{exportado['resumo']['elementos']} da atualização",
            "ok": len(exportado["elementos"]) == exportado["resumo"]["elementos"]}

        medida["ok"] = all(c["ok"] for c in medida["clausulas"].values())
    finally:
        cliente.delete(f"/api/rede/{rid}", timeout=600)
        if con is not None:
            con.close()

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    registro = {
        "item": ITEM,
        "assinado_por": "redes+backend+testador+adversario (trilha il404batual)",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "maquina": "PostgreSQL 16 em iagro_sat; base própria da trilha "
                   f"({os.environ.get('PLAT_SCHEMA', '?')}); fonte = BDGD da cooperativa de teste (ativo da casa, "
                   "somente leitura); outras sessões da casa na mesma máquina",
        "medidas": medida,
        "comando": "venv/bin/pytest tests/api/test_rede_subredes_medida.py -m lento -q",
    }
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert medida["ok"], medida["clausulas"]
