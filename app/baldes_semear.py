"""Semeadura idempotente dos baldes por inquilino no Garage (item L1-01-d; passo g3 do install.sh; ADR 0016).
Lê `id slug` por linha no stdin — a lista vem do psql como postgres (`SELECT id, slug FROM plat.tenant WHERE
ativo`), porque a role plat_app só enxerga o próprio inquilino pela RLS — e, para cada um, chama
`objetos.semear_bucket` dentro do contexto daquele inquilino. Imprime uma linha por balde e um resumo; a 2ª
execução tem de imprimir `0 alterados` (é a prova de idempotência, teste em tests/api/test_garage_inquilino.py).
Uso: `printf '1 demo\\n2 demo2\\n' | venv/bin/python -m app.baldes_semear`."""

from __future__ import annotations

import sys

from app import db, objetos
from app.garage import ErroGarage


def semear(inquilinos: list[tuple[int, str]], *, web: bool = True, saida=sys.stdout) -> dict:
    """Devolve `{criados_ou_alterados, sem_mudanca, linhas}`; cada linha = (slug, alias, cota_bytes, cota_objetos,
    web_ativo, mudanças)."""
    alterados = 0
    iguais = 0
    linhas = []
    for tenant_id, slug in inquilinos:
        with db.db(db.Contexto(tenant_id=int(tenant_id), usuario_id=0, login="instalador")) as cur:
            linha, mudancas = objetos.semear_bucket(cur, int(tenant_id), slug, web=web)
        if mudancas:
            alterados += 1
        else:
            iguais += 1
        estado = "; ".join(mudancas) if mudancas else "sem mudança"
        print(
            f"balde {linha['bucket_alias']} (inquilino {slug}): cota {linha['cota_bytes']} bytes / "
            f"{linha['cota_objetos']} objetos · web {'ligado' if linha['web_ativo'] else 'desligado'} · {estado}",
            file=saida,
        )
        linhas.append((slug, linha["bucket_alias"], int(linha["cota_bytes"]), int(linha["cota_objetos"]),
                       bool(linha["web_ativo"]), mudancas))
    print(f"baldes: {alterados} criados/alterados · {iguais} sem mudança", file=saida)
    return {"criados_ou_alterados": alterados, "sem_mudanca": iguais, "linhas": linhas}


def _ler_stdin(entrada) -> list[tuple[int, str]]:
    saida = []
    for texto in entrada:
        texto = texto.strip()
        if not texto:
            continue
        partes = texto.split()
        if len(partes) != 2 or not partes[0].isdigit():
            raise ValueError(f"linha fora do padrão 'id slug': {texto!r}")
        saida.append((int(partes[0]), partes[1]))
    return saida


def main(argv: list[str] | None = None) -> int:
    try:
        inquilinos = _ler_stdin(sys.stdin)
        if not inquilinos:
            print("nenhum inquilino recebido no stdin (esperado: 'id slug' por linha)", file=sys.stderr)
            return 2
        semear(inquilinos)
        return 0
    except (ErroGarage, objetos.ConfiguracaoAusente, ValueError) as e:
        print(f"semeadura dos baldes falhou: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
