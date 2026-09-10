"""Item L0-03-e: o token do link compartilhado viaja no CAMINHO da URL (/api/compartilhado/<token>, /c/<token>) e
não na query — a redação por parâmetro (`token=`) não o alcançava e ele ia inteiro para `log_acesso.rota` (lida pelo
admin do inquilino em /admin/log) e para o journal. Aqui: o segmento depois de /api/compartilhado/ e de /c/ vira
<redigido> em rota_redigida, caminho_redigido e linha_redigida; o resto do caminho fica igual."""

from app.auth.redigir import REDIGIDO, caminho_redigido, linha_redigida, rota_redigida

TOKEN = "ab" * 32
ITEM = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def test_token_no_caminho_do_link_e_redigido_em_todas_as_rotas_do_link():
    for caminho in (
        f"/api/compartilhado/{TOKEN}",
        f"/api/compartilhado/{TOKEN}/itens/{ITEM}",
        f"/api/compartilhado/{TOKEN}/itens/{ITEM}/miniatura",
        f"/c/{TOKEN}",
    ):
        r = rota_redigida(caminho, "")
        assert TOKEN not in r and REDIGIDO in r, r
        assert r.startswith("/api/compartilhado/" if caminho.startswith("/api") else "/c/")
    esperado = f"/api/compartilhado/{REDIGIDO}/itens/{ITEM}"
    assert rota_redigida(f"/api/compartilhado/{TOKEN}/itens/{ITEM}", "") == esperado


def test_tentativa_curta_ou_fora_do_alfabeto_tambem_e_redigida():
    assert rota_redigida("/api/compartilhado/abc", "") == f"/api/compartilhado/{REDIGIDO}"
    assert rota_redigida("/api/compartilhado/../x", "pagina=1") == f"/api/compartilhado/{REDIGIDO}/x?pagina=1"


def test_caminhos_sem_link_ficam_iguais():
    for caminho in ("/api/itens/" + ITEM, "/api/itens/" + ITEM + "/links", "/conteudo/" + ITEM, "/api/eu", "/c"):
        assert caminho_redigido(caminho) == caminho


def test_linha_de_log_com_a_url_do_link_nao_carrega_o_token():
    linha = f"GET https://exemplo.invalido/c/{TOKEN} -> 200; depois /api/compartilhado/{TOKEN}/itens/{ITEM}"
    r = linha_redigida(linha)
    assert TOKEN not in r and r.count(REDIGIDO) == 2 and ITEM in r
