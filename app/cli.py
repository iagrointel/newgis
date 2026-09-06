"""CLI de operação da plataforma — comando `plat` (shim em scripts/plat; `python -m app.cli` é equivalente).

Subcomando `modo` (item L7-33-modo-somente-leitura): liga e desliga o modo de manutenção/somente-leitura
global ou por inquilino, com MOTIVO OBRIGATÓRIO — toda operação grava uma linha em `plat.sistema_trilha`
com quem/quando/motivo (a trilha é a prova de quem mexeu e por quê; o SQL também recusa motivo vazio,
a exigência não é só da casca). Quem opera: atualização (L7-14), failover (L7-07-c), licença vencida
(L7-11-a) e manutenção planejada.

    plat modo ligar    --motivo "troca da versão 2026.09" [--inquilino SLUG] [--retry-after S] [--quem N]
    plat modo desligar --motivo "troca concluída, smoke ok" [--inquilino SLUG] [--quem N]
    plat modo estado   [--inquilino SLUG]

Conecta como a role do worker (PLAT_DSN_WORKER): ligar/desligar é operação de infraestrutura, nunca da
API — por isso a role da aplicação nem EXECUTE tem nessas funções (migração 20260906T2109).
"""

import argparse
import getpass
import json
import socket
import sys

import psycopg2

from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings


def _quem_padrao() -> str:
    return f"{getpass.getuser()}@{socket.gethostname()}"


def _conectar():
    if not settings.PLAT_DSN_WORKER:
        raise SystemExit("PLAT_DSN_WORKER ausente no ambiente: a CLI opera como a role do worker "
                         "(em produção o shim scripts/plat lê /etc/plat/segredos)")
    con = psycopg2.connect(settings.PLAT_DSN_WORKER, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    with con.cursor() as cur:
        cur.execute(f"SET search_path = {settings.PLAT_SCHEMA}, public")
    return con


def _tenant_id(con, slug: str | None) -> int | None:
    if slug is None:
        return None
    with con.cursor() as cur:
        cur.execute("SELECT * FROM plat.tenant_publico(%s)", (slug,))
        r = cur.fetchone()
    if r is None:
        raise SystemExit(f"inquilino inexistente: {slug!r}")
    return r["id"]


def _escopo(tenant_id: int | None) -> str:
    return "inquilino" if tenant_id is not None else "global"


def _emitir(estado: dict) -> int:
    print(json.dumps(estado, ensure_ascii=False, default=str))
    return 0


def _acao_modo(args: argparse.Namespace) -> int:
    with _conectar() as con:
        tenant_id = _tenant_id(con, getattr(args, "inquilino", None))
        with con.cursor() as cur:
            if args.acao == "estado":
                cur.execute("SELECT plat.modo_ler(%s) AS m", (tenant_id,))
            elif args.acao == "ligar":
                cur.execute("SELECT plat.modo_ligar(%s, %s, %s, %s, %s) AS m",
                            (_escopo(tenant_id), tenant_id, args.motivo, args.quem, args.retry_after))
            else:  # desligar
                cur.execute("SELECT plat.modo_desligar(%s, %s, %s, %s) AS m",
                            (_escopo(tenant_id), tenant_id, args.motivo, args.quem))
            return _emitir(dict(cur.fetchone()["m"]))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="plat", description="CLI de operação da plataforma")
    sub = ap.add_subparsers(dest="comando", required=True)
    modo = sub.add_parser("modo", help="modo de manutenção/somente-leitura (L7-33)")
    acoes = modo.add_subparsers(dest="acao", required=True)

    ligar = acoes.add_parser("ligar", help="liga o modo (motivo obrigatório; grava trilha)")
    ligar.add_argument("--motivo", required=True, help="por que o modo está sendo ligado (vai para a trilha)")
    ligar.add_argument("--inquilino", help="slug do inquilino; sem ele o modo é global")
    ligar.add_argument("--retry-after", type=int, default=300, dest="retry_after",
                       help="segundos do cabeçalho Retry-After das respostas 503 (padrão 300)")
    ligar.add_argument("--quem", default=_quem_padrao(), help="quem opera (padrão: usuário@host)")

    desligar = acoes.add_parser("desligar", help="desliga o modo (motivo obrigatório; grava trilha)")
    desligar.add_argument("--motivo", required=True,
                          help="por que o modo está sendo desligado (vai para a trilha)")
    desligar.add_argument("--inquilino", help="slug do inquilino; sem ele o modo é global")
    desligar.add_argument("--quem", default=_quem_padrao(), help="quem opera (padrão: usuário@host)")

    estado = acoes.add_parser("estado", help="estado efetivo do modo (global ou do inquilino)")
    estado.add_argument("--inquilino", help="slug do inquilino; sem ele só o modo global")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.comando == "modo":
            return _acao_modo(args)
    except psycopg2.Error as e:
        # motivo vazio, inquilino inexistente etc.: a mensagem em português vem do próprio SQL
        print(f"erro: {e.diag.message_primary if e.diag else e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
