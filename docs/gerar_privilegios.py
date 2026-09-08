"""Gera `docs/PRIVILEGIOS.md` a partir do BANCO (`plat.privilegio` + `plat.perfil_privilegio`), não de
`app/auth/privilegios.py` — item L0-07-b-papeis-privilegios, portão de pronto: "tabela de privilégios publicada
em docs/PRIVILEGIOS.md GERADA do banco (não escrita à mão)". `tests/api/test_privilegios_declarados.py` já prova
que o módulo Python e o banco coincidem (migração 003 semeia os dois); este gerador lê só o banco, para que o
documento nunca reflita um `privilegios.py` editado sem migração aplicada.

`python3 docs/gerar_privilegios.py` escreve o arquivo; `--check` só confere e sai != 0 se desatualizado (mesmo
padrão de `docs/gerar_limites.py`/`make limites`; aqui `make privilegios`/`tests/unit/test_privilegios_doc.py`).
Conecta com `PLAT_DSN` do `.env` (role `plat_app`; leitura de `plat.privilegio`/`plat.perfil_privilegio` não
precisa de contexto de inquilino — são tabelas globais, sem RLS, com `REVOKE INSERT/UPDATE/DELETE FROM plat_app`
na migração 003, então este script nunca escreve no banco)."""

import argparse
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # acha o pacote app
from app.schema_ambiente import CursorSchemaAmbiente  # noqa: E402 -- depois do sys.path acima

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:  # roda como `python docs/gerar_privilegios.py`, sem PYTHONPATH=.
    sys.path.insert(0, str(RAIZ))

DESTINO = RAIZ / "docs" / "PRIVILEGIOS.md"
PERFIS = ("visualizador", "campo", "editor", "admin")
ROTULO_PERFIL = {"visualizador": "V", "campo": "C", "editor": "E", "admin": "A"}


def _dsn() -> str:
    valores = dict(dotenv_values(RAIZ / ".env"))
    valores.update({k: v for k, v in __import__("os").environ.items() if k.startswith("PLAT_")})
    dsn = valores.get("PLAT_DSN")
    if not dsn:
        print("sem PLAT_DSN (.env ou ambiente) — rode sudo bash install.sh primeiro", file=sys.stderr)
        raise SystemExit(1)
    return dsn


def _conectar():
    """Fabrica de cursor do ambiente (achado F9): com `RealDictCursor` puro este gerador lia sempre o
    `plat` de PRODUCAO, entao `make privilegios` numa trilha publicava a tabela da producao."""
    return psycopg2.connect(_dsn(), cursor_factory=CursorSchemaAmbiente)


def _ler_banco() -> tuple[list[dict], dict[str, set[str]]]:
    # CursorSchemaAmbiente (não RealDictCursor puro), via `_conectar()` (achado F9): com conexão crua o
    # literal `plat.` abaixo sempre mirava o schema de PRODUÇÃO, então `tests/api/test_privilegios_doc.py`
    # (que roda com PLAT_SCHEMA de trilha/homologação) sempre dava `InsufficientPrivilege: permission denied
    # for schema plat` (a role da trilha não tem privilégio nenhum no `plat` real).
    con = _conectar()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT nome, grupo, descricao, administrativo FROM plat.privilegio ORDER BY grupo, nome")
            privilegios = list(cur.fetchall())
            cur.execute("SELECT perfil, privilegio FROM plat.perfil_privilegio")
            tetos: dict[str, set[str]] = {p: set() for p in PERFIS}
            for r in cur.fetchall():
                tetos.setdefault(r["perfil"], set()).add(r["privilegio"])
    finally:
        con.close()
    return privilegios, tetos


def gerar_markdown() -> str:
    privilegios, tetos = _ler_banco()
    n_administrativos = sum(1 for p in privilegios if p["administrativo"])
    partes = [
        "# Privilégios da plataforma\n",
        "Gerado de `plat.privilegio` + `plat.perfil_privilegio` (o banco vivo) por `docs/gerar_privilegios.py` "
        "(`make privilegios`) — item L0-07-b-papeis-privilegios; não editar à mão. O vocabulário é fechado: "
        "toda rota autenticada declara um destes nomes (ou uma composição `a|b`) em `x-privilegio` no OpenAPI, "
        "e `plat.tem(privilegio)`/`plat.privilegios_de(usuario_id)` são a única forma de perguntar, em rota e em "
        "RLS (ADR 0002 seções 3, 12.1). `app/auth/privilegios.py` espelha esta mesma lista em Python (para "
        "cálculo de `perfil_minimo` sem consulta); `tests/api/test_privilegios_declarados.py` prova que os dois "
        "batem, nome a nome, teto a teto.\n",
        f"**{len(privilegios)} privilégios** em {len({p['grupo'] for p in privilegios})} grupos, "
        f"**{n_administrativos} administrativos** (só entram em papel personalizado com `perfil_minimo = admin`, "
        "ou no perfil `admin` inteiro — ADR 0002 seção 3.3).\n",
        "## Papéis padrão fixos (teto de cada perfil)\n",
        "Os quatro perfis abaixo são fixos, não são linhas de `plat.papel_personalizado` e não se apagam nem se "
        "editam (ADR 0002 seção 2.3). Um papel personalizado é sempre um SUBCONJUNTO do teto do `perfil_minimo` "
        "calculado a partir dos privilégios escolhidos — nunca um acréscimo.\n",
        "| perfil | privilégios no teto |",
        "|---|---|",
    ]
    for perfil in PERFIS:
        partes.append(f"| `{perfil}` | {len(tetos.get(perfil, set()))} |")
    partes.append("\n## Vocabulário completo\n")
    partes.append("V = visualizador · C = campo · E = editor · A = admin · **adm** = privilégio administrativo\n")
    partes.append("| grupo | privilégio | descrição | adm | V | C | E | A |")
    partes.append("|---|---|---|---|---|---|---|---|")
    for p in privilegios:
        marcas = ["x" if p["nome"] in tetos.get(perfil, set()) else "" for perfil in PERFIS]
        adm = "**sim**" if p["administrativo"] else "não"
        partes.append(
            f"| {p['grupo']} | `{p['nome']}` | {p['descricao']} | {adm} | " + " | ".join(marcas) + " |"
        )
    partes.append(
        "\n## Papéis personalizados por inquilino\n"
        "Nome até 128 caracteres, descrição até 250, criados \"a partir de\" um conjunto de privilégios "
        "escolhido pelo administrador (nunca um privilégio que o próprio administrador não tenha — "
        "`403 privilegio_proprio_insuficiente`). O backend calcula `perfil_minimo` = o menor perfil cujo teto "
        "contém todos os privilégios pedidos; atribuir esse papel a um usuário de perfil menor é "
        "`422 papel_incompativel`. Ver `docs/adr/0002-identidade-e-acesso.md` seção 3.3 e "
        "`docs/PARIDADE.md` para a paridade linha a linha com a Esri.\n"
    )
    return "\n".join(partes) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check", action="store_true", help="não escreve; sai != 0 se PRIVILEGIOS.md estiver desatualizado"
    )
    args = ap.parse_args()
    novo = gerar_markdown()
    if args.check:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != novo:
            print(
                "docs/PRIVILEGIOS.md desatualizado em relação ao banco (plat.privilegio); rode: make privilegios",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return
    DESTINO.write_text(novo, encoding="utf-8")
    print(f"escrito: {DESTINO}")


if __name__ == "__main__":
    main()
