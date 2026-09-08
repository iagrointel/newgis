"""API dos modelos 3D (item L2-09-c-modelos-gltf-ifc-3dtiles).

Cobre, na ordem do portão de pronto:

* criação a partir de um arquivo já enviado, com a conversão indo para a fila;
* IFC aberto convertido: N elementos do arquivo = N linhas na tabela, consultáveis por GUID, tipo e
  pavimento, com as propriedades que o IFC declara;
* glTF entregue pela API (nunca uma URL do armazenamento) e árvore 3D Tiles servida por caminho relativo;
* recusas: recurso externo no glTF, sha256 que o inquilino não tem, nome repetido, caminho fora da árvore.

A conversão é rodada AQUI pela função do job, com o contexto do job, em vez de esperar o trabalhador da
máquina: o teste é do produto (o que a conversão grava e o que a API devolve), não do agendador — a fila
em si tem a suíte dela em tests/api/jobs.
"""

import hashlib

import pytest

from app.modelos3d import tarefas
from tests.api.conftest import novo_cliente
from tests.apoio_modelos3d import (
    ALTURA_M,
    IFC_ABERTO,
    LAT,
    LON,
    glb_caixa,
    glb_com_textura_externa,
)

PREFIXO = "zt-m3d-"
ELEMENTOS_IFC = 13
COM_FORMA_IFC = 11
GUID_LAJE = "3zR0BOEcLADRKln4HYporH"


# ------------------------------------------------------------------ apoio
def _enviar(sessao, dados: bytes, classe: str = "modelo3d") -> str:
    """`POST /api/arquivos` é só por token de serviço (corpo cru, nunca cookie). Devolve o sha256."""
    r = sessao.post("/api/tokens", json={"nome": f"{PREFIXO}tk-{hashlib.sha256(dados).hexdigest()[:8]}",
                                         "escopos": ["admin:inquilino"]})
    assert r.status_code == 201, r.text
    token = r.json()
    try:
        cliente = novo_cliente()
        envio = cliente.post(f"/api/arquivos?classe={classe}", content=dados,
                             headers={"Content-Type": "application/octet-stream",
                                      "Authorization": f"Bearer {token['token']}"})
        assert envio.status_code == 201, envio.text
        return envio.json()["sha256"]
    finally:
        sessao.delete(f"/api/tokens/{token['id']}")


class _Ctx:
    """Contexto mínimo de job para rodar a tarefa dentro do teste, no inquilino da sessão."""

    def __init__(self, tenant_id: int, usuario_id: int):
        from app import db as banco

        self.tenant_id = tenant_id
        self.usuario_id = usuario_id
        self._ctx = banco.Contexto(tenant_id, usuario_id, "worker")
        self._banco = banco
        self.entradas: list = []

    def db(self):
        return self._banco.db(self._ctx)

    def progresso(self, pct, mensagem=""):
        return None

    def entrada(self, item_id, sha256, descricao=""):
        self.entradas.append((item_id, sha256, descricao))


@pytest.fixture
def ctx_a(sessao_a, ids):
    """O id do inquilino não sai por rota (de propósito): vem da função SECURITY DEFINER do banco, a mesma
    que tests/api/test_rls.py usa."""
    from app import db as banco

    with banco.db() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login('demo', 'admin')")
        tenant_id = cur.fetchone()["tenant_id"]
    return _Ctx(tenant_id, ids["a"]["id"])


@pytest.fixture
def criar_modelo(sessao_a):
    criados: list[str] = []

    def criar(dados: bytes, origem: str, nome: str, **extra):
        sha = _enviar(sessao_a, dados)
        corpo = {"nome": nome, "origem": origem, "arquivo_sha256": sha,
                 "lon": LON, "lat": LAT, "altura_m": ALTURA_M, **extra}
        r = sessao_a.post("/api/modelos", json=corpo)
        assert r.status_code == 201, r.text
        modelo = r.json()
        criados.append(modelo["id"])
        sessao_a.post(f"/api/jobs/{modelo['job_id']}/cancelar")  # a conversão roda no teste, não na fila
        return modelo

    yield criar
    for mid in criados:
        sessao_a.delete(f"/api/modelos/{mid}")


# ------------------------------------------------------------------ criação e ficha
def test_criar_devolve_ficha_e_enfileira_a_conversao(sessao_a, criar_modelo):
    nome = f"{PREFIXO}caixa-{hashlib.sha256(nome_semente := b'caixa').hexdigest()[:6]}"
    assert nome_semente
    modelo = criar_modelo(glb_caixa(), "gltf", nome)
    assert modelo["estado"] == "pendente"
    assert modelo["origem"] == "gltf"
    assert modelo["lon"] == pytest.approx(LON)
    assert modelo["job_id"]
    assert "tileset_arquivos" not in modelo  # chave do armazenamento nunca sai na resposta
    ficha = sessao_a.get(f"/api/modelos/{modelo['id']}")
    assert ficha.status_code == 200
    assert ficha.json()["nome"] == nome
    lista = sessao_a.get("/api/modelos")
    assert lista.status_code == 200
    assert any(m["id"] == modelo["id"] for m in lista.json()["itens"])


def test_sha256_que_o_inquilino_nao_tem_e_404(sessao_a):
    r = sessao_a.post("/api/modelos", json={"nome": f"{PREFIXO}fantasma", "origem": "gltf",
                                            "arquivo_sha256": "0" * 64, "lon": LON, "lat": LAT})
    assert r.status_code == 404
    assert r.json()["erro"] == "arquivo_nao_encontrado"


def test_nome_repetido_e_409(sessao_a, criar_modelo):
    nome = f"{PREFIXO}repetido"
    criar_modelo(glb_caixa(), "gltf", nome)
    sha = _enviar(sessao_a, glb_caixa(nome="outro"))
    r = sessao_a.post("/api/modelos", json={"nome": nome, "origem": "gltf", "arquivo_sha256": sha,
                                            "lon": LON, "lat": LAT})
    assert r.status_code == 409


@pytest.mark.parametrize("campo, valor", [("lon", 200.0), ("lat", 91.0), ("escala", 0.0),
                                          ("rotacao_graus", 400.0), ("origem", "dwg"), ("nome", "")])
def test_corpo_invalido_e_422(sessao_a, campo, valor):
    corpo = {"nome": f"{PREFIXO}invalido", "origem": "gltf", "arquivo_sha256": "a" * 64,
             "lon": LON, "lat": LAT, campo: valor}
    r = sessao_a.post("/api/modelos", json=corpo)
    assert r.status_code == 422
    assert any(e["campo"] == campo for e in r.json()["detalhe"])


def test_id_que_nao_e_uuid_e_404(sessao_a):
    assert sessao_a.get("/api/modelos/nao-e-uuid").status_code == 404


# ------------------------------------------------------------------ conversão do IFC
@pytest.fixture
def modelo_ifc(sessao_a, criar_modelo, ctx_a):
    modelo = criar_modelo(IFC_ABERTO.read_bytes(), "ifc", f"{PREFIXO}casa-aberta")
    tarefas.modelo3d_converter(ctx_a, modelo["id"], gerar_tileset=False)
    return sessao_a.get(f"/api/modelos/{modelo['id']}").json()


def test_ifc_convertido_tem_uma_linha_por_elemento(sessao_a, modelo_ifc):
    """Cláusula do portão: N elementos no arquivo = N linhas na tabela."""
    assert modelo_ifc["estado"] == "pronto"
    assert modelo_ifc["elementos"] == ELEMENTOS_IFC
    assert modelo_ifc["elementos_sem_forma"] == ELEMENTOS_IFC - COM_FORMA_IFC
    r = sessao_a.get(f"/api/modelos/{modelo_ifc['id']}/elementos?limite=500")
    assert r.status_code == 200
    assert r.json()["total"] == ELEMENTOS_IFC
    assert len(r.json()["itens"]) == ELEMENTOS_IFC
    assert len({e["guid"] for e in r.json()["itens"]}) == ELEMENTOS_IFC


def test_clique_no_elemento_traz_as_propriedades(sessao_a, modelo_ifc):
    r = sessao_a.get(f"/api/modelos/{modelo_ifc['id']}/elementos/{GUID_LAJE}")
    assert r.status_code == 200
    e = r.json()
    assert e["tipo"] == "IFCSLAB"
    assert e["pavimento"] == "00 groundfloor"
    assert e["propriedades"]["Pset_SlabCommon"]["FireRating"] == "REI30"
    assert e["propriedades"]["Qto_SlabBaseQuantities"]["Depth"] == pytest.approx(250.0)


def test_elementos_filtram_por_tipo_e_pavimento(sessao_a, modelo_ifc):
    paredes = sessao_a.get(f"/api/modelos/{modelo_ifc['id']}/elementos?tipo=IFCWALL").json()
    assert paredes["total"] == 4
    assert {e["tipo"] for e in paredes["itens"]} == {"IFCWALL"}
    terreo = sessao_a.get(f"/api/modelos/{modelo_ifc['id']}/elementos?pavimento=00 groundfloor").json()
    assert 0 < terreo["total"] < ELEMENTOS_IFC


def test_guid_inexistente_e_404(sessao_a, modelo_ifc):
    assert sessao_a.get(f"/api/modelos/{modelo_ifc['id']}/elementos/NAOEXISTE").status_code == 404


def test_a_caixa_gravada_situa_o_modelo_no_ponto_pedido(modelo_ifc):
    """O ponto pedido é a ORIGEM do modelo, que a montagem põe no canto mínimo: o modelo cresce para leste
    (X), para o norte (-Z) e para cima (Y) a partir dele. Logo o ponto é o canto sudoeste da caixa."""
    caixa = modelo_ifc["caixa"]
    assert caixa["oeste"] == pytest.approx(LON, abs=1e-6)
    assert caixa["sul"] == pytest.approx(LAT, abs=1e-6)
    assert caixa["leste"] > LON and caixa["norte"] > LAT
    assert caixa["altura_minima"] == pytest.approx(ALTURA_M, abs=0.01)
    assert len(caixa["cantos"]) == 8


def test_o_glb_convertido_sai_pela_api(sessao_a, modelo_ifc):
    r = sessao_a.get(f"/api/modelos/{modelo_ifc['id']}/glb")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("model/gltf-binary")
    assert r.content[:4] == b"glTF"
    assert hashlib.sha256(r.content).hexdigest() == modelo_ifc["glb_sha256"]


def test_glb_antes_da_conversao_e_409(sessao_a, criar_modelo):
    modelo = criar_modelo(glb_caixa(nome="ainda-nao"), "gltf", f"{PREFIXO}sem-glb")
    r = sessao_a.get(f"/api/modelos/{modelo['id']}/glb")
    assert r.status_code == 409
    assert r.json()["erro"] == "sem_glb"


# ------------------------------------------------------------------ 3D Tiles
@pytest.fixture
def modelo_com_tileset(sessao_a, modelo_ifc, ctx_a):
    tarefas.modelo3d_tileset(ctx_a, modelo_ifc["id"])
    return sessao_a.get(f"/api/modelos/{modelo_ifc['id']}").json()


def test_tileset_sai_pela_api_com_conteudo_relativo(sessao_a, modelo_com_tileset):
    assert modelo_com_tileset["tileset"] is True
    assert modelo_com_tileset["tileset_tiles"] >= 1
    base = f"/api/modelos/{modelo_com_tileset['id']}/3dtiles"
    r = sessao_a.get(f"{base}/tileset.json")
    assert r.status_code == 200
    tileset = r.json()
    assert tileset["asset"]["version"] == "1.1"
    for filho in tileset["root"]["children"]:
        uri = filho["content"]["uri"]
        assert not uri.startswith("/") and "://" not in uri  # relativo: o cliente resolve a partir daqui
        conteudo = sessao_a.get(f"{base}/{uri}")
        assert conteudo.status_code == 200
        assert conteudo.content[:4] == b"glTF"


def test_caminho_fora_da_arvore_e_404(sessao_a, modelo_com_tileset):
    base = f"/api/modelos/{modelo_com_tileset['id']}/3dtiles"
    for caminho in ("conteudo/../../etc/senha", "outro.json", "conteudo/9999.glb"):
        assert sessao_a.get(f"{base}/{caminho}").status_code == 404


def test_tileset_antes_de_gerar_e_409(sessao_a, criar_modelo, ctx_a):
    modelo = criar_modelo(glb_caixa(nome="sem-arvore"), "gltf", f"{PREFIXO}sem-tileset")
    tarefas.modelo3d_converter(ctx_a, modelo["id"], gerar_tileset=False)
    r = sessao_a.get(f"/api/modelos/{modelo['id']}/3dtiles/tileset.json")
    assert r.status_code == 409
    assert r.json()["erro"] == "sem_tileset"


# ------------------------------------------------------------------ recusas de conteúdo
def test_glb_com_textura_externa_e_recusado_na_conversao(sessao_a, criar_modelo, ctx_a):
    """Refutação do item: o modelo mandaria o navegador do usuário buscar arquivo em servidor de terceiro."""
    from app.jobs.registro import FalhaDefinitiva

    modelo = criar_modelo(glb_com_textura_externa(), "gltf", f"{PREFIXO}textura-externa")
    with pytest.raises(FalhaDefinitiva) as e:
        tarefas.modelo3d_converter(ctx_a, modelo["id"], gerar_tileset=False)
    assert "recurso externo" in str(e.value)
    ficha = sessao_a.get(f"/api/modelos/{modelo['id']}").json()
    assert ficha["estado"] == "falhou"
    assert "recurso externo" in ficha["erro"]


def test_arquivo_que_nao_e_ifc_falha_com_motivo(sessao_a, criar_modelo, ctx_a):
    from app.jobs.registro import FalhaDefinitiva

    modelo = criar_modelo(b"isto nao e um IFC nem um GLB" * 40, "ifc", f"{PREFIXO}lixo")
    with pytest.raises(FalhaDefinitiva):
        tarefas.modelo3d_converter(ctx_a, modelo["id"], gerar_tileset=False)
    assert sessao_a.get(f"/api/modelos/{modelo['id']}").json()["estado"] == "falhou"


def test_apagar_leva_os_elementos_junto(sessao_a, criar_modelo, ctx_a):
    modelo = criar_modelo(IFC_ABERTO.read_bytes(), "ifc", f"{PREFIXO}apagavel")
    tarefas.modelo3d_converter(ctx_a, modelo["id"], gerar_tileset=False)
    assert sessao_a.get(f"/api/modelos/{modelo['id']}/elementos").json()["total"] == ELEMENTOS_IFC
    assert sessao_a.delete(f"/api/modelos/{modelo['id']}").status_code == 200
    assert sessao_a.get(f"/api/modelos/{modelo['id']}").status_code == 404
    assert sessao_a.get(f"/api/modelos/{modelo['id']}/elementos").status_code == 404


def test_sem_credencial_nenhuma_rota_responde():
    cliente = novo_cliente()
    for caminho in ("/api/modelos", "/api/modelos/11111111-2222-3333-4444-555555555555",
                    "/api/modelos/11111111-2222-3333-4444-555555555555/elementos",
                    "/api/modelos/11111111-2222-3333-4444-555555555555/glb",
                    "/api/modelos/11111111-2222-3333-4444-555555555555/3dtiles/tileset.json"):
        assert cliente.get(caminho).status_code == 401, caminho
