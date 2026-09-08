"""Ataque adversarial G3 — ingestão vetorial (itens L0-04-ingest-vetor, L0-04-b-inspecao, L0-04-c-tabela-camada,
L0-04-d-formatos-base). Todo teste aqui é uma CLÁUSULA LITERAL do portão de pronto ou da refutação do item.
Marcados `xfail(strict=True)`: viram prova no dia em que alguém consertar."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.api.ingestao.conftest import esperar_job

FORMATOS_DO_PORTAO = ["kml", "kmz", "gpx", "xlsx", "gml", "flatgeobuf", "dxf", "gdb"]


def _importar_bruto(ing, caminho: Path, formato: str):
    """Sobe o arquivo e pede a importação; devolve a RESPOSTA CRUA do POST /api/importacoes (sem assert)."""
    obj = ing.enviar_arquivo(caminho)
    item_id = ing.item_arquivo(obj, caminho.name)
    return ing.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": formato})


# --------------------------------------------------------------- L0-04-d: formatos do portão
@pytest.mark.xfail(
    strict=True,
    reason="L0-04-d: a instalacao anuncia 4 formatos (csv, geojson, gpkg, shapefile.zip); o portao exige 9",
)
def test_formatos_anunciados_cobrem_os_9_do_portao(sessao_a):
    """Portão do L0-04-d: 'teste automatizado com 1 arquivo aberto por formato (9 arquivos)'.
    Formatos exigidos: shapefile zip, GeoPackage, GeoJSON/GeoJSONSeq, KML/KMZ, CSV/TXT, GPX, XLSX/XLS."""
    r = sessao_a.get("/api/importacoes/formatos")
    assert r.status_code == 200, r.text
    tipos = sorted(f["tipo"] for f in r.json())
    assert len(tipos) >= 7, f"a instalação anuncia só {len(tipos)} formatos: {tipos}"


@pytest.mark.parametrize("formato", FORMATOS_DO_PORTAO)
@pytest.mark.xfail(
    strict=True,
    reason="L0-04-b/L0-04-d: KML/KMZ/GPX/XLSX/GML/FlatGeobuf/DXF/GDB nao existem na instalacao (formato_nao_suportado)",
)
def test_formato_do_portao_e_aceito(ingestor_a, arquivos_de_ataque, formato):
    """Cada formato que o portão do item pai lista tem de ser ACEITO (importar ou perguntar), nunca recusado
    como inexistente. Hoje só existem 4 formatos (app/ingestao/formatos.py FORMATOS)."""
    r = _importar_bruto(ingestor_a, arquivos_de_ataque / "tres_camadas.gpkg", formato)
    assert r.status_code != 422 or r.json().get("erro") != "formato_nao_suportado", \
        f"formato {formato} não existe nesta instalação: {r.text[:200]}"


# --------------------------------------------------------------- L0-04-b: 12 arquivos, multi-camada
@pytest.mark.xfail(strict=True, reason="L0-04-b/c: inspecionar.py usa camadas[0]; as camadas 2..N somem sem aviso")
def test_gpkg_com_3_camadas_propoe_as_3(ingestor_a, arquivos_de_ataque):
    """Portão literal do L0-04-b: 'GPKG com 3 camadas' entre os 12 arquivos, e do L0-04-c: '1 job por arquivo,
    N camadas'. inspecionar.py usa `camada = camadas[0]` e descarta as demais SEM AVISO."""
    obj = ingestor_a.enviar_arquivo(arquivos_de_ataque / "tres_camadas.gpkg")
    item_id = ingestor_a.item_arquivo(obj, "tres_camadas.gpkg")
    r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "gpkg"})
    assert r.status_code == 202, r.text
    esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=90)
    imp = ingestor_a.sessao.get(f"/api/importacoes/{r.json()['importacao_id']}").json()
    proposta = imp.get("proposta") or {}
    texto = json.dumps(imp, ensure_ascii=False)
    assert "camada_dois" in texto and "camada_tres" in texto, \
        f"a proposta só cita a 1ª camada; estado={imp['estado']}; proposta={json.dumps(proposta)[:400]}"


@pytest.mark.xfail(
    strict=True,
    reason="L0-04-b refutacao: CSV de 300 colunas e 0 linhas termina em proposta sem pergunta nem aviso (silencio)",
)
def test_csv_300_colunas_e_0_linhas_recusa_com_mensagem_na_inspecao(ingestor_a, arquivos_de_ataque):
    """Refutação literal do L0-04-b: 'adversário envia CSV com 300 colunas e 0 linhas ... silêncio ou 500 =
    refutado'. Hoje a inspeção conclui SEM pergunta e SEM aviso: o silêncio é a resposta."""
    obj = ingestor_a.enviar_arquivo(arquivos_de_ataque / "largo_300_colunas.csv")
    item_id = ingestor_a.item_arquivo(obj, "largo_300_colunas.csv")
    r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "csv"})
    assert r.status_code == 202, r.text
    esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=90)
    imp = ingestor_a.sessao.get(f"/api/importacoes/{r.json()['importacao_id']}").json()
    proposta = imp.get("proposta") or {}
    falou = bool(proposta.get("perguntas")) or bool(proposta.get("avisos")) or imp["estado"] == "falhou"
    assert falou, (f"inspeção terminou em '{imp['estado']}' sem pergunta nem aviso para um CSV de 300 colunas e "
                   f"0 linhas: perguntas={proposta.get('perguntas')} avisos={proposta.get('avisos')}")


# --------------------------------------------------------------- refutação: entrada malformada nunca 500
@pytest.mark.parametrize("nome", ["zip_corrompido.zip", "zip_aninhado.zip"])
@pytest.mark.xfail(
    strict=True,
    reason="L0-04-b refutacao: rotas.py captura ConteudoNaoCorresponde e nao ZipSuspeito (classes irmas) -> 500",
)
def test_zip_malformado_devolve_422_e_nunca_500(ingestor_a, arquivos_de_ataque, nome):
    """Refutação literal do item pai: 'cada um tem de ou importar certo ou recusar com mensagem exata —
    silêncio = refutado'; e do L0-04-b: 'silêncio ou 500 = refutado'. app/ingestao/rotas.py captura
    ConteudoNaoCorresponde mas NÃO ZipSuspeito (classes irmãs, não mãe/filha)."""
    r = _importar_bruto(ingestor_a, arquivos_de_ataque / nome, "shapefile.zip")
    assert r.status_code == 422, f"esperado 422 com mensagem; veio {r.status_code}: {r.text[:300]}"


def test_geojson_com_crs_legado_31982_e_perguntado_ou_avisado(ingestor_a, arquivos_de_ataque):
    """Refutação literal do L0-04-d: 'GeoJSON com crs legado em 31982 (deve avisar e reprojetar ou perguntar)'.
    inspecionar.py acha o EPSG por regex nos primeiros 4096 bytes e grava perguntar=False, e o único aviso é
    removido da proposta com `crs.pop('aviso')`."""
    obj = ingestor_a.enviar_arquivo(arquivos_de_ataque / "crs_legado_31982.geojson")
    item_id = ingestor_a.item_arquivo(obj, "crs_legado_31982.geojson")
    r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "geojson"})
    assert r.status_code == 202, r.text
    esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=90)
    imp = ingestor_a.sessao.get(f"/api/importacoes/{r.json()['importacao_id']}").json()
    proposta = imp.get("proposta") or {}
    crs = proposta.get("crs") or {}
    perguntou = "crs" in (proposta.get("perguntas") or []) or bool(crs.get("perguntar"))
    avisou = any("crs" in str(a).lower() or "31982" in str(a) for a in (proposta.get("avisos") or []))
    assert perguntou or avisou, f"nem perguntou nem avisou: crs={json.dumps(crs)} avisos={proposta.get('avisos')}"


# --------------------------------------------------------------- L0-04-b: arquivo grande demais
@pytest.mark.lento
# NAO e xfail: a 1 milhao de vertices a inspecao AGUENTA (14,8 s medidos). Fica como
# regua: se um teto de vertices/bytes for criado, este teste diz onde ele corta.
def test_geojson_de_uma_feicao_com_um_milhao_de_vertices(ingestor_a, geojson_muitos_vertices, tmp_path):
    """Refutação literal do L0-04-b: 'GeoJSON de 1 feição com 10 milhões de vértices; silêncio ou 500 =
    refutado'. Aqui a 1 milhão (1/10 da escala; ver fronteira no laudo). Mede tempo_inspecao_s e exige que a
    resposta seja uma proposta OU uma recusa com mensagem — nunca um job que morre sem explicação."""
    tamanho = geojson_muitos_vertices.stat().st_size
    obj = ingestor_a.enviar_arquivo(geojson_muitos_vertices)
    item_id = ingestor_a.item_arquivo(obj, geojson_muitos_vertices.name)
    t0 = time.monotonic()
    r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "geojson"})
    assert r.status_code == 202, r.text
    job = esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=600)
    dt = time.monotonic() - t0
    imp = ingestor_a.sessao.get(f"/api/importacoes/{r.json()['importacao_id']}").json()
    medida = {"bytes": tamanho, "vertices": 1_000_000, "tempo_inspecao_s": round(dt, 1),
              "job_estado": job["estado"], "job_erro": (job.get("erro") or "")[:300],
              "importacao_estado": imp["estado"], "importacao_erro": (imp.get("erro") or "")[:300]}
    Path("tests/medidas").mkdir(parents=True, exist_ok=True)
    Path("tests/medidas/adv-g3-vertices.json").write_text(json.dumps(medida, ensure_ascii=False, indent=2))
    assert job["estado"] == "concluido" or (job["estado"] == "falhou" and job.get("erro")), \
        f"nem proposta nem recusa explicada: {json.dumps(medida, ensure_ascii=False)}"
    assert dt <= 60, f"inspeção de 1 milhão de vértices levou {dt:.1f} s (portão: 100 mil feições em ≤ 5 s)"


# --------------------------------------------------------------- rota de descoberta de formatos
@pytest.mark.xfail(
    strict=True,
    reason="L0-04-d: GET /api/importacoes/formatos declarada depois de /api/importacoes/{id} -> 404 "
           "importacao_inexistente",
)
def test_rota_de_formatos_de_importacao_e_alcancavel(sessao_a):
    """`GET /api/importacoes/formatos` é declarada DEPOIS de `GET /api/importacoes/{id}` em
    app/ingestao/rotas.py, e o parâmetro de caminho é livre: a rota de descoberta nunca é alcançada."""
    r = sessao_a.get("/api/importacoes/formatos")
    assert r.status_code == 200, (f"a rota que anuncia os formatos responde {r.status_code} "
                                  f"(engolida por /api/importacoes/{{id}}): {r.text[:200]}")


# --------------------------------------------------------------- medidas exigidas pelos portões
@pytest.mark.xfail(
    strict=True,
    reason="L0-04-b/c: nenhuma medida tempo_inspecao_s nem tempo_import_100k_s existe em tests/medidas",
)
def test_medidas_de_desempenho_da_ingestao_estao_gravadas():
    """Portão do L0-04-b: 'medida tempo_inspecao_s por arquivo (100 mil feições ≤ 5 s)'. Portão do L0-04-c:
    'shapefile de 100 mil feições ... em ≤ 60 s medido (medida tempo_import_100k_s)'. O BRIEF do laço manda
    gravar cada medida em tests/medidas/<item>.json. Não existe nenhum arquivo de medida de L0-04."""
    import json as _json
    from pathlib import Path
    achadas = {}
    for arq in Path("tests/medidas").glob("*.json"):
        try:
            dados = _json.loads(arq.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for chave in ("tempo_inspecao_s", "tempo_import_100k_s"):
            if chave in _json.dumps(dados):
                achadas[chave] = arq.name
    assert set(achadas) == {"tempo_inspecao_s", "tempo_import_100k_s"}, \
        f"medidas do portão ausentes; achadas: {achadas}; "\
        f"arquivos: {sorted(p.name for p in Path('tests/medidas').glob('*.json'))}"


# --------------------------------------------------------------- isolamento do schema de dados
@pytest.mark.xfail(
    strict=True,
    reason="L0-04-c: d_<slug> sem prefixo de instalacao; producao, homologacao e trilhas partilham d_demo",
)
def test_schema_de_dados_do_inquilino_e_isolado_por_instalacao():
    """Hipótese do L0-04-c: 'tabela física no schema do inquilino d_<slug>'. O nome vem SÓ do slug
    (plat.camada_schema_garantir: 'd_' || p_slug), sem prefixo de instalação — duas instalações no mesmo
    banco (produção, homologação e as trilhas deste laço) escrevem no MESMO d_demo, com o schema pertencendo
    ao papel da instalação que o criou primeiro."""
    import os
    import subprocess
    esquema = os.environ.get("PLAT_SCHEMA", "plat")
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t", "-c",
                        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n "
                        f"ON n.oid = p.pronamespace WHERE n.nspname = '{esquema}' "
                        "AND p.proname = 'camada_schema_garantir'"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    corpo = r.stdout
    assert esquema == "plat" or f"d_{esquema}" in corpo or f"'{esquema}_d_'" in corpo, (
        f"a instalação '{esquema}' cria o schema de dados do inquilino como \"d_\" || slug, igual à produção: "
        "o mesmo d_demo é compartilhado por todas as instalações do mesmo banco")


# --------------------------------------------------------------- cota por inquilino: só sobe
@pytest.mark.xfail(
    strict=True,
    reason="L0-04 pai: uso_bytes so e somado (carregar.py); apagar a camada nunca devolve a cota",
)
def test_uso_de_armazenamento_e_devolvido_quando_a_camada_e_apagada(ingestor_a, sessao_a, con_pg_adv):
    """Portão do item pai L0-04-ingest-vetor: 'tamanho máximo e cota por inquilino aplicados'. A cota é
    aplicada na entrada, mas `plat.tenant.uso_bytes` só recebe soma (app/ingestao/carregar.py); nenhum
    caminho de apagar devolve bytes, então a cota do inquilino é irreversível."""
    from tests.api.ingestao.conftest import esperar_job

    def uso() -> int:
        with con_pg_adv.cursor() as cur:
            cur.execute("SELECT uso_bytes FROM plat.tenant WHERE slug = 'demo'")
            return int(cur.fetchone()["uso_bytes"] or 0)

    antes = uso()
    imp_id, _ = ingestor_a.importar("cobertura.gpkg", "gpkg")
    final = ingestor_a.confirmar(imp_id)
    assert final.get("estado") == "concluida", final
    depois_da_carga = uso()
    assert depois_da_carga > antes, "a carga nem sequer somou uso_bytes"
    item_id = final["item_id"]
    r = sessao_a.delete(f"/api/itens/{item_id}?cascata=true")
    assert r.status_code in (200, 202, 204), r.text
    # expurgo físico (mesma chamada do periódico catalogo.lixeira_expurgar)
    r = sessao_a.post("/api/jobs", json={"tipo": "catalogo.lixeira_expurgar", "parametros": {}})
    if r.status_code == 201:
        esperar_job(sessao_a, r.json()["id"], timeout=120)
    depois_do_expurgo = uso()
    assert depois_do_expurgo <= antes, (
        f"uso_bytes do inquilino: {antes} antes, {depois_da_carga} depois da carga, "
        f"{depois_do_expurgo} depois de apagar e expurgar a camada — a cota nunca desce")


@pytest.mark.xfail(
    strict=True,
    reason="L0-04-c: slug com hifen e valido como inquilino e invalido na ingestao (slug_invalido)",
)
def test_inquilino_com_hifen_no_slug_consegue_importar():
    """A migração 002 aceita hífen e dígito inicial no slug do inquilino
    (`slug ~ '^[a-z0-9][a-z0-9-]{1,38}$'`); a função de ingestão da migração 029 recusa os dois
    (`p_slug !~ '^[a-z][a-z0-9_]{0,60}$' -> RAISE slug_invalido`). Qualquer inquilino com hífen no slug
    nunca consegue importar camada nenhuma — e a base já tem dezenas de schemas d_zt-inq-* assim."""
    import os
    import subprocess
    esquema = os.environ.get("PLAT_SCHEMA", "plat")
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t", "-c",
                        f"SET search_path = {esquema}, public; "
                        "SELECT ('minha-org' ~ '^[a-z0-9][a-z0-9-]{1,38}$')::text || '|' || "
                        "('minha-org' ~ '^[a-z][a-z0-9_]{0,60}$')::text"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    inquilino, ingestao = [ln for ln in r.stdout.splitlines() if "|" in ln][-1].split("|")
    assert not (inquilino == "true" and ingestao == "false"), (
        "o slug 'minha-org' é aceito na criação do inquilino e recusado pela ingestão "
        f"(criação={inquilino}, ingestão={ingestao})")
