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
