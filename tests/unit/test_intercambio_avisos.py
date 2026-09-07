"""Regra de truncamento de nome de campo no DBF (item L6-02-o), sem banco: `app.intercambio.avisos`.
Referenciada no docstring do próprio módulo desde 06/09; escrita agora junto com o resto do item."""

from __future__ import annotations

from app.intercambio import avisos


def test_nome_ate_10_caracteres_nao_muda():
    usados: set[str] = set()
    assert avisos.nome_dbf("categoria", usados) == "categoria"


def test_nome_maior_que_10_e_truncado_em_10():
    usados: set[str] = set()
    assert avisos.nome_dbf("comprimento_total", usados) == "compriment"


def test_colisao_de_truncamento_ganha_sufixo_numerico():
    usados: set[str] = set()
    a = avisos.nome_dbf("comprimento_total", usados)
    b = avisos.nome_dbf("comprimento_parcial", usados)
    assert a == "compriment"
    assert b != a and b.startswith("comprime_")


def test_mapa_nomes_dbf_so_lista_o_que_muda():
    campos = [{"nome": "categoria", "tipo": "text"}, {"nome": "campo_muito_longo_de_verdade", "tipo": "text"}]
    mapa = avisos.mapa_nomes_dbf(campos)
    assert "categoria" not in mapa
    assert mapa["campo_muito_longo_de_verdade"] == "campo_muit"


def test_avisos_shapefile_nome_longo_e_data_hora():
    campos = [
        {"nome": "campo_muito_longo_de_verdade", "tipo": "text"},
        {"nome": "data_evento", "tipo": "timestamp with time zone"},
        {"nome": "categoria", "tipo": "text"},
    ]
    mapa, mensagens = avisos.avisos_shapefile(campos)
    assert mapa["campo_muito_longo_de_verdade"] == "campo_muit"
    assert any("mais de 10 caracteres" in m and "campo_muito_longo_de_verdade" in m for m in mensagens)
    assert any("data-hora" in m and "data_evento" in m for m in mensagens)
    assert not any("categoria" in m for m in mensagens)


def test_avisos_shapefile_texto_longo_gera_aviso_de_valor_truncado():
    campos = [{"nome": "descricao", "tipo": "text"}]
    _, mensagens = avisos.avisos_shapefile(campos, max_len_texto={"descricao": 999})
    assert any("texto de até 999" in m for m in mensagens)
