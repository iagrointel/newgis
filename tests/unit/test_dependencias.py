"""Cláusula "máquina que nunca viu o repo": a aplicação importa em subprocesso com PYTHONNOUSERSITE=1, isto é,
só com a venv (requirements.txt) e os pacotes dpkg do sistema, nunca com o ~/.local de quem instalou."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV = ROOT / "venv"
# configuração mínima válida via ambiente: o teste não depende de .env nem de banco (app.db cria o pool só no uso)
AMBIENTE_MINIMO = {
    "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat",
    "PLAT_SECRET": "ab" * 32,
    "PLAT_AMBIENTE": "dev",
    "PLAT_URL_PUBLICA": "https://exemplo.invalido",
}
PROGRAMA = (
    "import app.main, fastapi, starlette, pydantic, dotenv, uvicorn, psycopg2;"
    "print(fastapi.__file__); print(starlette.__file__); print(pydantic.__file__); print(dotenv.__file__)"
)


def _rodar(programa: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PLAT_")}
    env.update(AMBIENTE_MINIMO)
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.run([sys.executable, "-c", programa], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=60)


def test_python_da_suite_e_o_da_venv():
    assert Path(sys.prefix).resolve() == VENV.resolve(), sys.prefix  # sys.executable é symlink para o python do sistema


def test_app_main_importa_sem_site_do_usuario():
    r = _rodar(PROGRAMA)
    assert r.returncode == 0, r.stderr
    caminhos = r.stdout.split()
    assert len(caminhos) == 4
    for caminho in caminhos:
        assert Path(caminho).resolve().is_relative_to(VENV.resolve()), f"{caminho} não vem da venv"
        assert "/.local/" not in caminho


def test_site_do_usuario_esta_fora_do_caminho():
    r = _rodar("import site, sys; print(site.ENABLE_USER_SITE); print('\\n'.join(sys.path))")
    assert r.returncode == 0, r.stderr
    linhas = r.stdout.splitlines()
    assert linhas[0] == "False"
    assert not any("/.local/" in linha for linha in linhas[1:]), linhas


def test_requirements_fixa_o_que_a_aplicacao_importa():
    texto = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    fixadas = {linha.split("==")[0].lower().replace("_", "-") for linha in texto.splitlines() if "==" in linha}
    assert {"fastapi", "starlette", "pydantic", "python-dotenv", "httpx", "pytest", "playwright", "ruff"} <= fixadas
    for linha in texto.splitlines():
        if linha and not linha.startswith("#"):
            assert "==" in linha, f"dependência sem versão fixada: {linha}"


# ---- item L4-01-g: pyogrio é dependência declarada, e o import dela é tardio ----
# `app/rede_utilidades/bdgd.py` e `app/rede_utilidades/tarefas.py` leem FileGDB com pyogrio (GDAL/OGR).
# Importar no topo prendia `import app.main` — via app/jobs/tipos.py — a um pacote que, nesta máquina,
# só existia no site do usuário. Os dois testes abaixo travam as duas metades do conserto.

PROGRAMA_SEM_PYOGRIO = """
import sys


class _Bloqueia:
    def find_spec(self, nome, path=None, target=None):
        if nome == "pyogrio" or nome.startswith("pyogrio."):
            raise ImportError("pyogrio ausente de proposito")
        return None


sys.meta_path.insert(0, _Bloqueia())
import app.main  # noqa: E402
print("ok")
print("pyogrio" not in sys.modules)
"""


def test_app_main_importa_com_pyogrio_ausente():
    """Refutação do item: tirar o pyogrio da máquina não pode quebrar a importação da aplicação.
    A API não abre FileGDB; quem abre é o job `rede.importar_bdgd`, no worker."""
    r = _rodar(PROGRAMA_SEM_PYOGRIO)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["ok", "True"], r.stdout


def test_pyogrio_vem_da_venv_quando_o_job_pede():
    """A outra metade: o pacote é dependência declarada em requirements.txt e está NA venv, para que
    o job que lê o pacote da ANEEL funcione sem o site do usuário."""
    r = _rodar("from app.rede_utilidades import bdgd; print(bdgd._pyogrio().__file__)")
    assert r.returncode == 0, r.stderr
    caminho = Path(r.stdout.strip())
    assert caminho.resolve().is_relative_to(VENV.resolve()), caminho
    texto = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert any(linha.startswith("pyogrio==") for linha in texto.splitlines()), "pyogrio sem versão fixada"
