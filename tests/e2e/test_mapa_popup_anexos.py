"""e2e do popup com ANEXOS (item L2-03-e), no navegador de verdade: a cláusula do portão é "popup
mostra a lista de anexos da feição, com miniatura e link de download, e a captura prova".

A trilha não tem Garage nem Martin de plataforma (a máquina roda os de OUTRA worktree), então este
arquivo sobe a própria infra de módulo, tudo em portas efêmeras de 127.0.0.1:

  * GarageDuble em processo (tests/servidor_garage.py — o mesmo dos testes de API);
  * Martin próprio apontando para o DSN da trilha (yaml em /tmp, porta livre);
  * a app por scripts/servir_local.py com certificado autoassinado de /tmp: PLAT_URL_PUBLICA é
    obrigatoriamente https (app/settings.py) e o CSRF da sessão exige Origin idêntico — a receita do
    handoff de trilhas; o navegador do playwright abre com ignore_https_errors;
  * PLAT_GARAGE_* → duble, PLAT_MARTIN_URL → martin no ambiente do processo servidor.

A bancada de feições é a do item-pai (scripts/mapa_demo_popup.py — três pontos coincidentes); este
arquivo só pendura UM anexo com miniatura em cada uma das três feições coincidentes, direto pelo
mesmo caminho interno do envio (objetos.guardar + INSERT), e depois mede pela tela:

  * cada uma das 3 páginas do popup mostra a seção de anexos com o anexo DAQUELA feição
    (nomes distintos por fid — anexo de uma não vaza para a outra);
  * a miniatura é uma <img> carregada de verdade (naturalWidth > 0) servida pela rota /miniatura;
  * o link de download aponta para a rota /anexos/{id} da feição (globalid na URL, não fid);
  * captura em tests/e2e/capturas/L2-03-e-anexos_popup.png (inventário INVENTARIO_L2-03-e.txt).

Roda com: set -a; source laco/var/trilha/<t>.env; set +a;
          bash laco/roda_teste.sh tests/e2e/test_mapa_popup_anexos.py -q
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.e2e.apoio import Tela, credenciais
from tests.servidor_garage import GarageDuble

RAIZ = Path(__file__).resolve().parents[2]
CAPTURAS = Path(__file__).resolve().parent / "capturas"
MARTIN_BIN = "/home/dev/plat-frota/base/.bin/martin"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar_http(url: str, segundos: int = 60) -> None:
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            r = httpx.get(url, timeout=3, verify=False)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{url} não respondeu 200 em {segundos}s")


@pytest.fixture(scope="module")
def infra():
    """Sobe duble + martin + uvicorn + frente, cria a bancada do item-pai e pendura um anexo com
    miniatura em cada uma das três feições coincidentes (fid 1/2/3). Desfaz tudo ao fim do módulo.
    Conexão própria (a fixture conexao_plat_app é de função); mesma reescrita de schema da casa."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_edicao_transacional import _admin_usuario_id, ids_por_slug
    from tests.api.test_rls import contexto

    conexao_plat_app = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    conexao_plat_app.autocommit = False

    cred = credenciais()
    if "demo" not in cred:
        pytest.skip("tests/credenciais.txt sem o inquilino demo")

    # 1. Garage duble (em processo) + remendo no settings DESTE processo para a semeadura
    from app.settings import settings

    duble = GarageDuble()
    duble.__enter__()
    chaves_garage = ("PLAT_GARAGE_URL", "PLAT_GARAGE_ADMIN_URL", "PLAT_GARAGE_ADMIN_TOKEN")
    anteriores = {k: getattr(settings, k) for k in chaves_garage}
    object.__setattr__(settings, "PLAT_GARAGE_URL", duble.url)
    object.__setattr__(settings, "PLAT_GARAGE_ADMIN_URL", duble.url)
    object.__setattr__(settings, "PLAT_GARAGE_ADMIN_TOKEN", "token-do-duble-de-teste")

    porta_martin, porta_app = _porta_livre(), _porta_livre()
    url_app = f"https://127.0.0.1:{porta_app}"
    procs = []
    try:
        # 2. Martin da trilha (funções de tile são auto-publicadas do DSN do leitor)
        yaml = Path(f"/tmp/martin_l203eanexos_e2e_{porta_martin}.yaml")
        yaml.write_text(
            f"listen_addresses: '127.0.0.1:{porta_martin}'\n"
            "worker_processes: 1\n"
            "postgres:\n"
            "  connection_string: ${PLAT_DSN_LEITOR}\n"
            "  auto_publish:\n    tables: false\n"
            "  pool_size: 4\n  max_feature_count: 10000\n  default_srid: 4326\n",
            encoding="utf-8",
        )
        # 2. bancada do item-pai na base da trilha (idempotente: apaga a anterior antes de criar).
        # ANTES do Martin: o auto-publish de funções de tile acontece na SUBIDA do processo — Martin
        # ligado antes da bancada sobe com o catálogo vazio e todo tile volta 502 (medido 18/09).
        r = subprocess.run([sys.executable, "scripts/mapa_demo_popup.py", "criar"],
                           cwd=str(RAIZ), env=os.environ, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]

        # 3. Martin da trilha (funções de tile são auto-publicadas do DSN do leitor). Log em /tmp:
        # quando um tile volta 502 no boot o motivo real (erro PG dentro da função) só aparece aqui.
        martin_log = open(f"/tmp/martin_l203eanexos_e2e_{porta_martin}.log", "w")
        procs.append(subprocess.Popen([MARTIN_BIN, "--config", str(yaml)],
                                      stdout=martin_log, stderr=martin_log))

        # 4. a app por servir_local com certificado autoassinado de /tmp (https é obrigatório na
        # PLAT_URL_PUBLICA; o navegador do teste abre com ignore_https_errors)
        cert, chave = Path(f"/tmp/plat_e2e_cert_{porta_app}.pem"), Path(f"/tmp/plat_e2e_chave_{porta_app}.pem")
        r = subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=127.0.0.1", "-keyout", str(chave), "-out", str(cert)],
            capture_output=True, timeout=60)
        assert r.returncode == 0, r.stderr.decode()[-500:]
        env = dict(os.environ)
        env.update({
            "PLAT_GARAGE_URL": duble.url,
            "PLAT_GARAGE_ADMIN_URL": duble.url,
            "PLAT_GARAGE_ADMIN_TOKEN": "token-do-duble-de-teste",
            "PLAT_MARTIN_URL": f"http://127.0.0.1:{porta_martin}",
            "PLAT_URL_PUBLICA": url_app,
        })
        app_log = open(f"/tmp/plat_l203eanexos_e2e_app_{porta_app}.log", "w")
        procs.append(subprocess.Popen(
            [sys.executable, "scripts/servir_local.py", "--porta", str(porta_app),
             "--cert", str(cert), "--chave", str(chave)],
            cwd=str(RAIZ), env=env, stdout=app_log, stderr=app_log))
        _esperar_http(f"{url_app}/api/openapi.json", 90)
        _esperar_http(f"http://127.0.0.1:{porta_martin}/catalog", 60)

        # 5. um anexo com miniatura por feição coincidente, pelo mesmo caminho interno do envio
        from app.edicao import anexos

        ids = ids_por_slug(conexao_plat_app)
        admin_id = _admin_usuario_id(conexao_plat_app, "demo")
        contexto(conexao_plat_app, ids["demo"], usuario_id=admin_id, login="admin")
        anexos_semeados = []
        with conexao_plat_app.cursor() as cur:
            # lixo de rodadas MORTAS da suíte de API nesta trilha (prefixo "zt" = PREFIXO_TESTE): a
            # casca /sig pede tiles de toda camada viva do inquilino no boot, e camada de teste não tem
            # função de tile (FabricaCamada não chama camada_tile_garantir) — cada uma viva devolve 502
            # (medido 18/09), cada órfã de tabela devolve 500 no tilejson. As rodadas são serializadas
            # pelo trinco da trilha, então varrer TODA camada "zt" é seguro. plat.item não aceita DELETE
            # direto (política USING false): lixeira + expurgo, o caminho de produção. Hoje é rede de
            # segurança — o FabricaCamada.limpar já limpa pelo mesmo caminho; isto apanha o que uma
            # morte por timeout/worker deixou para trás.
            cur.execute(
                "SELECT id, dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item "
                "WHERE tipo = 'camada_vetorial' AND titulo LIKE 'zt %'"
            )
            for orfao in cur.fetchall():
                cur.execute(f'DROP TABLE IF EXISTS "{orfao["schema"]}"."{orfao["tabela"]}" CASCADE')
                cur.execute("DELETE FROM plat.feicao_anexo WHERE schema_dado = %s AND tabela_dado = %s",
                            (orfao["schema"], orfao["tabela"]))
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (orfao["id"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (orfao["id"],))
            cur.execute(
                "SELECT id, dados FROM plat.item WHERE tipo = 'camada_vetorial' "
                "AND titulo LIKE 'mapa-popup %(L2-01-d%' AND titulo NOT LIKE '%area%'"
            )
            item = cur.fetchone()
            assert item, "bancada mapa-popup (L2-01-d) não encontrada depois do criar"
            schema, tabela = item["dados"]["schema"], item["dados"]["tabela"]
            cur.execute(f'SELECT fid, globalid FROM "{schema}"."{tabela}" WHERE fid IN (1, 2, 3) ORDER BY fid')
            feicoes = cur.fetchall()
            assert len(feicoes) == 3, feicoes
            import io

            from PIL import Image
            for f in feicoes:
                buf = io.BytesIO()
                Image.new("RGB", (400, 300), (30 + f["fid"] * 60, 30, 200)).save(buf, format="PNG")
                obj, mini_chave = anexos._guardar_com_miniatura(
                    cur, buf.getvalue(), "image/png", str(f["globalid"]), admin_id)
                cur.execute(
                    "INSERT INTO plat.feicao_anexo (tenant_id, schema_dado, tabela_dado, globalid, nome, "
                    "content_type, bytes, sha256, chave, mini_chave, criado_por) VALUES "
                    "(plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (schema, tabela, str(f["globalid"]), f"foto-e2e-fid{f['fid']}.png", "image/png",
                     obj["bytes"], obj["sha256"], obj["chave"], mini_chave, admin_id),
                )
                anexos_semeados.append(cur.fetchone()["id"])
        conexao_plat_app.commit()

        yield type("Infra", (), {"url": url_app, "porta_app": porta_app, "camada_id": item["id"]})()

        # 6. desfaz: bancada fora, linhas de anexo fora (objetos morrem com o duble)
        contexto(conexao_plat_app, ids["demo"], usuario_id=admin_id, login="admin")
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "DELETE FROM plat.feicao_anexo WHERE schema_dado = %s AND tabela_dado = %s",
                (schema, tabela),
            )
        conexao_plat_app.commit()
        subprocess.run([sys.executable, "scripts/mapa_demo_popup.py", "apagar"],
                       cwd=str(RAIZ), env=os.environ, capture_output=True, timeout=120)
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
        for k, v in anteriores.items():
            object.__setattr__(settings, k, v)
        duble.__exit__(None, None, None)
        conexao_plat_app.rollback()
        conexao_plat_app.close()


def test_popup_mostra_anexos_da_feicao_com_miniatura_e_link(infra, page):
    login, senha = credenciais()["demo"]
    tela = Tela(page, infra.url)
    # navegação por URL ABSOLUTA: o goto relativo do Tela.entrar/ir resolve contra a base_url da
    # sessão (PLAT_URL_PUBLICA da trilha, .invalido), não contra a porta efêmera deste módulo
    page.goto(f"{infra.url}/entrar?inquilino=demo&proximo=/", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.fill("#login", login)
    page.fill("#senha", senha)
    page.click("#entrar")
    page.wait_for_url(lambda u: not u.rstrip("/").endswith("/entrar") and "/entrar?" not in u,
                      timeout=20000)
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.goto(f"{infra.url}/mapa", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    # a tela do popup é a casca /sig (L2-01-a-casca-sig): ela instala o JanelaPopup completo de
    # web/js/mapa/atributos.js e expõe window.plat.sig para o e2e. A /mapa perdeu a ponte
    # window.plat.mapa num RESGATE de tronco (d6928993) — a casca é o caminho vivo.
    page.goto(f"{infra.url}/sig", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=30000)
    page.wait_for_function("() => !!(window.plat && window.plat.sig && window.plat.sig.map)",
                           timeout=30000)
    page.evaluate("(id) => window.plat.sig.catalogo.ligar(id)", infra.camada_id)
    page.evaluate("""() => window.plat.sig.map.jumpTo({ center: [-46.633, -23.55], zoom: 16 })""")
    page.evaluate("""() => new Promise((r) => {
      const m = window.plat.sig.map;
      const fonte = 'plat-' + window.plat.sig.catalogo.ativas[0];
      if (m.areTilesLoaded() && m.getSource(fonte) && m.isSourceLoaded(fonte)) return r();
      m.once('idle', r);
    })""")
    page.wait_for_timeout(500)  # render do frame com a feição nova antes do clique
    caixa = page.locator("#mapa").bounding_box()
    page.mouse.click(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    page.wait_for_selector(".popup-plat .popup-anexos-lista", timeout=15000)

    vistos = []
    for n in (1, 2, 3):
        # anda por posição (a ordem dos fid vem do queryRenderedFeatures, não promete ordem)
        while True:
            atual = page.locator(".popup-pager-texto").inner_text().strip()
            if atual == f"{n} de 3":
                break
            page.locator('.popup-pager button[aria-label="próxima feição"]').click()
            page.wait_for_function(
                "(alvo) => document.querySelector('.popup-pager-texto').textContent.trim() !== alvo",
                arg=atual)
        page.wait_for_selector(".popup-anexos-lista li", timeout=15000)
        titulo = page.locator(".popup-anexos-titulo").inner_text().strip()
        assert titulo == "anexos (1)", titulo
        itens = page.locator(".popup-anexos-lista li")
        assert itens.count() == 1
        nome = itens.locator("a").inner_text().strip()
        assert nome.startswith("foto-e2e-fid"), nome
        vistos.append(nome)
        href = itens.locator("a").get_attribute("href")
        assert "/anexos/" in href and href.endswith(itens.get_attribute("data-anexo")), href
        mini = itens.locator("img.popup-anexo-mini")
        assert mini.count() == 1, "anexo com miniatura sem <img> no popup"
        # a <img> nasce com loading=lazy: naturalWidth só sobe quando o GET da miniatura volta
        page.wait_for_function(
            "() => { const img = document.querySelector('.popup-anexos-lista li img.popup-anexo-mini');"
            " return img && img.complete && img.naturalWidth > 0; }", timeout=10000)
        assert "/miniatura" in (mini.get_attribute("src") or "")
        if n == 1:
            CAPTURAS.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(CAPTURAS / "L2-03-e-anexos_popup.png"))

    # cada feição mostrou o SEU anexo: três nomes distintos, nenhum vazamento entre páginas
    assert len(set(vistos)) == 3, vistos
    tela.verificar()
