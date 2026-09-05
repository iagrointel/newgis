"""Gramática da busca (ADR 0004 seção 7.2): 12 consultas por campo → SQL esperado; ':' sem campo, campo
desconhecido, 201 termos = erro; sintaxe tsquery direta ('a & b', 'a:*') é texto; aspas, parênteses, OR/NOT/-,
intervalo com '*'. Nunca aparece to_tsquery com texto do usuário."""

import pytest

from app.catalogo import busca

TIPOS = {"mapa", "camada_vetorial", "arquivo"}
CFG = busca.CFG
U = "3f1e2d4c-5b6a-4798-8a9b-0c1d2e3f4a5b"


def t(q):
    return busca.traduzir(q, TIPOS)


CASOS = [
    ("municipio", f"i.busca @@ websearch_to_tsquery({CFG}, %s)", ["municipio"]),
    ("titulo:mapa", f"to_tsvector({CFG}, coalesce(i.titulo, '')) @@ websearch_to_tsquery({CFG}, %s)", ["mapa"]),
    (
        "tags:ibge",
        f"to_tsvector({CFG}, coalesce(plat.tags_texto(i.tags), '')) @@ websearch_to_tsquery({CFG}, %s)",
        ["ibge"],
    ),
    ("resumo:x", f"to_tsvector({CFG}, coalesce(i.resumo, '')) @@ websearch_to_tsquery({CFG}, %s)", ["x"]),
    ("descricao:x", f"to_tsvector({CFG}, coalesce(i.descricao, '')) @@ websearch_to_tsquery({CFG}, %s)", ["x"]),
    ("dono:maria", "i.dono_id IN (SELECT u.id FROM plat.usuario u WHERE u.login = %s)", ["maria"]),
    ("tipo:mapa", "i.tipo = %s", ["mapa"]),
    ("status:autoritativo", "i.status = %s", ["autoritativo"]),
    ("status:nenhum", "i.status IS NULL", []),
    ("acesso:inquilino", "i.acesso = %s", ["inquilino"]),
    (f"id:{U}", "i.id = %s::uuid", [U]),
    (f"grupo:{U}", "EXISTS (SELECT 1 FROM plat.item_grupo ig WHERE ig.item_id = i.id AND ig.grupo_id = %s::uuid)", [U]),
    ("origem:referenciado", "i.origem = %s", ["referenciado"]),
    (f"pasta:{U}", "i.pasta_id = %s::uuid", [U]),
    ("pasta:Ambiente", "i.pasta_id IN (SELECT p.id FROM plat.pasta p WHERE lower(p.nome) = %s)", ["ambiente"]),
]


@pytest.mark.parametrize("q,sql,params", CASOS, ids=[c[0] for c in CASOS])
def test_consulta_por_campo(q, sql, params):
    c = t(q)
    assert c.sql == sql
    assert c.params == params
    assert "to_tsquery(" not in c.sql.replace("websearch_to_tsquery(", "")


def test_intervalos():
    c = t("criado:[2026-01-01 TO 2026-03-31]")
    assert c.sql == "(i.criado_em >= %s AND i.criado_em < %s)"
    assert [p.isoformat() for p in c.params] == ["2026-01-01T00:00:00+00:00", "2026-04-01T00:00:00+00:00"]
    c = t("modificado:[2026-08 TO *]")
    assert c.sql == "(i.modificado_em >= %s)" and c.params[0].isoformat() == "2026-08-01T00:00:00+00:00"
    c = t("modificado:[* TO 2026]")
    assert c.sql == "(i.modificado_em < %s)" and c.params[0].isoformat() == "2027-01-01T00:00:00+00:00"


def test_operadores_e_arvore():
    c = t("(a OR b) c")
    assert c.sql.startswith("((") and " OR " in c.sql and " AND " in c.sql
    assert c.params == ["a", "b", "c"] and c.texto_rank == ["a", "b", "c"]
    c = t("a NOT b")
    assert c.sql.endswith("NOT i.busca @@ websearch_to_tsquery('plat.pt_sem_acento'::regconfig, %s))")
    assert c.texto_rank == ["a"]  # negado não entra no rank
    c = t("a -b")
    assert "NOT " in c.sql and c.params == ["a", "b"]


def test_frase_e_tsquery_direta_sao_texto():
    c = t('"setor censitario"')
    assert c.params == ['"setor censitario"'] and c.ultimo_livre is None
    c = t("a & b")
    assert c.params == ["a", "&", "b"]  # o & vira texto: websearch_to_tsquery nunca levanta
    # "a:*" e "foo:bar" são campo desconhecido (422), não sintaxe tsquery: a regra do campo vence
    with pytest.raises(busca.ErroSintaxe):
        t("a:*")
    with pytest.raises(busca.ErroSintaxe) as e:
        t("foo:bar")
    assert e.value.codigo == "campo_invalido" and e.value.detalhe == {"campo": "foo", "valor": "bar"}


def test_erros_de_sintaxe():
    with pytest.raises(busca.ErroSintaxe) as e:
        t(":x")
    assert e.value.codigo == "campo_invalido"
    with pytest.raises(busca.ErroSintaxe) as e:
        t(" ".join(["t"] * 201))
    assert e.value.codigo == "busca_complexa" and e.value.detalhe == {"termos": 201}
    with pytest.raises(busca.ErroSintaxe) as e:
        t("a" * 1001)
    assert e.value.codigo == "busca_complexa"
    with pytest.raises(busca.ErroSintaxe) as e:
        t("tipo:inexistente")
    assert e.value.codigo == "campo_invalido"
    with pytest.raises(busca.ErroSintaxe):
        t("id:nao-e-uuid")
    with pytest.raises(busca.ErroSintaxe):
        t("criado:[x TO y]")
    with pytest.raises(busca.ErroSintaxe):
        t("titulo:[2026 TO 2027]")


def test_vazio_e_prefixo():
    assert t("").sql == "true" and t("   ").params == []
    c = t("muni")
    assert c.ultimo_livre == "muni" and c.termos == 1


def test_cursor_ida_e_volta_e_assinatura():
    assinatura = busca.assinatura({"q": "x", "tipo": ["mapa"]})
    cur = busca.cursor_codificar("modificado_em", "desc", ["2026-09-05T10:00:00+00:00"], U, assinatura)
    corpo = busca.cursor_decodificar(cur, assinatura)
    assert corpo["v"] == ["2026-09-05T10:00:00+00:00"] and corpo["id"] == U and corpo["o"] == "modificado_em"
    with pytest.raises(Exception) as e:
        busca.cursor_decodificar(cur, busca.assinatura({"q": "outra"}))
    assert getattr(e.value, "erro", "") == "cursor_invalido"
    with pytest.raises(Exception) as e:
        busca.cursor_decodificar("nao-e-base64!!", assinatura)
    assert getattr(e.value, "erro", "") == "cursor_invalido"
