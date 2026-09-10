#!/usr/bin/env python3
"""Prova de protocolo do VersionManagementServer (item L2-13-a): a sequência de chamadas que o cliente
Python `arcgis` faz para criar, reconciliar e publicar um ramo.

Duas formas de rodar, e o relatório diz qual foi usada:

1. `--cliente arcgis` — importa `arcgis.features._version.VersionManager` e usa o cliente de verdade.
   Exige o pacote `arcgis` instalado, o que NÃO é o caso desta máquina: ele traz uma árvore de
   dependências grande (a instalação recomendada é por conda) e o disco desta máquina está a 96 %, e a
   regra da casa é não acrescentar dependência. Sem o pacote o script diz isso e sai com código 3 — não
   finge que passou.
2. `--cliente http` (padrão) — faz as MESMAS chamadas, nos mesmos caminhos, com os mesmos parâmetros de
   formulário e conferindo as mesmas chaves de resposta que o cliente da Esri lê. É a prova de que o
   servidor fala o protocolo; não é prova de que aquele cliente específico funciona.

Uso:
    set -a; source laco/var/trilha/<trilha>.env; set +a
    venv/bin/python tests/esri/cliente_arcgis_versoes.py [--cliente http|arcgis] [--base-url URL]

Saída: relatório em texto + `tests/medidas/L2-13-a-versoes-ramo-reconciliar-protocolo.json`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("PLAT_AMBIENTE", "dev")

PASSOS: list[dict] = []


def marcar(passo: str, estado: str, evidencia: str) -> None:
    assert estado in ("ok", "falhou", "nao_verificado")
    PASSOS.append({"passo": passo, "estado": estado, "evidencia": evidencia[:600]})
    print(f"[{estado:>14}] {passo}: {evidencia[:160]}")


def _sessao(base_url: str | None):
    """Cliente HTTP: contra uma URL de verdade quando `--base-url` vem, senão contra a própria
    aplicação em processo (TestClient do Starlette, que passa pelo mesmo caminho ASGI)."""
    if base_url:
        import httpx

        return httpx.Client(base_url=base_url, timeout=60)
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


def _entrar(cliente) -> None:
    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or (RAIZ / "tests" / "credenciais.txt"))
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    dados = {p[0]: (p[1], " ".join(p[2:])) for p in (li.split() for li in linhas) if len(p) >= 3}
    if "demo" not in dados:
        raise SystemExit("tests/credenciais.txt sem a linha do inquilino demo (rode install.sh)")
    login, senha = dados["demo"]
    r = cliente.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha})
    if r.status_code != 200:
        raise SystemExit(f"login falhou: {r.status_code} {r.text[:300]}")


def _camada_versionada(cliente):
    """Cria a camada da prova (a mesma `FabricaCamada` das baterias de API: `plat.camada_schema_garantir`
    + `plat.camada_preparar`, que é o que a ingestão faz) e liga o versionamento nela. Não se aproveita
    camada do catálogo porque numa base de trilha o catálogo guarda item de bateria antiga cuja tabela
    física já foi derrubada. Devolve (item_id, encerrar)."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
    from tests.api.test_rls import ids_por_slug

    # CursorSchemaAmbiente (e não RealDictCursor cru) pelo mesmo motivo de tests/conftest.py: sem a
    # reescrita, o SQL com `plat.` literal ignora PLAT_SCHEMA e vai bater no schema de produção.
    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    fabrica = FabricaCamada(con)
    ids = ids_por_slug(con)
    admin_id = _admin_usuario_id(con, "demo")
    item_id, _dados = fabrica.criar(
        "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}], geometria="Point",
    )
    r = cliente.post(f"/api/camadas/{item_id}/versionar", json={})
    if r.status_code != 200:
        raise SystemExit(f"não foi possível ligar o versionamento: {r.status_code} {r.text[:300]}")

    def encerrar():
        fabrica.limpar()
        con.close()

    return item_id, encerrar


def prova_http(cliente, item_id: str) -> None:
    """A sequência de `arcgis.features._version`: descritor, versions, create, startReading,
    startEditing, reconcile, stopEditing, post, conflicts, delete."""
    vms = f"/rest/services/{item_id}/VersionManagementServer"
    nome = f"zt-arcgis-{uuid.uuid4().hex[:6]}"

    r = cliente.get(f"{vms}?f=json")
    corpo = r.json()
    ok = r.status_code == 200 and corpo.get("defaultVersionName") and corpo.get("capabilities")
    marcar("descritor do VersionManagementServer", "ok" if ok else "falhou", json.dumps(corpo)[:300])

    r = cliente.get(f"{vms}/versions?f=json")
    corpo = r.json()
    ok = r.status_code == 200 and isinstance(corpo.get("versions"), list) and corpo["versions"]
    marcar("versions lista o padrão", "ok" if ok else "falhou", json.dumps(corpo)[:300])

    r = cliente.post(f"{vms}/create", data={"versionName": nome, "accessPermission": "public", "f": "json"})
    corpo = r.json()
    info = corpo.get("versionInfo") or {}
    guid = info.get("versionGuid", "")
    ok = r.status_code == 200 and corpo.get("success") and guid.startswith("{") and guid.endswith("}")
    marcar("create devolve versionInfo com versionGuid entre chaves", "ok" if ok else "falhou",
           json.dumps(corpo)[:300])
    if not ok:
        return

    sessao_id = "{" + str(uuid.uuid4()).upper() + "}"
    for passo in ("startReading", "startEditing", "stopEditing", "stopReading"):
        r = cliente.post(f"{vms}/{guid}/{passo}", data={"sessionId": sessao_id, "f": "json"})
        corpo = r.json()
        ok = r.status_code == 200 and corpo.get("success") is True and corpo.get("sessionId") == sessao_id
        marcar(f"{passo} aceita e ecoa sessionId", "ok" if ok else "falhou", json.dumps(corpo)[:300])

    r = cliente.post(
        f"{vms}/{guid}/reconcile",
        data={"sessionId": sessao_id, "abortIfConflicts": "false",
              "conflictDetection": "byObject", "withPost": "false", "f": "json"},
    )
    corpo = r.json()
    ok = r.status_code == 200 and corpo.get("success") is True and "hasConflicts" in corpo and "moment" in corpo
    marcar("reconcile devolve success, hasConflicts e moment", "ok" if ok else "falhou",
           json.dumps(corpo)[:300])

    r = cliente.get(f"{vms}/{guid}/conflicts?f=json")
    corpo = r.json()
    ok = r.status_code == 200 and isinstance(corpo.get("conflicts"), list)
    marcar("conflicts devolve a lista por camada", "ok" if ok else "falhou", json.dumps(corpo)[:300])

    r = cliente.post(f"{vms}/{guid}/post", data={"sessionId": sessao_id, "f": "json"})
    corpo = r.json()
    ok = r.status_code == 200 and corpo.get("success") is True and "moment" in corpo
    marcar("post devolve success e moment", "ok" if ok else "falhou", json.dumps(corpo)[:300])

    outro = f"zt-arcgis-{uuid.uuid4().hex[:6]}"
    guid2 = cliente.post(
        f"{vms}/create", data={"versionName": outro, "f": "json"}
    ).json()["versionInfo"]["versionGuid"]
    r = cliente.post(f"{vms}/{guid2}/delete", data={"sessionId": sessao_id, "f": "json"})
    corpo = r.json()
    ok = r.status_code == 200 and corpo.get("success") is True
    marcar("delete apaga o ramo", "ok" if ok else "falhou", json.dumps(corpo)[:300])

    nomes = [v["versionName"] for v in cliente.get(f"{vms}/versions?f=json").json()["versions"]]
    marcar("o ramo apagado sai da lista", "ok" if outro not in nomes else "falhou", json.dumps(nomes)[:300])


def prova_arcgis(base_url: str | None) -> None:
    try:
        import arcgis  # noqa: F401
    except ImportError as e:
        marcar(
            "cliente Python arcgis", "nao_verificado",
            f"pacote `arcgis` não instalado nesta máquina ({e}); a casa não acrescenta dependência e o "
            "disco está a 96 %. Rode com --cliente http, ou instale o pacote noutra máquina e repita.",
        )
        raise SystemExit(3) from e
    raise SystemExit(
        "o caminho --cliente arcgis existe mas nunca foi executado: sem o pacote instalado não há como "
        "afirmar que funciona. Não escrevemos a chamada sem poder rodá-la."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cliente", choices=("http", "arcgis"), default="http")
    ap.add_argument("--base-url", default=None)
    args = ap.parse_args()

    if args.cliente == "arcgis":
        prova_arcgis(args.base_url)
        return 3

    cliente = _sessao(args.base_url)
    _entrar(cliente)
    item_id, encerrar = _camada_versionada(cliente)
    try:
        prova_http(cliente, item_id)
    finally:
        encerrar()

    destino = RAIZ / "tests" / "medidas" / "L2-13-a-versoes-ramo-reconciliar-protocolo.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(
            {
                "item": "L2-13-a-versoes-ramo-reconciliar",
                "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "cliente": "http (sequência do arcgis.features._version reproduzida)",
                "camada": item_id,
                "passos": PASSOS,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nrelatório: {destino}")
    falhas = [p for p in PASSOS if p["estado"] == "falhou"]
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
