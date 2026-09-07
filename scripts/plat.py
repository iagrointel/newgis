"""Linha de comando de operação da plataforma (item L7-06-c).

    plat logs --req-id <id>                   reúne as linhas dos serviços do MESMO pedido, em ordem
    plat log nivel DEBUG --por 10min           muda o nível de log em tempo de execução, sem reinício
    plat log nivel DEBUG --componente app.db --por 10min
    plat log nivel --listar                    overrides ativos
    plat log nivel --remover app.db

Chame por `scripts/plat` (embrulho que usa a venv do projeto). O nível é gravado num arquivo que todos
os processos da API e do worker releem sozinhos; nada é reiniciado, nada é sinalizado.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import log as plat_log  # noqa: E402
from app import logs_consulta  # noqa: E402
from app.settings import NIVEIS  # noqa: E402

_PRAZO = re.compile(r"^(?P<n>\d+(?:[.,]\d+)?)(?P<u>s|min|m|h)?$", re.IGNORECASE)
_EM_MINUTOS = {"s": 1 / 60, "min": 1.0, "m": 1.0, "h": 60.0}


def minutos(texto: str) -> float:
    """`10min`, `30s`, `2h`, `10` (minutos). Devolve minutos como número."""
    achado = _PRAZO.match(texto.strip())
    if not achado:
        raise argparse.ArgumentTypeError(f"prazo inválido: {texto!r}; use 30s, 10min ou 2h")
    return float(achado.group("n").replace(",", ".")) * _EM_MINUTOS[(achado.group("u") or "min").lower()]


def comando_logs(args) -> int:
    linhas = logs_consulta.reunir(args.req_id, desde=args.desde, ate=args.ate, especificacao=args.fonte)
    if args.json:
        print(json.dumps([linha.como_dicionario() for linha in linhas], ensure_ascii=False, indent=2))
    else:
        for linha in linhas:
            marca = linha.em.isoformat(timespec="milliseconds") if linha.em else "sem horario"
            print(f"{marca}  {linha.servico:<9} {linha.texto}")
    if not linhas:
        print(f"nenhuma linha com {args.req_id} nas fontes consultadas desde {args.desde}", file=sys.stderr)
        return 1
    return 0


def comando_log_nivel(args) -> int:
    if args.listar:
        print(json.dumps(plat_log.listar_overrides(), ensure_ascii=False, indent=2))
        return 0
    if args.remover:
        if not plat_log.remover_override(args.remover):
            print(f"não há override do componente {args.remover!r}", file=sys.stderr)
            return 1
        print(f"removido: {args.remover}")
        return 0
    if not args.nivel:
        print(f"informe o nível ({'|'.join(NIVEIS)}), --listar ou --remover", file=sys.stderr)
        return 2
    registro = plat_log.definir_override(args.componente, args.nivel, args.por)
    print(json.dumps(registro, ensure_ascii=False))
    return 0


def analisador() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plat", description="operação da plataforma")
    sub = p.add_subparsers(dest="comando", required=True)

    logs = sub.add_parser("logs", help="linhas de todos os serviços de um mesmo pedido")
    logs.add_argument("--req-id", required=True, help="X-Req-Id devolvido na resposta")
    logs.add_argument("--desde", default="-24h", help="janela para trás (padrão -24h; formato do journalctl)")
    logs.add_argument("--ate", default=None)
    logs.add_argument("--fonte", default=None,
                      help="lista de fontes, ex. nginx=arquivo:/var/log/nginx/access.log,api=journal:plat-api.service")
    logs.add_argument("--json", action="store_true")
    logs.set_defaults(funcao=comando_logs)

    log = sub.add_parser("log", help="nível de log em tempo de execução")
    subl = log.add_subparsers(dest="subcomando", required=True)
    nivel = subl.add_parser("nivel", help="ver ou mudar o nível sem reiniciar")
    nivel.add_argument("nivel", nargs="?", choices=[*NIVEIS, *[n.lower() for n in NIVEIS]])
    nivel.add_argument("--componente", default="*",
                       help="logger (app.db), prefixo de rota (rota:/api/tiles) ou * (tudo; padrão)")
    nivel.add_argument("--por", type=minutos, default=None, help="prazo: 30s, 10min, 2h (padrão: sem prazo)")
    nivel.add_argument("--listar", action="store_true")
    nivel.add_argument("--remover", default=None, metavar="COMPONENTE")
    nivel.set_defaults(funcao=comando_log_nivel)
    return p


def principal(argumentos=None) -> int:
    args = analisador().parse_args(argumentos)
    try:
        return args.funcao(args)
    except ValueError as erro:
        print(str(erro), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(principal())
