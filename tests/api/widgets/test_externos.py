"""API dos widgets externos por inquilino (item L5-36-widgets-personalizados-sdk).

* instalar/atualizar (POST, admin com org.configurar), listar, obter, módulo servido same-origin com
  X-Plat-Widget-Sha256 + no-store, i18n do pacote, desinstalar;
* recusas nomeadas: api_widget diferente de 1, i18n fora do namespace do widget, módulo acima do teto,
  manifesto.modulo fora da forma relativa;
* o sha256 é calculado na INSTALAÇÃO (o teste confere contra hashlib);
* RLS: o widget de um inquilino não existe para o outro (lista, obter e módulo);
* editor sem org.configurar recebe 403 na escrita e lê normalmente.
O pacote do exemplo da casa (web/ext/exemplo/semaforo) é a carga de prova.
"""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.widget_empacotar import empacotar

ROOT = Path(__file__).resolve().parents[3]
EXEMPLO = ROOT / "web" / "ext" / "exemplo" / "semaforo"
NOME = "semaforo"


@pytest.fixture
def limpa_widget(sessao_a):
    instalados = []
    yield instalados
    for nome in instalados:
        sessao_a.delete(f"/api/widgets/externos/{nome}")


def _instalar_exemplo(cliente, instalados=None):
    pacote = empacotar(EXEMPLO)
    r = cliente.post("/api/widgets/externos", json=pacote)
    assert r.status_code == 201, r.text
    if instalados is not None:
        instalados.append(NOME)
    return pacote, r.json()


def test_instalar_listar_obter_modulo_i18n_e_apagar(sessao_a, limpa_widget):
    pacote, instalado = _instalar_exemplo(sessao_a, limpa_widget)
    sha = hashlib.sha256(pacote["modulo"].encode("utf-8")).hexdigest()
    assert instalado["nome"] == NOME and instalado["sandbox"] is True
    assert instalado["sha256"] == sha
    assert instalado["instalado_em"] and instalado["origem"] == "upload"

    lista = sessao_a.get("/api/widgets/externos").json()
    nomes = [i["nome"] for i in lista["itens"]]
    assert NOME in nomes
    assert all("modulo" not in i for i in lista["itens"]), "listagem não devolve código"

    obtido = sessao_a.get(f"/api/widgets/externos/{NOME}").json()
    assert obtido["sha256"] == sha and obtido["manifesto"]["nome"] == NOME

    r_mod = sessao_a.get(f"/api/widgets/externos/{NOME}/modulo.js")
    assert r_mod.status_code == 200
    assert r_mod.text == pacote["modulo"]
    assert r_mod.headers["content-type"].startswith("text/javascript")
    assert r_mod.headers["x-plat-widget-sha256"] == sha
    assert r_mod.headers["cache-control"] == "no-store"

    i18n = sessao_a.get(f"/api/widgets/externos/{NOME}/i18n.json").json()
    assert i18n == json.loads((EXEMPLO / "i18n.json").read_text(encoding="utf-8"))

    assert sessao_a.delete(f"/api/widgets/externos/{NOME}").status_code == 204
    limpa_widget.remove(NOME)
    assert sessao_a.get(f"/api/widgets/externos/{NOME}").status_code == 404
    assert sessao_a.get(f"/api/widgets/externos/{NOME}/modulo.js").status_code == 404


def test_reinstalar_atualiza_por_cima(sessao_a, limpa_widget):
    _instalar_exemplo(sessao_a, limpa_widget)
    pacote = empacotar(EXEMPLO)
    pacote["manifesto"]["versao"] = "1.0.1"
    r = sessao_a.post("/api/widgets/externos", json=pacote)
    assert r.status_code == 201, r.text
    assert r.json()["versao"] == "1.0.1"
    lista = sessao_a.get("/api/widgets/externos").json()
    assert [i["nome"] for i in lista["itens"]].count(NOME) == 1, "upsert não pode duplicar"
    assert sessao_a.delete(f"/api/widgets/externos/{NOME}").status_code == 204
    limpa_widget.clear()


def test_api_widget_antiga_recusada_422_nomeando(sessao_a):
    pacote = empacotar(EXEMPLO)
    pacote["manifesto"]["api_widget"] = 2
    r = sessao_a.post("/api/widgets/externos", json=pacote)
    assert r.status_code == 422
    assert r.json()["erro"] == "api_widget_incompativel"
    assert NOME in r.json()["mensagem"]


def test_i18n_fora_do_prefixo_do_widget_422(sessao_a):
    pacote = empacotar(EXEMPLO)
    pacote["i18n"]["mapa.titulo"] = "sobrescrever a casa, nem pensar"
    r = sessao_a.post("/api/widgets/externos", json=pacote)
    assert r.status_code == 422
    assert r.json()["erro"] == "i18n_invalido"
    assert "mapa.titulo" in r.json()["mensagem"]


def test_modulo_acima_do_teto_422(sessao_a):
    pacote = empacotar(EXEMPLO)
    pacote["modulo"] = "// enchimento\n" + "//" + "x" * (256 * 1024)
    r = sessao_a.post("/api/widgets/externos", json=pacote)
    assert r.status_code == 422 and r.json()["erro"] == "modulo_grande_demais"


def test_modulo_em_url_absoluta_422_o_codigo_sai_do_proprio_servidor(sessao_a):
    pacote = empacotar(EXEMPLO)
    pacote["manifesto"]["modulo"] = "/api/widgets/externos/semaforo/modulo.js"
    r = sessao_a.post("/api/widgets/externos", json=pacote)
    assert r.status_code == 422 and r.json()["erro"] == "manifesto_invalido"
    assert "./" in r.json()["mensagem"]


def test_rls_widget_do_inquilino_a_nao_existe_para_b(sessao_a, sessao_b, limpa_widget):
    _instalar_exemplo(sessao_a, limpa_widget)
    assert all(i["nome"] != NOME for i in sessao_b.get("/api/widgets/externos").json()["itens"])
    assert sessao_b.get(f"/api/widgets/externos/{NOME}").status_code == 404
    assert sessao_b.get(f"/api/widgets/externos/{NOME}/modulo.js").status_code == 404
    # B instala o SEU semáforo: mesmo nome, outro conteúdo, e o sha256 de A não muda
    pacote = empacotar(EXEMPLO)
    pacote["modulo"] = pacote["modulo"] + "\n// inquilino B\n"
    pacote["i18n"]["widget.semaforo.rotulo"] = "Semáforo do B"
    try:
        assert sessao_b.post("/api/widgets/externos", json=pacote).status_code == 201
        sha_a = sessao_a.get(f"/api/widgets/externos/{NOME}").json()["sha256"]
        sha_b = sessao_b.get(f"/api/widgets/externos/{NOME}").json()["sha256"]
        assert sha_a != sha_b
    finally:
        sessao_b.delete(f"/api/widgets/externos/{NOME}")  # o do B é limpo aqui, nunca vira resíduo


def test_editor_sem_org_configurar_nao_instala_mas_le(sessao_a, usuarios_a, limpa_widget):
    editor, _, _ = usuarios_a.sessao(perfil="editor")
    pacote = empacotar(EXEMPLO)
    r = editor.post("/api/widgets/externos", json=pacote)
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio"
    assert editor.delete(f"/api/widgets/externos/{NOME}").status_code == 403
    # leitura é de qualquer autenticado do inquilino (o widget entra no app de todo mundo)
    _instalar_exemplo(sessao_a, limpa_widget)
    assert editor.get("/api/widgets/externos").status_code == 200
    assert editor.get(f"/api/widgets/externos/{NOME}/modulo.js").status_code == 200


def test_sem_sessao_nenhuma_401():
    from tests.api.conftest import novo_cliente

    anonimo = novo_cliente()
    assert anonimo.get("/api/widgets/externos").status_code == 401
    assert anonimo.post("/api/widgets/externos", json={}).status_code == 401
