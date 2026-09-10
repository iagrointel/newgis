"""Lighthouse (pacote npm, item L2-07-a-pwa-instalavel-cache): a categoria `pwa` foi removida do Lighthouse
a partir da v12 (o binário não aceita mais `--only-categories=pwa`); por isso `tools/package.json` fixa
`lighthouse@^11.7.1`, a última major que ainda tem os audits `installable-manifest`/`maskable-icon`/etc.
`node_modules/` fica fora do git (`.gitignore`); esta função instala sob demanda (só uma vez, ~170 MB) e
reusa o Chromium que o playwright já baixou (`~/.cache/ms-playwright`), sem baixar um Chrome próprio."""

import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TOOLS = RAIZ / "tools"
LIGHTHOUSE_BIN = TOOLS / "node_modules" / ".bin" / "lighthouse"


class LighthouseIndisponivel(RuntimeError):
    pass


def _chrome_do_playwright() -> str:
    candidatos = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    if not candidatos:
        raise LighthouseIndisponivel("nenhum chromium do playwright em ~/.cache/ms-playwright")
    return str(candidatos[-1])


def _instalar_se_preciso() -> None:
    if LIGHTHOUSE_BIN.is_file():
        return
    r = subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund"], cwd=TOOLS, timeout=180, capture_output=True, text=True
    )
    if r.returncode != 0 or not LIGHTHOUSE_BIN.is_file():
        raise LighthouseIndisponivel(f"npm install falhou: {r.returncode}\n{r.stdout}\n{r.stderr}")


def auditoria_pwa(url: str, saida_json: Path) -> dict:
    """Roda `lighthouse --only-categories=pwa` contra `url`, grava o JSON bruto em `saida_json` e devolve o
    dict carregado. Levanta `LighthouseIndisponivel` (o chamador decide entre pular ou marcar `não medida`,
    NUNCA afrouxar a cláusula) se o binário não existir e o `npm install` sob demanda falhar."""
    _instalar_se_preciso()
    chrome = _chrome_do_playwright()
    r = subprocess.run(
        [
            str(LIGHTHOUSE_BIN), url,
            "--only-categories=pwa",
            "--output=json",
            f"--output-path={saida_json}",
            "--chrome-flags=--headless=new --no-sandbox --ignore-certificate-errors",
            "--quiet",
        ],
        env={"PATH": "/usr/bin:/bin", "CHROME_PATH": chrome, "HOME": str(Path.home())},
        timeout=120,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not saida_json.is_file():
        raise LighthouseIndisponivel(f"lighthouse saiu com {r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return json.loads(saida_json.read_text(encoding="utf-8"))


def itens_vermelhos(relatorio: dict) -> list[tuple[str, float | None, str]]:
    """[(id, score, modo)] dos audits da categoria pwa cujo `score` é 0 — os `scoreDisplayMode: manual`
    (ex.: `pwa-cross-browser`) não têm score numérico e não contam como vermelho."""
    cat = relatorio["categories"]["pwa"]
    vermelhos = []
    for ref in cat["auditRefs"]:
        a = relatorio["audits"][ref["id"]]
        modo = a.get("scoreDisplayMode")
        if modo in ("manual", "notApplicable", "informative"):
            continue
        if a.get("score") == 0:
            vermelhos.append((ref["id"], a.get("score"), modo))
    return vermelhos
