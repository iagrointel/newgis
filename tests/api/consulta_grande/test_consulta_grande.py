"""Portão de pronto do item L2-15-b-consultas-duckdb-em-escala, cláusula por cláusula.

1. "agregação de >= 100 mi de linhas por célula de grade e por mês em tempo medido (tests/medidas) e contagem
   total igual ao PostGIS" — a AGREGAÇÃO em escala está em `scripts/medir_consulta_grande.py`, que grava
   `tests/medidas/L2-15-b-consultas-duckdb-em-escala.json`; a suíte não gera 100 mi de linhas (disco a 96 % nos
   dois servidores). O que a suíte prova, e é a parte que pode regredir, é a IGUALDADE: a mesma ferramenta, com
   os mesmos parâmetros, rodada nos dois motores sobre o mesmo conteúdo, dá a mesma contagem.
2. "junção espacial de 1 mi de pontos x 5.570 municípios: contagens iguais ao PostGIS" — mesma divisão: a
   escala está na medida; a igualdade está aqui, em 40 mil pontos x 40 polígonos.
3. "SQL do usuário com read_csv/read_parquet de caminho externo, http, ATTACH ou INSTALL = recusado (teste com
   10 tentativas)" — aqui pela API (as mesmas dez tentativas do teste de unidade, agora com resposta HTTP).
4. "consulta acima do limite de tempo cancelada com mensagem" — aqui.
5. "resultado vira camada com proveniência (sql + sha256 dos arquivos)" — aqui.
6. "e2e com captura" — `tests/e2e/test_consulta_grande.py`.
7. "paridade escrita com a nota da aposentadoria do GeoAnalytics Server em 11.4" — `docs/PARIDADE_ESRI_L2_15_B.md`,
   conferido pelo teste de unidade da paridade (existência e conteúdo mínimo) e lido por gente.

Refutação do adversário: contagem contra PostGIS (aqui), Parquet de outro inquilino por caminho e por view
(aqui), cinco consultas grandes ao mesmo tempo (aqui: as cinco entram na fila e o worker as serializa).
"""

from __future__ import annotations

import time

import pytest

from app import limites
from tests.api.consulta_grande.conftest import NAVIOS, contar_no_banco
from tests.api.jobs.conftest import esperar

pytestmark = pytest.mark.lento
TEMPO_JOB = 420


def executar(cliente, ferramenta: str, parametros: dict, titulo: str | None = None, timeout: float = TEMPO_JOB):
    """Enfileira a ferramenta e espera o job. Toda ferramenta grande custa acima do teto do caminho em
    processo, então a resposta é sempre 202 — é a fila que garante uma consulta grande de cada vez."""
    r = cliente.post(f"/api/ferramentas/{ferramenta}/executar",
                     json={"parametros": parametros, "titulo": titulo, "modo": "job"})
    assert r.status_code == 202, r.text
    job = esperar(cliente, r.json()["job_id"], timeout=timeout)
    return job


def item_do_job(cliente, job: dict) -> dict:
    assert job["estado"] == "concluido", job.get("erro") or job
    r = cliente.get(f"/api/itens/{job['resultado']['item_id']}")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- cláusulas 1 e 2: igualdade DuckDB x PostGIS
CASOS_DE_IGUALDADE = [
    ("agregar_em_grade", lambda p, g: {
        "camada": p, "tamanho_celula": {"distance": 25, "units": "esriKilometers"},
        "campo_periodo": "instante", "grao_periodo": "mes", "campo_valor": "carga", "projecao_metrica": 5880}),
    ("juncao_espacial", lambda p, g: {"pontos": p, "poligonos": g, "campo_chave": "codigo"}),
    ("resumir_dentro", lambda p, g: {
        "poligonos": g, "pontos": p, "campo_chave": "codigo", "campo_valor": "carga",
        "estatisticas": ["contagem", "soma", "media"]}),
    ("contagem_por_periodo", lambda p, g: {"camada": p, "campo_periodo": "instante", "grao_periodo": "mes"}),
    ("detectar_duplicatas", lambda p, g: {"camada": p, "campos": ["navio"], "mesma_posicao": False}),
    ("padroes_deslocamento", lambda p, g: {
        "camada": p, "campo_id": "navio", "campo_periodo": "instante", "velocidade_maxima": 200.0}),
]


@pytest.mark.parametrize(("ferramenta", "monta"), CASOS_DE_IGUALDADE)
def test_a_mesma_pergunta_no_duckdb_e_no_postgis_da_a_mesma_contagem(
    inquilino_cg, fonte_pontos, fonte_poligonos, worker_cg, ferramenta, monta,
):
    cliente = inquilino_cg.admin
    no_duckdb = item_do_job(cliente, executar(
        cliente, ferramenta, monta(fonte_pontos["parquet_id"], fonte_poligonos["parquet_id"]),
        titulo=f"zt {ferramenta} duckdb"))
    no_postgis = item_do_job(cliente, executar(
        cliente, ferramenta, monta(fonte_pontos["item_id"], fonte_poligonos["item_id"]),
        titulo=f"zt {ferramenta} postgis"))
    n_duck = no_duckdb["dados"]["estatisticas"]["feicoes"]
    n_pg = no_postgis["dados"]["estatisticas"]["feicoes"]
    assert n_duck == n_pg, (
        f"{ferramenta}: DuckDB devolveu {n_duck} feições e o PostGIS {n_pg} para a MESMA pergunta")
    assert n_duck > 0
    assert no_duckdb["dados"]["procedencia"]["ferramenta"]["ferramenta"] == ferramenta
    assert "DuckDB" in no_duckdb["dados"]["procedencia"]["metodo"]
    assert "PostGIS" in no_postgis["dados"]["procedencia"]["metodo"]


def test_juncao_espacial_no_duckdb_nao_perde_nem_inventa_ponto(
    env, inquilino_cg, fonte_pontos, fonte_poligonos, worker_cg,
):
    """A cláusula do portão é de contagem: com polígonos que não se sobrepõem, cada ponto sai uma vez só, e o
    total tem de bater com a contagem da tabela de origem lida direto no banco."""
    cliente = inquilino_cg.admin
    item = item_do_job(cliente, executar(cliente, "juncao_espacial", {
        "pontos": fonte_pontos["parquet_id"], "poligonos": fonte_poligonos["parquet_id"],
        "campo_chave": "codigo"}, titulo="zt juncao contagem"))
    na_origem = contar_no_banco(env, inquilino_cg, fonte_pontos["schema"], fonte_pontos["tabela"])
    assert item["dados"]["estatisticas"]["feicoes"] == na_origem


def test_detectar_duplicatas_acha_os_grupos_esperados(inquilino_cg, fonte_pontos, worker_cg):
    """A semeadura cria exatamente NAVIOS identificadores; agrupando por navio, todos repetem."""
    cliente = inquilino_cg.admin
    item = item_do_job(cliente, executar(cliente, "detectar_duplicatas", {
        "camada": fonte_pontos["parquet_id"], "campos": ["navio"], "mesma_posicao": False},
        titulo="zt duplicatas"))
    assert item["dados"]["estatisticas"]["feicoes"] == NAVIOS


# ---------------------------------------------------------------- cláusula 3: SQL do usuário recusado
DEZ_TENTATIVAS = [
    "SELECT * FROM read_parquet('/etc/hostname')",
    "SELECT * FROM read_parquet('/home/dev/plataforma/enterprise/app/limites.py')",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM read_csv_auto('/etc/passwd')",
    "SELECT * FROM read_parquet('https://exemplo.invalido/dados.parquet')",
    "SELECT * FROM read_json('http://exemplo.invalido/dados.json')",
    "ATTACH '/tmp/outro.duckdb' AS outro",
    "INSTALL httpfs",
    "LOAD httpfs",
    "SELECT * FROM glob('/etc/*')",
]


@pytest.mark.parametrize("sql", DEZ_TENTATIVAS)
def test_sql_do_usuario_com_leitura_de_arquivo_rede_attach_ou_install_e_recusado(
    inquilino_cg, fonte_pontos, worker_cg, sql,
):
    cliente = inquilino_cg.admin
    r = cliente.post("/api/ferramentas/consulta_sql/executar",
                     json={"parametros": {"fonte_a": fonte_pontos["parquet_id"], "sql": sql}, "modo": "job"})
    if r.status_code == 202:
        job = esperar(cliente, r.json()["job_id"], timeout=TEMPO_JOB)
        assert job["estado"] == "falhou", (sql, job)
        assert job["erro"], job
    else:
        assert r.status_code == 422, (sql, r.text)


def test_sao_dez_tentativas():
    assert len(DEZ_TENTATIVAS) == 10


def test_sql_do_usuario_legitimo_roda_e_conta_igual_ao_postgis(
    env, inquilino_cg, fonte_pontos, worker_cg,
):
    cliente = inquilino_cg.admin
    job = executar(cliente, "consulta_sql", {
        "fonte_a": fonte_pontos["parquet_id"],
        "sql": "SELECT navio, count(*) AS posicoes FROM fonte_a GROUP BY navio ORDER BY navio"},
        titulo="zt sql livre")
    item = item_do_job(cliente, job)
    assert item["dados"]["estatisticas"]["feicoes"] == NAVIOS
    na_origem = contar_no_banco(env, inquilino_cg, fonte_pontos["schema"], fonte_pontos["tabela"])
    assert na_origem > 0


# ---------------------------------------------------------------- cláusula 4: teto de tempo
def test_consulta_acima_do_teto_de_tempo_e_cancelada_com_mensagem(inquilino_cg, fonte_pontos, worker_cg):
    """Um produto cartesiano da fonte com ela mesma não termina dentro do teto; o job tem de FALHAR com a
    mensagem do teto, e não ficar pendurado nem devolver resultado parcial."""
    cliente = inquilino_cg.admin
    sql = ("SELECT a.navio, count(*) AS n FROM fonte_a a, fonte_a b "
           "WHERE a.carga + b.carga > 0 GROUP BY a.navio")
    r = cliente.post("/api/ferramentas/consulta_sql/executar", json={"parametros": {
        "fonte_a": fonte_pontos["parquet_id"], "sql": sql, "tempo_maximo_s": 3}, "modo": "job"})
    assert r.status_code == 202, r.text
    job = esperar(cliente, r.json()["job_id"], timeout=TEMPO_JOB)
    assert job["estado"] == "falhou", job
    assert "teto de 3 segundos" in (job["erro"] or ""), job


def test_teto_de_tempo_pedido_acima_do_da_plataforma_e_recusado(inquilino_cg, fonte_pontos, worker_cg):
    """O parâmetro só encolhe o teto, nunca o alarga: o máximo declarado é o da plataforma."""
    r = inquilino_cg.admin.post("/api/ferramentas/consulta_sql/executar", json={"parametros": {
        "fonte_a": fonte_pontos["parquet_id"], "sql": "SELECT count(*) AS n FROM fonte_a",
        "tempo_maximo_s": limites.CONSULTA_GRANDE_TEMPO_S + 1}})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"][0]["campo"] == "tempo_maximo_s", r.text


# ---------------------------------------------------------------- cláusula 5: proveniência da camada
def test_resultado_vira_camada_com_o_sql_e_o_sha256_dos_arquivos(
    inquilino_cg, fonte_pontos, worker_cg,
):
    cliente = inquilino_cg.admin
    sql = "SELECT navio, count(*) AS posicoes, min(instante) AS primeira FROM fonte_a GROUP BY navio"
    item = item_do_job(cliente, executar(cliente, "consulta_sql", {
        "fonte_a": fonte_pontos["parquet_id"], "sql": sql}, titulo="zt proveniencia"))
    procedencia = item["dados"]["procedencia"]
    consulta = procedencia["consulta_grande"]
    assert consulta["motor"] == "duckdb"
    assert consulta["sql"] == sql
    assert consulta["fontes"], consulta
    fonte = consulta["fontes"][0]
    assert fonte["item_id"] == fonte_pontos["parquet_id"]
    assert fonte["arquivos"], "a proveniência tem de nomear cada arquivo lido"
    for arquivo in fonte["arquivos"]:
        assert len(arquivo["sha256"]) == 64, arquivo
        assert arquivo["chave"]
    assert consulta["teto_tempo_s"] == limites.CONSULTA_GRANDE_TEMPO_S
    assert consulta["memoria_mb"] == limites.CONSULTA_GRANDE_MEMORIA_MB
    assert consulta["threads"] == limites.CONSULTA_GRANDE_THREADS
    assert consulta["duracao_ms"] >= 0
    # o item de resultado aponta para a fonte
    rel = cliente.get(f"/api/itens/{item['id']}/criado-a-partir-de").json()
    assert any(x["id"] == fonte_pontos["parquet_id"] for x in rel), rel


# ---------------------------------------------------------------- refutação: isolamento entre inquilinos
def test_parquet_de_outro_inquilino_nao_e_lido_por_item_nem_por_view(
    inquilino_cg, fonte_pontos, fonte_do_vizinho, worker_cg,
):
    cliente = inquilino_cg.admin
    # (a) apontando o item do vizinho no parâmetro: a resolução da fonte nem confirma que ele existe
    r = cliente.post("/api/ferramentas/consulta_sql/executar", json={"parametros": {
        "fonte_a": fonte_do_vizinho["parquet_id"], "sql": "SELECT count(*) AS n FROM fonte_a"}})
    assert r.status_code == 404, r.text
    # (b) nomeando uma view que não foi injetada: o portão recusa antes de qualquer leitura
    r = cliente.post("/api/ferramentas/consulta_sql/executar", json={"parametros": {
        "fonte_a": fonte_pontos["parquet_id"], "sql": "SELECT count(*) FROM fonte_b"}, "modo": "job"})
    if r.status_code == 202:
        job = esperar(cliente, r.json()["job_id"], timeout=TEMPO_JOB)
        assert job["estado"] == "falhou", job
        assert "relação" in (job["erro"] or "") or "relacao" in (job["erro"] or ""), job
    else:
        assert r.status_code == 422, r.text


# ---------------------------------------------------------------- refutação: cinco ao mesmo tempo serializam
def test_cinco_consultas_grandes_ao_mesmo_tempo_sao_serializadas_pela_fila(
    inquilino_cg, fonte_pontos, worker_cg,
):
    """O worker segura um advisory lock enquanto há filho `pesado` rodando (app/jobs/worker.py). Cinco jobs
    grandes enfileirados de uma vez não podem estar `executando` ao mesmo tempo: é isso, e não um semáforo
    novo, que garante uma consulta grande de cada vez por base."""
    cliente = inquilino_cg.admin
    ids = []
    for i in range(5):
        r = cliente.post("/api/ferramentas/consulta_sql/executar", json={"parametros": {
            "fonte_a": fonte_pontos["parquet_id"],
            "sql": f"SELECT navio, count(*) AS n, {i} AS rodada FROM fonte_a GROUP BY navio"},
            "modo": "job", "titulo": f"zt paralelo {i}"})
        assert r.status_code == 202, r.text
        ids.append(r.json()["job_id"])
    maximo_simultaneo = 0
    fim = time.monotonic() + TEMPO_JOB
    estados = {}
    while time.monotonic() < fim:
        estados = {j: cliente.get(f"/api/jobs/{j}").json()["estado"] for j in ids}
        maximo_simultaneo = max(maximo_simultaneo, sum(1 for e in estados.values() if e == "executando"))
        if all(e in ("concluido", "falhou", "cancelado") for e in estados.values()):
            break
        time.sleep(0.2)
    assert all(e == "concluido" for e in estados.values()), estados
    assert maximo_simultaneo <= 1, (
        f"{maximo_simultaneo} consultas grandes executando ao mesmo tempo; a fila devia serializar")
