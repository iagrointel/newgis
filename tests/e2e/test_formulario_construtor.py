"""e2e do item L5-03-form-builder: construtor de formulário de atributos arrasta-e-solta.

Portão (cláusula "e2e"): um formulário desenhado por ARRASTO na tela `/camadas/{id}/formulario`, salvo e
publicado, passa a valer nas duas frentes que preenchem atributo (edição web e PWA de campo) com a mesma
condicional/cálculo. Aqui: o navegador de verdade (chromium do playwright) monta o desenho por
`page.drag_and_drop` (mesma mecânica HTML5 DnD do item L5-08-editor-arrasto, `web/js/editor/arrasto.js`,
reaproveitada, nunca copiada), salva e publica pela tela; a seguir a MESMA sessão de navegador (cookie),
via `Tela.api`, chama `POST /api/campo/visitas` (refutação do item-pai: "adversário define campo
obrigatório e submete sem ele pela API") — condicional e cálculo funcionando, provados no navegador.

A validação campo-a-campo completa (obrigatório/domínio/condicional/cálculo, nos DOIS caminhos de
escrita, com camada de tabela física de verdade) está em `tests/api/test_formulario.py` — mais barata de
rodar e mais fácil de ler cláusula a cláusula. Este arquivo prova o que só o navegador prova: o ARRASTO
em si e que a MESMA sessão que construiu o formulário o vê funcionar sem outro passo manual."""

import uuid

import pytest

from tests.e2e.apoio import Tela, sufixo

ITEM = "L5-03-form-builder"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _criar_camada_catalogo(tela: Tela, titulo: str) -> str:
    """Item `camada_vetorial` só de CATÁLOGO (sem tabela física) — o bastante para o construtor (lê
    `dados.campos`) e para `/api/campo/visitas` (não toca a tabela referenciada, só grava `dados` jsonb
    livre — ver `app/campo/servico.py::visita_criar`). A prova com tabela física de verdade, para
    `/api/camadas/{id}/edicoes`, está em `tests/api/test_formulario.py` (`FabricaCamada`)."""
    r = tela.api("POST", "/api/itens", {
        "tipo": "camada_vetorial", "titulo": titulo,
        "dados": {
            "schema": "d_demo", "tabela": f"c_{sufixo()}0000000000", "geometria": "Point", "srid": 4326,
            "fonte": "hospedada", "edicao": {"habilitada": True},
            "campos": [
                {"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"},
                {"nome": "ativo", "tipo": "boolean"}, {"nome": "area", "tipo": "double precision"},
                {"nome": "total", "tipo": "double precision"},
            ],
        },
    })
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _campo_editor(page, nome_campo: str):
    return page.locator(f'.formulario-campo-editor[data-campo="{nome_campo}"]')


def test_montar_por_arrasto_publicar_e_valer_no_campo(page, base_url, credenciais_demo, medida):
    # viewport alto: a lista de propriedades de cada campo empurra o alvo do arrasto para baixo da
    # dobra e o Chromium confunde o ponto de soltura com um auto-scroll no meio do gesto nativo de
    # Drag and Drop (medido: o 3º arrasto falhava sempre, em qualquer ordem de campo, só por posição)
    page.set_viewport_size({"width": 1400, "height": 1800})
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    grava = medida(ITEM)

    camada_id = _criar_camada_catalogo(tela, f"zt-form-{sufixo()}")

    tela.ir(f"/camadas/{camada_id}/formulario", "pagina_pronta_ms")
    page.wait_for_selector('[data-campo="nome"].formulario-chip', timeout=20000)

    # arrasta 4 atributos da paleta para o grupo 1 (mesma mecânica HTML5 DnD do L5-08)
    grupo = page.locator(".formulario-grupo-editor").first
    for campo in ("nome", "categoria", "ativo", "area"):
        page.drag_and_drop(f'.formulario-chip[data-campo="{campo}"]', ".formulario-grupo-corpo")
        page.wait_for_selector(f'.formulario-campo-editor[data-campo="{campo}"]', timeout=10000)
    assert grupo.locator(".formulario-campo-editor").count() == 4

    # + grupo 2, arrasta "total" nele — prova o segundo drop-target (dois grupos == "suporta seção")
    page.click('button:text-is("+ grupo")')
    grupos = page.locator(".formulario-grupo-editor")
    assert grupos.count() == 2
    alvo2 = ".formulario-grupo-editor:nth-child(2) .formulario-grupo-corpo"
    page.locator(alvo2).scroll_into_view_if_needed()
    page.drag_and_drop('.formulario-chip[data-campo="total"]', alvo2)
    page.wait_for_selector('.formulario-campo-editor[data-campo="total"]', timeout=10000)

    # propriedades: nome obrigatório; categoria com domínio A/B/C; ativo obrigatório SÓ quando categoria==A
    # (condicional); total = area*2 (cálculo) — a MESMA linguagem que o servidor valida (docs/EXPRESSAO.md)
    nome_ed = _campo_editor(page, "nome")
    nome_ed.locator('label:has-text("Obrigatório") input[type=checkbox]').check()

    cat_ed = _campo_editor(page, "categoria")
    cat_ed.locator('label:has-text("Domínio") input').fill("A, B, C")

    ativo_ed = _campo_editor(page, "ativo")
    ativo_ed.locator('label:has-text("Obrigatório quando") input').fill("$categoria == 'A'")

    total_ed = _campo_editor(page, "total")
    total_ed.locator('label:has-text("Cálculo") input').fill("$area * 2")

    page.click('button:text-is("Salvar rascunho")')
    page.wait_for_function(
        "() => document.getElementById('aviso').textContent.includes('rascunho salvo')", timeout=10000
    )
    page.click('button:text-is("Publicar")')
    page.wait_for_function(
        "() => document.getElementById('aviso').textContent.includes('publicado')", timeout=10000
    )
    tela.capturar("construtor_publicado")

    # o desenho publicado casa com o que foi arrastado
    r = tela.api("GET", f"/api/camadas/{camada_id}/formulario")
    assert r.status == 200, r.text()
    desenho = r.json()["desenho"]
    campos = {c["campo"]: c for g in desenho["grupos"] for c in g["campos"]}
    assert set(campos) == {"nome", "categoria", "ativo", "area", "total"}
    assert campos["nome"]["obrigatorio"] is True
    assert campos["categoria"]["dominio"]["valores"] == ["A", "B", "C"]
    assert campos["ativo"]["obrigatorio_se"] == "$categoria == 'A'"
    assert campos["total"]["calculo"] == "$area * 2"

    # refutação (mesmo navegador/sessão, sem outro passo): sem "nome" -> 422 campo_obrigatorio
    r = tela.api("POST", "/api/campo/visitas", {
        "cliente_uuid": str(uuid.uuid4()), "camada_id": camada_id,
        "globalid": str(uuid.uuid4()), "status": "visitado",
        "capturado_em": "2026-09-10T12:00:00Z", "dados": {"categoria": "B"},
    })
    assert r.status == 422, r.text()
    assert r.json()["erro"] == "campo_obrigatorio", r.text()

    # condicional: categoria=A sem "ativo" -> 422; cálculo: categoria=B com area=5 -> total=10 (servidor
    # recomputa, ignora o "total":999 que o cliente mandou)
    r = tela.api("POST", "/api/campo/visitas", {
        "cliente_uuid": str(uuid.uuid4()), "camada_id": camada_id,
        "globalid": str(uuid.uuid4()), "status": "visitado",
        "capturado_em": "2026-09-10T12:00:00Z", "dados": {"nome": "x", "categoria": "A"},
    })
    assert r.status == 422 and r.json()["detalhe"]["campo"] == "ativo", r.text()

    r = tela.api("POST", "/api/campo/visitas", {
        "cliente_uuid": str(uuid.uuid4()), "camada_id": camada_id,
        "globalid": str(uuid.uuid4()), "status": "visitado",
        "capturado_em": "2026-09-10T12:00:00Z",
        "dados": {"nome": "x", "categoria": "B", "area": 5, "total": 999},
    })
    assert r.status == 201, r.text()
    assert r.json()["dados"]["total"] == 10, r.text()

    tela.verificar()
    grava(
        "formulario_montado_por_arrasto", campos["ativo"] is not None, "bool",
        "e2e: 5 campos em 2 grupos, montados por page.drag_and_drop; condicional/cálculo publicados batem "
        "com o que POST /api/campo/visitas exige/recomputa na mesma sessão",
    )
