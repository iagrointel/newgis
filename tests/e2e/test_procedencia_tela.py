"""E2e de navegador do bloco de procedência na tela do item (cláusula que faltava no item L0-09-a; a API
e o SQL já estavam provados em tests/api/catalogo/test_procedencia.py e na migração). Prova: item com o
bloco cheio mostra a seção, a nota 10,0/10, os campos com a etiqueta de origem (medido/declarado) e segue
legível em 390 px; item sem bloco mostra "Sem procedência registrada" — ausência de registro nunca é 0/10.
Capturas em tests/e2e/capturas/L0-09-a_*.png."""

from __future__ import annotations

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, credenciais, sufixo

ITEM = "L0-09-a-procedencia"

BLOCO_CHEIO = {
    "fonte": "Malha municipal IBGE",
    "url": "https://geoftp.ibge.gov.br/exemplo",
    "licenca": "CC BY 4.0",
    "data_do_dado": "2024-07-01",
    "data_de_acesso": "2026-09-06",
    "gerador": "plat e2e v1",
    "sha256": "a" * 64,
    "comando_reexecucao": "sha256sum malha.gpkg",
    "metodo": "ogr2ogr + ST_MakeValid",
    "confianca": "alta: arquivo oficial, hash conferido",
    "limites": ["não serve para medir área abaixo de 1 ha"],
    "frescor": "anual",
    "proxima_verificacao": "2027-01-31",
    "responsavel": "equipe de dados",
    "origem": {"licenca": "declarado", "sha256": "medido", "metodo": "medido"},
}


@pytest.fixture(scope="session")
def credenciais_demo(api_auth) -> tuple[str, str, str]:
    c = credenciais()
    if "demo" not in c:
        pytest.skip("tests/credenciais.txt sem a linha do inquilino demo (rode install.sh)")
    return ("demo", *c["demo"])


def _capturar(tela: Tela, nome: str) -> None:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    tela.page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


def test_bloco_de_procedencia_na_tela_do_item(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    s = sufixo()
    titulo_cheio = f"E2E procedência {s}"
    titulo_vazio = f"E2E sem procedência {s}"
    ids: list[str] = []
    try:
        tela.entrar(slug, login, senha, proximo="/conteudo")

        # item de dado com o bloco cheio, criado pela mesma rota que a tela consome (o esquema do tipo
        # camada_vetorial aceita dados.procedencia; o do mapa é estrito e a recusa — a tabela de trabalho
        # não precisa existir: a ficha lê o registro do catálogo, não a tabela)
        r = tela.api("POST", "/api/itens", {
            "tipo": "camada_vetorial", "titulo": titulo_cheio,
            "dados": {"schema": "plat_trabalho", "tabela": f"zt_e2e_{s}", "geometria": "Point", "srid": 4326,
                      "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada",
                      "procedencia": BLOCO_CHEIO}})
        assert r.status == 201, r.text
        cheio = r.json()
        ids.append(cheio["id"])
        assert cheio["procedencia"]["completude_texto"] == "10,0/10", cheio.get("procedencia")

        # item de dado sem bloco nenhum (mesmo tipo, sem procedência)
        r = tela.api("POST", "/api/itens", {
            "tipo": "camada_vetorial", "titulo": titulo_vazio,
            "dados": {"schema": "plat_trabalho", "tabela": f"zt_e2e_{s}b", "geometria": "Point", "srid": 4326,
                      "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada"}})
        assert r.status == 201, r.text
        vazio = r.json()
        ids.append(vazio["id"])

        # 1280x800: a ficha do item com bloco abre na aba Visão geral
        tela.ir(f"/conteudo/{cheio['id']}")
        secao = page.locator("#painel dialog[open] section.procedencia[data-campo='procedencia']")
        secao.wait_for(timeout=15000)
        assert secao.count() == 1
        nota = secao.locator("h3 .chip").inner_text().strip()
        assert nota == "10,0/10", nota
        # campos com valor: título do campo, valor e a etiqueta de origem de quem afirmou
        linha_licenca = secao.locator(".campo-linha[data-campo='procedencia_licenca']")
        assert linha_licenca.count() == 1 and "CC BY 4.0" in linha_licenca.inner_text()
        linha_sha = secao.locator(".campo-linha[data-campo='procedencia_sha256']")
        assert linha_sha.count() == 1
        assert linha_sha.locator(".chip.origem[data-origem='medido']").count() == 1
        origem_licenca = secao.locator(
            ".campo-linha[data-campo='procedencia_licenca'] .chip.origem[data-origem='declarado']")
        assert origem_licenca.count() == 1
        _capturar(tela, "bloco_1280")

        # 390x844: o mesmo bloco segue legível no celular
        page.set_viewport_size({"width": 390, "height": 844})
        assert secao.is_visible()
        _capturar(tela, "bloco_390")
        page.set_viewport_size({"width": 1280, "height": 800})

        # item sem bloco: a ausência de registro é dita, nunca "0/10"
        tela.ir(f"/conteudo/{vazio['id']}")
        secao_vazia = page.locator("#painel dialog[open] section.procedencia[data-campo='procedencia']")
        secao_vazia.wait_for(timeout=15000)
        assert secao_vazia.locator("p.fraco.vazio", has_text="Sem procedência registrada").count() == 1
        assert secao_vazia.locator("h3 .chip").count() == 0, "item sem bloco não pode exibir nota"
        _capturar(tela, "sem_bloco_1280")

        tela.verificar()
    finally:
        for i in ids:
            tela.api("DELETE", f"/api/itens/{i}")
