"""Núcleo puro do ensaio de restauração (item L0-06-c): a classificação das diferenças de COUNT(*) contra
o instante do dump, o nome do banco temporário e a escolha determinística dos objetos do manifesto."""

from app.backup import drill


def test_nome_do_banco_temporario_e_seguro_e_prefixado():
    nome = drill.nome_banco_temporario("demo2_1234_1757280000")
    assert nome.startswith("plat_drill_")
    assert nome == nome.lower()
    assert all(c.isalnum() or c == "_" for c in nome)
    assert len(nome) <= 63


def test_nome_do_banco_temporario_limpa_o_que_precisaria_de_aspas():
    assert drill.nome_banco_temporario("Inq Uilino-Á/x") == "plat_drill_inq_uilino_x"
    assert drill.nome_banco_temporario("---") == "plat_drill_sem_marca"
    assert len(drill.nome_banco_temporario("a" * 200)) == 63


def test_sem_diferenca_nao_ha_divergencia_nem_posterior():
    div, post = drill.classificar_contagens([
        {"tabela": "camada", "restaurado": 12, "producao": 12},
        {"tabela": "item", "restaurado": 0, "producao": 0},
    ])
    assert div == []
    assert post == []


def test_linha_acrescentada_apos_o_dump_e_posterior_nomeada_com_o_delta():
    div, post = drill.classificar_contagens([{"tabela": "evento", "restaurado": 100, "producao": 103}])
    assert div == []
    assert post == [{"tabela": "evento", "restaurado": 100, "producao": 103, "delta": 3}]


def test_producao_com_menos_linhas_que_a_copia_e_divergencia():
    div, post = drill.classificar_contagens([{"tabela": "camada", "restaurado": 50, "producao": 49}])
    assert post == []
    assert len(div) == 1 and div[0]["tabela"] == "camada" and div[0]["delta"] == -1
    assert "mais linhas que a produção" in div[0]["motivo"]


def test_tabela_ausente_na_copia_restaurada_e_divergencia():
    div, _ = drill.classificar_contagens([{"tabela": "item", "restaurado": None, "producao": 7}])
    assert len(div) == 1 and div[0]["restaurado"] is None
    assert "ausente" in div[0]["motivo"]


def test_divergencias_saem_em_ordem_de_tabela():
    div, post = drill.classificar_contagens([
        {"tabela": "z", "restaurado": 2, "producao": 1},
        {"tabela": "a", "restaurado": None, "producao": 1},
        {"tabela": "m", "restaurado": 1, "producao": 4},
    ])
    assert [d["tabela"] for d in div] == ["a", "z"]
    assert [p["tabela"] for p in post] == ["m"]


def test_escolha_de_objetos_e_deterministica_e_limitada():
    objetos = [{"chave": f"demo2/{n}.dump", "sha256": "0" * 64, "bytes": 1} for n in "edcba"]
    escolhidos = drill.escolher_objetos(objetos, 3)
    assert [o["chave"] for o in escolhidos] == ["demo2/a.dump", "demo2/b.dump", "demo2/c.dump"]
    assert drill.escolher_objetos(objetos, 0) == []
    assert len(drill.escolher_objetos(objetos[:2], 3)) == 2
