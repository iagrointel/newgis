"""Apoio dos e2e do item L2-07-a-pwa-instalavel-cache (PWA de campo): criação de um item tipo `mapa` para a
lista de campo ter o que mostrar, leitura do IndexedDB do navegador (mesmo banco que `web/campo/idb.js` usa)
e espera pela ativação do service worker — tudo por `page.evaluate`, sem reimplementar a lógica do app.js."""

import time

ITEM = "L2-07-a-pwa-instalavel-cache"


def entrar_por_api(pagina, slug: str, login: str, senha: str) -> None:
    """Login pela API (`POST /api/login`) em vez da tela `/entrar`: o cookie de sessão que a resposta grava
    é do MESMO contexto de navegador do `page` (a API request context do playwright, obtida por `page.request`,
    compartilha o cookie jar com a página) — a navegação seguinte a `/campo/` já sai autenticada, sem passar
    pela UI de login. Só isso; nada do que este item testa depende da tela `/entrar` (isso é do item
    L0-02-a-login-sessao, já com o seu próprio e2e). Necessário nesta trilha porque a app deliberadamente NÃO
    serve `/static/` sozinha (ADR: só o nginx serve — ver `handoffs/T1/20_arquitetura.md`), e a trilha isolada
    roda só `uvicorn`, sem nginx na frente; o shell de `/campo/` não depende de `/static/`, então funciona
    igual — só a TELA de login (que não é objeto deste item) não renderiza aqui."""
    r = pagina.request.post("/api/login", data={"inquilino": slug, "login": login, "senha": senha})
    assert r.status == 200 and r.json().get("ok") is True, (r.status, r.text())


def sair_por_api(pagina) -> None:
    pagina.request.post("/api/logout", data={})


def criar_mapa_de_campo(tela, titulo: str, n_camadas: int = 2) -> str:
    corpo = {
        "tipo": "mapa",
        "titulo": titulo,
        "dados": {
            "esquema_versao": 1,
            "corpo": {"camadas": [{"id": f"camada-{i}", "nome": f"camada {i}"} for i in range(n_camadas)]},
        },
    }
    r = tela.api("POST", "/api/itens", corpo)
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def apagar_item(tela, item_id: str) -> None:
    tela.api("DELETE", f"/api/itens/{item_id}")
    tela.api("POST", "/api/lixeira/esvaziar", {"ids": [item_id]})


def esperar_service_worker_ativo(page, timeout_ms: int = 15000) -> None:
    page.wait_for_function(
        "async () => { const r = await navigator.serviceWorker.getRegistration('/campo/'); "
        "return !!(r && r.active && r.active.state === 'activated'); }",
        timeout=timeout_ms,
    )


def nomes_de_cache(page) -> list[str]:
    return page.evaluate("() => caches.keys()")


def idb_ler(page, banco: str, loja: str, chave):
    """Lê um registro do IndexedDB do PWA de campo pela mesma API nativa que `idb.js` usa — não importa o
    módulo (é um ES module com import relativo, não dá para `require` de dentro do `page.evaluate`)."""
    return page.evaluate(
        """([banco, loja, chave]) => new Promise((resolve, reject) => {
            const pedido = indexedDB.open(banco);
            pedido.onsuccess = () => {
              const db = pedido.result;
              if (!db.objectStoreNames.contains(loja)) { resolve(null); return; }
              const req = db.transaction(loja, 'readonly').objectStore(loja).get(chave);
              req.onsuccess = () => resolve(req.result || null);
              req.onerror = () => reject(req.error);
            };
            pedido.onerror = () => reject(pedido.error);
        })""",
        [banco, loja, chave],
    )


def idb_config(page, chave: str):
    """`idb_ler` na loja `config` devolve o registro inteiro `{chave, valor}` (é como `idb.js::gravarConfig`
    grava, com `chave` de keyPath); os testes só querem o `valor` — o mesmo que `lerConfig()` do app.js devolve."""
    rec = idb_ler(page, "plat_campo", "config", chave)
    return rec["valor"] if rec else None


def idb_listar(page, banco: str, loja: str) -> list:
    return page.evaluate(
        """([banco, loja]) => new Promise((resolve, reject) => {
            const pedido = indexedDB.open(banco);
            pedido.onsuccess = () => {
              const db = pedido.result;
              if (!db.objectStoreNames.contains(loja)) { resolve([]); return; }
              const req = db.transaction(loja, 'readonly').objectStore(loja).getAll();
              req.onsuccess = () => resolve(req.result || []);
              req.onerror = () => reject(req.error);
            };
            pedido.onerror = () => reject(pedido.error);
        })""",
        [banco, loja],
    )


def idb_apagar_banco(page, banco: str) -> None:
    page.evaluate(
        "(banco) => new Promise((resolve, reject) => { "
        "const p = indexedDB.deleteDatabase(banco); p.onsuccess = () => resolve(); p.onerror = () => reject(p.error); "
        "p.onblocked = () => resolve(); })",
        banco,
    )


def esperar(segundos: float) -> None:
    time.sleep(segundos)
