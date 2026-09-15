"""Persistência da varredura de CVE em banco (item L7-03-f-dependencias-cve-log-correcoes; docs/SEGURANCA.md
seção 7.6). Fecha a parte do bloqueio que `scripts/varredura_dependencias.py` (que continua sendo a fonte de
verdade do pip-audit — nada aqui reimplementa CVSS/OSV) não cobria: grava cada achado em `plat.vulnerabilidade`
e cada execução em `plat.varredura_cve` (migração `db/migracoes/20260915T2252_vulnerabilidade.sql`).

`rodar()` faz só a varredura (pip-audit via `scripts/varredura_dependencias.avaliar`; npm via
`scripts/varredura_seguranca.rodar_npm`, quando `npm` está no PATH) e devolve um dicionário — sem tocar banco,
para o teste de unidade dublar as duas fontes sem precisar de rede nem de venv com pip-audit instalado. `main()`
é o que roda pelo timer (`deploy/plat-varredura-cve.timer` + `.service`, oneshot diário, mesmo espírito de
`deploy/plat-segredo-expira.timer`): chama `rodar()`, grava um instantâneo em
`var/seguranca/ultima_varredura_cve.json` (fonte de fallback de `docs/gerar_correcoes.py` quando o banco não
responde) e persiste via `plat.varredura_cve_registrar()` (SECURITY DEFINER — plat_app só lê as tabelas).

Sem rede (pip-audit precisa do OSV.dev; npm precisa do registry.npmjs.org): a fonte que falhou entra no resumo
como "sem rede" e o rc da execução fica != 0 — nunca "0 CVE" fingido, e a fonte que falhou NÃO fecha
(resolve) os achados abertos dela (só quem rodou com sucesso pode dizer que um achado sumiu porque foi
corrigido). O job (`app/jobs/seguranca.py`) reaproveita exatamente `rodar()` e `persistir()` daqui — a
diferença é só de onde vem o cursor (`ctx.db()` do worker vs. uma conexão própria aqui)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
import varredura_dependencias as vd  # noqa: E402 — módulo em scripts/, fora do pacote app
import varredura_seguranca as vs  # noqa: E402

if str(RAIZ) not in sys.path:  # roda como `python scripts/varredura_cve.py`, sem PYTHONPATH=.
    sys.path.insert(0, str(RAIZ))

INSTANTANEO = RAIZ / "var" / "seguranca" / "ultima_varredura_cve.json"


def _parece_rede(e: Exception) -> bool:
    texto = str(e).lower()
    return any(p in texto for p in ("timeout", "não respondeu", "rede", "network", "resolve", "connection"))


# npm audit fala inglês (critical/high/moderate/low/info); plat.vulnerabilidade fala o mesmo vocabulário de
# scripts/varredura_dependencias.py (critica/alta/media/baixa/desconhecida) — CHECK constraint da migração
# 20260915T2252 reprova qualquer outra palavra, então a tradução é obrigatória, não cosmética.
_GRAVIDADE_NPM = {"critical": "critica", "high": "alta", "moderate": "media", "low": "baixa", "info": "baixa"}


def _gravidade_de_npm(severidade_npm: str) -> str:
    return _GRAVIDADE_NPM.get((severidade_npm or "").lower(), "desconhecida")


def rodar() -> dict:
    """Roda pip-audit e (se houver `npm`) npm audit; nunca lança — toda falha vira entrada no resumo e rc != 0.
    Devolve {"rc", "duracao_ms", "resumo", "achados", "fontes_ok"}; `achados` já normalizado para as colunas
    de `plat.vulnerabilidade` (fonte, pacote, versao, id_cve, gravidade, corrigido_em_versao)."""
    inicio = time.perf_counter()
    achados: list[dict] = []
    resumos: list[str] = []
    fontes_ok: list[str] = []
    rc = 0

    try:
        r = vd.avaliar(RAIZ / "requirements.txt", RAIZ / "docs" / "excecoes_cve.json",
                       executavel=str(RAIZ / "venv" / "bin" / "pip-audit"))
        for a in r["achados"]:
            achados.append({
                "fonte": "pip-audit", "pacote": a["pacote"], "versao": a["versao"], "id_cve": a["id"],
                "gravidade": a["severidade"], "corrigido_em_versao": (a["fix_versions"] or [None])[0],
            })
        fontes_ok.append("pip-audit")
        resumos.append(f"pip-audit: {len(r['achados'])} achado(s)")
    except vd.ErroVarredura as e:
        rc = 2
        resumos.append(f"pip-audit: falhou ({'sem rede' if _parece_rede(e) else e})")

    try:
        achados_npm, _versao_npm = vs.rodar_npm(RAIZ)
        for a in achados_npm:
            achados.append({
                "fonte": "npm-audit", "pacote": a.get("pacote") or "?", "versao": a.get("versao") or "?",
                "id_cve": a["id"], "gravidade": _gravidade_de_npm(a["severidade"]), "corrigido_em_versao": None,
            })
        fontes_ok.append("npm-audit")
        resumos.append(f"npm-audit: {len(achados_npm)} achado(s)")
    except vs.ErroVarredura as e:
        motivo = "sem rede" if _parece_rede(e) else str(e)
        resumos.append(f"npm-audit: indisponível ({motivo})")
        if _parece_rede(e):
            rc = 2  # ausência de `npm`/VERSOES.txt não é falha de varredura; rede fora, sim

    duracao_ms = int((time.perf_counter() - inicio) * 1000)
    return {"rc": rc, "duracao_ms": duracao_ms, "resumo": "; ".join(resumos) or "nenhuma fonte tentada",
            "achados": achados, "fontes_ok": fontes_ok}


def persistir(cur, resultado: dict) -> int:
    """Chama `plat.varredura_cve_registrar` com o resultado de `rodar()`. `cur` é qualquer cursor estilo
    dict (RealDictCursor/CursorSchemaAmbiente do app, ou o de `ctx.db()` do job) — mesma chamada nos dois
    caminhos, só muda de onde vem a conexão."""
    cur.execute(
        "SELECT plat.varredura_cve_registrar(%s, %s, %s, %s::jsonb, %s) AS id",
        (resultado["rc"], resultado["duracao_ms"], resultado["resumo"],
         json.dumps(resultado["achados"], ensure_ascii=False), resultado["fontes_ok"]),
    )
    return cur.fetchone()["id"]


def gravar_instantaneo(resultado: dict, caminho: Path = INSTANTANEO) -> None:
    """Fallback lido por `docs/gerar_correcoes.py` quando o banco não responde — só os achados ABERTOS desta
    execução (o histórico de resolvida_em, esse só o banco tem: o instantâneo não substitui o log)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps({
        "quando": _agora_iso(), "rc": resultado["rc"], "resumo": resultado["resumo"],
        "achados": resultado["achados"],
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def _agora_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dsn() -> str:
    """Mesma receita de `docs/gerar_privilegios.py`: `.env`, depois `LoadCredential=` do systemd
    (`$CREDENTIALS_DIRECTORY`, item L7-19 — é assim que `deploy/plat-varredura-cve.service` entrega o
    segredo sem `.env` na máquina), depois o ambiente do processo por cima."""
    from dotenv import dotenv_values

    valores = dict(dotenv_values(RAIZ / ".env"))
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if cred_dir and (Path(cred_dir) / "PLAT_DSN").is_file():
        valores["PLAT_DSN"] = (Path(cred_dir) / "PLAT_DSN").read_text(encoding="utf-8").strip()
    valores.update({k: v for k, v in os.environ.items() if k.startswith("PLAT_")})
    dsn = valores.get("PLAT_DSN")
    if not dsn:
        print("sem PLAT_DSN (.env, LoadCredential= ou ambiente) — rode sudo bash install.sh primeiro",
              file=sys.stderr)
        raise SystemExit(2)
    return dsn


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sem-banco", action="store_true",
                   help="só roda a varredura e grava o instantâneo JSON; não conecta no banco (uso em teste)")
    args = p.parse_args(argv)

    resultado = rodar()
    gravar_instantaneo(resultado)
    print(f"varredura_cve: {resultado['resumo']} (rc={resultado['rc']}, {resultado['duracao_ms']} ms)")

    if not args.sem_banco:
        import psycopg2

        from app.schema_ambiente import CursorSchemaAmbiente

        con = psycopg2.connect(_dsn(), cursor_factory=CursorSchemaAmbiente)
        try:
            with con.cursor() as cur:
                varredura_id = persistir(cur, resultado)
            con.commit()
            print(f"varredura_cve: gravado como plat.varredura_cve id={varredura_id}")
        finally:
            con.close()

    return resultado["rc"]


if __name__ == "__main__":
    raise SystemExit(main())
