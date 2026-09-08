"""Medição do curto-circuito num alimentador REAL da cooperativa de teste (item L4-27, marcador `lento`).

É a cláusula de portão "curto em 1 alimentador da cooperativa de teste com Ik por barra". O recorte é
declarado e determinístico: o MENOR alimentador do arquivo que ainda tem pelo menos
`TRECHOS_MINIMOS` trechos de média tensão — medir no menor de todos (3 trechos) daria um número bonito e
sem valor, e medir no maior não cabe na janela do semáforo de testes.

A rede vem do schema lido de `PLAT_REDE_REFERENCIA_ESQUEMA` (ativo da casa, somente leitura). Sem a
variável, o teste PULA com a razão escrita — as demais cláusulas do item continuam valendo, provadas em
`tests/unit/test_curto_circuito.py` e `tests/api/test_rede_curto.py`.

O arquivo `tests/medidas/L4-27-curto-circuito-e-protecao.json` é escrito por este teste, com a carga da
máquina ao lado do tempo, como manda a regra de medida de desempenho da casa.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.rede_utilidades import subredes
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd

ITEM = "L4-27-curto-circuito-e-protecao"
MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / f"{ITEM}.json"
TRECHOS_MINIMOS = 100
CARGA_MAXIMA_PARA_MEDIR = 8.0  # 12 núcleos; acima disso o número mede a casa, não o produto
# premissas do estudo, todas declaradas (é o ponto do item): potência de curto da subestação de
# distribuição em 250 MVA, relação X/R 10, fator de tensão 1,05 (corrente máxima em média tensão).
PREMISSAS = {"potencia_de_curto_mva": 250.0, "relacao_x_r_fonte": 10.0, "fator_tensao_c": 1.05}


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
            (str(tenant_id), str(usuario_id), "medida-l427"),
        )
    return con


def _alimentador_do_recorte(cur) -> tuple[str, int, int]:
    """O menor alimentador com pelo menos `TRECHOS_MINIMOS` trechos, e quantos alimentadores o arquivo tem."""
    esquema = carga_bdgd.exigir_esquema()
    cur.execute(
        f"SELECT ctmt, count(*) AS n FROM {esquema}.ssdmt "
        "WHERE ctmt IS NOT NULL AND wkt IS NOT NULL GROUP BY 1 HAVING count(*) >= %s "
        "ORDER BY n, ctmt LIMIT 1", (TRECHOS_MINIMOS,))
    escolhido = cur.fetchone()
    cur.execute(f"SELECT count(DISTINCT ctmt) AS n FROM {esquema}.ssdmt WHERE ctmt IS NOT NULL")
    return escolhido["ctmt"], escolhido["n"], cur.fetchone()["n"]


@pytest.mark.lento
def test_medida_curto_em_alimentador_da_cooperativa(cred, env):
    if not carga_bdgd.esquema():
        pytest.skip("sem PLAT_REDE_REFERENCIA_ESQUEMA: o acervo BDGD da casa não está nesta máquina")
    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)["demo"]
    con.close()

    r = cliente.post("/api/rede", json={"nome": "zt-medida-curto", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    medida = {"rede_id": rid, "clausulas": {}, "avisos": []}
    con = None
    try:
        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text

        con = _conectar(env, tenant_id, int(eu["id"]))
        with con.cursor() as cur:
            ctmt, trechos_do_ctmt, alimentadores_no_arquivo = _alimentador_do_recorte(cur)
            cron = carga_bdgd.carregar(cur, tenant_id, rid, ctmts=[ctmt], com_postes=False)
        con.commit()
        medida["recorte"] = {"alimentador": ctmt, "trechos_mt_no_arquivo": trechos_do_ctmt,
                             "de_quantos_alimentadores": alimentadores_no_arquivo,
                             "postes": "fora (0 nó de topologia)"}
        medida["carga_bdgd"] = cron
        assert cron["ssdmt"]["linhas"] == trechos_do_ctmt, (cron["ssdmt"], trechos_do_ctmt)

        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        assert r.status_code == 201, r.text[:2000]
        medida["topologia"] = r.json()
        r = cliente.post(f"/api/rede/{rid}/controladores/importar", timeout=3600)
        assert r.status_code == 200, r.text[:2000]

        # ⛔ FRONTEIRA DECLARADA DO ATIVO: a extração da casa NÃO tem a camada `unsemt` (as chaves de
        # média tensão). É nela que a BDGD guarda o equipamento de saída da subestação, e é dele que sai
        # a tensão nominal do alimentador. Sem esse equipamento a marcação de controlador cai no NÓ DE
        # CABEÇA (convenção declarada, sem atributo nenhum) e o modelo elétrico recusa com
        # `tensao_ausente` — que é o comportamento certo: nunca se inventa tensão de base.
        # Para medir o curto na rede real, o teste escreve esse equipamento onde ele estaria: no nó de
        # cabeça daquele alimentador, com o TEN_NOM lido da tabela `ctmt` DO MESMO ARQUIVO. O dado é do
        # arquivo; o que é do teste é a POSIÇÃO da feição, e está dito aqui.
        controladores = cliente.get(f"/api/rede/{rid}/controladores").json()["itens"]
        cabeca = next(c for c in controladores if c["subrede"] == ctmt)
        with con.cursor() as cur:
            ten_nom = carga_bdgd.tensao_nominal_do_alimentador(cur, ctmt)
        assert ten_nom is not None, f"o arquivo não traz TEN_NOM para {ctmt}"
        medida["saida_da_subestacao"] = {
            "origem_do_controlador_antes": cabeca["origem"], "ten_nom_do_arquivo": str(ten_nom),
            "posicao": "nó de cabeça do alimentador (convenção declarada, não lida do arquivo)"}
        r = cliente.post(f"/api/rede/{rid}/feicoes/pontos", json={
            "tipo_codigo": 4, "grupo": "chave_de_media_tensao",
            "lon": cabeca["lon"], "lat": cabeca["lat"],
            "atributos": {"ctmt": ctmt, "unsemt_cod_id": f"SAIDA-{ctmt}", "unsemt_p_n_ope": "F",
                          # `ctmt_ten_nom` é o código do atributo no pacote eletrica-br
                          # (camada CTMT, coluna TEN_NOM)
                          "ctmt_ten_nom": str(ten_nom)}})
        assert r.status_code == 201, r.text
        feicao_saida = r.json()["id"]
        assert cliente.delete(f"/api/rede/{rid}/controlador/{cabeca['id']}").status_code == 204
        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        assert r.status_code == 201, r.text[:2000]
        medida["topologia"] = r.json()
        # o controlador é declarado no TERMINAL do equipamento de saída que a topologia ligou à rede. Na
        # ponta do alimentador só há um trecho encostando, então só o terminal 1 ganha nó — o terminal de
        # jusante, que a importação automática escolheria, não existe ali. Declarar o terminal é mais
        # honesto que a importação cair no nó de cabeça outra vez.
        with con.cursor() as cur:
            cur.execute("SELECT terminal_num FROM plat.rede_topo_no WHERE origem_id = %s::uuid "
                        "ORDER BY terminal_num", (feicao_saida,))
            terminais = [linha["terminal_num"] for linha in cur.fetchall()]
        assert terminais, "o equipamento de saída não encostou na rede"
        r = cliente.post(f"/api/rede/{rid}/controlador", json={
            "feicao_id": feicao_saida, "terminal": terminais[0], "subrede": ctmt,
            "tier": "media_tensao", "papel": "fonte", "nome": ctmt})
        assert r.status_code == 201, r.text
        medida["saida_da_subestacao"]["terminal_do_controlador"] = terminais[0]
        # o alimentador propaga a sua tensão nominal a partir do equipamento de saída
        r = cliente.put(f"/api/rede/{rid}/tier/media_tensao/propagadores",
                        json={"propagadores": ["ctmt_ten_nom"]})
        assert r.status_code == 200, r.text

        with con.cursor() as cur:
            lote = subredes.atualizar_todas(cur, tenant_id, rid, todas=True, tier="media_tensao")
        con.commit()
        assert lote["atualizadas"] >= 1, (lote, lote.get("recusadas"))

        # --- cláusula 1: curto no alimentador real, com Ik por barra
        antes = _carga_da_maquina()
        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/subrede/{ctmt}/curto", json=PREMISSAS, timeout=3600)
        segundos = round(time.perf_counter() - t0, 3)
        assert r.status_code == 200, r.text[:2000]
        saida = r.json()
        tabela = cliente.get(f"/api/rede/{rid}/subrede/{ctmt}/curto", timeout=600).json()
        com_ik = [linha for linha in tabela["linhas"] if linha["ik3_a"] is not None]
        medida["curto"] = {"segundos": segundos, "barras": saida["barras"],
                           "resumo": saida["resumo"], "avisos": saida["avisos"],
                           "premissas": saida["premissas"], **antes}
        medida["clausulas"]["ik_por_barra_em_alimentador_real"] = {
            "prova": f"alimentador {ctmt} ({trechos_do_ctmt} trechos de média tensão de "
                     f"{alimentadores_no_arquivo} alimentadores do arquivo): {saida['barras']} barras, "
                     f"{len(com_ik)} com corrente calculada, de "
                     f"{saida['resumo']['ik3_minima_a']} A a {saida['resumo']['ik3_maxima_a']} A "
                     f"(trifásica), em {segundos} s, com carga {antes['carga_1min']} e "
                     f"{antes['ram_livre_gb']} GB de RAM livre; premissas declaradas ao lado",
            "ok": len(com_ik) >= 1 and saida["resumo"]["ik3_maxima_a"] > 0}
        if antes["carga_1min"] > CARGA_MAXIMA_PARA_MEDIR:
            medida["avisos"].append(
                f"carga {antes['carga_1min']} acima de {CARGA_MAXIMA_PARA_MEDIR}: o tempo mede a máquina "
                "cheia, não o produto; o número fica registrado com a carga ao lado")

        # --- cláusula 2: dispositivo sem faixa cadastrada sai "sem dado" (é o caso REAL: a BDGD não tem
        #     campo de faixa de interrupção)
        vereditos: dict[str, int] = {}
        for linha in tabela["linhas"]:
            vereditos[linha["veredito"]] = vereditos.get(linha["veredito"], 0) + 1
        medida["vereditos"] = vereditos
        medida["clausulas"]["dispositivo_sem_faixa_sai_sem_dado"] = {
            "prova": f"vereditos no alimentador real: {vereditos}; nenhuma barra recebeu faixa de "
                     "interrupção suposta (a BDGD não traz esse campo)",
            "ok": set(vereditos) <= {"sem_dado", "sem_dispositivo_a_montante"}}

        # --- cláusula 3: camada e tabela do mesmo cálculo
        camada = cliente.get(f"/api/rede/{rid}/subrede/{ctmt}/curto/camada", timeout=600).json()
        medida["camada"] = {"feicoes": len(camada["features"]),
                            "barras_sem_coordenada": camada["barras_sem_coordenada"],
                            "linhas_na_tabela": len(tabela["linhas"])}
        medida["clausulas"]["camada_e_tabela"] = {
            "prova": f"{len(camada['features'])} pontos na camada + "
                     f"{camada['barras_sem_coordenada']} barras sem coordenada = "
                     f"{len(tabela['linhas'])} linhas na tabela",
            "ok": len(camada["features"]) + camada["barras_sem_coordenada"] == len(tabela["linhas"])}

        # --- cláusula 4 (refutação): fonte de impedância nula é recusada, também na rede real
        r = cliente.post(f"/api/rede/{rid}/subrede/{ctmt}/curto", json={"potencia_de_curto_mva": 0},
                         timeout=600)
        medida["clausulas"]["fonte_de_impedancia_nula_recusada"] = {
            "prova": f"POST com potencia_de_curto_mva = 0 devolveu {r.status_code} "
                     f"{r.json().get('erro')}",
            "ok": r.status_code == 422 and r.json().get("erro") == "impedancia_de_fonte_nula"}
        medida["ok"] = all(c["ok"] for c in medida["clausulas"].values())
    finally:
        cliente.delete(f"/api/rede/{rid}", timeout=600)
        if con is not None:
            con.close()

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    registro = {
        "item": ITEM,
        "assinado_por": "redes+backend+testador (trilha il427curtoc)",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "maquina": "PostgreSQL 16 em iagro_sat; base própria da trilha (plat_til427curtoc); fonte = "
                   "schema da cooperativa de teste (BDGD, ativo da casa, somente leitura); outras "
                   "sessões da casa na mesma máquina",
        "metodo": "fonte de tensão equivalente no ponto de falta (forma da IEC 60909); impedância de "
                  "trecho e de transformador são valores de REFERÊNCIA declarados, porque o cadastro "
                  "não os traz; rede tratada como radial e equilibrada. Triagem: sinal, não prova.",
        "medidas": medida,
        "clausulas_provadas_fora_desta_medida": {
            "resposta_analitica": "tests/unit/test_curto_circuito.py::"
                                  "test_ik_bate_com_a_conta_analitica_em_tres_barras",
            "dispositivo_com_faixa_interrompe": "tests/api/test_rede_curto.py::"
                                                "test_dispositivo_sem_faixa_sai_sem_dado_e_com_faixa_"
                                                "interrompe",
            "paridade_fora_na_esri": "docs/PARIDADE.md, seção do item",
        },
    }
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert medida["ok"], medida["clausulas"]
