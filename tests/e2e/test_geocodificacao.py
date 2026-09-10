"""e2e playwright da tela `/geocodificacoes/{id}` (item L2-11-a-geocodificacao-csv): a tela de REVISÃO da
geocodificação de uma planilha, com o mapa e o arrasto do marcador.

O que se prova aqui é a TELA, contra a URL interna real: o resumo com as contagens e a contagem por tipo de
acerto, a lista filtrada por estado (a linha pendente aparece), o marcador que nasce ao clicar na linha, o
ARRASTO do marcador gravando a coordenada com origem 'manual' (a linha volta como resolvida/manual sem
recarregar a página à mão) e 0 erro de console. Capturas em
`tests/e2e/capturas/L2-11-a-geocodificacao-csv_*.png`.

O lote é preparado pela API (mesmo cookie do navegador) e o job é executado NESTE processo — o worker da
trilha não está no ar durante o e2e, mesmo caminho de `tests/e2e/test_migracao.py`. Sem
`/api/geocodificacoes` no OpenAPI da URL interna a suíte é pulada com a razão escrita.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-11-a-geocodificacao-csv"
ROTAS = ("/api/geocodificacoes", "/api/geocodificacoes/{geocodificacao_id}/linhas")
CSV = (
    'id,logradouro,numero,municipio,uf\n'
    '1,RUA CURITIBA,1043,Boa Vista,RR\n'
    '2,ZZQQXXWWKKVV NAO EXISTE,1,,\n'
)


class TelaGeocodificacao(Tela):
    def capturar(self, nome: str):
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def api_geocodificacao(api_auth):
    faltam = [r for r in ROTAS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item L2-11-a)")
    return api_auth


def test_revisao_lista_pendente_e_arrasto_grava_manual(page, base_url, credenciais_demo, api_geocodificacao,
                                                        medida, env):
    from app.geocodificador.lote import geocodificacao_lote
    from tests.api.test_rls import ids_por_slug
    from tests.e2e.apoio_geocodificacao import CtxLocal, conexao_direta

    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    tela = TelaGeocodificacao(page, base_url)
    tela.entrar(slug, admin_login, senha_admin, proximo="/conteudo")

    # 1. arquivo -> item -> lote (pela API, com o cookie do navegador)
    r = tela.api("POST", "/api/tokens", {"nome": f"zt-e2e-geocod-{s}", "escopos": ["admin:inquilino"]})
    assert r.status == 201, r.text()
    token = r.json()["token"]
    token_id = r.json()["id"]
    # o envio do BYTE vai por httpx, fora do navegador: o contexto do playwright já leva o cookie de sessão,
    # e mandar cookie + Authorization juntos é 400 `autenticacao_ambigua` por regra da casa (ADR 0002)
    resp = httpx.post(f"{base_url}/api/arquivos?classe=camada_arquivo", content=CSV.encode("utf-8"),
                       headers={"authorization": f"Bearer {token}", "content-type": "text/csv"}, timeout=30)
    assert resp.status_code == 201, resp.text
    obj = resp.json()
    r = tela.api("POST", "/api/itens", {
        "tipo": "arquivo", "titulo": f"zt e2e geocod {s}",
        "dados": {"chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"],
                   "content_type": obj["content_type"], "nome_original": "enderecos.csv"}})
    assert r.status == 201, r.text()
    arquivo_id = r.json()["id"]
    r = tela.api("POST", "/api/geocodificacoes", {
        "arquivo_id": arquivo_id, "titulo": f"zt e2e {s}",
        "mapeamento": {"logradouro": "logradouro", "numero": "numero", "municipio": "municipio",
                        "uf": "uf"}})
    assert r.status == 202, r.text()
    gid = r.json()["geocodificacao_id"]
    job_id = r.json()["job_id"]

    # 2. o job roda NESTE processo (a trilha não tem worker no ar durante o e2e)
    eu = tela.api("GET", "/api/eu").json()
    con = conexao_direta(env)
    try:
        tenant_id = ids_por_slug(con)[slug]
    finally:
        con.rollback()
        con.close()
    ctx = CtxLocal(env, tenant_id, eu["id"], job_id)
    geocodificacao_lote(ctx, gid, False)

    try:
        # 3. a tela: resumo, filtro de pendentes, marcador e arrasto
        tela.medidas["pagina_revisao_ms"] = tela.ir(f"/geocodificacoes/{gid}")
        page.wait_for_selector("#linhas tr[data-linha]", timeout=20000)
        assert "1" in page.locator(".geo-cartao", has_text="pendentes").inner_text()
        pendentes = page.locator("#linhas tr[data-linha]")
        assert pendentes.count() == 1, "o filtro abre em 'pendentes' e só a linha 2 é pendente"
        assert pendentes.first.get_attribute("data-linha") == "2"
        tela.capturar("lista_pendentes")

        pendentes.first.click()
        page.wait_for_selector(".maplibregl-marker", timeout=20000)
        caixa = page.locator(".maplibregl-marker").first.bounding_box()
        assert caixa is not None, "o marcador tinha de estar visível para ser arrastado"
        tela.capturar("marcador_na_linha_pendente")

        # arrasto de verdade: mouse down no marcador, move, up
        page.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
        page.mouse.down()
        page.mouse.move(caixa["x"] + caixa["width"] / 2 + 90, caixa["y"] + caixa["height"] / 2 + 60, steps=12)
        page.mouse.up()

        page.wait_for_function(
            "() => (document.querySelector('#aviso')?.textContent || '').includes('origem manual')",
            timeout=20000)
        tela.capturar("coordenada_gravada_manual")

        r = tela.api("GET", f"/api/geocodificacoes/{gid}/linhas")
        linha2 = next(li for li in r.json()["linhas"] if li["n"] == 2)
        assert linha2["origem"] == "manual" and linha2["estado"] == "resolvida", linha2
        assert linha2["lon"] is not None and linha2["lat"] is not None, linha2

        page.wait_for_function(
            "() => [...document.querySelectorAll('.geo-cartao')].some("
            "  (c) => c.textContent.includes('manuais') && c.textContent.trim().startsWith('1'))",
            timeout=20000)
        tela.verificar()
        m = medida(ITEM)
        m("e2e_pagina_revisao_ms", tela.medidas["pagina_revisao_ms"], "ms",
          "test_revisao_lista_pendente_e_arrasto_grava_manual")
        m("e2e_erros_de_console", 0, "erros", "test_revisao_lista_pendente_e_arrasto_grava_manual")
    finally:
        tela.api("DELETE", f"/api/tokens/{token_id}")
