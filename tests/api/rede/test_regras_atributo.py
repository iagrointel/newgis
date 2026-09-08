"""Motor de regras de atributo de rede (item L4-29-regras-de-atributo-de-rede).

Portão, cláusula por cláusula:
  a) "≥ 6 funções de rede na linguagem documentadas e testadas" -> tests/unit/test_expressao_rede.py
     (aqui só se usa o que lá está provado);
  b) "regra de restrição recusa fechar chave entre 13,8 kV e 34,5 kV" -> test_restricao_recusa_chave_na_faixa
  c) "regra de cálculo preenche tensão em trecho novo" -> test_calculo_preenche_tensao_de_trecho_novo
  d) "validação em lote lista trafos sem UC" -> test_validacao_em_lote_lista_trafo_sem_uc
  e) paridade contra UN attribute rules -> docs/PARIDADE_REGRAS_ATRIBUTO.md (doc, testada a existência)
Refutação: "adversário escreve regra com laço infinito (jusante de jusante) e confere limite de
tempo/profundidade" -> test_laço_* (uma rodada avança o atributo exatamente UMA vez; limite de
passos/tempo corta com erro nomeado; profundidade acima da gramática é recusada na criação).

Banco: a suíte conecta como o app da TRILHA (`conexao_plat_app`), os inquilinos demo/demo2 vêm de
`plat.auth_login` (SECURITY DEFINER, o mesmo caminho de tests/api/test_rls.py) e o contexto de
inquilino é GUC local à transação — a fixture desfaz tudo no fim. Nada toca no schema de produção.
"""

import pytest

from app import limites
from app.erros import ErroAPI
from app.expressao.avaliador_py import ErroExpressao, avaliar_texto
from app.rede import regras

# ------------------------------------------------------------------ helpers de banco (padrão test_rls)


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


def _objeto(cur, tenant_id, tipo, codigo, *, nivel=None, subrede=None, alimentador=None, atributos=None):
    cur.execute(
        "INSERT INTO plat.rede_objeto(tenant_id, tipo, codigo, nivel, subrede, alimentador, atributos) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb) RETURNING id, tipo, codigo, nivel, subrede, "
        "alimentador, atributos",
        (tenant_id, tipo, codigo, nivel, subrede, alimentador, _json(atributos or {})),
    )
    return cur.fetchone()


def _json(v) -> str:
    import json

    return json.dumps(v, ensure_ascii=False)


# ------------------------------------------------------------------ contexto (puro)


def test_contexto_achata_atributos_e_monta_rede():
    ctx = regras.montar_contexto(
        {"tipo": "trecho", "codigo": "TG-1", "nivel": "mt", "subrede": "SR-A", "alimentador": "AL-1",
         "atributos": {"comprimento_km": 2.5, "clientes_jusante": 7}},
        {"tipo": "alimentador", "codigo": "AL-1", "atributos": {"tensao_kv": 13.8}},
    )
    assert ctx["comprimento_km"] == 2.5
    assert ctx["rede"] == {
        "nivel": "mt", "subrede": "SR-A", "alimentador": "AL-1",
        "tensao_alimentador_kv": 13.8, "jusante": 7,
        "atributos": {"comprimento_km": 2.5, "clientes_jusante": 7},
    }


def test_contexto_sem_alimentador_e_sem_jusante_e_nulo_nunca_erro():
    ctx = regras.montar_contexto({"tipo": "chave", "codigo": "CH-1", "atributos": {}})
    assert ctx["rede"]["tensao_alimentador_kv"] is None
    assert ctx["rede"]["jusante"] is None
    assert avaliar_texto("TensaoAlimentador()", ctx) is None
    assert avaliar_texto("ContarJusante()", ctx) is None


def test_atributo_chamado_rede_nunca_substitui_a_reservada():
    ctx = regras.montar_contexto(
        {"tipo": "x", "codigo": "X-1", "atributos": {"rede": "tentativa"}},
    )
    assert isinstance(ctx["rede"], dict)
    assert ctx["rede"]["atributos"]["rede"] == "tentativa"


# ------------------------------------------------------------------ validação de regra (pura)


def test_regra_com_perfil_desconhecido_e_recusada():
    with pytest.raises(ErroAPI) as e:
        regras.validar_regra(perfil="bloqueio", nome="n", alvo_tipo="chave", expressao="verdadeiro")
    assert e.value.status_code == 422  # type: ignore[attr-defined]
    assert e.value.erro == "perfil_invalido"  # type: ignore[attr-defined]


def test_regra_de_calculo_exige_atributo_alvo_e_restricao_nao_pode_ter():
    with pytest.raises(ErroAPI) as obrigatoria:
        regras.validar_regra(perfil="calculo", nome="n", alvo_tipo="trecho", expressao="13.8")
    assert obrigatoria.value.erro == "atributo_alvo_obrigatorio"  # type: ignore[attr-defined]
    with pytest.raises(ErroAPI) as proibida:
        regras.validar_regra(perfil="restricao", nome="n", alvo_tipo="chave", expressao="falso",
                             atributo_alvo="x")
    assert proibida.value.erro == "atributo_alvo_proibido"  # type: ignore[attr-defined]


def test_atributo_alvo_proibido_e_recusado():
    with pytest.raises(ErroAPI) as e:
        regras.validar_regra(perfil="calculo", nome="n", alvo_tipo="trafo", expressao="1",
                             atributo_alvo="__proto__")
    assert e.value.erro == "campo_nao_permitido"  # type: ignore[attr-defined]


def test_expressao_que_nao_compila_e_recusada_na_criacao():
    with pytest.raises(ErroAPI) as e:
        regras.validar_regra(perfil="restricao", nome="n", alvo_tipo="chave", expressao="Subrede((")
    assert e.value.erro == "expressao_invalida"  # type: ignore[attr-defined]


def test_expressao_profunda_demais_e_recusada_na_criacao():
    """Refutação (metade profundidade): 70 `Se` aninhados passam do teto de aninhamento do parser
    (60, docs/EXPRESSAO.md §2) — a regra não entra no banco, o erro é nomeado na hora de criar."""
    profunda = "Se(verdadeiro," * 70 + "1" + ",0)" * 70
    with pytest.raises(ErroAPI) as e:
        regras.validar_regra(perfil="restricao", nome="profunda", alvo_tipo="chave", expressao=profunda)
    assert "profundidade_excedida" in str(e.value.detail)  # type: ignore[attr-defined]


# ------------------------------------------------------------------ lógica de três valores (puro)


def test_restricao_na_faixa_13_8_a_34_5_kv():
    """A regra do portão, avaliada na mão: a janela 13,8-34,5 kV é a de média tensão de
    distribuição; fora dela (69 kV = subtransmissão) a chave pode ser fechada."""
    expressao = "TensaoAlimentador() >= 13.8 && TensaoAlimentador() <= 34.5"
    dentro = regras.montar_contexto(
        {"tipo": "chave", "codigo": "C", "alimentador": "AL-1"},
        {"tipo": "alimentador", "codigo": "AL-1", "atributos": {"tensao_kv": 13.8}},
    )
    fora = regras.montar_contexto(
        {"tipo": "chave", "codigo": "C", "alimentador": "AL-2"},
        {"tipo": "alimentador", "codigo": "AL-2", "atributos": {"tensao_kv": 69.0}},
    )
    sem = regras.montar_contexto({"tipo": "chave", "codigo": "C", "atributos": {}})
    assert avaliar_texto(expressao, dentro) is True
    assert avaliar_texto(expressao, fora) is False
    assert avaliar_texto(expressao, sem) is None  # sem alimentador: nulo NÃO recusa


# ------------------------------------------------------------------ banco: os três perfis


def test_restricao_recusa_chave_na_faixa(conexao_plat_app, _ids):
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    with con.cursor() as cur:
        alimento = _objeto(cur, _ids["demo"], "alimentador", "AL-MT-1", nivel="mt",
                           atributos={"tensao_kv": 13.8})
        _objeto(cur, _ids["demo"], "alimentador", "AL-AT-1", nivel="at",
                atributos={"tensao_kv": 69.0})
        media = _objeto(cur, _ids["demo"], "chave", "CH-101", alimentador="AL-MT-1")
        subtransmissao = _objeto(cur, _ids["demo"], "chave", "CH-202", alimentador="AL-AT-1")
        orfa = _objeto(cur, _ids["demo"], "chave", "CH-303")
        assert alimento and media and subtransmissao and orfa
        regras.criar_regra(
            cur, _ids["demo"], perfil="restricao", nome="chave so em media tensao",
            alvo_tipo="chave",
            expressao="TensaoAlimentador() >= 13.8 && TensaoAlimentador() <= 34.5",
            mensagem="fechamento de chave só entre 13,8 kV e 34,5 kV",
        )
        r_media = regras.checar_restricao(cur, media)
        r_fora = regras.checar_restricao(cur, subtransmissao)
        r_orfa = regras.checar_restricao(cur, orfa)
    assert r_media["permitido"] is False
    assert r_media["recusas"][0]["regra"] == "chave so em media tensao"
    assert r_fora["permitido"] is True and r_fora["recusas"] == []
    assert r_orfa["permitido"] is True  # nulo não recusa


def test_regra_que_erra_recusa_com_erro_nomeado(conexao_plat_app, _ids):
    """Falha fechada: expressão que compila mas erra na avaliação (texto + número) RECUSA, com o
    código do erro na resposta — regra que não consegue avaliar nunca autoriza por omissão."""
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    with con.cursor() as cur:
        alvo = _objeto(cur, _ids["demo"], "chave", "CH-ERR", atributos={"fase": "ABC"})
        regras.criar_regra(
            cur, _ids["demo"], perfil="restricao", nome="regra que erra", alvo_tipo="chave",
            expressao="AtributoRede('fase') + 1 > 0",
        )
        r = regras.checar_restricao(cur, alvo)
    assert r["permitido"] is False
    assert r["recusas"][0]["erro"] == "tipo_invalido"


def test_calculo_preenche_tensao_de_trecho_novo(conexao_plat_app, _ids, medida):
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    with con.cursor() as cur:
        _objeto(cur, _ids["demo"], "alimentador", "AL-1", nivel="mt", atributos={"tensao_kv": 13.8})
        trecho = _objeto(cur, _ids["demo"], "trecho", "TG-9001", nivel="mt", alimentador="AL-1")
        assert trecho["atributos"] == {}
        regras.criar_regra(
            cur, _ids["demo"], perfil="calculo", nome="herda tensao do alimentador",
            alvo_tipo="trecho", expressao="TensaoAlimentador()", atributo_alvo="tensao_kv",
        )
        r1 = regras.aplicar_calculo(cur)
        cur.execute("SELECT atributos FROM plat.rede_objeto WHERE tipo = 'trecho' AND codigo = 'TG-9001'")
        depois = cur.fetchone()["atributos"]
    assert r1["escritos"] == 1 and r1["erros"] == []
    assert depois["tensao_kv"] == 13.8
    medida("L4-29-regras-de-atributo-de-rede")(
        "rodada_calculo_escritos", r1["escritos"], "atributos",
        "regras.aplicar_calculo(cur) sobre 1 trecho novo + 1 alimentador",
    )
    # reavaliar é rodada NOVA e explícita; o valor fica o mesmo (sem acúmulo)


def test_laco_autorreferente_avanca_uma_vez_por_rodada(conexao_plat_app, _ids, medida):
    """Refutação do item: a regra lê o atributo que ela mesma escreve. O motor NÃO itera até um
    ponto fixo: cada rodada avança exatamente 1. O laço "jusante de jusante" não existe por
    construção — rodar de novo é ação do operador, e cada rodada é barata e medida."""
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    with con.cursor() as cur:
        _objeto(cur, _ids["demo"], "trafo", "TR-LACO", atributos={"contador": 0})
        regras.criar_regra(
            cur, _ids["demo"], perfil="calculo", nome="avanca contador", alvo_tipo="trafo",
            expressao="AtributoRede('contador') + 1", atributo_alvo="contador",
        )
        regras.aplicar_calculo(cur)
        cur.execute("SELECT atributos FROM plat.rede_objeto WHERE codigo = 'TR-LACO'")
        assert cur.fetchone()["atributos"]["contador"] == 1
        regras.aplicar_calculo(cur)  # rodada 2: +1, não 2^n
        cur.execute("SELECT atributos FROM plat.rede_objeto WHERE codigo = 'TR-LACO'")
        depois = cur.fetchone()["atributos"]["contador"]
        assert depois == 2
        medida("L4-29-regras-de-atributo-de-rede")(
            "contador_apos_duas_rodadas", depois, "unidades",
            "regra autorreferente (AtributoRede('contador') + 1) rodada 2x: laço não existe",
        )


def test_laco_corta_no_orcamento_de_passos_com_erro_nomeado(conexao_plat_app, _ids):
    """Refutação (metade tempo): o orçamento do avaliador é costura exposta do motor (`limite_passos`/
    `limite_ms`, documentado em docs/PARIDADE_REGRAS_ATRIBUTO.md §4) — apertado, a rodada registra o
    erro NOMEADO e a casa continua de pé; erro de regra em cálculo nunca derruba a rodada."""
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    with con.cursor() as cur:
        _objeto(cur, _ids["demo"], "trafo", "TR-CARO", atributos={"n": 2})
        regras.criar_regra(
            cur, _ids["demo"], perfil="calculo", nome="expressao cara", alvo_tipo="trafo",
            expressao="Potencia(AtributoRede('n'), 10) * Potencia(AtributoRede('n'), 10)",
            atributo_alvo="m",
        )
        r = regras.aplicar_calculo(cur, limite_passos=2)
    assert r["escritos"] == 0
    assert r["erros_total"] == 1
    assert r["erros"][0]["erro"] == "limite_passos"
    assert r["erros"][0]["objeto"] == "TR-CARO"


def test_validacao_em_lote_lista_trafo_sem_uc(conexao_plat_app, _ids, medida):
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    with con.cursor() as cur:
        _objeto(cur, _ids["demo"], "trafo", "TR-SEM-UC", atributos={"clientes_jusante": 0})
        _objeto(cur, _ids["demo"], "trafo", "TR-OK", atributos={"clientes_jusante": 42})
        _objeto(cur, _ids["demo"], "trafo", "TR-SEM-DADO", atributos={})
        regras.criar_regra(
            cur, _ids["demo"], perfil="validacao", nome="trafo sem uc a jusante",
            alvo_tipo="trafo", expressao="ContarJusante() == 0",
            mensagem="transformador sem unidade consumidora a jusante",
        )
        r = regras.rodar_validacao(cur)
    assert r["regras"] == 1 and r["truncado"] is False
    codigos = sorted(i["objeto"] for i in r["itens"])
    assert codigos == ["TR-SEM-UC"]  # nulo (TR-SEM-DADO) não lista; com UC (TR-OK) não lista
    assert r["itens"][0]["mensagem"] == "transformador sem unidade consumidora a jusante"
    medida("L4-29-regras-de-atributo-de-rede")(
        "validacao_itens_sem_uc", r["total"], "itens",
        "regras.rodar_validacao(cur) sobre 3 trafos (1 sem UC, 1 com UC, 1 sem dado)",
    )


# ------------------------------------------------------------------ teto e RLS


def test_teto_de_regras_ativas_e_recusado(conexao_plat_app, _ids, monkeypatch):
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    monkeypatch.setattr(limites, "REDE_REGRA_MAX", 1)
    with con.cursor() as cur:
        regras.criar_regra(cur, _ids["demo"], perfil="validacao", nome="r1", alvo_tipo="trafo",
                           expressao="falso")
        with pytest.raises(ErroAPI) as e:
            regras.criar_regra(cur, _ids["demo"], perfil="validacao", nome="r2", alvo_tipo="trafo",
                               expressao="falso")
    assert e.value.erro == "regras_demais"  # type: ignore[attr-defined]


def test_inquilino_b_nao_ve_regra_nem_objeto_de_a(conexao_plat_app, _ids):
    con = conexao_plat_app
    _contexto(con, _ids["demo"])
    with con.cursor() as cur:
        _objeto(cur, _ids["demo"], "trafo", "TR-DE-A", atributos={"clientes_jusante": 0})
        regras.criar_regra(cur, _ids["demo"], perfil="validacao", nome="de a", alvo_tipo="trafo",
                           expressao="ContarJusante() == 0")
    _contexto(con, _ids["demo2"])
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.rede_regra")
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.rede_objeto")
        assert cur.fetchone()["n"] == 0
        r = regras.rodar_validacao(cur)
    assert r == {"regras": 0, "itens": [], "total": 0, "truncado": False}


def test_erro_de_avaliacao_nunca_e_engolido_pela_regra_de_rede(conexao_plat_app, _ids):
    """Guarda do contrato da linguagem: por trás do motor está o avaliador comum — campo fora do
    contexto continua sendo PERMISSÃO (campo_nao_permitido), nunca nulo silencioso."""
    with pytest.raises(ErroExpressao) as e:
        avaliar_texto("Subrede()", {})
    assert e.value.codigo == "campo_nao_permitido"
