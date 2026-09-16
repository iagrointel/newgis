"""web/vendor: uma cópia por versão, versão no nome do arquivo, sha256 e licença em VERSOES.txt
(ADR 0001 seção 11.2 regra 3). Regra 3 estendida no item L0-14-identidade-visual (06/09/2026) para
admitir fontes .woff2: versão Major.Minor (fontes não seguem semver de 3 dígitos como as libs JS) e
licença OFL-1.1 (SIL Open Font License, padrão de toda fonte aberta do Google Fonts — ver VERSOES.txt).
Estendida de novo no item L2-02-e-simbolos-sprites-glifos (07/09/2026) para admitir .ttf (fontes de
glifo de mapa, servidas ao Martin — diferentes das .woff2 acima, que são tipografia da INTERFACE).
Estendida uma terceira vez na junção do wt/cx202c (item L2-02-b, 09/09/2026) para admitir o texto
de licença <nome>-<versão>.LICENSE.txt: o portão do L2-02-c exige a licença Apache-Style da
ColorBrewer EM ARQUIVO ao lado das rampas, e o arquivo é o package/LICENSE.txt do próprio pacote —
mesma versão no nome, mesmo sha256 em VERSOES.txt, mesma disciplina de uma cópia por versão.
Estendida uma quarta vez (item L2-01-h/L2-01-k, terra-draw): declarado em VERSOES.txt pelo caminho
relativo a web/vendor/ — inclui subpasta —, com `rglob` percorrendo a árvore inteira em vez de só os
filhos diretos. Uma quinta vez (UX-04, terra-draw): sufixo de EMPACOTAMENTO `.umd`/`.min` antes da
extensão (a lib publica só o build UMD com esse nome na cauda; pode vir mais de um, ex. `.umd.min.js`).
Uma sexta vez (item L2-09-c, three.js/deck.gl, 08/09/2026): (a) three.js é ESM em dois arquivos que se
referenciam por caminho relativo, então mora numa PASTA `<nome>-<versão>/` e é o NOME DA PASTA que seguem
a convenção — o arquivo dentro pode ter qualquer nome, inclusive `LICENSE` sem versão nem extensão; (b)
deck.gl publica a licença como `LICENSE` sem `.txt` — aceito como `.LICENSE` também, sem o `.txt` final.

xeokit-sdk-2.6.113.js é AGPL-3.0-only, fora da lista de licenças admitidas — DE PROPÓSITO: é o gate do
D-pendente sobre o módulo de modelo 3D (ver VERSOES.txt). Este arquivo de teste REPROVA aquela linha
sozinha; não editar `LICENCAS` nem este teste para calar o aviso (a nota em VERSOES.txt é explícita
sobre isso)."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "web" / "vendor"
LICENCAS = {"BSD-3-Clause", "MIT", "Apache-2.0", "ISC", "OFL-1.1"}
# sufixo de empacotamento (.umd/.min, um ou mais, ex. "chart-4.5.1.umd.min.js") antes da extensão real
_SUFIXO_EMPACOTAMENTO = r"(?:\.(?:umd|min))*"
NOME = re.compile(
    r"^(?P<nome>[a-z][a-z0-9.-]*)-(?P<versao>\d+\.\d+(?:\.\d+)?)"
    rf"(?:{_SUFIXO_EMPACOTAMENTO}\.(?:js|css|woff2|ttf)|\.LICENSE(?:\.(?:txt|md))?)$"
)
# three-0.185.1/qualquer-nome: só a PASTA segue <nome>-<versão> (ver docstring, item L2-09-c)
PASTA_VERSIONADA = re.compile(r"^(?P<nome>[a-z][a-z0-9.-]*)-(?P<versao>\d+\.\d+(?:\.\d+)?)$")


def _linhas():
    for linha in (VENDOR / "VERSOES.txt").read_text(encoding="utf-8").splitlines():
        if linha and not linha.startswith("#"):
            yield linha.split(maxsplit=4)


def test_todo_arquivo_do_vendor_esta_em_versoes_com_sha_e_licenca():
    declarados = {}
    for caminho, versao, sha, licenca, origem in _linhas():
        partes = caminho.split("/")
        if len(partes) == 2:
            pasta, _folha = partes
            m = PASTA_VERSIONADA.match(pasta)
            assert m and m["versao"] == versao, (
                f"pasta fora da convenção <nome>-<versão>/<arquivo>: {caminho}"
            )
        else:
            m = NOME.match(caminho)
            assert m and m["versao"] == versao, f"nome fora da convenção <nome>-<versão>.<ext|LICENSE[.txt]>: {caminho}"
        assert licenca in LICENCAS, (caminho, licenca)
        assert origem.startswith("https://"), (caminho, origem)
        declarados[caminho] = sha
    arquivos = {str(p.relative_to(VENDOR)) for p in VENDOR.rglob("*") if p.is_file() and p.name != "VERSOES.txt"}
    assert arquivos == set(declarados), arquivos ^ set(declarados)
    for caminho, sha in declarados.items():
        assert hashlib.sha256((VENDOR / caminho).read_bytes()).hexdigest() == sha, caminho


def test_swagger_referenciado_pela_api_existe_no_vendor():
    from app import main

    for rota in (main.SWAGGER_JS, main.SWAGGER_CSS):
        assert rota.startswith("/static/vendor/")
        assert (VENDOR / rota.removeprefix("/static/vendor/")).is_file(), rota
    assert (ROOT / "web" / main.FAVICON.removeprefix("/static/")).is_file()
