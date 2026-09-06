"""Assinatura com aceite gravado da licença, registro de leitura por camada e exportação com LICENCA.txt
(item L6-01-e-assinatura-e-uso; migração 20260906T2114_acervo_assinatura_uso.sql; rotas em
app/acervo/publicacao.py; texto canônico da licença em app/acervo/licenca.py).

Cada cláusula do portão vira um teste aqui:

  1. "assinar exige clique no texto da licença (gravado)" — POST sem aceite é 409, POST com sha defasado é
     409, POST com o sha exibido grava QUEM, QUANDO e O TEXTO byte a byte (conferido como postgres na
     tabela, não na resposta da API). Camada sem licença curada: 409 sem_licenca (regra D17).
  2. "registro conta consultas do dia (teste faz 10 e lê 10)" — 10 GETs de feições, GET /api/acervo/uso
     mostra exatamente +10 consultas no dia, e o relatório mensal agrega a mesma camada.
  3. "revogação corta leitura em ≤ 1 s" — DELETE da assinatura e o GET seguinte já é 403; a medida fica
     gravada, e a prova no BANCO (a view devolve zero linha na mesma hora) acompanha.
  4. "export leva LICENCA.txt" — o pacote .zip tem LICENCA.txt com tipo, termo verificado, trecho literal,
     atribuição e obrigações; ODbL leva atribuição E share-alike. É a refutação do item, feita aqui mesmo:
     exportar a camada ODbL e procurar o aviso de atribuição no pacote.

Camada de teste: `cbre.osm_aeroway` (1.523 feições reais do OpenStreetMap nesta base, medido 06/09/2026),
fonte `openstreetmap` — a fonte ODbL canônica da curadoria do item L6-01-g. A licença NÃO é semeada de
cabeça: a fixture faz o GET de verdade em https://www.openstreetmap.org/copyright, exige HTTP 200 e os
termos esperados, e grava o recorte literal como evidência — o mesmo critério do script de curadoria, na
hora do teste. Uma segunda camada (`cbre.osm_rail`, fonte `dnit-osm-rodovias`, SEM licença curada) prova a
recusa D17.
"""

import hashlib
import io
import json
import os
import subprocess
import time
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
PUBLICAR = ROOT / "scripts" / "acervo_publicar.py"
ITEM = "L6-01-e-assinatura-e-uso"

FONTE_ODBL = "openstreetmap"
URL_LICENCA_OSM = "https://www.openstreetmap.org/copyright"
TERMOS_OSM = ["Open Data Commons Open Database License", "ODbL"]
CAMADA_ODBL_ID = "openstreetmap/cbre.osm_aeroway"
VIEW_ODBL = "cbre_osm_aeroway"

CAMADA_SEM_LICENCA_ID = "dnit-osm-rodovias/cbre.osm_rail"
VIEW_SEM_LICENCA = "cbre_osm_rail"


def _schema() -> str:
    return os.environ.get("PLAT_SCHEMA", "plat")


def _psql(sql: str, *params: str) -> str:
    """psql como postgres — a identidade que escreve os registros do acervo (nunca plat_app). Parâmetros vão
    por -v e se citam no SQL como :'p1' — nunca por formatação de string."""
    cmd = ["sudo", "-u", "postgres", "psql", "-d", os.environ.get("PLAT_BANCO", "iagro_sat"),
           "-X", "-q", "-tA", "-v", "ON_ERROR_STOP=1"]
    for i, p in enumerate(params, start=1):
        cmd += ["-v", f"p{i}={p}"]
    r = subprocess.run(cmd + ["-c", sql], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _tabela_existe(nome: str) -> bool:
    return _psql(f"SELECT to_regclass('{nome}') IS NOT NULL") == "t"


def _colunas_reais(tabela: str) -> list[str]:
    """Lista branca lida da PRÓPRIA tabela (sem a geometria), nunca digitada: se a tabela mudar, o teste
    acompanha; se sumir, o teste falha em voz alta."""
    schema_nome, tabela_nome = tabela.split(".")
    saida = _psql(
        "SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns "
        f"WHERE table_schema = :'p1' AND table_name = :'p2' AND column_name <> 'geom' AND data_type <> 'USER-DEFINED'",
        schema_nome, tabela_nome)
    return saida.split(",")


def _registrar_camada(camada_id: str, fonte_id: str, tabela: str, tipo_geom: str) -> None:
    schema_nome, tabela_nome = tabela.split(".")
    colunas = _colunas_reais(tabela)
    assert colunas and colunas != [""], f"sem colunas lidas em {tabela}"
    exatas = _psql(f"SELECT count(*) FROM {tabela}")
    s = _schema()
    lista = ",".join("'" + c + "'" for c in colunas)
    _psql(
        f"INSERT INTO {s}.acervo_camada (acervo_camada_id, fonte_id, servidor, banco, schema_nome, tabela, "
        f"coluna_geom, srid, tipo_geom, colunas_expostas, colunas_bloqueadas, linhas_exatas, "
        f"linhas_contadas_em, estado) "
        f"VALUES (:'p1', :'p2', 'vultr', 'iagro_sat', :'p3', :'p4', 'geom', 4326, :'p5', "
        f"ARRAY[{lista}], ARRAY[]::text[], {exatas}, current_date, 'exposta') "
        f"ON CONFLICT (acervo_camada_id) DO UPDATE SET estado = 'exposta', "
        f"colunas_expostas = EXCLUDED.colunas_expostas, linhas_exatas = EXCLUDED.linhas_exatas",
        camada_id, fonte_id, schema_nome, tabela_nome, tipo_geom)


def _verificar_licenca_osm_agora() -> tuple[int, str]:
    """GET de verdade na página de copyright do OSM, AGORA: devolve (http_status, recorte literal da
    evidência). Falha o teste se a página não mostrar o termo — licença nunca é digitada (regra D17)."""
    r = httpx.get(URL_LICENCA_OSM, timeout=25, follow_redirects=True,
                  headers={"User-Agent": "plat-teste-licenca/1.0 (item L6-01-e)"})
    assert r.status_code == 200, f"página de licença do OSM respondeu {r.status_code}"
    corpo = r.text
    for termo in TERMOS_OSM:
        assert termo.lower() in corpo.lower(), f"termo {termo!r} não está mais na página do OSM"
    i = corpo.lower().index(TERMOS_OSM[0].lower())
    evidencia = corpo[max(0, i - 120): i + 200].replace("\n", " ").strip()
    return r.status_code, evidencia


def _semeia_licenca(http_status: int, evidencia: str) -> None:
    s = _schema()
    _psql(
        f"INSERT INTO {s}.acervo_licenca (fonte_id, tipo, url_licenca, metodo, identificador_remoto, "
        f"http_status, evidencia, confianca, verificado_em, atualizado_em) "
        f"VALUES (:'p1', 'ODbL', :'p2', 'html_regex', NULL, {http_status}, :'p3', "
        f"'correspondência exata (refeita por HTTP na semeadura do teste)', now(), now()) "
        f"ON CONFLICT (fonte_id) DO UPDATE SET tipo = EXCLUDED.tipo, url_licenca = EXCLUDED.url_licenca, "
        f"http_status = EXCLUDED.http_status, evidencia = EXCLUDED.evidencia, "
        f"verificado_em = EXCLUDED.verificado_em, atualizado_em = now()",
        FONTE_ODBL, URL_LICENCA_OSM, evidencia)


def _publicar() -> None:
    r = subprocess.run(
        ["sudo", "-u", "postgres", "python3", str(PUBLICAR), "--schema", _schema(),
         "--banco", os.environ.get("PLAT_BANCO", "iagro_sat")],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr


def _limpar_estado() -> None:
    """Zera assinaturas e uso das duas camadas de teste (como postgres; plat_app não tem DELETE em
    acervo_uso de propósito) para a rodada ser determinística mesmo depois de uma execução abortada."""
    s = _schema()
    _psql(
        f"DELETE FROM {s}.acervo_assinatura WHERE acervo_camada_id IN "
        f"('{CAMADA_ODBL_ID}', '{CAMADA_SEM_LICENCA_ID}'); "
        f"DELETE FROM {s}.acervo_uso WHERE acervo_camada_id IN "
        f"('{CAMADA_ODBL_ID}', '{CAMADA_SEM_LICENCA_ID}')")


@pytest.fixture(scope="module")
def camadas_prontas():
    """Camada ODbL publicada COM licença verificada por HTTP na hora + camada SEM licença para a recusa."""
    if not (_tabela_existe("cbre.osm_aeroway") and _tabela_existe("cbre.osm_rail")):
        pytest.skip("tabelas cbre.osm_aeroway/cbre.osm_rail não existem nesta base")
    status, evidencia = _verificar_licenca_osm_agora()
    _semeia_licenca(status, evidencia)
    _registrar_camada(CAMADA_ODBL_ID, FONTE_ODBL, "cbre.osm_aeroway", "GEOMETRY")
    _registrar_camada(CAMADA_SEM_LICENCA_ID, "dnit-osm-rodovias", "cbre.osm_rail", "LINESTRING")
    _publicar()
    _limpar_estado()
    return {"odbl": VIEW_ODBL, "sem_licenca": VIEW_SEM_LICENCA}


def _licenca_na_lista(sessao, view: str) -> dict:
    """Os campos licenca_* da camada na lista: o que a tela mostraria e o que o clique ecoa."""
    r = sessao.get("/api/acervo/camadas")
    assert r.status_code == 200, r.text
    camada = {c["view_nome"]: c for c in r.json()["camadas"]}[view]
    return camada


def _assinar_pela_api(sessao, view: str) -> dict:
    """O fluxo do clique, inteiro: lê o texto+sha da lista e confirma. Devolve a resposta do POST."""
    camada = _licenca_na_lista(sessao, view)
    r = sessao.post(
        f"/api/acervo/camadas/{view}/assinatura",
        json={"aceite_licenca": True, "licenca_sha256": camada["licenca_sha256"]})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def assinatura_odbl(camadas_prontas, sessao_a):
    """Inquilino A assina a camada ODbL pelo fluxo do clique; cancela no fim."""
    _assinar_pela_api(sessao_a, VIEW_ODBL)
    yield
    sessao_a.delete(f"/api/acervo/camadas/{VIEW_ODBL}/assinatura")


# ------------------------------------------- cláusula: assinar exige clique no texto da licença (gravado)

def test_lista_traz_o_texto_da_licenca_e_o_sha_para_o_clique(camadas_prontas, sessao_a):
    """A tela não monta texto nenhum: recebe tipo, texto, url e sha256 prontos; o sha bate com o texto."""
    camada = _licenca_na_lista(sessao_a, VIEW_ODBL)
    assert camada["licenca_tipo"] == "ODbL"
    assert camada["licenca_url"] == URL_LICENCA_OSM
    texto = camada["licenca_texto"]
    assert "Open Data Commons Open Database License" in texto  # trecho literal da evidência
    assert "Atribuição exigida" in texto and "share-alike" in texto
    assert hashlib.sha256(texto.encode()).hexdigest() == camada["licenca_sha256"]
    # a camada sem licença curada vem com os campos vazios — nada de texto inventado
    sem = _licenca_na_lista(sessao_a, VIEW_SEM_LICENCA)
    assert sem["licenca_tipo"] is None and sem["licenca_texto"] is None


def test_assinar_sem_aceite_e_recusado_e_nada_grava(camadas_prontas, sessao_a):
    r = sessao_a.post(f"/api/acervo/camadas/{VIEW_ODBL}/assinatura", json={})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "aceite_exigido"
    r = sessao_a.post(f"/api/acervo/camadas/{VIEW_ODBL}/assinatura",
                      json={"aceite_licenca": False, "licenca_sha256": "qualquer"})
    assert r.status_code == 409 and r.json()["erro"] == "aceite_exigido", r.text
    assert _licenca_na_lista(sessao_a, VIEW_ODBL)["assinada"] is False


def test_assinar_com_sha_defasado_e_recusado(camadas_prontas, sessao_a):
    """O sha que não bate com o texto atual é a prova de que a tela NÃO mostrou aquele texto: recusa."""
    camada = _licenca_na_lista(sessao_a, VIEW_ODBL)
    r = sessao_a.post(f"/api/acervo/camadas/{VIEW_ODBL}/assinatura",
                      json={"aceite_licenca": True, "licenca_sha256": "0" * 64})
    assert r.status_code == 409, r.text
    corpo = r.json()
    assert corpo["erro"] == "licenca_mudou"
    assert corpo["detalhes"]["licenca_sha256"] == camada["licenca_sha256"]
    assert _licenca_na_lista(sessao_a, VIEW_ODBL)["assinada"] is False


def test_assinar_grava_quem_quando_e_o_texto_aceito(camadas_prontas, sessao_a, ids):
    """Portão, parte 1: o clique fica GRAVADO — quem (assinado_por), quando (assinado_em) e o texto da
    licença aceito na hora, byte a byte (conferido na tabela, como postgres, não na resposta da API)."""
    antes = _licenca_na_lista(sessao_a, VIEW_ODBL)
    marco = time.time()
    resposta = _assinar_pela_api(sessao_a, VIEW_ODBL)
    try:
        assert resposta["assinada"] is True and resposta["licenca_tipo"] == "ODbL"
        assert resposta["assinado_em"], "a resposta traz o carimbo para a tela não precisar reler"
        s = _schema()
        linha = _psql(
            f"SELECT assinado_por, extract(epoch from (now() - assinado_em))::int, licenca_tipo, "
            f"licenca_url, licenca_sha256, licenca_texto FROM {s}.acervo_assinatura a "
            f"JOIN {s}.tenant t ON t.id = a.tenant_id "
            f"WHERE t.slug = 'demo' AND a.acervo_camada_id = :'p1'",
            CAMADA_ODBL_ID).split("|")
        assinado_por, segundos, tipo, url, sha, texto = (linha[0], int(linha[1]), *linha[2:5], "|".join(linha[5:]))
        assert int(assinado_por) == ids["a"]["usuario"]["id"], "QUEM: o admin do inquilino demo"
        assert 0 <= segundos <= max(60, int(time.time() - marco) + 60), "QUANDO: agora, não uma data fixa"
        assert tipo == "ODbL" and url == URL_LICENCA_OSM
        assert texto == antes["licenca_texto"], "O TEXTO gravado é byte a byte o que a lista mostrou"
        assert sha == hashlib.sha256(texto.encode()).hexdigest() == antes["licenca_sha256"]
    finally:
        sessao_a.delete(f"/api/acervo/camadas/{VIEW_ODBL}/assinatura")


def test_camada_sem_licenca_curada_recusa_assinatura(camadas_prontas, sessao_a):
    """Regra D17: sem licença escrita a camada não circula — nem com aceite, nem com sha."""
    r = sessao_a.post(f"/api/acervo/camadas/{VIEW_SEM_LICENCA}/assinatura",
                      json={"aceite_licenca": True, "licenca_sha256": "0" * 64})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "sem_licenca"
    r = sessao_a.get(f"/api/acervo/camadas/{VIEW_SEM_LICENCA}/feicoes?limite=1")
    assert r.status_code == 403, r.text


# --------------------------------------------- cláusula: registro conta consultas do dia (faz 10, lê 10)

def test_dez_consultas_aparecem_como_dez_no_registro_do_dia(camadas_prontas, assinatura_odbl, sessao_a, medida):
    """Portão, parte 2, literal: o teste FAZ 10 leituras e LÊ 10 no registro do dia (delta antes/depois,
    por camada — o registro é por inquilino, camada e dia)."""
    hoje = date.today().isoformat()

    def lido() -> dict:
        r = sessao_a.get(f"/api/acervo/uso?dia={hoje}")
        assert r.status_code == 200, r.text
        corpo = r.json()
        por_camada = {c["acervo_camada_id"]: c for c in corpo["camadas"]}
        eu = por_camada.get(CAMADA_ODBL_ID, {"consultas": 0, "feicoes": 0})
        return {"total": corpo["total_consultas"], "camada": eu}

    antes = lido()
    feicoes_servidas = 0
    for _ in range(10):
        r = sessao_a.get(f"/api/acervo/camadas/{VIEW_ODBL}/feicoes?limite=3")
        assert r.status_code == 200, r.text
        feicoes_servidas += r.json()["total"]
    depois = lido()
    assert depois["camada"]["consultas"] - antes["camada"]["consultas"] == 10, (antes, depois)
    assert depois["total"] - antes["total"] == 10
    assert depois["camada"]["feicoes"] - antes["camada"]["feicoes"] == feicoes_servidas
    medida(ITEM)("dez_consultas_registradas_no_dia",
                 depois["camada"]["consultas"] - antes["camada"]["consultas"], "consultas",
                 "10 x GET /api/acervo/camadas/cbre_osm_aeroway/feicoes; delta de GET /api/acervo/uso")


def test_relatorio_mensal_agrega_o_uso_da_camada(camadas_prontas, assinatura_odbl, sessao_a):
    """Hipótese do item: relatório mensal de uso do acervo por inquilino — entrada do item L7-09."""
    hoje = date.today()

    def mensal() -> dict:
        r = sessao_a.get(f"/api/acervo/uso/mensal?ano={hoje.year}&mes={hoje.month}")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ano"] == hoje.year and corpo["mes"] == hoje.month
        por_camada = {c["acervo_camada_id"]: c for c in corpo["camadas"]}
        return por_camada.get(CAMADA_ODBL_ID, {"consultas": 0, "feicoes": 0, "dias": 0})

    antes = mensal()
    for _ in range(2):
        assert sessao_a.get(f"/api/acervo/camadas/{VIEW_ODBL}/feicoes?limite=1").status_code == 200
    depois = mensal()
    assert depois["consultas"] - antes["consultas"] == 2, (antes, depois)
    assert depois["dias"] >= 1


def test_uso_de_um_inquilino_nao_aparece_para_outro(camadas_prontas, assinatura_odbl, sessao_a, sessao_b):
    """A RLS de plat.acervo_uso recorta pelo inquilino da sessão: B lê o próprio registro, nunca o de A."""
    hoje = date.today().isoformat()
    assert sessao_a.get(f"/api/acervo/camadas/{VIEW_ODBL}/feicoes?limite=1").status_code == 200
    de_a = sessao_a.get(f"/api/acervo/uso?dia={hoje}").json()
    assert any(c["acervo_camada_id"] == CAMADA_ODBL_ID for c in de_a["camadas"])
    de_b = sessao_b.get(f"/api/acervo/uso?dia={hoje}").json()
    assert all(c["acervo_camada_id"] != CAMADA_ODBL_ID for c in de_b["camadas"]), de_b
    assert de_b["total_consultas"] == 0


# ------------------------------------------------------- cláusula: revogação corta leitura em ≤ 1 s

def test_revogacao_corta_a_leitura_em_ate_1s(camadas_prontas, sessao_a, conexao_plat_app, medida):
    """Portão, parte 3: assina, lê 200, revoga e o GET IMEDIATAMENTE seguinte já é 403 — a medida
    (revogar → primeiro 403) fica gravada. E a prova no BANCO: a view devolve zero linha na mesma hora,
    não só a API (o porteiro está no WHERE da view)."""
    _assinar_pela_api(sessao_a, VIEW_ODBL)
    try:
        assert sessao_a.get(f"/api/acervo/camadas/{VIEW_ODBL}/feicoes?limite=1").status_code == 200

        inicio = time.monotonic()
        r = sessao_a.delete(f"/api/acervo/camadas/{VIEW_ODBL}/assinatura")
        assert r.status_code == 200, r.text
        r = sessao_a.get(f"/api/acervo/camadas/{VIEW_ODBL}/feicoes?limite=1")
        ms = (time.monotonic() - inicio) * 1000
        assert r.status_code == 403, r.text
        assert ms <= 1000, f"revogação demorou {ms:.0f} ms para cortar a leitura"
        medida(ITEM)("revogacao_corte_leitura_ms", round(ms, 1), "ms",
                     "DELETE /api/acervo/camadas/<view>/assinatura até o primeiro GET feicoes 403 "
                     "(mesmo processo de teste, mediana não — uma medição)")

        tenant = _psql(f"SELECT id FROM {_schema()}.tenant WHERE slug = 'demo'")
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (tenant,))
            cur.execute(f'SELECT count(*) AS n FROM "{_schema()}_acervo"."{VIEW_ODBL}"')  # noqa: S608
            assert cur.fetchone()["n"] == 0, "a view ainda devolve linha depois da revogação"
        conexao_plat_app.rollback()
        medida(ITEM)("revogacao_view_zero_linha", 1, "booleano",
                     "SELECT count(*) na view como plat_app com o tenant revogado = 0 na mesma hora")
    finally:
        sessao_a.delete(f"/api/acervo/camadas/{VIEW_ODBL}/assinatura")


# -------------------------------------------------------------- cláusula: export leva LICENCA.txt

def _abrir_pacote(resposta) -> tuple[zipfile.ZipFile, str, dict]:
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/zip"
    pacote = zipfile.ZipFile(io.BytesIO(resposta.content))
    nomes = pacote.namelist()
    assert "LICENCA.txt" in nomes, f"pacote sem LICENCA.txt: {nomes}"
    geojson_nome = f"{VIEW_ODBL}.geojson"
    assert geojson_nome in nomes, nomes
    texto = pacote.read("LICENCA.txt").decode("utf-8")
    dados = json.loads(pacote.read(geojson_nome).decode("utf-8"))
    return pacote, texto, dados


def test_export_leva_licenca_txt_com_atribuicao_odbl(camadas_prontas, assinatura_odbl, sessao_a, medida):
    """Portão, parte 4, e a refutação do item feita aqui mesmo: exportar a camada ODbL e procurar o aviso
    de atribuição no pacote. LICENCA.txt carrega tipo, termo verificado, trecho literal, a atribuição
    exigida e as obrigações (ODbL = atribuição E share-alike), mais o registro do aceite do inquilino."""
    r = sessao_a.get(f"/api/acervo/camadas/{VIEW_ODBL}/exportar?limite=50")
    pacote, texto, dados = _abrir_pacote(r)
    assert "Licença: ODbL" in texto
    assert "Open Data Commons Open Database License" in texto, "trecho literal da página do termo ausente"
    assert URL_LICENCA_OSM in texto
    assert "Atribuição exigida: Dados de OpenStreetMap" in texto, "aviso de atribuição ausente"
    assert "compartilhamento pela mesma licença (share-alike)" in texto
    assert "Inquilino: demo." in texto and "Assinatura registrada em" in texto
    assert "sha256 do texto aceito" in texto
    assert dados["type"] == "FeatureCollection" and dados["total"] >= 1
    medida(ITEM)("export_pacote_leva_licenca_txt_e_atribuicao", 1, "booleano",
                 "GET /api/acervo/camadas/cbre_osm_aeroway/exportar; LICENCA.txt com 'Licença: ODbL', "
                 "'Atribuição exigida: Dados de OpenStreetMap' e share-alike")
    medida(ITEM)("export_pacote_bytes", len(r.content), "bytes",
                 "tamanho do .zip de 50 feições de cbre.osm_aeroway com LICENCA.txt")


def test_export_sem_assinatura_e_403(camadas_prontas, sessao_b):
    """O pacote (com os dados E a licença) só sai para quem assina — inquilino B leva 403."""
    r = sessao_b.get(f"/api/acervo/camadas/{VIEW_ODBL}/exportar?limite=1")
    assert r.status_code == 403, r.text
    assert r.json()["erro"] == "sem_assinatura"


def test_export_registra_uso_e_evento(camadas_prontas, assinatura_odbl, sessao_a):
    """A exportação também é leitura: conta no registro do dia e grava evento acervo/exportar (quem,
    quando, quantas feições) — a trilha de auditoria que o relatório do inquilino explica."""
    hoje = date.today().isoformat()
    antes = sessao_a.get(f"/api/acervo/uso?dia={hoje}").json()
    antes_n = {c["acervo_camada_id"]: c for c in antes["camadas"]}.get(CAMADA_ODBL_ID, {"consultas": 0})
    r = sessao_a.get(f"/api/acervo/camadas/{VIEW_ODBL}/exportar?limite=2")
    assert r.status_code == 200, r.text
    depois = sessao_a.get(f"/api/acervo/uso?dia={hoje}").json()
    depois_n = {c["acervo_camada_id"]: c for c in depois["camadas"]}[CAMADA_ODBL_ID]
    assert depois_n["consultas"] - antes_n["consultas"] == 1

    eventos = sessao_a.get("/api/eventos?limite=20").json()["itens"]
    meus = [e for e in eventos if e["tipo"] == "acervo/exportar"
            and e["propriedades"].get("acervo_camada_id") == CAMADA_ODBL_ID]
    assert meus, "nenhum evento acervo/exportar registrado"
    assert meus[0]["propriedades"]["feicoes"] >= 1
    assert meus[0]["propriedades"]["licenca_tipo"] == "ODbL"
