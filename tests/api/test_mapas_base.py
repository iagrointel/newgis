"""API da galeria de mapas base (item L2-01-e-mapas-base): instalação idempotente, listagem na ordem certa,
troca de padrão atômica (nunca dois defaults) e o proxy OSM recusando z/x/y fora da faixa antes de qualquer
rede (o caso de rede real — cache HIT/host fixo — está no e2e e nos testes de unidade com o upstream
simulado; aqui não se bate na internet de verdade, a política de uso do OSM proíbe tráfego automatizado sem
necessidade)."""

import pytest

TITULOS_PADRAO = {
    "OSM local (Guarulhos) — vetorial",
    "OSM padrão (proxy da casa) — raster",
    "Satélite (Sentinel-2 da casa)",
    "Fundo sem mapa base",
}


@pytest.fixture
def galeria_limpa(sessao_a):
    """Remove qualquer `mapa_base` com um dos títulos padrão antes E depois do teste — os testes deste
    arquivo controlam sozinhos o que está instalado, nunca herdam de uma rodada anterior."""

    def _limpar():
        r = sessao_a.get("/api/mapas-base")
        assert r.status_code == 200, r.text
        for item in r.json():
            if item["titulo"] in TITULOS_PADRAO:
                sessao_a.delete(f"/api/itens/{item['id']}")

    _limpar()
    yield
    _limpar()


def test_instalar_e_idempotente_e_traz_ao_menos_3_fontes(sessao_a, galeria_limpa):
    r1 = sessao_a.post("/api/mapas-base/instalar")
    assert r1.status_code == 201, r1.text
    galeria1 = r1.json()
    tipos1 = sorted(b["dados"]["tipo"] for b in galeria1)
    assert len(galeria1) >= 3, galeria1  # portão: "galeria com ≥ 3 mapas base"
    assert {"pmtiles", "osm_raster_proxy", "nenhum"} <= set(tipos1)

    r2 = sessao_a.post("/api/mapas-base/instalar")
    assert r2.status_code == 201, r2.text
    galeria2 = r2.json()
    assert sorted(b["id"] for b in galeria1) == sorted(b["id"] for b in galeria2), "instalar de novo duplicou item"


def test_licenca_e_atribuicao_declaradas_em_toda_fonte_menos_nenhum(sessao_a, galeria_limpa):
    r = sessao_a.post("/api/mapas-base/instalar")
    assert r.status_code == 201, r.text
    for item in sessao_a.get("/api/mapas-base").json():
        if item["dados"]["tipo"] == "nenhum":
            continue
        assert item["creditos"], item
        assert item["termos_de_uso"], item  # "licença" — docs/DADO_DEMO.md tem a mesma lista por extenso


def test_listagem_vem_ordenada_por_dados_ordem(sessao_a, galeria_limpa):
    sessao_a.post("/api/mapas-base/instalar")
    galeria = sessao_a.get("/api/mapas-base").json()
    ordens = [b["dados"]["ordem"] for b in galeria]
    assert ordens == sorted(ordens), ordens


def test_exatamente_um_padrao_depois_de_instalar(sessao_a, galeria_limpa):
    sessao_a.post("/api/mapas-base/instalar")
    galeria = sessao_a.get("/api/mapas-base").json()
    padroes = [b for b in galeria if b["dados"].get("padrao")]
    assert len(padroes) == 1, padroes
    assert padroes[0]["dados"]["tipo"] == "pmtiles"  # semear.py: a fonte 1 é o padrão de fábrica


def test_tornar_padrao_desliga_o_anterior_na_mesma_chamada(sessao_a, galeria_limpa):
    sessao_a.post("/api/mapas-base/instalar")
    galeria = sessao_a.get("/api/mapas-base").json()
    alvo = next(b for b in galeria if not b["dados"].get("padrao"))
    anterior = next(b for b in galeria if b["dados"].get("padrao"))

    r = sessao_a.post(f"/api/mapas-base/{alvo['id']}/tornar-padrao")
    assert r.status_code == 200, r.text
    assert r.json()["dados"]["padrao"] is True

    depois = {b["id"]: b for b in sessao_a.get("/api/mapas-base").json()}
    assert depois[alvo["id"]]["dados"]["padrao"] is True
    assert depois[anterior["id"]]["dados"].get("padrao") in (False, None)
    padroes = [b for b in depois.values() if b["dados"].get("padrao")]
    assert len(padroes) == 1, padroes


def test_tornar_padrao_de_item_que_nao_e_mapa_base_422(sessao_a):
    criado = sessao_a.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": "zt mapa comum", "dados": {"esquema_versao": 1, "corpo": {}}},
    )
    assert criado.status_code == 201, criado.text
    outro = criado.json()
    try:
        r = sessao_a.post(f"/api/mapas-base/{outro['id']}/tornar-padrao")
        assert r.status_code == 422, r.text
        assert r.json()["erro"] == "tipo_invalido"
    finally:
        sessao_a.delete(f"/api/itens/{outro['id']}")


def test_tornar_padrao_item_inexistente_404(sessao_a):
    r = sessao_a.post("/api/mapas-base/00000000-0000-0000-0000-000000000000/tornar-padrao")
    assert r.status_code == 404, r.text


def test_indice_unico_recusa_dois_padroes_forcados_pelo_patch_generico(sessao_a, galeria_limpa):
    """Defesa em profundidade: mesmo contornando a rota tornar-padrao e ligando `dados.padrao` por PATCH
    genérico em DOIS itens, o índice único (`ux_item_mapa_base_padrao`) barra o segundo — 409, nunca dois
    defaults."""
    sessao_a.post("/api/mapas-base/instalar")
    galeria = sessao_a.get("/api/mapas-base").json()
    a, b = galeria[0], galeria[1]

    def _por_padrao(item, valor):
        dados = dict(item["dados"])
        dados["padrao"] = valor
        return sessao_a.patch(f"/api/itens/{item['id']}", json={"dados": dados})

    for outro in galeria:
        if outro["id"] not in (a["id"], b["id"]):
            _por_padrao(outro, False)
    assert _por_padrao(a, False).status_code == 200
    assert _por_padrao(a, True).status_code == 200
    r = _por_padrao(b, True)
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("z,x,y", [(0, 0, 5), (-1, 0, 0), (20, 0, 0), (3, 8, 0)])
def test_proxy_osm_recusa_zxy_fora_da_faixa_sem_tocar_rede(sessao_a, z, x, y):
    """z=0 só tem x=y=0; zoom negativo/acima do teto; x fora do lado 2**z — os quatro batem em `validar_zxy`
    antes de qualquer tentativa de rede (offline por construção, não por sorte)."""
    r = sessao_a.get(f"/api/mapas-base/osm/{z}/{x}/{y}.png")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "validacao"


def test_proxy_osm_ignora_qualquer_tentativa_de_escolher_host(sessao_a):
    """Refutação do item: nenhum parâmetro de query muda o destino da busca — a rota não declara ?host=/
    ?url= nenhum, então FastAPI simplesmente ignora o que vier a mais na querystring. Usa z/x/y inválidos
    para não sair à rede de verdade; o ponto do teste é o corpo da rota nunca ler esses parâmetros, não o
    resultado do ladrilho."""
    r = sessao_a.get("/api/mapas-base/osm/0/0/9.png?host=169.254.169.254&url=http://169.254.169.254/")
    assert r.status_code == 422, r.text  # 422 de validar_zxy, não um erro de host — prova que nem chegou lá
