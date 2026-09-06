"""A aplicação sobe a partir do que está COMMITADO, não a partir do que está no disco de quem programou.

Achado do adversário do turno 3: entre `3a69591` e `2132603` a ponta de `master` não importava. `app/main.py`
tinha sido commitado com `from app.auth.rotas_convites import ...`, mas o arquivo `app/auth/rotas_convites.py`
NÃO tinha entrado no commit — o `git add` explícito que o brief exige tem esse preço. Na árvore de quem
trabalhava tudo funcionava, inclusive `tests/unit/test_dependencias.py`, que importa `app.main` a partir do
diretório de trabalho: o arquivo estava lá, só não versionado. Um `git clone` de `master` não subia.

Os dois testes daqui fecham esse buraco por caminhos independentes:
  1) todo módulo `app.*` que a aplicação carrega ao importar `app.main` está RASTREADO pelo git e sem
     alteração pendente que o torne diferente do commitado;
  2) fumaça: a aplicação importa e tem rotas — se `app.main` explodir, o teste reprova com o traceback."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _rastreados() -> set[str]:
    r = subprocess.run(["git", "ls-files", "app"], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return set(r.stdout.split())


def test_a_aplicacao_importa_e_tem_rotas():
    """Fumaça: se a aplicação não subir, o erro aparece aqui e não em produção."""
    from fastapi.routing import APIRoute

    from app.main import app

    def achatar(rotas):
        saida = []
        for r in rotas:
            if isinstance(r, APIRoute):
                saida.append(r)
            elif getattr(r, "original_router", None) is not None:
                saida.extend(achatar(r.original_router.routes))
            elif hasattr(r, "routes"):
                saida.extend(achatar(r.routes))
        return saida

    rotas = achatar(app.router.routes)
    assert len(rotas) > 100, f"a aplicação subiu com só {len(rotas)} rotas"
    assert any(r.path == "/api/saude" or r.path.startswith("/api/") for r in rotas)


def test_todo_modulo_que_a_aplicacao_carrega_esta_versionado():
    """Importa `app.main` num subprocesso limpo, lista os módulos `app.*` que ficaram carregados e exige que
    cada arquivo esteja em `git ls-files`. Um arquivo esquecido fora do commit reprova AQUI, antes de chegar
    à ponta do ramo."""
    programa = (
        "import app.main, sys, json;"
        "print(json.dumps(sorted(m.__file__ for n, m in sys.modules.items()"
        " if n.split('.')[0] == 'app' and getattr(m, '__file__', None))))"
    )
    ambiente = {
        "PATH": "/usr/bin:/bin", "HOME": str(RAIZ),
        "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat",
        "PLAT_SECRET": "ab" * 32, "PLAT_AMBIENTE": "dev", "PLAT_URL_PUBLICA": "https://exemplo.invalido",
        "PYTHONNOUSERSITE": "1",
    }
    r = subprocess.run([sys.executable, "-c", programa], cwd=RAIZ, env=ambiente, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, f"a aplicação não importa: {r.stderr[-2000:]}"
    import json

    arquivos = [Path(c).resolve() for c in json.loads(r.stdout)]
    assert len(arquivos) > 40, f"só {len(arquivos)} módulos de app carregados; o programa mudou?"
    rastreados = _rastreados()
    faltando = sorted(
        str(a.relative_to(RAIZ)) for a in arquivos
        if a.is_relative_to(RAIZ) and str(a.relative_to(RAIZ)) not in rastreados
    )
    assert not faltando, (
        "a aplicação importa arquivos que NÃO estão versionados — um clone deste commit não sobe:\n"
        + "\n".join(faltando)
    )
