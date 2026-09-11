"""Todo arquivo de JavaScript do front tem de ser sintaticamente válido.

Por que este teste existe: em 11/09/2026 a fusão de ramos deixou DUAS CHAVES ÓRFÃS no fim de uma
função em `web/js/mapa/atributos.js`. O arquivo continuou lá, com todas as suas exportações, e nada
no lado do servidor acusou nada — mas o navegador recusava o módulo inteiro com
`SyntaxError: Unexpected token '}'`, e isso derruba a CADEIA DE IMPORTAÇÃO INTEIRA da casca SIG:
sem mapa, sem painel de camadas, sem clique. O dono viu uma tela morta.

Nenhuma varredura anterior pegava isso: `ruff` não lê JavaScript, o `grep` por marcador de conflito
não acha (não havia marcador), e o grafo de módulos respondia 200 em tudo, porque o arquivo EXISTE —
ele só não compila. A prova barata é `node --check`, que custa milissegundos por arquivo.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
NODE = shutil.which("node")


def arquivos_js() -> list[Path]:
    # `vendor/` é código de terceiro, com build próprio: não é nosso para consertar
    return sorted(p for p in WEB.rglob("*.js") if "vendor" not in p.parts)


@pytest.mark.skipif(NODE is None, reason="node não está nesta máquina")
@pytest.mark.parametrize("caminho", arquivos_js(), ids=lambda p: str(p.relative_to(WEB)))
def test_modulo_js_compila(caminho: Path):
    r = subprocess.run(
        [NODE, "--input-type=module", "--check"],
        input=caminho.read_bytes(), capture_output=True, timeout=30,
    )
    assert r.returncode == 0, (
        f"{caminho.relative_to(WEB)} não compila como módulo ES:\n"
        + r.stderr.decode("utf-8", "replace")[:800]
    )
