"""Item L7-13-a-chamados — unidade. Cobre as peças que não precisam de banco nem de Garage: os textos do
correio nos 3 idiomas (contra a regra de escrita de 03/09, uma por uma), o mapa de transições de estado, a
sanitização do contexto que chega do navegador (`contexto_limpo`), a prova de captura (`_captura_bytes`), a
prova de anexo (`_verificar_anexo`) e o cálculo do SLA de primeira resposta (`_sla`). As cláusulas de portão
que precisam de inquilino, fila, SMTP e inquilino cruzado estão em `tests/api/test_chamados.py`, e o fluxo de
interface em `tests/e2e/test_chamados.py`."""

import base64
import datetime
import io
import os

import pytest
from PIL import Image

from app import limites
from app.chamados import correio
from app.chamados.rotas import TRANSICOES, _captura_bytes, _sla, _verificar_anexo, contexto_limpo
from app.erros import ErroAPI

UTC = datetime.UTC


# ---------------------------------------------------------------- correio: 3 idiomas × regra de escrita
def _png_pequeno() -> bytes:
    im = Image.new("RGBA", (2, 2), (10, 20, 30, 255))
    buffer = io.BytesIO()
    im.save(buffer, "PNG")
    return buffer.getvalue()


def test_correio_cobre_todos_os_idiomas_de_perfil_para_todo_evento():
    for evento in ("resposta", "resolvido"):
        assert set(correio.TEXTOS[evento]) == set(limites.PERFIL_IDIOMAS)


@pytest.mark.parametrize("evento", ["resposta", "resolvido"])
@pytest.mark.parametrize("idioma", ["pt-BR", "en", "es"])
def test_correio_monta_assunto_com_numero_e_texto_com_url(evento, idioma):
    assunto, texto = correio.monta(evento, idioma, 42, "Título do chamado")
    assert "42" in assunto
    assert "Título do chamado" in texto
    assert "/chamados" in texto


def test_correio_idioma_desconhecido_cai_em_pt_br():
    assert correio.monta("resposta", "fr", 9, "t") == correio.monta("resposta", "pt-BR", 9, "t")


@pytest.mark.parametrize("evento", ["resposta", "resolvido"])
@pytest.mark.parametrize("idioma", ["pt-BR", "en", "es"])
def test_correio_segue_a_regra_de_escrita_de_0309(evento, idioma):
    """Regra de 03/09 vale para TODO texto que sai de casa: uma ideia por frase, zero exclamação, zero
    travessão interno, nada de "você recebe". O assunto nunca leva texto do cliente (só o número)."""
    assunto, texto = correio.monta(evento, idioma, 7, "t" * 200)
    for trecho in (assunto, texto):
        assert "!" not in trecho
        assert "—" not in trecho
        assert "você recebe" not in trecho.lower()
    assunto_longo, _ = correio.monta(evento, idioma, 10**6, "")
    assert len(assunto_longo) <= limites.SMTP_ASSUNTO_MAX


def test_correio_titulo_nao_vaza_para_o_assunto():
    assunto, texto = correio.monta("resposta", "pt-BR", 7, "segredo do cliente")
    assert "segredo" not in assunto
    assert "segredo" in texto


# ---------------------------------------------------------------- transições de estado
def test_transicoes_cobre_todos_os_estados_e_fechado_é_terminal():
    assert set(TRANSICOES) == set(limites.CHAMADO_ESTADOS)
    assert TRANSICOES["fechado"] == set()
    # nenhum estado volta a "aberto": aberto é só o nascimento
    for destinos in TRANSICOES.values():
        assert "aberto" not in destinos
    # resolvido reabre para em_analise e encerra em fechado
    assert TRANSICOES["resolvido"] == {"fechado", "em_analise"}


def test_transicoes_destinos_sao_estados_validos():
    for origem, destinos in TRANSICOES.items():
        for d in destinos:
            assert d in limites.CHAMADO_ESTADOS
            assert d != origem


# ---------------------------------------------------------------- contexto do navegador
def test_contexto_limpo_corta_campos_conhecidos():
    ctx = contexto_limpo({
        "tela": "a" * 500, "versao": "b" * 100, "navegador": "c" * 1000, "idioma": "d" * 50,
    })
    assert ctx["tela"] == "a" * 200
    assert ctx["versao"] == "b" * 40
    assert ctx["navegador"] == "c" * 300
    assert ctx["idioma"] == "d" * 10


def test_contexto_limpo_filtra_req_ids_pelo_formato_real():
    validos = [f"{i:016x}" for i in range(25)]
    ctx = contexto_limpo({"req_ids": ["curto", "Z" * 16, None, 7, *validos]})
    assert ctx["req_ids"] == validos[:20]  # só 16 hex, no máximo 20


def test_contexto_limpo_reduz_dom_a_estrutura_sem_valor_de_campo():
    dom = [{"tag": "h1", "texto": " " * 10 + "título " * 30}, {"tag": "x" * 30, "texto": ""},
           "lixo", 42, {"sem_tag": True}]
    ctx = contexto_limpo({"dom": dom})
    assert ctx["dom"][0] == {"tag": "h1", "texto": (" " * 10 + "título " * 30)[:120]}  # cortado a 120
    assert all(set(e) == {"tag", "texto"} for e in ctx["dom"])
    assert len(ctx["dom"]) <= limites.CHAMADO_DOM_ENTRADAS_MAX


def test_contexto_limpo_observa_o_teto_de_bytes_do_contexto(monkeypatch):
    monkeypatch.setattr(limites, "CHAMADO_CONTEXTO_BYTES_MAX", 1000)
    dom = [{"tag": "div", "texto": "x" * 120} for _ in range(60)]
    ctx = contexto_limpo({"tela": "/mapa", "versao": "0.1.0", "req_ids": [f"{i:016x}" for i in range(20)],
                          "dom": dom})
    import json as _json
    assert len(_json.dumps(ctx).encode()) <= 1000
    # o essencial sobra: o que é cortado primeiro é a parte maior (dom)
    assert ctx["tela"] == "/mapa"


def test_contexto_limpo_ignora_entrada_que_nao_e_objeto():
    assert contexto_limpo(None) == {}
    assert contexto_limpo("ataque") == {}


# ---------------------------------------------------------------- captura de tela
def test_captura_aceita_data_url_de_png_verdadeiro_e_reencoda():
    png = _png_pequeno()
    captura = _captura_bytes("data:image/png;base64," + base64.b64encode(png).decode())
    assert captura.startswith(b"\x89PNG\r\n\x1a\n")
    Image.open(io.BytesIO(captura)).load()  # o re-encode decodifica


def test_captura_recusa_o_que_nao_e_data_url_de_png():
    png = _png_pequeno()
    with pytest.raises(ErroAPI) as e:
        _captura_bytes(base64.b64encode(png).decode())  # sem o prefixo data:
    assert e.value.status_code == 422 and e.value.erro == "captura_invalida"
    with pytest.raises(ErroAPI) as e:
        _captura_bytes("data:image/png;base64,###")
    assert e.value.status_code == 422
    with pytest.raises(ErroAPI) as e:
        _captura_bytes("data:image/png;base64," + base64.b64encode(b"isto nao e png").decode())
    assert e.value.status_code == 422  # bytes sem assinatura PNG


def test_captura_recusa_png_acima_do_teto():
    ruído = Image.frombytes("RGBA", (900, 900), os.urandom(900 * 900 * 4))
    buffer = io.BytesIO()
    ruído.save(buffer, "PNG")
    assert len(buffer.getvalue()) > limites.CHAMADO_CAPTURA_BYTES_MAX  # o ruído não comprime
    with pytest.raises(ErroAPI) as e:
        _captura_bytes("data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode())
    assert e.value.status_code == 413 and e.value.erro == "captura_grande"


# ---------------------------------------------------------------- anexos
def test_anexo_recusa_tipo_fora_da_lista():
    with pytest.raises(ErroAPI) as e:
        _verificar_anexo("exe", b"MZ\x90\x00")
    assert e.value.status_code == 422 and e.value.erro == "tipo_desconhecido"


def test_anexo_malicioso_com_tipo_de_dado_e_recusado_pela_varredura():
    """A prova unitária do portão: bytes de executável (MZ, PE) declarados como geojson. A varredura de
    cabeçalho (L7-03-b) identifica o tipo real e recusa antes de o objeto chegar a tocar o Garage."""
    with pytest.raises(ErroAPI) as e:
        _verificar_anexo("geojson", b"MZ\x90\x00" + os.urandom(256))
    assert e.value.status_code == 415 and e.value.erro == "conteudo_recusado"


def test_anexo_recusa_bytes_que_nao_batem_com_a_imagem_declarada():
    with pytest.raises(ErroAPI) as e:
        _verificar_anexo("png", b"isto e texto, nao imagem")
    assert e.value.status_code in (415, 422)
    with pytest.raises(ErroAPI) as e:
        _verificar_anexo("jpeg", _png_pequeno())  # PNG declarado como JPEG: família errada
    assert e.value.status_code in (415, 422)


def test_anexo_aceita_imagem_verdadeira_e_zip_verdadeiro():
    _verificar_anexo("png", _png_pequeno())  # não levanta
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("a.txt", "conteúdo")
    _verificar_anexo("zip", buffer.getvalue())  # não levanta


# ---------------------------------------------------------------- SLA de primeira resposta
def _linha(severidade, horas_resposta=None):
    aberto = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
    return {
        "severidade": severidade, "aberto_em": aberto,
        "primeira_resposta_em": None if horas_resposta is None else aberto + datetime.timedelta(hours=horas_resposta),
    }


def test_sla_sem_resposta_mostra_só_o_prazo_declarado():
    s = _sla(_linha("media"))
    assert s["primeira_resposta_em"] is None
    assert s["primeira_resposta_horas"] is None
    assert s["sla_primeira_resposta_horas"] == 24
    assert s["sla_origem"] == "declarado"
    assert s["sla_dentro"] is None


def test_sla_resposta_dentro_e_fora_do_prazo():
    dentro = _sla(_linha("media", horas_resposta=1))
    assert dentro["primeira_resposta_horas"] == 1.0 and dentro["sla_dentro"] is True
    fora = _sla(_linha("media", horas_resposta=30))
    assert fora["primeira_resposta_horas"] == 30.0 and fora["sla_dentro"] is False
    # severidade crítica tem o prazo mais apertado e baixa o mais folgado
    assert limites.CHAMADO_SLA_PRIMEIRA_RESPOSTA_HORAS["critica"] < limites.CHAMADO_SLA_PRIMEIRA_RESPOSTA_HORAS["baixa"]
    critica = _sla(_linha("critica", horas_resposta=5))
    assert critica["sla_dentro"] is False and critica["sla_primeira_resposta_horas"] == 4


def test_sla_toda_severidade_tem_prazo():
    for sev in limites.CHAMADO_SEVERIDADES:
        assert _sla(_linha(sev, horas_resposta=0))["sla_primeira_resposta_horas"] > 0
