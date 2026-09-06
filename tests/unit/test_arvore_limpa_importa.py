"""Teste de fumaça: uma CÓPIA LIMPA do ramo (só o que está versionado) sobe a aplicação.

Dois adversários diferentes esbarraram nisto em turnos seguidos: em 06/09 o commit `master` 90ab545 não
importava, porque `app/main.py` referenciava seis módulos que nunca tinham sido comitados (app/auth/
rotas_convites.py, rotas_redefinicao.py, modelos_convite.py, modelos_redefinicao.py, app/correio/, app/uploads/,
app/migracoes.py). Toda medida daquele dia valia para a árvore de trabalho, não para o repositório. A janela se
fechou sozinha quando os arquivos foram comitados — e não ficou nada que impedisse a próxima.

É isto que este teste fecha, e só isto: `git archive` do HEAD para um diretório temporário (que por construção
só contém arquivo versionado) e `python -c "from app.main import app"` lá dentro, em subprocesso próprio. Se
faltar um módulo, se um import circular aparecer, se um arquivo de dados que a partida lê não estiver
versionado, o subprocesso morre e o teste reprova nomeando o erro.

Não toca banco: `app.settings` exige PLAT_SECRET/PLAT_DSN, então o subprocesso recebe valores SINTÉTICOS pelo
ambiente (DSN que nunca é aberto — importar o app não conecta) e nunca lê o .env real.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
TEMPO_MAX_S = 180


def _git(*args, cwd=RAIZ) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="module")
def copia_limpa():
    """Só o que `git archive HEAD` entrega: nenhum arquivo não versionado, nenhum .pyc, nenhum var/."""
    destino = Path(tempfile.mkdtemp(prefix="plat-arvore-limpa-"))
    try:
        tar = subprocess.run(["git", "archive", "HEAD"], cwd=RAIZ, capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(destino)], input=tar, check=True)
        yield destino
    finally:
        shutil.rmtree(destino, ignore_errors=True)


def _ambiente_sintetico() -> dict[str, str]:
    """Nunca herda o .env real: só o mínimo que app/settings.py exige, com valores inertes."""
    base = {k: v for k, v in os.environ.items() if not k.startswith("PLAT_")}
    base.update(
        {
            "PATH": os.environ.get("PATH", ""),
            "PLAT_AMBIENTE": "dev",
            "PLAT_SECRET": "0" * 64,
            "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:1/base_que_nao_existe",
            "PLAT_URL_PUBLICA": "https://arvore-limpa.invalido",
            "PYTHONPATH": "",
        }
    )
    return base


def test_copia_limpa_do_ramo_importa_a_aplicacao(copia_limpa):
    r = subprocess.run(
        [sys.executable, "-c", "from app.main import app; print(len(app.routes))"],
        cwd=copia_limpa, env=_ambiente_sintetico(), capture_output=True, text=True, timeout=TEMPO_MAX_S,
    )
    assert r.returncode == 0, (
        "uma cópia limpa do ramo não importa a aplicação — falta arquivo no git ou a partida depende de algo "
        f"que não está versionado.\nstdout: {r.stdout}\nstderr: {r.stderr[-4000:]}"
    )
    assert r.stdout.strip().isdigit(), r.stdout


def test_copia_limpa_monta_o_contrato_openapi(copia_limpa):
    """Importar não basta: o OpenAPI é montado por FastAPI a partir de todos os modelos, e é onde aparecem
    colisões de nome de modelo e referência a esquema inexistente (o defeito que o commit 2fe849d consertou)."""
    r = subprocess.run(
        [sys.executable, "-c", "from app.main import app; d=app.openapi(); print(len(d['paths']))"],
        cwd=copia_limpa, env=_ambiente_sintetico(), capture_output=True, text=True, timeout=TEMPO_MAX_S,
    )
    assert r.returncode == 0, f"cópia limpa não monta o OpenAPI.\nstdout: {r.stdout}\nstderr: {r.stderr[-4000:]}"
    assert int(r.stdout.strip()) > 120, f"OpenAPI da cópia limpa com poucas rotas: {r.stdout!r}"


def test_nenhum_modulo_da_aplicacao_esta_fora_do_git():
    """O mesmo defeito visto do outro lado, e barato: todo módulo `app.*` carregado neste processo está no git.
    Pega o arquivo novo que ainda não foi `git add`ado ANTES de ele virar um commit que não importa."""
    versionados = set(_git("ls-files").splitlines())
    import app.main  # noqa: F401 — o import é o que popula sys.modules

    faltando = sorted(
        str(Path(mod.__file__).relative_to(RAIZ))
        for nome, mod in list(sys.modules.items())
        if (nome == "app" or nome.startswith("app."))
        and getattr(mod, "__file__", None)
        and str(Path(mod.__file__)).startswith(str(RAIZ))
        and str(Path(mod.__file__).relative_to(RAIZ)) not in versionados
    )
    assert faltando == [], "módulos importados pela aplicação que não estão no git"
