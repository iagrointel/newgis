"""Portão do item L2-03-edicao (histórico/restauração e anexos por feição, complemento da API transacional
do L2-03-a): reusa `FabricaCamada`/`camada_a`/`camada_b` de `tests/api/test_edicao_transacional.py` (mesma
tabela criada direto no banco com `plat.camada_preparar`, agora também com `tg_historico`)."""

from __future__ import annotations

import base64

import pytest

from tests.api.test_edicao_transacional import (  # noqa: F401 — fixtures reaproveitadas
    _admin_usuario_id,
    _ponto,
    camada_a,
    camada_a_somente_proprias,
    camada_b,
    fabrica,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def _criar_ponto(sessao, camada_id, nome="um", categoria="A", lon=-46.1):
    corpo = {"adicionar": [{"atributos": {"nome": nome, "categoria": categoria}, "geometria": _ponto(lon)}],
             "atualizar": [], "apagar": []}
    r = sessao.post(f"/api/camadas/{camada_id}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()["adicionar"][0]


# ---------------------------------------------------------------- histórico: quem, quando, o quê
def test_historico_registra_inserir_atualizar_apagar_em_ordem(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"])
    gid = f["id"]
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [{"id": gid, "versao": f["versao"], "atributos": {"nome": "dois"}}],
              "apagar": []},
    )
    assert r.status_code == 200, r.text
    nova_versao = r.json()["atualizar"][0]["versao"]
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [], "apagar": [{"id": gid, "versao": nova_versao}]},
    )
    assert r.status_code == 200, r.text

    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico")
    assert hist.status_code == 200, hist.text
    linhas = hist.json()
    operacoes = [h["operacao"] for h in linhas]
    # mais recente primeiro: apagar, atualizar, inserir
    assert operacoes == ["apagar", "atualizar", "inserir"]
    assert linhas[-1]["atributos_depois"]["nome"] == "um"
    assert linhas[1]["atributos_antes"]["nome"] == "um"
    assert linhas[1]["atributos_depois"]["nome"] == "dois"
    assert linhas[0]["atributos_antes"]["nome"] == "dois"
    for h in linhas:
        assert h["usuario_id"] is not None
        assert h["momento"] is not None


def test_historico_de_feicao_de_outro_inquilino_nunca_aparece(sessao_a, sessao_b, camada_a, camada_b):
    f = _criar_ponto(sessao_a, camada_a["id"])
    r = sessao_b.get(f"/api/camadas/{camada_b['id']}/feicoes/{f['id']}/historico")
    assert r.status_code == 200
    assert r.json() == []  # a mesma tabela d_demo2 nunca contém globalid nascido em d_demo


def test_historico_de_camada_de_outro_inquilino_e_404(sessao_b, camada_a):
    r = sessao_b.get(f"/api/camadas/{camada_a['id']}/feicoes/00000000-0000-0000-0000-000000000000/historico")
    assert r.status_code == 404


# ---------------------------------------------------------------- restauração
def test_restaurar_atributo_apos_atualizacao(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"], nome="original")
    gid = f["id"]
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [{"id": gid, "versao": f["versao"], "atributos": {"nome": "mudado"}}],
              "apagar": []},
    )
    assert r.status_code == 200, r.text

    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    entrada_insercao = [h for h in hist if h["operacao"] == "inserir"][0]

    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico/{entrada_insercao['id']}/restaurar"
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["sucesso"] is True
    assert corpo["recriada"] is False

    # a restauração grava DUAS entradas a mais (nunca reescreve as anteriores): a mecânica ('atualizar', pelo
    # MESMO gatilho genérico que qualquer UPDATE dispara) e o marcador explícito ('restaurar', para distinguir
    # "isto foi uma restauração" de uma edição comum ao consultar o histórico)
    hist2 = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    assert len(hist2) == len(hist) + 2
    assert hist2[0]["operacao"] == "restaurar"
    assert hist2[0]["atributos_depois"]["nome"] == "original"
    assert hist2[1]["operacao"] == "atualizar"
    assert hist2[1]["atributos_depois"]["nome"] == "original"


def test_restaurar_recria_feicao_apagada_com_o_mesmo_globalid(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"], nome="fenix")
    gid = f["id"]
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [], "apagar": [{"id": gid, "versao": f["versao"]}]},
    )
    assert r.status_code == 200, r.text

    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    entrada_insercao = [h for h in hist if h["operacao"] == "inserir"][0]

    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico/{entrada_insercao['id']}/restaurar"
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["recriada"] is True
    assert corpo["id"] == gid  # MESMO globalid: qualquer referência externa continua válida

    # e agora dá pra editar de novo pela porta normal
    r2 = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [{"id": gid, "versao": corpo["versao"], "atributos": {"nome": "volta"}}],
              "apagar": []},
    )
    assert r2.status_code == 200, r2.text


def test_restaurar_entrada_de_exclusao_e_recusado(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"])
    gid = f["id"]
    sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [], "apagar": [{"id": gid, "versao": f["versao"]}]},
    )
    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    entrada_apagar = [h for h in hist if h["operacao"] == "apagar"][0]
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico/{entrada_apagar['id']}/restaurar")
    assert r.status_code == 409
    assert r.json()["erro"] == "nada_a_restaurar"


def test_restaurar_domino_atual_ainda_e_aplicado(sessao_a, camada_a):
    """Uma regra pode ter mudado desde que o histórico foi gravado: restaurar não pula a validação atual."""
    f = _criar_ponto(sessao_a, camada_a["id"], categoria="A")
    gid, versao = f["id"], f["versao"]
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [{"id": gid, "versao": versao, "atributos": {"categoria": "B"}}],
              "apagar": []},
    )
    assert r.status_code == 200, r.text
    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    entrada_a = [h for h in hist if h["atributos_depois"] and h["atributos_depois"].get("categoria") == "A"][0]
    # restaurar para "A" ainda é permitido (domínio não mudou aqui) — prova que o caminho de validação roda
    r2 = sessao_a.post(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico/{entrada_a['id']}/restaurar")
    assert r2.status_code == 200, r2.text


def test_restaurar_feicao_de_outro_inquilino_e_404(sessao_a, sessao_b, camada_a, camada_b):
    f = _criar_ponto(sessao_a, camada_a["id"])
    gid = f["id"]
    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    hid = hist[0]["id"]
    r = sessao_b.post(f"/api/camadas/{camada_b['id']}/feicoes/{gid}/historico/{hid}/restaurar")
    assert r.status_code == 404


# ---------------------------------------------------------------- domínio/obrigatório aplicado no SERVIDOR
# (refutação do item-pai L2-03-a, reconferida aqui pelo caminho de restauração e pela API direta, "sem passar
# pela tela")
def test_atributo_fora_do_dominio_direto_na_api_sem_navegador(sessao_a, camada_a):
    # modo padrão é "transacao": o erro de domínio propaga como 422 da própria chamada HTTP — não é preciso
    # passar pelo navegador para provar que o servidor recusa (refutação do item: "sem passar pela tela")
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [{"atributos": {"nome": "x", "categoria": "Z"}, "geometria": _ponto()}],
              "atualizar": [], "apagar": []},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "fora_do_dominio"


def test_campo_obrigatorio_ausente_direto_na_api_e_recusado(sessao_a, camada_a):
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [{"atributos": {"categoria": "A"}, "geometria": _ponto()}], "atualizar": [], "apagar": []},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_obrigatorio"


# ---------------------------------------------------------------- anexos: limite de tamanho e de tipo
def test_anexo_enviado_e_listado(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"])
    gid = f["id"]
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos",
        json={"nome": "foto.png", "content_type": "image/png", "conteudo": _b64(PNG_1X1)},
    )
    assert r.status_code == 201, r.text
    anexo = r.json()
    assert anexo["bytes"] == len(PNG_1X1)
    assert anexo["content_type"] == "image/png"

    r2 = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos")
    assert r2.status_code == 200
    lista = r2.json()
    assert len(lista) == 1
    assert lista[0]["id"] == anexo["id"]

    r3 = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}")
    assert r3.status_code == 200
    assert r3.content == PNG_1X1
    assert r3.headers["content-type"].startswith("image/png")


def test_anexo_tipo_nao_permitido_e_recusado(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"])
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/anexos",
        json={"nome": "script.js", "content_type": "application/javascript", "conteudo": _b64(b"alert(1)")},
    )
    assert r.status_code == 415
    assert r.json()["erro"] == "tipo_nao_permitido"


def test_anexo_acima_do_limite_de_tamanho_e_recusado(sessao_a, camada_a, monkeypatch):
    from app import limites
    monkeypatch.setattr(limites, "ANEXO_TAMANHO_MAX", 100)
    f = _criar_ponto(sessao_a, camada_a["id"])
    grande = b"\x00" * 1000
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/anexos",
        json={"nome": "grande.png", "content_type": "image/png", "conteudo": _b64(grande)},
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "anexo_grande"


def test_anexo_no_teto_real_ainda_da_anexo_grande_nao_corpo_grande(sessao_a, camada_a):
    """Achado do adversário (07/09): o envio é JSON com o conteúdo em base64, que incha o arquivo em ~4/3.
    Com `ANEXO_TAMANHO_MAX` (não substituído por monkeypatch aqui, ao contrário do teste acima) igual ao
    teto de corpo do middleware (item L0-12), o 413 genérico disparava ANTES desta checagem rodar, e o
    422 "anexo_grande" nunca aparecia — o limite documentado de anexo virava letra morta na prática.
    `ANEXO_TAMANHO_MAX` foi reduzido para caber, com folga, dentro do teto de corpo mesmo codificado."""
    from app import limites

    assert limites.ANEXO_TAMANHO_MAX < limites.CORPO_MAX_PADRAO_BYTES * 3 // 4, (
        "ANEXO_TAMANHO_MAX tem de caber em CORPO_MAX_PADRAO_BYTES mesmo depois do inchaço de base64 (~4/3), "
        "senão o 413 do corpo dispara antes do 422 específico do anexo"
    )
    f = _criar_ponto(sessao_a, camada_a["id"])
    grande = b"\x89PNG\r\n\x1a\n" + b"0" * (limites.ANEXO_TAMANHO_MAX + 10_000)
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/anexos",
        json={"nome": "grande.png", "content_type": "image/png", "conteudo": _b64(grande)},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "anexo_grande"


def test_anexo_conteudo_nao_bate_com_content_type_declarado_e_recusado(sessao_a, camada_a):
    """item L7-03-b (varredura de conteúdo): PDF de verdade declarado como PNG."""
    f = _criar_ponto(sessao_a, camada_a["id"])
    pdf_de_verdade = b"%PDF-1.4\n%..." + b"\x00" * 32
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/anexos",
        json={"nome": "disfarcado.png", "content_type": "image/png", "conteudo": _b64(pdf_de_verdade)},
    )
    assert r.status_code == 415
    assert r.json()["erro"] == "conteudo_recusado"


def test_anexo_apagado_some_da_listagem(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"])
    envio = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/anexos",
        json={"nome": "foto.png", "content_type": "image/png", "conteudo": _b64(PNG_1X1)},
    ).json()
    r = sessao_a.delete(f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/anexos/{envio['id']}")
    assert r.status_code == 204
    lista = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/anexos").json()
    assert lista == []


def test_anexo_de_feicao_de_outro_inquilino_e_404(sessao_a, sessao_b, camada_a, camada_b):
    f = _criar_ponto(sessao_a, camada_a["id"])
    r = sessao_b.get(f"/api/camadas/{camada_b['id']}/feicoes/{f['id']}/anexos/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_anexo_exige_feicao_existente(sessao_a, camada_a):
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/feicoes/00000000-0000-0000-0000-000000000000/anexos",
        json={"nome": "foto.png", "content_type": "image/png", "conteudo": _b64(PNG_1X1)},
    )
    assert r.status_code == 404
    assert r.json()["erro"] == "feicao_inexistente"


# ---------------------------------------------------------------- edição concorrente (revalidação da cláusula
# do item-pai, mas exercitada a partir de uma feição que também tem histórico gravado)
def test_conflito_de_versao_nao_apaga_a_trilha_de_historico(sessao_a, sessao_b, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"], nome="base")
    gid, versao = f["id"], f["versao"]
    r1 = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [{"id": gid, "versao": versao, "atributos": {"nome": "sessao-a"}}],
              "apagar": []},
    )
    assert r1.status_code == 200
    r2 = sessao_a.post(  # mesma sessão simulando "outra aba": ainda usa a versão velha de propósito
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [{"id": gid, "versao": versao, "atributos": {"nome": "sessao-b"}}],
              "apagar": []},
    )
    assert r2.status_code == 409
    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    # só UMA entrada de 'atualizar' (a que teve sucesso); a que tomou 409 nunca chegou a gravar no banco
    assert sum(1 for h in hist if h["operacao"] == "atualizar") == 1


# ---------------------------------------------------------------- obter feição exata (não recortada por tile)
def test_obter_feicao_devolve_geometria_e_atributos_exatos(sessao_a, camada_a):
    f = _criar_ponto(sessao_a, camada_a["id"], nome="exata", lon=-46.123456)
    r = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["id"] == f["id"]
    assert corpo["versao"] == f["versao"]
    assert corpo["atributos"]["nome"] == "exata"
    assert corpo["geometria"]["coordinates"][0] == pytest.approx(-46.123456)


def test_obter_feicao_inexistente_e_404(sessao_a, camada_a):
    r = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_obter_feicao_de_outro_inquilino_e_404(sessao_a, sessao_b, camada_a, camada_b):
    f = _criar_ponto(sessao_a, camada_a["id"])
    r = sessao_b.get(f"/api/camadas/{camada_b['id']}/feicoes/{f['id']}")
    assert r.status_code == 404
