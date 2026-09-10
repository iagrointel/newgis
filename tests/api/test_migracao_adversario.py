# ruff: noqa: F811 — `portal` e `limpar` são fixtures importadas do módulo do construtor e aparecem como parâmetro
"""ADVERSÁRIO INDEPENDENTE do item L2-08-a-leitor-portal-inventario (commits 17fdef1/944ab62 do ramo wt/l208a).

Cada `xfail(strict=True)` é um ACHADO; nada aqui é conserto. Base própria da trilha (`laco/trilha_ambiente.sh
advl4`). Reusa o servidor de mentira do construtor (`tests/migracao/portal_falso.py`) e acrescenta um segundo
servidor, o "host alheio", que só REGISTRA o que recebe — é ele que prova para onde o token viaja.

Ataques do prompt: o token fora das colunas de texto (inclusive log, job, erro e CSV); retomada que repete ou
pula; portal com 100 mil itens ou item com nome de 1 MB; inventário de A visível para B por id de job; a tela
exposta antes do login."""

import http.server
import json
import threading

import pytest

from app.migracao import relatorio
from app.migracao.portal import ErroPortal, ErroRede
from tests.api.test_migracao_inventario import (  # noqa: F401 — as fixtures precisam estar no módulo
    TOKEN,
    _cursor,
    _preparar,
    _rodar,
    limpar,
    portal,
)
from tests.migracao.portal_falso import PortalFalso, acervo, ip_publico

ITEM = "L2-08-a-leitor-portal-inventario"
ID_ALHEIO = "f" * 32


# ----------------------------------------------------------------------------------------- host alheio

class _Registrador(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        cabecalhos = {k.lower(): v for k, v in self.headers.items()}
        self.server.recebidos.append({"caminho": self.path, "cabecalhos": cabecalhos})
        destino = self.server.redirecionar_para
        if destino:
            self.send_response(302)
            self.send_header("Location", destino + self.path)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if "/query" in self.path:
            corpo = json.dumps({"count": 7}).encode()
        else:
            corpo = json.dumps({"currentVersion": 11.1, "tables": [],
                                "layers": [{"id": 0, "name": "a", "geometryType": "esriGeometryPoint"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


class HostAlheio:
    """Servidor no IP público (a defesa de SSRF recusa loopback) que guarda cabeçalho por cabeçalho."""

    def __init__(self, redirecionar_para: str | None = None):
        self.redirecionar_para = redirecionar_para

    def __enter__(self):
        ip = ip_publico()
        if ip is None:
            pytest.skip("máquina sem IP público")
        self.servidor = http.server.ThreadingHTTPServer((ip, 0), _Registrador)
        self.servidor.recebidos = []
        self.servidor.redirecionar_para = self.redirecionar_para
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.servidor.shutdown()
        self.thread.join(timeout=5)
        self.servidor.server_close()
        return False

    @property
    def base(self) -> str:
        return f"http://{self.servidor.server_address[0]}:{self.servidor.server_address[1]}"

    @property
    def recebidos(self) -> list:
        return self.servidor.recebidos


def _item_apontando_para(url: str, item_id: str = ID_ALHEIO) -> dict:
    """Um item de serviço como qualquer membro da organização pode registrar no portal: `url` livre."""
    return {"id": item_id, "owner": "ana.tec", "title": "camada registrada por um membro", "type": "Feature Service",
            "typeKeywords": ["Feature Service", "Service"], "created": 1_700_000_000_000,
            "modified": 1_700_000_000_000, "lastViewed": 1_700_000_000_000, "url": url, "size": 10, "numViews": 1}


# ----------------------------------------------------------------------------------------- token: para onde vai

@pytest.mark.xfail(strict=True, reason="ACHADO B1: o token do portal do cliente é enviado, em "
                   "X-Esri-Authorization, para QUALQUER host que apareça no campo `url` de um item — campo que "
                   "qualquer membro da organização escreve ao registrar um item. Um membro sem privilégio captura "
                   "a credencial usada pelo inventário (que é de administrador, perfil_minimo='admin')")
def test_token_nao_viaja_para_o_host_da_url_de_um_item(sessao_a, env, portal, limpar):
    with HostAlheio() as alheio:
        portal.servidor.acervo["itens"].append(
            _item_apontando_para(alheio.base + "/arcgis/rest/services/Alheio/FeatureServer"))
        inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
        _rodar(inv, job, tenant, usuario)
        assert alheio.recebidos, "o leitor nem chamou o host alheio — o teste não provaria nada"
        com_token = [r for r in alheio.recebidos if TOKEN in r["cabecalhos"].get("x-esri-authorization", "")]
        assert com_token == [], f"token do portal entregue ao host alheio em {len(com_token)} pedido(s): " \
                                f"{[r['caminho'] for r in com_token]}"


@pytest.mark.xfail(strict=True, reason="ACHADO B1b: o mesmo cabeçalho com o token acompanha o redirecionamento "
                   "(302) para um terceiro host — `_requisitar` remonta `_cabecalhos()` a cada salto sem olhar "
                   "se o host mudou")
def test_token_nao_segue_redirecionamento_para_outro_host(sessao_a, env, portal, limpar):
    with HostAlheio() as destino, HostAlheio(redirecionar_para=None) as intermediario:
        intermediario.servidor.redirecionar_para = destino.base
        portal.servidor.acervo["itens"].append(
            _item_apontando_para(intermediario.base + "/arcgis/rest/services/Salto/FeatureServer"))
        inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
        _rodar(inv, job, tenant, usuario)
        assert intermediario.recebidos and destino.recebidos
        com_token = [r for r in destino.recebidos if TOKEN in r["cabecalhos"].get("x-esri-authorization", "")]
        assert com_token == [], f"token entregue ao host de destino do 302 em {len(com_token)} pedido(s)"


# ----------------------------------------------------------------------------------------- item que derruba o job

def _tres_tentativas(inv, job, tenant, usuario):
    """O worker tenta 3 vezes (tentativas=3 na tarefa). Reproduz sem worker; devolve as exceções."""
    excecoes = []
    for _ in range(3):
        try:
            _rodar(inv, job, tenant, usuario)
            excecoes.append(None)
        except Exception as e:  # noqa: BLE001 — é exatamente o tipo que se quer ver
            excecoes.append(e)
    return excecoes


def _estado(env, tenant, usuario, inv):
    with _cursor(env, tenant, usuario) as cur:
        cur.execute("SELECT estado, mensagem, retomada FROM plat.migracao_inventario WHERE id = %s::uuid", (inv,))
        return dict(cur.fetchone())


@pytest.mark.xfail(strict=True, reason="ACHADO B2: um item com campo fora do esperado (título com NUL, numViews "
                   "que não é número) derruba a tarefa com exceção que NÃO é ErroPortal; a tarefa só trata "
                   "ErroPortal, o worker esgota as 3 tentativas e o inventário fica 'rodando' para sempre, sem "
                   "mensagem — e a tela mostra isso como leitura em curso")
@pytest.mark.parametrize("campo,valor", [("title", "Mapa\u0000escondido"), ("numViews", "muitos")])
def test_item_malformado_leva_o_inventario_a_falhou_com_mensagem(sessao_a, env, portal, limpar, campo, valor):
    portal.servidor.acervo["itens"][0][campo] = valor
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    excecoes = _tres_tentativas(inv, job, tenant, usuario)
    assert all(e is not None for e in excecoes), "o inventário passou? então o dado não era problema"
    assert not any(isinstance(e, ErroRede) for e in excecoes)
    est = _estado(env, tenant, usuario, inv)
    assert est["estado"] == "falhou" and est["mensagem"], est


@pytest.mark.xfail(strict=True, reason="ACHADO B3: uma página de busca acima de 8 MiB (9 itens com título de 1 MB "
                   "cabem numa página de 100) levanta `resposta_grande_demais`, que não é rede nem definitivo: "
                   "a retomada volta SEMPRE para a mesma página, as 3 tentativas morrem no mesmo ponto e o "
                   "inventário fica 'rodando' — não há como pular a página nem reduzir `num`")
def test_pagina_gigante_nao_prende_a_retomada_no_mesmo_ponto(sessao_a, env, portal, limpar):
    for item in portal.servidor.acervo["itens"][:9]:
        item["title"] = "N" * (1024 * 1024)
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    excecoes = _tres_tentativas(inv, job, tenant, usuario)
    assert all(isinstance(e, ErroPortal) and e.motivo == "resposta_grande_demais" for e in excecoes), excecoes
    est = _estado(env, tenant, usuario, inv)
    assert est["estado"] == "falhou", est


# ----------------------------------------------------------------------------------------- retomada que pula

@pytest.mark.xfail(strict=True, reason="ACHADO B4: a retomada continua do `start` da página e confia que a ordem "
                   "do portal não mudou; se mudou (empate em `created`, item criado ou apagado durante a leitura), "
                   "os itens que migraram para as páginas já lidas nunca são lidos e o inventário conclui com "
                   "MENOS itens que o `total` que o próprio portal declarou, sem aviso")
def test_retomada_nao_pula_itens_quando_a_ordem_do_portal_muda(sessao_a, env, limpar):
    with PortalFalso(itens_sinteticos=250) as falso:
        inv, job, tenant, usuario = _preparar(sessao_a, env, falso, limpar, com_token=False)
        falso.configurar(falhar_apos=4)  # raiz, self, página 1 lidas; corta na página 2
        with pytest.raises(ErroRede):
            _rodar(inv, job, tenant, usuario)
        assert _estado(env, tenant, usuario, inv)["retomada"] == {"fase": "itens", "start": 101}
        falso.servidor.sinteticos.reverse()  # a ordem do portal mudou entre as duas tentativas
        falso.configurar(falhar_apos=None)
        _, totais = _rodar(inv, job, tenant, usuario)
    r = sessao_a.get(f"/api/migracao/inventarios/{inv}").json()
    assert r["estado"] == "concluido"
    assert totais["itens"] == 250, f"concluído com {totais['itens']} de 250 itens, sem aviso"


def test_retomada_nao_repete_item_ja_gravado(sessao_a, env, limpar):
    """Contraprova do B4 (passa): com a ordem estável, corte e retomada não duplicam nem perdem item."""
    with PortalFalso(itens_sinteticos=250) as falso:
        inv, job, tenant, usuario = _preparar(sessao_a, env, falso, limpar, com_token=False)
        falso.configurar(falhar_apos=4)
        with pytest.raises(ErroRede):
            _rodar(inv, job, tenant, usuario)
        falso.configurar(falhar_apos=None)
        _, totais = _rodar(inv, job, tenant, usuario)
    assert totais["itens"] == 250
    with _cursor(env, tenant, usuario) as cur:
        cur.execute("SELECT count(*) AS n, count(DISTINCT item_esri_id) AS d FROM plat.migracao_item "
                    "WHERE inventario_id = %s::uuid", (inv,))
        r = cur.fetchone()
        assert r["n"] == r["d"] == 250


# ----------------------------------------------------------------------------------------- CSV

@pytest.mark.xfail(strict=True, reason="ACHADO B5: o CSV leva o título do item do portal (texto de terceiro) "
                   "sem neutralizar prefixo de fórmula; o destinatário abre no Excel (o BOM existe para isso) e "
                   "uma célula '=HYPERLINK(...)' ou '=cmd|...' vira fórmula executada")
def test_csv_neutraliza_formula_no_titulo():
    linhas = [{"item_esri_id": "a" * 32, "tipo": "Web Map", "titulo": '=HYPERLINK("http://alheio.invalido";"abra")',
               "classificacao": "migra", "classificacao_motivo": "", "dono_login": "x", "tamanho_bytes": 1,
               "contagem_total": None, "camadas": [], "dependencias": [], "num_visualizacoes": 0,
               "modificado_esri_em": None, "ultimo_acesso_em": None, "url": None},
              {**{"item_esri_id": "b" * 32, "tipo": "CSV", "classificacao": "nao_migra", "classificacao_motivo": "",
                  "dono_login": "x", "tamanho_bytes": 1, "contagem_total": None, "camadas": [], "dependencias": [],
                  "num_visualizacoes": 0, "modificado_esri_em": None, "ultimo_acesso_em": None, "url": None},
               "titulo": "+cmd|' /C calc'!A0"}]
    corpo = relatorio.csv_de_itens(linhas).decode("utf-8-sig")
    celulas = [linha.split(";")[1] for linha in corpo.split("\r\n")[1:3]]
    for celula in celulas:
        assert not celula.lstrip('"').startswith(("=", "+", "-", "@")), f"célula sai como fórmula: {celula!r}"


# ----------------------------------------------------------------------------------------- tamanho declarado

@pytest.mark.xfail(strict=True, reason="ACHADO B6: o AGOL devolve `size: -1` para item sem arquivo (web map, "
                   "referência a serviço); o motor grava -1 e SOMA os -1 em `totais.bytes_declarados` e em "
                   "`por_tipo[].bytes` — o tamanho declarado do relatório fica errado para baixo")
def test_tamanho_menos_um_do_agol_nao_entra_na_soma(sessao_a, env, portal, limpar):
    itens = portal.servidor.acervo["itens"]
    positivos = sum(i["size"] for i in itens[3:] if i["size"] and i["size"] > 0)
    for item in itens[:3]:
        item["size"] = -1
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    _, totais = _rodar(inv, job, tenant, usuario)
    assert totais["bytes_declarados"] == positivos, (totais["bytes_declarados"], positivos)


# ----------------------------------------------------------------------------------------- cruzado por id de job

def test_inventario_e_job_de_a_por_id_nao_abrem_para_b(sessao_a, sessao_b, env, portal, limpar):
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    _rodar(inv, job, tenant, usuario)
    for caminho in (f"/api/jobs/{job}", f"/api/jobs/{job}/log", f"/api/migracao/inventarios/{inv}",
                    f"/api/migracao/inventarios/{inv}/itens", f"/api/migracao/inventarios/{inv}/relatorio.csv"):
        r = sessao_b.get(caminho)
        assert r.status_code == 404, (caminho, r.status_code, r.text[:120])
    assert sessao_b.post(f"/api/jobs/{job}/cancelar").status_code in (403, 404)
    assert sessao_b.delete(f"/api/migracao/inventarios/{inv}").status_code == 404
    assert job not in {j["id"] for j in sessao_b.get("/api/jobs").json()["itens"]}


# ----------------------------------------------------------------------------------------- token depois de falha

def test_token_nao_aparece_em_coluna_alguma_depois_de_falha_nao_tratada(sessao_a, env, portal, limpar):
    """Depois do B2 (exceção fora do caminho tratado), varre TODA coluna de texto/jsonb do schema, com o
    contexto do inquilino, à procura do token. Passa: o token não vaza para o banco; vaza pela REDE (B1)."""
    portal.servidor.acervo["itens"][0]["numViews"] = "muitos"
    inv, job, tenant, usuario = _preparar(sessao_a, env, portal, limpar)
    ctx = None
    try:
        ctx, _ = _rodar(inv, job, tenant, usuario)
    except Exception as e:  # noqa: BLE001
        from tests.api.test_migracao_inventario import CtxFalso

        ctx = CtxFalso(tenant, usuario, job)
        ctx.log("ERRO", f"{type(e).__name__}: {e}")  # o que o worker gravaria da exceção
    achados = []
    with _cursor(env, tenant, usuario) as cur:
        cur.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = "
                    "current_schema() AND data_type IN ('text', 'character varying', 'jsonb') "
                    "AND NOT (table_name = 'conexao' AND column_name = 'credencial_cifrada')")
        colunas = [(r["table_name"], r["column_name"]) for r in cur.fetchall()]
        assert len(colunas) > 100
        for tabela, coluna in colunas:
            cur.execute(f'SELECT count(*) AS n FROM plat."{tabela}" WHERE "{coluna}"::text LIKE %s',  # noqa: S608
                        (f"%{TOKEN}%",))
            if int(cur.fetchone()["n"]):
                achados.append((tabela, coluna))
    assert achados == [], achados
    assert portal.tokens_na_query == []


@pytest.mark.xfail(strict=True, reason="ACHADO B7: a rota exige `conteudo.registrar_fonte` (o perfil editor tem), "
                   "mas o job `migracao.inventariar` exige perfil admin; o editor recebe 403 DEPOIS de a linha do "
                   "inventário e o evento serem gravados em transações já fechadas — fica um inventário 'pendente' "
                   "sem job para sempre, visível na lista")
def test_editor_com_registrar_fonte_e_recusado_antes_de_gravar_ou_cria_de_verdade(
    sessao_a, env, portal, limpar, usuarios_a,
):
    import uuid as uuid_mod

    from tests.api.conftest import PREFIXO_TESTE

    editor, _, _ = usuarios_a.sessao("editor")
    conexoes, inventarios = limpar
    r = editor.post("/api/conexoes", json={"tipo": "esri_rest", "url": portal.base, "credencial": None,
                                            "nome": f"{PREFIXO_TESTE}-ed-{uuid_mod.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    conexoes.append(cid)
    r2 = editor.post("/api/migracao/inventarios", json={"conexao_id": cid})
    orfaos = [i for i in sessao_a.get("/api/migracao/inventarios").json()["itens"]
              if i["conexao_id"] == cid and i["job_id"] is None]
    inventarios.extend(i["id"] for i in orfaos)
    assert r2.status_code == 201 or orfaos == [], (r2.status_code, r2.text[:160], [i["estado"] for i in orfaos])


def test_senha_longa_nao_volta_no_422(sessao_a, limpar):
    conexoes, _ = limpar
    r = sessao_a.post("/api/migracao/inventarios",
                      json={"conexao_id": "0" * 36, "usuario": "u", "senha": "S3nh4-secreta-" * 30})
    assert r.status_code == 422
    assert "S3nh4-secreta" not in r.text


# ----------------------------------------------------------------------------------------- tela antes do login

def test_tela_migracao_antes_do_login_nao_carrega_dado(cliente):
    r = cliente.get("/migracao")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "maps.arcgis.com" not in r.text and "tok-" not in r.text
    for caminho in ("/api/migracao/inventarios", "/api/conexoes"):
        assert cliente.get(caminho).status_code == 401, caminho


# ----------------------------------------------------------------------------------------- custo por item

def test_custo_por_item_de_servico_e_por_camada_medido(sessao_a, env, limpar, medida):
    """Não é achado, é a medida que faltou: a refutação '10 mil itens em 107 pedidos' usou itens CSV, que
    custam ZERO pedido cada. Um Feature Service custa 1 + camadas + 2 pedidos; um serviço com 300 camadas custa
    303 pedidos sozinho, sem teto."""
    with PortalFalso() as falso:
        a = falso.servidor.acervo
        servico = next(i for i in a["itens"] if i["type"] == "Feature Service" and i["url"])
        base_url = servico["url"]
        # 120 cópias do mesmo serviço, ids novos
        for i in range(120):
            a["itens"].append(dict(servico, id=f"{i:032x}", title=f"copia {i}"))
        # um serviço com 300 camadas
        url_gordo = base_url.rsplit("/", 2)[0] + "/Gordo/FeatureServer"
        gordo = dict(servico, id="e" * 32, title="servico gordo", url=url_gordo)
        a["itens"].append(gordo)
        a["servicos"][gordo["url"]] = {"layers": [{"id": k, "name": f"c{k}", "geometryType": "esriGeometryPoint"}
                                                  for k in range(300)],
                                       "tables": [], "contagens": {str(k): 1 for k in range(300)}}
        inv, job, tenant, usuario = _preparar(sessao_a, env, falso, limpar, com_token=False)
        antes = falso.pedidos
        _, totais = _rodar(inv, job, tenant, usuario)
        pedidos = falso.pedidos - antes
    camadas = len(a["servicos"][base_url]["layers"]) + len(a["servicos"][base_url]["tables"])
    gravar = medida(ITEM + "-adversario")
    gravar("pedidos_totais_com_120_servicos_copiados_e_um_de_300_camadas", pedidos, "pedidos", "portal de mentira")
    gravar("pedidos_por_feature_service_copiado", 3 + camadas, "pedidos", "1 descrição + camadas + 2 relações")
    gravar("pedidos_do_servico_de_300_camadas", 303, "pedidos", "sem teto de camadas por serviço")
    assert totais["itens"] == len(acervo()["itens"]) + 121
    assert pedidos >= 120 * (3 + camadas) + 303
