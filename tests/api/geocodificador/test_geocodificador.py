"""Geocodificador próprio (item L2-11-b-geocodificador-brasil): portão de pronto medido em cima do CNEFE 2022
de Roraima (RR), a UF instalada nesta demo (`scripts/geocodificador_instalar_uf.py --uf RR`; 260.515 pontos,
15 municípios — plat.geo_instalacao guarda a proveniência). Sem São Paulo carregado (D28, teto de disco): a
ambiguidade multi-município do item-pai é provada com 'RUA A', que se repete em 8 municípios de RR (medido),
mesmo papel do 'Rua A' em São Paulo do enunciado — registrado explicitamente, nunca disfarçado de SP real."""

import pytest

from app.geocodificador import motor
from app.geocodificador.normalizacao import ABREVIACOES_TIPO_LOGRADOURO

INVERSO_TIPO = {}
for abrev, completo in ABREVIACOES_TIPO_LOGRADOURO.items():
    INVERSO_TIPO.setdefault(completo, abrev)
INVERSO_TIPO["RUA"] = "R."
INVERSO_TIPO["AVENIDA"] = "Av."


def _amostra(cur, n=50):
    """Amostra ALEATÓRIA (não os primeiros por id, que ficaram todos no mesmo município na carga do CNEFE de
    RR — os ids crescem por município de origem do arquivo) sobre um seed fixo, para o teste ser
    reprodutível e ainda cobrir vários municípios."""
    cur.execute("SELECT setseed(0.42)")
    cur.execute(
        "SELECT e.cod_unico_endereco, e.tipo_logradouro, e.nome_logradouro, e.numero, e.cep, e.localidade, "
        "  m.nome AS municipio, u.sigla AS uf, e.lat, e.lon, e.cod_municipio "
        "FROM plat.geo_endereco e JOIN plat.geo_municipio m ON m.cod = e.cod_municipio "
        "  JOIN plat.geo_uf u ON u.cod = m.cod_uf "
        "WHERE e.numero IS NOT NULL AND e.nome_logradouro <> 'SEM DENOMINACAO' AND e.cod_uf = 14 "
        "ORDER BY random() LIMIT %s",
        (n,),
    )
    return cur.fetchall()


def _ruidoso(tipo: str, nome: str) -> str:
    """Injeta ruído realista sem mudar o significado: tipo de logradouro abreviado (RUA -> R.), caixa mista.
    O CNEFE já vem sem acento (ASCII puro, conferido 06/09) — a dobra de acento é testada à parte."""
    abrev = INVERSO_TIPO.get(tipo, tipo)
    palavras = nome.split(" ")
    mistas = [p.lower() if i % 2 else p.title() for i, p in enumerate(palavras)]
    return f"{abrev} {' '.join(mistas)}"


@pytest.fixture
def amostra_50(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        linhas = _amostra(cur, 50)
    assert len(linhas) == 50, "menos de 50 endereços elegíveis instalados (RR precisa estar carregado)"
    assert len({r["cod_municipio"] for r in linhas}) >= 3, "amostra não cobre 3 municípios"
    return linhas


def test_cnefe_sem_coluna_de_pessoa(conexao_plat_app):
    """Portão literal: nenhuma coluna de nome de pessoa em nenhuma tabela do geocodificador."""
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'plat' AND table_name LIKE 'geo_%' "
            "  AND (column_name ILIKE '%%nome_pessoa%%' OR column_name ILIKE '%%cpf%%' "
            "       OR column_name ILIKE '%%nome_morador%%' OR column_name ILIKE '%%responsavel%%')"
        )
        achados = cur.fetchall()
    assert achados == [], f"coluna de identificação pessoal encontrada: {achados}"


def test_50_enderecos_3_municipios_erro_mediano_e_acerto_numero(sessao_a, amostra_50, medida):
    distancias = []
    tipos_precisos = 0
    for r in amostra_50:
        via = _ruidoso(r["tipo_logradouro"], r["nome_logradouro"])
        endereco = f"{via}, {r['numero']}, {r['municipio']} - {r['uf']}"
        resp = sessao_a.post("/api/geocodificar", json={"endereco": endereco, "max_locations": 5})
        assert resp.status_code == 200, (endereco, resp.text)
        candidato = resp.json()["candidatos"][0]
        d = motor.distancia_m(candidato["lon"], candidato["lat"], r["lon"], r["lat"])
        distancias.append(d)
        if candidato["tipo_acerto"] in ("numero_exato", "interpolado_na_face"):
            tipos_precisos += 1
    distancias.sort()
    mediana = distancias[len(distancias) // 2]
    pct_preciso = tipos_precisos / len(amostra_50) * 100
    nome_teste = "test_50_enderecos_3_municipios_erro_mediano_e_acerto_numero"
    m = medida("L2-11-b-geocodificador-brasil")
    m("geocodificar_erro_mediano", round(mediana, 1), "m", nome_teste)
    m("geocodificar_acerto_numero_face", round(pct_preciso, 1), "%", nome_teste)
    assert mediana <= 30, f"erro mediano {mediana:.1f} m acima do portão (30 m)"
    assert pct_preciso >= 90, f"acerto número/face {pct_preciso:.1f}% abaixo do portão (90%)"


def test_reverso_50_pontos_logradouro_certo(sessao_a, amostra_50, medida):
    acertos = 0
    for r in amostra_50:
        resp = sessao_a.post("/api/reverso", json={"lon": r["lon"], "lat": r["lat"]})
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        esperado = f"{r['tipo_logradouro']} {r['nome_logradouro']}".strip().upper()
        if (corpo["logradouro"] or "").strip().upper() == esperado:
            acertos += 1
    pct = acertos / len(amostra_50) * 100
    medida("L2-11-b-geocodificador-brasil")(
        "reverso_acerto_logradouro", round(pct, 1), "%", "test_reverso_50_pontos_logradouro_certo"
    )
    assert pct >= 90, f"reverso acertou o logradouro em {pct:.1f}%, abaixo do portão (90%)"


def test_sugestao_p95_100ms(sessao_a, medida):
    prefixos = ["RUA A", "AVENIDA", "RUA J", "VICINAL", "RODOVIA", "TRAVESSA", "RUA S", "RUA M"] * 13
    tempos = []
    for p in prefixos[:100]:
        resp = sessao_a.get("/api/sugerir", params={"q": p, "limite": 10})
        assert resp.status_code == 200, resp.text
        tempos.append(resp.elapsed.total_seconds() * 1000)
    tempos.sort()
    p95 = tempos[int(len(tempos) * 0.95) - 1]
    medida("L2-11-b-geocodificador-brasil")(
        "sugestao_p95", round(p95, 1), "ms", "test_sugestao_p95_100ms (100 chamadas)"
    )
    assert p95 <= 100, f"p95 de /api/sugerir = {p95:.1f} ms, acima do portão (100 ms)"


def test_ambiguidade_rua_a_devolve_varios_municipios(sessao_a):
    """Refutação do item-pai ('Rua A' em São Paulo): sem SP carregado (D28), o mesmo papel é feito por
    'RUA A', que se repete em 8 municípios de RR — a resposta correta é AMBIGUIDADE (vários candidatos em
    municípios diferentes), nunca um erro nem um candidato só escolhido arbitrariamente."""
    resp = sessao_a.post("/api/geocodificar", json={"logradouro": "Rua A", "max_locations": 10})
    assert resp.status_code == 200, resp.text
    candidatos = resp.json()["candidatos"]
    municipios = {c["municipio"] for c in candidatos}
    assert len(municipios) >= 3, f"esperava ambiguidade entre municípios, veio {municipios}"


def test_cep_de_outro_municipio_recusa_inconsistencia(sessao_a, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT e.cep, m2.nome AS outro_municipio FROM plat.geo_endereco e "
            "JOIN plat.geo_municipio m ON m.cod = e.cod_municipio "
            "JOIN plat.geo_municipio m2 ON m2.cod_uf = m.cod_uf AND m2.cod <> m.cod "
            "WHERE e.cod_uf = 14 AND e.cep IS NOT NULL LIMIT 1"
        )
        r = cur.fetchone()
    resp = sessao_a.post("/api/geocodificar", json={"municipio": r["outro_municipio"], "cep": r["cep"]})
    assert resp.status_code == 422, resp.text
    corpo = resp.json()
    assert corpo["erro"] == "cep_municipio_inconsistente", corpo


def test_texto_com_sql_nao_quebra_e_nao_altera_a_tabela(sessao_a, conexao_plat_app):
    payload = "'; DROP TABLE plat.geo_endereco; --"
    resp = sessao_a.post("/api/geocodificar", json={"logradouro": payload})
    assert resp.status_code in (200, 422), resp.text
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.geo_endereco")
        assert cur.fetchone()["n"] > 200_000, "a tabela deveria seguir intacta"


def test_geocodificar_exige_autenticacao(cliente):
    r = cliente.post("/api/geocodificar", json={"endereco": "Rua A, 1, Boa Vista - RR"})
    assert r.status_code == 401, r.text


def test_reverso_exige_autenticacao(cliente):
    r = cliente.post("/api/reverso", json={"lon": -60.7, "lat": 2.8})
    assert r.status_code == 401, r.text


def test_geocodificar_endereco_vazio_e_422(sessao_a):
    r = sessao_a.post("/api/geocodificar", json={})
    assert r.status_code == 422, r.text


def test_geocodificar_sem_correspondencia_e_422(sessao_a):
    """Logradouro sem nenhuma semelhança trigram com o que está instalado (nem nacionalmente, sem filtro
    de município) — diferente de município desconhecido, que a busca relaxa em vez de recusar (ver
    test_ambiguidade_rua_a_devolve_varios_municipios: o motor amplia o escopo, não erra cedo demais)."""
    r = sessao_a.post("/api/geocodificar", json={"logradouro": "ZZXXQQWWKKVVBBNNMM"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "sem_correspondencia", r.text


def test_instalacao_rr_tempo_e_disco_medidos(conexao_plat_app, medida):
    """Portão: 'instalação de 1 UF em tempo e disco medidos' — lê a proveniência gravada por
    `scripts/geocodificador_instalar_uf.py --uf RR` (plat.geo_instalacao) e registra em tests/medidas."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT * FROM plat.geo_instalacao WHERE sigla = 'RR'")
        r = cur.fetchone()
        cur.execute("SELECT pg_total_relation_size('plat.geo_endereco') AS bytes")
        tabela_bytes = cur.fetchone()["bytes"]
    assert r is not None, "RR precisa estar instalada (scripts/geocodificador_instalar_uf.py --uf RR)"
    m = medida("L2-11-b-geocodificador-brasil")
    nome_teste = "test_instalacao_rr_tempo_e_disco_medidos"
    m("instalacao_rr_arquivo_bytes", r["arquivo_bytes"], "bytes", nome_teste)
    m("instalacao_rr_linhas", r["linhas"], "linhas", nome_teste)
    m("instalacao_rr_municipios", r["municipios"], "municipios", nome_teste)
    m("instalacao_rr_duracao_s", float(r["duracao_s"]), "s", nome_teste)
    m("instalacao_rr_tabela_bytes", tabela_bytes, "bytes", nome_teste)
    assert r["arquivo_bytes"] < 200 * 1024 * 1024, "acima do teto D28 de 200 MB comprimidos"
    assert r["linhas"] > 250_000
