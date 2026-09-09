"""Ajuste por mínimos quadrados e suspeitas (item L4-parcelas-03-ajuste-e-qualidade).

Portão, cláusula por cláusula:
  b) "ajuste por mínimos quadrados em malha sintética de 20 parcelas com 3 pontos de controle:
     resíduos <= tolerância e coordenadas reproduzem a solução analítica (teste)" ->
     test_ajuste_malha_20_parcelas_reproduz_solucao_analitica (as observações nascem EXATAS da
     malha verdadeira; a solução analítica é a malha própria — o ajuste devolve coordenada
     verdadeira e resíduo zero dentro da tolerância);
  c) "'analisar' não altera geometria, 'aplicar' altera e grava versão" ->
     test_analisar_nao_altera_geometria_checksum (checksum da malha igual antes/depois, também
     com medida grosseira na rede) e test_aplicar_altera_geometria_e_grava_versao (pontos
     movidos, geometria de linha e de face propagada, linha em plat.parcela_ajuste com o
     relatório integral; a segunda aplicação APPENDA outra versão);
  d) "analyzeByLSA/applyLSA da fachada mapeados" -> test_fachada_analyze_by_lsa_nao_escreve e
     test_fachada_apply_lsa_grava_versao (HTTP na forma da documentação Esri, inquilino
     temporário);
  e) "paridade escrita" -> test_paridade_secao_13 (docs/PARIDADE_PARCELAS.md §13);
Refutação: "adversário adiciona medida grosseiramente errada (1 m em 100) e confere que o
  resíduo a destaca e que o ajuste sem ela converge; confere que 'analisar' não escreveu nada
  (checksum)" -> test_medida_grosseira_e_destacada_e_ajuste_sem_ela_converge.

Banco: suíte conecta como o app da TRILHA (conexao_plat_app); inquilinos demo/demo2 vêm de
plat.auth_login (padrão tests/api/test_rls.py); GUC local à transação; fixture desfaz tudo.
"""

import math
from pathlib import Path

import pytest

from app.parcelas import ajuste, modelo

# ------------------------------------------------------------------ helpers (padrão test_rls)


def _contexto(con, tenant_id, login="teste"):
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)",
            (str(tenant_id), "0", login),
        )


@pytest.fixture
def _ids(conexao_plat_app):
    ids = {}
    with conexao_plat_app.cursor() as cur:
        for slug in ("demo", "demo2"):
            cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
            r = cur.fetchone()
            assert r is not None, f"admin de {slug} não semeado na trilha"
            ids[slug] = r["tenant_id"]
    return ids


# ------------------------------------------------------------------ malha sintética (portão b)


class Malha:
    """Malha retangular COLUNAS x LINHAS de lados LADO m, com medida COGO EXATA (rumo e
    distância calculados da malha verdadeira) e coordenada inicial dos pontos de apoio
    PERTURBADA (o ajuste tem o que corrigir). Os 3 pontos de CONTROLE (dois de uma base e um
    em quadrante oposto) fixam translação, rotação e escala: a rede tem solução única e a
    solução analítica é a própria malha verdadeira."""

    def __init__(self, cur, tid, colunas=5, linhas=4, lado=50.0):
        self.cur, self.tid, self.lado = cur, tid, lado
        self.verdade = {}
        self.ponto_id = {}
        self.linha_id = {}
        self.parcela_ids = []
        reg = modelo.criar_registro(cur, tid, codigo="LSA-001", tipo="loteamento",
                                    origem="sintetico")
        self.registro_id = str(reg["id"])
        for j in range(linhas + 1):
            for i in range(colunas + 1):
                verdade = (i * lado, j * lado)
                chave = (i, j)
                self.verdade[chave] = verdade
                controle = chave in ((0, 0), (colunas, 0), (0, linhas))
                if controle:
                    x, y = verdade  # controle nasce onde está: é o datum
                else:
                    # perturbação determinística de até 4 cm (o levantamento "errou")
                    x = verdade[0] + (0.04 if (i + j) % 2 == 0 else -0.03)
                    y = verdade[1] + (0.02 if i % 2 == 0 else -0.02)
                p = modelo.criar_ponto(cur, tid, x=x, y=y, nome=f"N{i}-{j}",
                                       categoria="controle" if controle else "apoio",
                                       fixo=controle)
                self.ponto_id[chave] = str(p["id"])
        for j in range(linhas + 1):
            for i in range(colunas):
                self._linha((i, j), (i + 1, j))
        for j in range(linhas):
            for i in range(colunas + 1):
                self._linha((i, j), (i, j + 1))
        for j in range(linhas):
            for i in range(colunas):
                anel = [(i * lado, j * lado), ((i + 1) * lado, j * lado),
                        ((i + 1) * lado, (j + 1) * lado), (i * lado, (j + 1) * lado)]
                bordas = [self.linha_id[(i, j, (i + 1, j))],
                          self.linha_id[((i + 1), j, (i + 1, j + 1))],
                          self.linha_id[(i, j + 1, (i + 1, j + 1))],
                          self.linha_id[(i, j, (i, j + 1))]]
                p = modelo.criar_parcela(cur, tid, tipo="lote", codigo=f"LSA-L{j}{i}",
                                         registro_id=self.registro_id, anel=anel,
                                         area_declarada_m2=lado * lado, linha_ids=bordas)
                self.parcela_ids.append(str(p["id"]))

    def _linha(self, a, b):
        if (a, b) in self.linha_id:
            return self.linha_id[(a, b)]
        xa, ya = self.verdade[a]
        xb, yb = self.verdade[b]
        dx, dy = xb - xa, yb - ya
        ln = modelo.criar_linha(
            self.cur, self.tid, de_ponto_id=self.ponto_id[a], para_ponto_id=self.ponto_id[b],
            rumo_graus=math.degrees(math.atan2(dx, dy)) % 360.0, distancia_m=math.hypot(dx, dy),
            tipo_cogo="reta",
        )
        self.linha_id[(a, b)] = str(ln["id"])
        return str(ln["id"])

    def _chave_da_linha(self, linha_id):
        for chave, valor in self.linha_id.items():
            if valor == linha_id:
                return chave
        raise AssertionError(f"linha {linha_id} não é da malha")

    def _grosseira(self, fracao=0.01):
        """A medida grosseira da refutação: UMA linha ganha 1% a mais de distância
        (1 m em 100). Devolve o id da linha alterada."""
        linha_id = self.linha_id[((0, 0), (1, 0))]
        cur = self.cur
        cur.execute(
            "UPDATE plat.parcela_linha SET distancia_m = distancia_m * (1 + %s) "
            "WHERE id = %s::uuid AND tenant_id = %s RETURNING distancia_m",
            (fracao, linha_id, self.tid),
        )
        r = cur.fetchone()
        assert r is not None
        return linha_id

    def checksum(self):
        """md5 sobre ponto, linha e face: é a prova de que 'analisar' não escreve nada."""
        cur = self.cur
        cur.execute(
            "SELECT md5(string_agg(s, '' ORDER BY s)) AS soma FROM ("
            "  SELECT id::text || ST_X(geom)::text || ST_Y(geom)::text AS s "
            "  FROM plat.parcela_ponto WHERE tenant_id = %s"
            "  UNION ALL"
            "  SELECT id::text || ST_AsBinary(geom)::text AS s FROM plat.parcela_linha "
            "   WHERE tenant_id = %s"
            "  UNION ALL"
            "  SELECT id::text || ST_AsBinary(geom)::text AS s FROM plat.parcela "
            "   WHERE tenant_id = %s"
            ") t",
            (self.tid, self.tid, self.tid),
        )
        return cur.fetchone()["soma"]

    def coordenadas_do_banco(self):
        cur = self.cur
        cur.execute("SELECT id::text AS id, ST_X(geom) AS x, ST_Y(geom) AS y "
                    "FROM plat.parcela_ponto WHERE tenant_id = %s", (self.tid,))
        return {r["id"]: (float(r["x"]), float(r["y"])) for r in cur.fetchall()}


@pytest.fixture
def malha(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        m = Malha(cur, tid)
    m.con = con
    return m


def _verdade_por_id(malha):
    return {malha.ponto_id[chave]: xy for chave, xy in malha.verdade.items()}


# ------------------------------------------------------------------ portão b


def test_ajuste_malha_20_parcelas_reproduz_solucao_analitica(malha, medida):
    cur = malha.cur
    r = ajuste.analisar(cur, malha.tid, parcela_ids=malha.parcela_ids)
    assert r["convergiu"] is True
    assert r["redundancia"] > 0
    # a malha tem exatamente 20 parcelas e 3 controles (o portão é literal)
    assert len(malha.parcela_ids) == 20
    controles = [p for p in r["pontos"] if p["categoria"] == "controle"]
    assert len(controles) == 3 and all(p["fixo"] for p in controles)
    # resíduos <= tolerância: medida exata fecha em resíduo zero (a tolerância de parada é 5 cm)
    assert max(abs(ln["residuo_distancia_m"]) for ln in r["linhas"]) <= ajuste.TOLERANCIA_PADRAO_M
    assert max(ln["normalizado"] for ln in r["linhas"]) <= ajuste.TETO_RESIDUO
    assert r["suspeitas"] == []
    # coordenadas reproduzem a solução analítica (a malha verdadeira) — controle NÃO se move
    verdade = _verdade_por_id(malha)
    for p in r["pontos"]:
        x0, y0 = verdade[p["id"]]
        assert p["x"] == pytest.approx(x0, abs=1e-3)
        assert p["y"] == pytest.approx(y0, abs=1e-3)
        if p["fixo"]:
            assert (p["x"], p["y"]) == (round(x0, 6), round(y0, 6))
            assert p["deslocamento_m"] == 0.0
    medida("L4-parcelas-03-ajuste-e-qualidade")("malha_sintetica_parcelas", 20, "parcelas",
                                                "pytest tests/api/parcelas/test_ajuste.py::"
                                                "test_ajuste_malha_20_parcelas_reproduz_solucao_"
                                                "analitica PLAT_GRAVAR_MEDIDAS=1")
    medida("L4-parcelas-03-ajuste-e-qualidade")("malha_sintetica_pontos_controle", 3, "pontos",
                                                "idem")
    medida("L4-parcelas-03-ajuste-e-qualidade")("sigma_zero_malha_exata", r["sigma_zero"],
                                                "sigma (adimensional)",
                                                "idem")


def test_rede_sem_controle_e_recusada(conexao_plat_app, _ids):
    """Sem ponto de controle a rede é livre: sem sobra para avaliar resíduo é recusa explícita,
    nunca ajuste sem datum passado por bom."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="LSA-002", tipo="loteamento",
                                    origem="sintetico")
        p1 = modelo.criar_ponto(cur, tid, x=0.0, y=0.0, categoria="apoio")
        p2 = modelo.criar_ponto(cur, tid, x=100.02, y=0.0, categoria="apoio")
        ln = modelo.criar_linha(cur, tid, de_ponto_id=p1["id"], para_ponto_id=p2["id"],
                                rumo_graus=90.0, distancia_m=100.0, tipo_cogo="reta")
        parcela = modelo.criar_parcela(cur, tid, tipo="lote", codigo="LSA-L0", registro_id=reg["id"],
                                       anel=[(0, 0), (100, 0), (100, 50), (0, 50)],
                                       linha_ids=[ln["id"]])
        from app.erros import ErroAPI
        with pytest.raises(ErroAPI) as e:
            ajuste.analisar(cur, tid, parcela_ids=[str(parcela["id"])])
        assert e.value.status_code == 422


# ------------------------------------------------------------------ refutação (medida grosseira)


def test_medida_grosseira_e_destacada_e_ajuste_sem_ela_converge(malha, medida):
    cur = malha.cur
    linha_id = malha._grosseira(fracao=0.01)  # 1 m em 100
    antes = malha.checksum()
    com_erro = ajuste.analisar(cur, malha.tid, parcela_ids=malha.parcela_ids)
    assert com_erro["convergiu"] is True  # o ajuste converge MESMO com a medida errada...
    suspeita = [ln for ln in com_erro["linhas"] if ln["id"] == linha_id][0]
    assert suspeita["normalizado"] > ajuste.TETO_RESIDUO, "a grosseira precisa ser destacada"
    # data snooping honesto: a malha pequena VAZA resíduo acima de 3σ nos vizinhos do
    # grosseiro (física da distribuição de mínimos quadrados, não defeito) — o que a
    # destaca é ser o TOPO por margem folgada, não ser a única apontada
    normas = [ln["normalizado"] for ln in com_erro["linhas"]]
    assert linha_id in com_erro["suspeitas"]
    assert normas[0] > 2.0 * normas[1], "o grosseiro tem de dominar a lista por margem"
    assert com_erro["maior_residuo"]["linha_id"] == linha_id
    # o ajuste SEM ela: a exclusão tira a medida DA RODADA e a rede fecha limpa
    sem_erro = ajuste.analisar(cur, malha.tid, parcela_ids=malha.parcela_ids,
                               sem_linhas=[linha_id])
    assert sem_erro["convergiu"] is True
    assert linha_id in sem_erro["linhas_excluidas"]
    assert sem_erro["suspeitas"] == []
    assert max(ln["normalizado"] for ln in sem_erro["linhas"]) <= ajuste.TETO_RESIDUO
    assert sem_erro["sigma_zero"] < com_erro["sigma_zero"]
    # e a solução sem a grosseira volta a ser a malha verdadeira
    verdade = _verdade_por_id(malha)
    for p in sem_erro["pontos"]:
        x0, y0 = verdade[p["id"]]
        assert p["x"] == pytest.approx(x0, abs=1e-3)
        assert p["y"] == pytest.approx(y0, abs=1e-3)
    # 'analisar' NADA escreve: checksum da malha idêntico, com e sem exclusão
    assert malha.checksum() == antes
    medida("L4-parcelas-03-ajuste-e-qualidade")("normalizado_medida_grosseira",
                                                suspeita["normalizado"], "v/sigma",
                                                "pytest tests/api/parcelas/test_ajuste.py::"
                                                "test_medida_grosseira_e_destacada_e_ajuste_sem_"
                                                "ela_converge PLAT_GRAVAR_MEDIDAS=1")
    medida("L4-parcelas-03-ajuste-e-qualidade")("sigma_zero_sem_a_grosseira",
                                                sem_erro["sigma_zero"], "sigma (adimensional)",
                                                "idem")


def test_analisar_nao_altera_geometria_checksum(malha):
    """A cláusula literal do portão: 'analisar' não altera geometria — provado por checksum
    com a rede integra E com a grosseira dentro."""
    cur = malha.cur
    antes = malha.checksum()
    ajuste.analisar(cur, malha.tid, parcela_ids=malha.parcela_ids,
                    analysis_type="CONSISTENCY_CHECK")
    malha._grosseira(fracao=0.01)
    ajuste.analisar(cur, malha.tid, parcela_ids=malha.parcela_ids)
    assert malha.checksum() == antes


# ------------------------------------------------------------------ portão c (aplicar)


def test_aplicar_altera_geometria_e_grava_versao(malha, medida):
    cur = malha.cur
    cur.execute("SELECT count(*) AS n FROM plat.parcela_ajuste WHERE tenant_id = %s", (malha.tid,))
    versoes_antes = int(cur.fetchone()["n"])
    r = ajuste.aplicar(cur, malha.tid, parcela_ids=malha.parcela_ids,
                       tolerancia_movimento_m=0.01)
    assert r["relatorio"]["convergiu"] is True
    movidos = {p["id"] for p in r["movidos"]}
    assert movidos, "a malha nasce perturbada: a aplicação precisa mover pontos"
    # a versão do ajuste ficou gravada com o relatório integral (append-only)
    cur.execute("SELECT id, analise, pontos_ajustados, linhas_observadas "
                "FROM plat.parcela_ajuste WHERE tenant_id = %s ORDER BY criado_em", (malha.tid,))
    versoes = cur.fetchall()
    assert len(versoes) == versoes_antes + 1
    versao = versoes[-1]
    assert str(versao["id"]) == r["id"]
    assert versao["pontos_ajustados"] == len(r["movidos"])
    assert versao["analise"]["pontos"][0]["x_anterior"] is not None  # o antes ficou no relatório
    # geometria do ponto no banco == coordenada ajustada
    banco = malha.coordenadas_do_banco()
    verdade = _verdade_por_id(malha)
    for p in r["relatorio"]["pontos"]:
        x, y = banco[p["id"]]
        assert x == pytest.approx(p["x"], abs=1e-6) and y == pytest.approx(p["y"], abs=1e-6)
        assert x == pytest.approx(verdade[p["id"]][0], abs=1e-3)  # e a malha voltou à verdade
    # a geometria da LINHA segue os pontos (invariante do modelo): distância medida de novo
    cur.execute("SELECT ST_Length(geom) AS d FROM plat.parcela_linha WHERE id = %s::uuid",
                (malha.linha_id[((0, 0), (1, 0))],))
    assert float(cur.fetchone()["d"]) == pytest.approx(malha.lado, abs=1e-3)
    # a face voltou a fechar no quadrado de 50 m: área calculada == declarada
    cur.execute("SELECT area_calculada_m2 FROM plat.parcela WHERE id = %s::uuid",
                (malha.parcela_ids[0],))
    assert float(cur.fetchone()["area_calculada_m2"]) == pytest.approx(malha.lado ** 2, abs=1e-4)
    # segunda aplicação APPENDA outra versão (a casa nunca sobrescreve versão)
    ajuste.aplicar(cur, malha.tid, parcela_ids=malha.parcela_ids, tolerancia_movimento_m=0.01)
    cur.execute("SELECT count(*) AS n FROM plat.parcela_ajuste WHERE tenant_id = %s", (malha.tid,))
    assert int(cur.fetchone()["n"]) == versoes_antes + 2
    medida("L4-parcelas-03-ajuste-e-qualidade")("aplicar_pontos_movidos", len(r["movidos"]),
                                                "pontos",
                                                "pytest tests/api/parcelas/test_ajuste.py::"
                                                "test_aplicar_altera_geometria_e_grava_versao "
                                                "PLAT_GRAVAR_MEDIDAS=1")


# ------------------------------------------------------------------ portão e (paridade escrita)


def test_paridade_secao_13():
    doc = Path(__file__).resolve().parents[3] / "docs" / "PARIDADE_PARCELAS.md"
    assert doc.exists(), "docs/PARIDADE_PARCELAS.md não existe"
    texto = doc.read_text(encoding="utf-8")
    for termo in ("analyzeByLSA", "applyLSA", "WEIGHTED_LEAST_SQUARES", "CONSISTENCY_CHECK",
                  "convergenceTolerance", "movementTolerance", "updateAttributes",
                  "suspeitas", "semLinhas", "sigma_zero", "plat.parcela_ajuste",
                  "findgapsoverlaps", "parcelfabricattributerules", "controle", "apoio",
                  "medido", "escritura", "derivado"):
        assert termo in texto, f"paridade §13 sem '{termo}'"


# ------------------------------------------------------------------ portão d (fachada HTTP)


@pytest.fixture
def fabrica_lsa(conexao_plat_app, inquilino_temporario):
    """Inquilino temporário com uma malha pequena (2 lotes de 50 m, 3 controles) COMMITADA —
    a fachada roda em transação própria."""
    inq = inquilino_temporario
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (inq.slug,))
        tid = cur.fetchone()["tenant_id"]
    _contexto(con, tid)
    with con.cursor() as cur:
        m = Malha(cur, tid, colunas=2, linhas=1)
    con.commit()
    return {"inq": inq, "con": con, "tid": tid, "malha": m}


def test_fachada_analyze_by_lsa_nao_escreve(fabrica_lsa):
    """analyzeByLSA mapeado: resposta na forma da doc e NENHUMA escrita (checksum + ausência
    de versão em plat.parcela_ajuste)."""
    m = fabrica_lsa["malha"]
    _contexto(m.con, m.tid)
    antes = m.checksum()
    r = fabrica_lsa["inq"].admin.post("/api/parcelas/fabrica/analyzeByLSA", json={
        "parcelFeatures": [{"id": p, "layerId": "Parcela"} for p in m.parcela_ids],
        "analysisType": "WEIGHTED_LEAST_SQUARES",
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] is True and j["moment"].endswith("Z")
    assert j["resumo"]["convergiu"] is True
    assert j["resumo"]["suspeitas"] == []
    assert len(j["pontos"]) == len(m.verdade)
    with fabrica_lsa["con"].cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ajuste WHERE tenant_id = %s",
                    (m.tid,))
        assert int(cur.fetchone()["n"]) == 0  # análise não grava versão
        assert m.checksum() == antes          # e não mexe na malha


def test_fachada_apply_lsa_grava_versao(fabrica_lsa):
    m = fabrica_lsa["malha"]
    _contexto(m.con, m.tid)
    r = fabrica_lsa["inq"].admin.post("/api/parcelas/fabrica/applyLSA", json={
        "parcelFeatures": [{"id": p, "layerId": "Parcela"} for p in m.parcela_ids],
        "movementTolerance": 0.0,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] is True
    updates = j["serviceEdits"][0]["editedFeatures"]["updates"]
    assert len(updates) == len(m.verdade) - 3  # os 3 controles não se movem
    assert j["ajuste"]["id"]
    with fabrica_lsa["con"].cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ajuste WHERE tenant_id = %s",
                    (m.tid,))
        assert int(cur.fetchone()["n"]) == 1  # a versão GRAVOU


def test_fachada_qualidade_forma_da_resposta(fabrica_lsa):
    """A camada de qualidade responde por HTTP com as três seções (sobreposições, lacunas,
    regras de atributo) sobre o inquilino do token."""
    m = fabrica_lsa["malha"]
    _contexto(m.con, m.tid)
    r = fabrica_lsa["inq"].admin.post("/api/parcelas/qualidade", json={})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["lotes_avaliados"] == 2
    assert j["sobreposicoes"]["total"] == 0
    assert j["lacunas"]["total"] == 0
    assert "area_declarada_vs_calculada" in j["atributos"] and "fechamento" in j["atributos"]
