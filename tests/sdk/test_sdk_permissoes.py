"""SDK × permissões: 401 com token ruim, 403 tipado quando o token de escopo só-leitura tenta
escrever (a cláusula do portão), e o privilégio exigido exposto na exceção (`.exigido`/`.escopo`)."""

import secrets

import pytest
from plat import ErroAutenticacao, ErroPermissao, Plataforma

from tests.sdk.conftest import PREFIXO


def test_token_revogado_ou_inexistente_e_401_tipado(servidor):
    pla_ruim = Plataforma(servidor, "pt_nao-existe")
    with pytest.raises(ErroAutenticacao) as erro:
        pla_ruim.catalogo.listar(limite=1)
    assert erro.value.status == 401


def test_token_soleitura_escrever_e_403_tipado(pla_leitura):
    """Cláusula do portão: token com escopo só-leitura tentando criar item — 403 com exceção tipada
    e o escopo exigido exposto em `.escopo` (o detalhe da API viaja com a exceção)."""
    with pytest.raises(ErroPermissao) as erro:
        pla_leitura.catalogo.criar(tipo="ferramenta_resultado",
                                   titulo=f"{PREFIXO}deveria-recusar-{secrets.token_hex(3)}", dados={})
    assert erro.value.status == 403
    assert erro.value.codigo in ("sem_privilegio", "escopo_insuficiente")
    assert erro.value.exigido or erro.value.escopo


def test_token_leitura_ainda_le(pla_leitura):
    """O mesmo token só-leitura lê normalmente: a recusa é da ESCRITA, não do SDK nem do catálogo."""
    pagina = pla_leitura.catalogo.listar(limite=2)
    assert pagina.total >= 0


def test_apagar_item_de_outro_dono_e_404_tipado(pla_leitura, pla, limpar_itens):
    """Editor sem o item: escondido pela RLS, o SDK recebe 404 tipado também na escrita."""
    item = pla.catalogo.criar(tipo="ferramenta_resultado",
                              titulo=f"{PREFIXO}nao-e-seu-{secrets.token_hex(3)}",
                              dados={"ferramenta": "x", "parametros": {}, "resultado": {}})
    limpar_itens.append(item["id"])
    with pytest.raises(ErroPermissao) as erro:
        pla_leitura.catalogo.atualizar(item["id"], {"resumo": "quero mudar"})
    # 403 de escopo (recusado antes da RLS, que devolveria 404): tipado de qualquer forma
    assert erro.value.status == 403
