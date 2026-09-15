"""Gera `docs/CORRECOES.md` — o "log de correções" que a spec (seções 8 e 17.4) promete: CVE, pacote,
versão, gravidade, quando foi detectado, quando foi corrigido (item L7-03-f-dependencias-cve-log-correcoes).
NÃO editar à mão: o conteúdo vem de `plat.vulnerabilidade` (uma linha por achado; `resolvida_em` preenchido
quando o pacote/CVE some de uma varredura para a próxima — ver `db/migracoes/20260915T2252_vulnerabilidade.sql`
e `scripts/varredura_cve.py`), nunca de texto digitado.

Fonte primária: o BANCO (papel `plat_app`, mesma receita de conexão de `docs/gerar_privilegios.py` — `.env`,
depois `LoadCredential=` do systemd, depois o ambiente). Quando o banco não responde (máquina sem `.env`
configurado, ou Postgres fora do ar no instante da geração), cai para o ÚLTIMO instantâneo gravado por
`scripts/varredura_cve.py` em `var/seguranca/ultima_varredura_cve.json` — esse arquivo só tem os achados
ABERTOS da última execução (nenhum histórico de correção), então o documento sai mais pobre nesse caminho e
diz isso no cabeçalho; não é um segundo caminho de "verdade", é só o que sobra sem banco.

`python3 docs/gerar_correcoes.py` escreve o arquivo; `--check` só confere e sai != 0 se estiver desatualizado
(mesmo padrão de `docs/gerar_limites.py`/`docs/gerar_privilegios.py`)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:  # roda como `python docs/gerar_correcoes.py`, sem PYTHONPATH=.
    sys.path.insert(0, str(RAIZ))

DESTINO = RAIZ / "docs" / "CORRECOES.md"
INSTANTANEO = RAIZ / "var" / "seguranca" / "ultima_varredura_cve.json"
GRAVIDADE_ROTULO = {"critica": "crítica", "alta": "alta", "media": "média", "baixa": "baixa",
                    "desconhecida": "desconhecida"}


def _dsn() -> str | None:
    from dotenv import dotenv_values

    valores = dict(dotenv_values(RAIZ / ".env"))
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if cred_dir and (Path(cred_dir) / "PLAT_DSN").is_file():
        valores["PLAT_DSN"] = (Path(cred_dir) / "PLAT_DSN").read_text(encoding="utf-8").strip()
    valores.update({k: v for k, v in os.environ.items() if k.startswith("PLAT_")})
    return valores.get("PLAT_DSN")


def _ler_banco() -> tuple[list[dict], dict] | None:
    """[{fonte, pacote, versao, id_cve, gravidade, corrigido_em_versao, detectada_em, resolvida_em}], {última
    varredura: quando/rc/resumo} — ou None se o banco não respondeu (rede fora, `.env` ausente etc.)."""
    dsn = _dsn()
    if not dsn:
        return None
    try:
        import psycopg2

        from app.schema_ambiente import CursorSchemaAmbiente
    except ImportError:
        return None
    try:
        con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente, connect_timeout=5)
    except Exception:  # noqa: BLE001 — qualquer falha de conexão cai no fallback, nunca reprova a geração
        return None
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT fonte, pacote, versao, id_cve, gravidade, corrigido_em_versao, detectada_em, resolvida_em "
                "FROM plat.vulnerabilidade ORDER BY resolvida_em IS NOT NULL, detectada_em DESC"
            )
            linhas = list(cur.fetchall())
            cur.execute("SELECT quando, rc, resumo, fonte FROM plat.varredura_cve ORDER BY quando DESC LIMIT 1")
            ultima = cur.fetchone()
    finally:
        con.close()
    return linhas, (dict(ultima) if ultima else {})


def _ler_instantaneo() -> tuple[list[dict], dict] | None:
    if not INSTANTANEO.exists():
        return None
    dados = json.loads(INSTANTANEO.read_text(encoding="utf-8"))
    linhas = [
        {**a, "detectada_em": dados.get("quando"), "resolvida_em": None}
        for a in dados.get("achados", [])
    ]
    ultima = {"quando": dados.get("quando"), "rc": dados.get("rc"), "resumo": dados.get("resumo"), "fonte": None}
    return linhas, ultima


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, str):
        return v[:19].replace("T", " ")  # ISO -> "AAAA-MM-DD HH:MM:SS", sem fuso repetido
    return v.astimezone().strftime("%Y-%m-%d %H:%M") if hasattr(v, "astimezone") else str(v)


def gerar_markdown() -> str:
    do_banco = _ler_banco()
    fonte_dados = "banco (plat.vulnerabilidade)"
    if do_banco is not None:
        linhas, ultima = do_banco
    else:
        do_json = _ler_instantaneo()
        try:
            caminho_mostrado = INSTANTANEO.relative_to(RAIZ)
        except ValueError:  # instantâneo fora de RAIZ (ex.: teste com tmp_path) — mostra o caminho absoluto
            caminho_mostrado = INSTANTANEO
        fonte_dados = f"último instantâneo ({caminho_mostrado}) — banco indisponível na geração"
        linhas, ultima = do_json if do_json is not None else ([], {})

    partes = [
        "# Log de correções — CVE conhecido\n",
        "Gerado por `docs/gerar_correcoes.py` (`make correcoes`) a partir de `plat.vulnerabilidade` — "
        "item L7-03-f-dependencias-cve-log-correcoes; não editar à mão. Uma linha por achado de "
        "`scripts/varredura_cve.py` (pip-audit em `requirements.txt`, npm audit em "
        "`web/vendor/VERSOES.txt`); `resolvida` fica vazio enquanto o achado segue aberto e ganha data no "
        "instante em que ele some de uma varredura para a próxima (nunca apagado — histórico completo).\n",
        f"Fonte desta geração: {fonte_dados}.\n",
    ]
    if ultima.get("quando"):
        estado = "ok" if (ultima.get("rc") in (0, None)) else "falhou"
        partes.append(
            f"Última varredura: {_fmt(ultima['quando'])} — **{estado}** — {ultima.get('resumo') or '—'}\n"
        )
    else:
        partes.append("Última varredura: nenhuma registrada ainda.\n")

    abertas = sum(1 for r in linhas if not r.get("resolvida_em"))
    partes.append(f"**{len(linhas)} achado(s)** no log · **{abertas} aberto(s)** agora.\n")
    partes.append("| aviso | pacote | versão | gravidade | detectada | resolvida |")
    partes.append("|---|---|---|---|---|---|")
    if not linhas:
        partes.append("| _(vazio — nenhum achado registrado ainda)_ | | | | | |")
    for r in linhas:
        partes.append(
            f"| `{r['id_cve']}` | `{r['pacote']}` | `{r['versao']}` | "
            f"{GRAVIDADE_ROTULO.get(r['gravidade'], r['gravidade'])} | {_fmt(r['detectada_em'])} | "
            f"{_fmt(r['resolvida_em'])} |"
        )
    return "\n".join(partes) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                     help="não escreve; sai != 0 se CORRECOES.md estiver desatualizado")
    args = ap.parse_args()
    novo = gerar_markdown()
    if args.check:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != novo:
            print("docs/CORRECOES.md desatualizado; rode: make correcoes", file=sys.stderr)
            raise SystemExit(1)
        return
    DESTINO.write_text(novo, encoding="utf-8")
    print(f"escrito: {DESTINO}")


if __name__ == "__main__":
    main()
