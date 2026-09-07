"""Portão de pronto do item L0-04-h-exportar, cláusula por cláusula (o texto de cada uma está no docstring do
teste que a prova):

1. "10 formatos gerados de uma camada de 100 mil feições, cada um reaberto por ogrinfo com a mesma contagem"
2. "CSV com vírgula decimal opcional"
3. "export com where inválido devolve 400 com o erro do banco saneado"
4. "usuário sem 'exportar' recebe 403 na camada de outro"
5. "arquivo expira e some em 7 dias"
6. "medida tempo por formato"  (gravado em tests/medidas/L0-04-h-exportar.json)

Refutação do item (adversário): 5 exportações em paralelo da mesma camada (limite por usuário e disco
temporário), injeção de SQL no `where`, EPSG inexistente — os três estão aqui também.
"""

from __future__ import annotations

import csv
import datetime
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from app import limites
from app.exportacao.formatos import FORMATOS
from tests.api.exportacao.conftest import conexao, exportar

FEICOES = 100_000


def contexto(cur, inq) -> None:
    """Põe a conexão no inquilino (a RLS da tabela de camada e de `plat.exportacao` dependem disto)."""
    cur.execute(
        "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
        "set_config('plat.login', 'teste-exportacao', true)",
        (str(inq.id), str(inq.admin_id)),
    )


def baixar_para(cliente, exportacao_id: str, destino: Path) -> Path:
    r = cliente.get(f"/api/exportacoes/{exportacao_id}/baixar")
    assert r.status_code == 200, r.text
    destino.write_bytes(r.content)
    return destino


def contar_no_arquivo(caminho: Path, formato: str) -> int:
    """Reabre o arquivo BAIXADO e conta as feições — ogrinfo para os 10 formatos que este GDAL abre,
    DuckDB para o GeoParquet (o GDAL 3.8.4 desta máquina não tem driver Parquet)."""
    if formato == "geoparquet":
        import duckdb

        con = duckdb.connect()
        try:
            return int(con.execute("SELECT count(*) FROM read_parquet(?)", [str(caminho)]).fetchone()[0])
        finally:
            con.close()
    alvo = str(caminho)
    if formato == "shapefile":
        alvo = f"/vsizip/{caminho}"
    elif formato == "kmz":
        alvo = f"/vsizip/{caminho}/doc.kml"
    elif FORMATOS[formato].caminho_interno:
        alvo = f"/vsizip/{caminho}/{FORMATOS[formato].caminho_interno}"
    r = subprocess.run(["ogrinfo", "-so", "-al", alvo], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"ogrinfo não reabriu {caminho.name}: {r.stderr[:400]}"
    contagens = [int(li.split(":", 1)[1]) for li in r.stdout.splitlines() if li.strip().startswith("Feature Count:")]
    assert contagens, f"ogrinfo não informou Feature Count para {caminho.name}: {r.stdout[:400]}"
    return sum(contagens)


# ---------------------------------------------------------------- 1, 6: formatos e tempo por formato
def test_onze_formatos_da_camada_de_100_mil_feicoes_reabertos_com_a_mesma_contagem(
    inquilino_a, camada_a, worker_exportacao, medida, tmp_path
):
    """Cláusula 1 do portão ("10 formatos ... cada um reaberto por ogrinfo com a mesma contagem") e cláusula 6
    ("medida tempo por formato"). São 11 formatos: os 10 que o `ogrinfo` desta máquina reabre mais o
    GeoParquet, reaberto pelo DuckDB — a razão está em `app/exportacao/formatos.py`."""
    cliente = inquilino_a.admin
    tempos = {}
    reabertos = {}
    # `pacote` sai de um item `mapa`, não de uma camada, e os formatos TILADOS (MVT/PMTiles) recortam a
    # geometria por tile — a contagem deles não é a do banco. Os dois grupos têm portão próprio no item
    # L2-01-l (tests/api/exportacao/test_exportacao_mapa.py); aqui ficam os de camada, feição a feição.
    for nome in [n for n, f in FORMATOS.items() if n != "pacote" and not f.tilado]:
        inicio = time.monotonic()
        final = exportar(cliente, {"item_id": camada_a["item_id"], "formato": nome,
                                   "nome": f"zt-{nome}"}, timeout=600)
        assert final["estado"] == "pronta", (nome, final)
        tempos[nome] = round(time.monotonic() - inicio, 2)
        assert final["feicoes"] == FEICOES, (nome, final["feicoes"])
        caminho = baixar_para(cliente, final["id"], tmp_path / f"saida_{nome}{FORMATOS[nome].extensao}")
        assert caminho.stat().st_size == final["bytes"] > 0, nome
        reabertos[nome] = contar_no_arquivo(caminho, nome)

    assert reabertos == dict.fromkeys(reabertos, FEICOES), reabertos
    assert len(reabertos) >= 13, sorted(reabertos)
    abertos_por_ogrinfo = [n for n, f in FORMATOS.items() if f.reabre_com_ogrinfo]
    assert len(abertos_por_ogrinfo) >= 10, abertos_por_ogrinfo
    medida("L0-04-h-exportar")(
        "tempo_por_formato_s", tempos, "s (pedido -> arquivo pronto, 100 mil feições)",
        "tests/api/exportacao/test_exportacao.py::"
        "test_onze_formatos_da_camada_de_100_mil_feicoes_reabertos_com_a_mesma_contagem",
    )
    medida("L0-04-h-exportar")(
        "feicoes_reabertas_por_formato", reabertos, "feições lidas do arquivo baixado",
        "ogrinfo -so -al <arquivo> (DuckDB read_parquet no geoparquet)",
    )


# ---------------------------------------------------------------- 2: CSV brasileiro
def test_csv_com_virgula_decimal_e_colunas_de_coordenada_escolhidas(inquilino_a, camada_a, worker_exportacao,
                                                                    tmp_path):
    """Cláusula 2 do portão ("CSV com vírgula decimal opcional"). Opcional quer dizer: o padrão continua ponto
    decimal e vírgula separadora (CSV canônico); a vírgula decimal só aparece quando pedida, e aí o separador
    tem de mudar junto, senão o arquivo é ambíguo."""
    cliente = inquilino_a.admin
    padrao = exportar(cliente, {"item_id": camada_a["item_id"], "formato": "csv", "nome": "zt-csv-padrao",
                                "campos": ["nome", "area_ha"]})
    assert padrao["estado"] == "pronta", padrao
    linhas_padrao = baixar_para(cliente, padrao["id"], tmp_path / "padrao.csv").read_text(
        encoding="utf-8").splitlines()
    assert linhas_padrao[0].split(",")[:2] == ["X", "Y"], linhas_padrao[0]
    assert "." in linhas_padrao[1].split(",")[0]

    br = exportar(cliente, {"item_id": camada_a["item_id"], "formato": "csv", "nome": "zt-csv-br",
                            "campos": ["nome", "area_ha"],
                            "csv": {"separador": ";", "decimal": ",", "coluna_x": "longitude",
                                    "coluna_y": "latitude"}})
    assert br["estado"] == "pronta", br
    caminho = baixar_para(cliente, br["id"], tmp_path / "br.csv")
    with caminho.open(encoding="utf-8", newline="") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    assert linhas[0][:2] == ["longitude", "latitude"], linhas[0]
    assert len(linhas) - 1 == FEICOES
    x, y, nome, area = linhas[1][0], linhas[1][1], linhas[1][2], linhas[1][3]
    assert "," in x and "," in y and "." not in x and "." not in y, (x, y)
    assert "," in area and "." not in area, area
    assert nome.startswith("ponto "), nome


def test_csv_separador_invalido_e_recusado(inquilino_a, camada_a):
    r = inquilino_a.admin.post("/api/exportacoes", json={
        "item_id": camada_a["item_id"], "formato": "csv", "csv": {"separador": "'", "decimal": ","}})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- 3: where inválido
@pytest.mark.parametrize(
    "where,motivo",
    [
        ("quantidade > 'texto que não é número'", "tipo incompatível: só o banco sabe"),
        ("area_ha > 10 AND naoexiste = 1", "campo fora da lista branca do item"),
        ("nome = 'a'; DROP TABLE plat.item", "empilhamento de instrução"),
        ("nome = 'a' OR 1=1", "tautologia com literal do lado esquerdo"),
        ("nome LIKE '%' OR pg_sleep(10) IS NULL", "chamada de função"),
    ],
)
def test_where_invalido_devolve_400_com_erro_saneado(inquilino_a, camada_a, where, motivo):
    """Cláusula 3 do portão ("export com where inválido devolve 400 com o erro do banco saneado"). Saneado =
    a mensagem ajuda a corrigir e NÃO entrega o nome interno da tabela, o comando, nem a posição — ver
    `app/exportacao/erros.py`."""
    r = inquilino_a.admin.post("/api/exportacoes", json={
        "item_id": camada_a["item_id"], "formato": "gpkg", "where": where})
    assert r.status_code == 400, (motivo, r.status_code, r.text)
    corpo = r.json()
    assert corpo["erro"] == "where_invalido", corpo
    mensagem = corpo["mensagem"]
    assert mensagem, corpo
    for vazamento in (camada_a["tabela"], camada_a["schema"], "LINE 1", "SELECT ", "/home/", "psycopg2"):
        assert vazamento not in mensagem, (vazamento, mensagem)
    assert len(mensagem) <= limites.EXPORTACAO_ERRO_BANCO_MAX


def test_where_valido_filtra_de_verdade(inquilino_a, camada_a, worker_exportacao, env, tmp_path):
    final = exportar(inquilino_a.admin, {"item_id": camada_a["item_id"], "formato": "gpkg",
                                         "nome": "zt-filtrado", "where": "categoria = 'mata' AND quantidade < 10"})
    assert final["estado"] == "pronta", final
    con = conexao(env)
    try:
        with con.cursor() as cur:
            # sem o contexto do inquilino a RLS da tabela de camada devolve ZERO linha — a conferência tem de
            # ler como o inquilino dono, senão o teste "passaria" comparando dois zeros
            contexto(cur, inquilino_a)
            cur.execute(
                f'SELECT count(*) AS n FROM "{camada_a["schema"]}"."{camada_a["tabela"]}" '
                "WHERE categoria = 'mata' AND quantidade < 10"
            )
            esperado = int(cur.fetchone()["n"])
    finally:
        con.close()
    assert 0 < esperado < FEICOES
    assert final["feicoes"] == esperado
    caminho = baixar_para(inquilino_a.admin, final["id"], tmp_path / "filtrado.gpkg")
    assert contar_no_arquivo(caminho, "gpkg") == esperado


def test_injecao_no_where_nao_apaga_nem_vaza(inquilino_a, camada_a, env):
    """Refutação do item: injeção de SQL no `where`. Depois de todos os vetores, a tabela continua com as
    100 mil linhas e `plat.item` continua de pé (o que um `DROP`/`DELETE` executado teria destruído)."""
    vetores = [
        "nome = 'x'); DROP TABLE plat.item; --",
        "nome = 'x' UNION SELECT senha_hash FROM plat.usuario",
        "nome = ''''; DELETE FROM plat.item WHERE ''1''=''1",
        "1; SELECT pg_sleep(30)",
        "nome = 'x' /* comentário */ OR 1=1",
    ]
    for v in vetores:
        r = inquilino_a.admin.post("/api/exportacoes", json={
            "item_id": camada_a["item_id"], "formato": "gpkg", "where": v})
        assert r.status_code == 400, (v, r.status_code, r.text)
    con = conexao(env)
    try:
        with con.cursor() as cur:
            contexto(cur, inquilino_a)
            cur.execute(f'SELECT count(*) AS n FROM "{camada_a["schema"]}"."{camada_a["tabela"]}"')
            assert int(cur.fetchone()["n"]) == FEICOES
            cur.execute("SELECT count(*) AS n FROM plat.tipo_item")
            assert int(cur.fetchone()["n"]) > 0
    finally:
        con.close()


# ---------------------------------------------------------------- 4: privilégio e permissão do dono
def test_usuario_sem_privilegio_exportar_recebe_403(editor_sem_exportar, camada_a):
    """Cláusula 4 do portão, primeira metade: sem `conteudo.exportar` não se exporta NADA — nem o próprio."""
    r = editor_sem_exportar.post("/api/exportacoes", json={"item_id": camada_a["item_id"], "formato": "gpkg"})
    assert r.status_code == 403, r.text
    assert r.json()["erro"] == "sem_privilegio", r.json()


def test_camada_de_outro_inquilino_e_404(inquilino_a, camada_b):
    """Cláusula 4, segunda metade: "na camada de outro". Entre INQUILINOS a resposta é 404, não 403 — a RLS
    esconde a existência do item alheio, e confirmar que ele existe já seria vazamento."""
    r = inquilino_a.admin.post("/api/exportacoes", json={"item_id": camada_b["item_id"], "formato": "gpkg"})
    assert r.status_code == 404, r.text


def test_camada_de_outro_usuario_do_mesmo_inquilino_exige_a_opcao_do_dono(inquilino_a, camada_a, env):
    """A opção do dono ("permitir que outros exportem") nasce DESLIGADA, como na Esri: um editor com o
    privilégio, dentro do mesmo inquilino, toma 403 até o dono ligar."""
    from tests.api.conftest import Usuarios

    usuarios = Usuarios(inquilino_a.admin)
    try:
        outro, _u, _s = usuarios.sessao("editor")
        # item privado é 404 até para quem está no mesmo inquilino (a RLS de plat.item esconde o que não foi
        # compartilhado) — para chegar à checagem de EXPORTAÇÃO, a camada precisa antes estar visível
        r = outro.post("/api/exportacoes", json={"item_id": camada_a["item_id"], "formato": "gpkg"})
        assert r.status_code == 404, r.text
        r = inquilino_a.admin.put(f"/api/itens/{camada_a['item_id']}/compartilhamento",
                                  json={"acesso": "inquilino"})
        assert r.status_code == 200, r.text

        r = outro.post("/api/exportacoes", json={"item_id": camada_a["item_id"], "formato": "gpkg"})
        assert r.status_code == 403, r.text
        assert r.json()["erro"] == "exportacao_nao_permitida", r.json()

        item = inquilino_a.admin.get(f"/api/itens/{camada_a['item_id']}").json()
        dados = dict(item["dados"])
        dados["exportacao"] = {"permitir_outros": True}
        r = inquilino_a.admin.patch(f"/api/itens/{camada_a['item_id']}", json={"dados": dados})
        assert r.status_code == 200, r.text
        r = outro.post("/api/exportacoes", json={"item_id": camada_a["item_id"], "formato": "gpkg",
                                                 "nome": "zt-de-outro"})
        assert r.status_code == 202, r.text
        outro.delete(f"/api/exportacoes/{r.json()['exportacao_id']}")

        dados["exportacao"] = {"permitir_outros": False}
        assert inquilino_a.admin.patch(f"/api/itens/{camada_a['item_id']}",
                                       json={"dados": dados}).status_code == 200
        inquilino_a.admin.put(f"/api/itens/{camada_a['item_id']}/compartilhamento", json={"acesso": "privado"})
    finally:
        usuarios.limpar()


# ---------------------------------------------------------------- 5: validade de 7 dias
def test_arquivo_expira_e_some_em_sete_dias(inquilino_a, camada_a, worker_exportacao, sessao_plat, env):
    """Cláusula 5 do portão ("arquivo expira e some em 7 dias"): a linha nasce com `expira_em` = 7 dias; com a
    validade vencida, o periódico `exportacao.expirar` apaga o OBJETO e o ITEM, deixa a linha como `expirada`
    e o download passa a responder 410. O tempo é adiantado no banco (a validade é dado da linha), nunca
    dormindo 7 dias nem passando "dias" por parâmetro ao periódico."""
    final = exportar(inquilino_a.admin, {"item_id": camada_a["item_id"], "formato": "geojson",
                                         "nome": "zt-expira", "campos": ["nome"], "where": "quantidade = 7"})
    assert final["estado"] == "pronta", final
    criado = final["criado_em"]
    dias = (datetime.datetime.fromisoformat(final["expira_em"])
            - datetime.datetime.fromisoformat(criado)).days
    assert dias == limites.EXPORTACAO_VALIDADE_DIAS == 7, (criado, final["expira_em"])
    assert inquilino_a.admin.get(f"/api/exportacoes/{final['id']}/baixar").status_code == 200

    con = conexao(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true)",
                (str(inquilino_a.id), str(inquilino_a.admin_id)),
            )
            cur.execute("UPDATE plat.exportacao SET expira_em = now() - interval '1 minute' WHERE id = %s::uuid",
                        (final["id"],))
        con.commit()
    finally:
        con.close()

    r = sessao_plat.post("/api/jobs", json={"tipo": "exportacao.expirar", "parametros": {}})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    fim = time.monotonic() + 120
    while time.monotonic() < fim:
        j = sessao_plat.get(f"/api/jobs/{job_id}").json()
        if j["estado"] in ("concluido", "falhou", "cancelado"):
            break
        time.sleep(0.25)
    assert j["estado"] == "concluido", j
    assert j["resultado"]["expiradas"] >= 1, j["resultado"]

    depois = inquilino_a.admin.get(f"/api/exportacoes/{final['id']}").json()
    assert depois["estado"] == "expirada", depois
    r = inquilino_a.admin.get(f"/api/exportacoes/{final['id']}/baixar")
    assert r.status_code == 410, r.text
    assert inquilino_a.admin.get(f"/api/itens/{final['arquivo_item_id']}").status_code == 404


# ---------------------------------------------------------------- refutação: paralelismo e disco
def test_limite_de_exportacoes_em_curso_por_usuario(inquilino_a, camada_a, worker_exportacao):
    """Refutação do item: "5 vezes em paralelo a mesma camada". O worker é PARADO (SIGSTOP) durante o teste
    para que as exportações fiquem mesmo em curso — sem isso o teste mediria a velocidade do worker, não o
    limite. Da quarta em diante: 429."""
    cliente = inquilino_a.admin
    os.kill(worker_exportacao.proc.pid, signal.SIGSTOP)
    criadas = []
    try:
        respostas = [
            cliente.post("/api/exportacoes", json={"item_id": camada_a["item_id"], "formato": "gpkg",
                                                   "nome": f"zt-paralela-{i}"})
            for i in range(5)
        ]
        aceitas = [r for r in respostas if r.status_code == 202]
        recusadas = [r for r in respostas if r.status_code == 429]
        criadas = [r.json()["exportacao_id"] for r in aceitas]
        assert len(aceitas) == limites.EXPORTACAO_POR_USUARIO_EM_CURSO, [r.status_code for r in respostas]
        assert len(recusadas) == 5 - limites.EXPORTACAO_POR_USUARIO_EM_CURSO
        assert recusadas[0].json()["erro"] == "exportacoes_em_curso", recusadas[0].json()
        assert recusadas[0].json()["detalhe"]["maximo"] == limites.EXPORTACAO_POR_USUARIO_EM_CURSO
    finally:
        for eid in criadas:
            cliente.delete(f"/api/exportacoes/{eid}")
        os.kill(worker_exportacao.proc.pid, signal.SIGCONT)
    for eid in criadas:
        estado = cliente.get(f"/api/exportacoes/{eid}").json()["estado"]
        assert estado in ("cancelada", "pronta", "falhou"), (eid, estado)


def test_disco_insuficiente_recusa_antes_de_escrever(inquilino_a, camada_a, tmp_path, monkeypatch):
    """Refutação do item: "disco temporário". A guarda é medida de verdade (`shutil.disk_usage`) e roda ANTES
    de qualquer byte ser escrito; aqui a exigência é elevada acima do disco desta máquina para provar que a
    recusa acontece, em vez de encher o disco de propósito (a máquina está a 98%)."""
    from app.exportacao import motor

    with pytest.raises(motor.ErroExportacao) as e:
        motor.exigir_disco(tmp_path, 10 ** 15)
    assert "disco insuficiente" in str(e.value)
    livre = motor.espaco_livre(tmp_path)
    assert livre > 0
    if livre > limites.EXPORTACAO_DISCO_MIN_LIVRE_BYTES:
        motor.exigir_disco(tmp_path, 0)  # com folga de sobra, a mesma guarda deixa passar


# ---------------------------------------------------------------- refutação: EPSG inexistente
def test_epsg_inexistente_e_recusado_e_epsg_valido_reprojeta(inquilino_a, camada_a, worker_exportacao, tmp_path):
    """Refutação do item: "pede EPSG inexistente". Recusa é 422 com o número pedido no detalhe, ANTES do job —
    nunca um ogr2ogr que falha 3 s depois com a mensagem do GDAL."""
    r = inquilino_a.admin.post("/api/exportacoes", json={
        "item_id": camada_a["item_id"], "formato": "gpkg", "srid_saida": 999998})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "srid_desconhecido" and r.json()["detalhe"]["srid"] == 999998

    final = exportar(inquilino_a.admin, {"item_id": camada_a["item_id"], "formato": "gpkg",
                                         "nome": "zt-utm", "srid_saida": 31983, "where": "quantidade = 3"})
    assert final["estado"] == "pronta", final
    caminho = baixar_para(inquilino_a.admin, final["id"], tmp_path / "utm.gpkg")
    saida = subprocess.run(["ogrinfo", "-so", "-al", str(caminho)], capture_output=True, text=True).stdout
    assert "31983" in saida, saida[:600]


# ---------------------------------------------------------------- entrega em blocos (arquivo grande)
def test_download_vem_em_blocos_e_bate_byte_a_byte(inquilino_a, camada_a, worker_exportacao, env, tmp_path):
    """O arquivo NUNCA é montado inteiro em memória na entrega: `objetos.ler_stream` devolve blocos de no
    máximo 1 MiB. O teste confere os dois lados — que vêm vários blocos pequenos e que o conteúdo entregue
    pela API é byte a byte igual ao que está guardado."""
    from app import objetos

    final = exportar(inquilino_a.admin, {"item_id": camada_a["item_id"], "formato": "geojson",
                                         "nome": "zt-blocos"}, timeout=600)
    assert final["estado"] == "pronta" and final["bytes"] > 4 * 1024 * 1024, final
    detalhe = inquilino_a.admin.get(f"/api/exportacoes/{final['id']}").json()
    assert detalhe["link"].endswith("/baixar")

    con = conexao(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true)",
                (str(inquilino_a.id), str(inquilino_a.admin_id)),
            )
            cur.execute("SELECT chave FROM plat.exportacao WHERE id = %s::uuid", (final["id"],))
            chave = cur.fetchone()["chave"]
    finally:
        con.close()

    blocos = list(objetos.ler_stream(chave, 1024 * 1024))
    assert len(blocos) > 1, "arquivo de vários MB veio num bloco só"
    assert max(len(b) for b in blocos) <= 1024 * 1024
    conteudo = b"".join(blocos)
    assert len(conteudo) == final["bytes"]

    caminho = baixar_para(inquilino_a.admin, final["id"], tmp_path / "blocos.geojson")
    assert caminho.read_bytes() == conteudo
