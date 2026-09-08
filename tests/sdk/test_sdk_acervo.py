"""SDK × acervo da casa: listagem só traz fonte com licença ESCRITA (regra D17), a ficha devolve os
mesmos campos da rota, e a assinatura de fonte marcada com risco de dado pessoal SEM a confirmação
explícita é 409 tipado (`Conflito`)."""

import psycopg2
import pytest
from plat import Conflito, NaoEncontrado, Plataforma

from tests.sdk.conftest import PREFIXO


def test_fontes_e_ficha_paginam_sem_erro(pla):
    d = pla.acervo.fontes(limite=5)
    assert d["total"] >= len(d["itens"]) >= 0
    todas = list(pla.acervo.iterar(limite=5))
    assert len(todas) <= d["total"]
    if d["itens"]:
        ficha = pla.acervo.ficha(d["itens"][0]["fonte_id"])
        assert ficha["fonte_id"] == d["itens"][0]["fonte_id"]
        assert ficha["licenca"]  # D17: o que aparece tem licença escrita


def _fonte_marcada_risco_pii(con) -> str | None:
    """Curadoria manual em plat.acervo_lgpd (migração 037/041): fonte com licença escrita E risco_pii."""
    from app.schema_ambiente import CursorSchemaAmbiente

    with con.cursor(cursor_factory=CursorSchemaAmbiente) as cur:
        cur.execute(
            "SELECT f.fonte_id FROM plat.acervo_ficha f JOIN plat.acervo_lgpd l USING (fonte_id) "
            "WHERE l.risco_pii AND f.licenca IS NOT NULL AND btrim(f.licenca) <> '' LIMIT 1"
        )
        r = cur.fetchone()
    return r["fonte_id"] if r else None


def test_assinar_sem_confirmacao_pii_e_409_tipado(pla, env, limpar_itens):
    """Fonte marcada em plat.acervo_lgpd: `assinar` sem `confirma_risco_pii=True` é recusado com
    409 tipado; com a confirmação, cria o item `conexao` (a suíte apaga o item no fim)."""
    con = psycopg2.connect(env["PLAT_DSN"])
    try:
        fonte_id = _fonte_marcada_risco_pii(con)
    finally:
        con.close()
    if not fonte_id:
        pytest.skip("nenhuma fonte marcada com risco de dado pessoal nesta base")
    with pytest.raises(Conflito) as recusa:
        pla.acervo.assinar(fonte_id)
    assert recusa.value.status == 409
    item = pla.acervo.assinar(fonte_id, confirma_risco_pii=True)
    assert item["tipo"] == "conexao"
    assert item["dados"]["parametros"]["fonte_id"] == fonte_id
    limpar_itens.append(item["id"])


def test_ficha_de_fonte_inexistente_e_404(pla, pla_leitura):
    assert isinstance(pla_leitura, Plataforma)  # o token só-leitura existe e lê; a recusa é da ficha
    with pytest.raises(NaoEncontrado):
        pla.acervo.ficha(f"{PREFIXO}fonte-inexistente")
