"""e2e playwright do item L2-10-a-dominios-subtipos, contra a URL passada em --base-url.

Prova a cláusula "formulário mostra descrição e grava código": a lista de escolha do campo `uf` exibe
"São Paulo" e o que chega à tabela do banco é "SP"; trocar o subtipo troca a lista do campo `situacao` e
preenche o valor padrão do subtipo; a tabela de feições mostra a descrição, não o código.

A montagem (inquilino, tabela PostGIS, domínios, ligações, subtipos) é feita pelas MESMAS classes do teste de
API (`tests/api/test_dominios_subtipos.py`), que escrevem no mesmo banco que o servidor sob teste lê — o
navegador só faz o que um usuário faria. Capturas em tests/e2e/capturas/L2-10-a-dominios-subtipos_*.png.
"""

from __future__ import annotations

from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import credenciais as credenciais_api
from tests.api.conftest import entrar as entrar_api
from tests.api.conftest import ligar_2fa, novo_cliente, totp_guardado, totp_guardar
from tests.api.test_dominios_subtipos import Camada, Inquilino
from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-10-a-dominios-subtipos"
ROTAS = ("/api/camadas/{item_id}/dominios", "/api/camadas/{item_id}/subtipos",
         "/api/camadas/{item_id}/feicoes")


class TelaDominios(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def api_dominios(api_auth):
    faltam = [r for r in ROTAS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item L2-10-a)")
    return api_auth


@pytest.fixture
def superadmin(api_dominios):
    c = credenciais_api()
    if "plataforma" not in c:
        pytest.skip("sem credenciais do inquilino plataforma (rode install.sh)")
    login, senha = c["plataforma"]
    cliente = novo_cliente()
    r = entrar_api(cliente, "plataforma", login, senha, totp_guardado("plataforma"))
    assert r.status_code == 200 and r.json()["ok"] is True, (r.status_code, r.text)
    if "configurar_2fa" in r.json()["usuario"]["pendencias"]:
        segredo, _ = ligar_2fa(cliente)
        totp_guardar("plataforma", login, segredo)
    return cliente


@pytest.fixture
def cenario(superadmin, env):
    """Inquilino novo com uma camada de 4 campos, 3 domínios, 2 subtipos e as ligações do caso."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    inq = Inquilino(superadmin)
    camada = None
    try:
        camada = Camada(con, inq, [
            {"nome": "uf", "tipo": "text"}, {"nome": "situacao", "tipo": "text"},
            {"nome": "altura", "tipo": "double precision"}, {"nome": "classe", "tipo": "integer"},
        ])
        s = inq.admin

        def dominio(nome, **corpo):
            r = s.post("/api/dominios", json={"nome": nome, **corpo})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        uf = dominio("zt UF", tipo="codificado", tipo_campo="text",
                     valores=[{"codigo": "SP", "descricao": "São Paulo"},
                              {"codigo": "RJ", "descricao": "Rio de Janeiro"},
                              {"codigo": "MG", "descricao": "Minas Gerais"}])
        alt = dominio("zt Altura", tipo="intervalo", tipo_campo="double precision",
                      valores={"min": 0, "max": 50})
        urbano = dominio("zt Pavimento urbano", tipo="codificado", tipo_campo="text",
                         valores=[{"codigo": "asfalto", "descricao": "Asfalto"},
                                  {"codigo": "paralelo", "descricao": "Paralelepípedo"}])
        rural = dominio("zt Pavimento rural", tipo="codificado", tipo_campo="text",
                        valores=[{"codigo": "terra", "descricao": "Terra"},
                                 {"codigo": "cascalho", "descricao": "Cascalho"}])
        assert s.put(f"/api/camadas/{camada.item_id}/subtipos", json={
            "campo": "classe",
            "valores": [{"codigo": 1, "nome": "Urbano", "padroes": {"situacao": "asfalto"}},
                        {"codigo": 2, "nome": "Rural", "padroes": {"situacao": "terra"}}],
        }).status_code == 200
        for corpo in ({"campo": "uf", "dominio_id": uf},
                      {"campo": "altura", "dominio_id": alt},
                      {"campo": "situacao", "dominio_id": urbano, "subtipo_codigo": 1},
                      {"campo": "situacao", "dominio_id": rural, "subtipo_codigo": 2}):
            assert s.post(f"/api/camadas/{camada.item_id}/dominios", json=corpo).status_code == 201
        yield inq, camada
    finally:
        if camada is not None:
            for li in (inq.admin.get(f"/api/camadas/{camada.item_id}/dominios").json() or {}).get("ligacoes", []):
                inq.admin.delete(f"/api/camadas/{camada.item_id}/dominios/{li['id']}")
            camada.apagar()
        inq.apagar()
        con.rollback()
        con.close()


def test_formulario_mostra_descricao_e_grava_codigo(page, base_url, cenario, medida):
    inq, camada = cenario
    tela = TelaDominios(page, base_url)
    try:
        tela.entrar(inq.slug, "admin", inq.senha, proximo=f"/camadas/{camada.item_id}/dominios")
        tela.medidas["pagina_dominios_ms"] = tela.ir(f"/camadas/{camada.item_id}/dominios")
        page.wait_for_selector("#tabela-ligacoes tbody tr")
        tela.capturar("ligacoes")

        # 1. a lista de escolha MOSTRA a descrição (nunca o código)
        textos = page.eval_on_selector_all("#campo-uf option", "os => os.map(o => o.textContent.trim())")
        valores = page.eval_on_selector_all("#campo-uf option", "os => os.map(o => o.value)")
        assert textos[1:] == ["São Paulo", "Rio de Janeiro", "Minas Gerais"], textos
        assert valores[1:] == ["SP", "RJ", "MG"], valores
        # o campo de intervalo carrega mínimo e máximo do domínio
        assert page.get_attribute("#campo-altura", "min") == "0"
        assert page.get_attribute("#campo-altura", "max") == "50"

        # 2. o subtipo troca o domínio do MESMO campo e aplica o padrão
        page.select_option("#campo-classe", "1")
        assert page.eval_on_selector_all("#campo-situacao option",
                                         "os => os.map(o => o.textContent.trim())")[1:] == ["Asfalto", "Paralelepípedo"]
        assert page.input_value("#campo-situacao") == "asfalto"     # valor padrão do subtipo Urbano
        page.select_option("#campo-classe", "2")
        assert page.eval_on_selector_all("#campo-situacao option",
                                         "os => os.map(o => o.textContent.trim())")[1:] == ["Terra", "Cascalho"]
        assert page.input_value("#campo-situacao") == "terra"
        tela.capturar("formulario_subtipo_rural")

        # 3. gravar: a tela escolhe pela descrição, o banco recebe o código
        page.select_option("#campo-uf", label="São Paulo")
        page.fill("#campo-altura", "12.5")
        page.click("#gravar")
        page.wait_for_function("() => document.querySelector('#aviso')?.textContent?.includes('feição gravada')",
                               timeout=20000)
        tela.capturar("feicao_gravada")

        r = tela.api("GET", f"/api/camadas/{camada.item_id}/feicoes?limite=1")
        assert r.status == 200, r.text()
        gravada = r.json()["itens"][0]
        assert gravada["uf"] == "SP" and gravada["situacao"] == "terra" and gravada["classe"] == 2
        assert gravada["altura"] == 12.5

        # 4. a tabela mostra a descrição, com o código no title (o dado bruto continua visível a quem procura)
        page.wait_for_selector("#tabela-feicoes tbody tr")
        primeira = page.eval_on_selector_all(
            "#tabela-feicoes tbody tr:first-child td", "ts => ts.map(t => t.textContent.trim())")
        assert "São Paulo" in primeira and "Terra" in primeira, primeira
        assert "SP" not in primeira, primeira
        assert page.get_attribute("#tabela-feicoes tbody tr:first-child td:nth-child(2)", "title") == "SP"

        # 5. valor fora do domínio, forçado por fora da lista: o 422 do banco chega ao lado do campo
        page.evaluate("() => { const s = document.querySelector('#campo-uf');"
                      " const o = document.createElement('option'); o.value = 'ZZ'; o.textContent = 'ZZ';"
                      " s.append(o); s.value = 'ZZ'; }")
        tela.esperar_status(422)
        page.click("#gravar")
        page.wait_for_function("() => (document.querySelector('#erro-uf')?.textContent || '').length > 0",
                               timeout=20000)
        erro = page.text_content("#erro-uf") or ""
        assert "uf" in erro and "ZZ" in erro, erro
        tela.capturar("valor_fora_do_dominio")

        tela.verificar()
        gravar = medida(ITEM)
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "playwright chromium (tests/e2e/test_dominios.py) com --base-url próprio")
        gravar("formulario_opcoes_com_descricao", textos[1:], "rótulos",
               "page.eval_on_selector_all('#campo-uf option') no e2e")
        gravar("formulario_valores_gravados", valores[1:], "códigos",
               "page.eval_on_selector_all('#campo-uf option') no e2e")
    finally:
        tela.sair()
