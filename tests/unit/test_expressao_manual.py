"""O portão do item L5-11 pede "documentação da linguagem em MANUAL.md com um exemplo por função".
A seção 25 do manual é GERADA de `TABELA_FUNCOES` e de `PERFIS` por `docs/gerar_manual_expressao.py`
(mesmo padrão de `docs/gerar_limites.py` para `docs/LIMITES.md`): aqui se confere que o arquivo no
disco é o que o gerador produz hoje, que toda função tem uma linha com exemplo e que nenhum exemplo
ficou vazio."""

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from app.expressao.avaliador_py import TABELA_FUNCOES  # noqa: E402
from app.expressao.perfis import PERFIS  # noqa: E402

MANUAL = RAIZ / "MANUAL.md"
GERADOR = RAIZ / "docs" / "gerar_manual_expressao.py"
LINHA_FUNCAO = re.compile(r"^\| `([A-Za-z]+)` \| ([^|]+) \| ([^|]+) \| `([^|]+)` \|$", re.MULTILINE)


def _secao_gerada() -> str:
    texto = MANUAL.read_text(encoding="utf-8")
    inicio = texto.index("<!-- inicio: catalogo de expressao gerado")
    fim = texto.index("<!-- fim: catalogo de expressao gerado")
    return texto[inicio:fim]


def test_manual_esta_sincronizado_com_o_codigo():
    r = subprocess.run(
        [sys.executable, str(GERADOR), "--check"], cwd=RAIZ, capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr


def test_manual_tem_uma_linha_e_um_exemplo_para_cada_funcao():
    linhas = LINHA_FUNCAO.findall(_secao_gerada())
    nomes = [nome for nome, _aridade, _descricao, _exemplo in linhas]
    assert len(nomes) == len(set(nomes)), "função repetida no manual"
    assert set(nomes) == set(TABELA_FUNCOES)
    for nome, aridade, descricao, exemplo in linhas:
        assert aridade.strip(), nome
        assert descricao.strip(), nome
        assert nome in exemplo, f"o exemplo de {nome} não usa a própria função: {exemplo}"


def test_portao_ao_menos_quarenta_funcoes_no_manual():
    assert len({n for n, _a, _d, _e in LINHA_FUNCAO.findall(_secao_gerada())}) >= 40


def test_manual_documenta_os_sete_perfis():
    secao = _secao_gerada()
    for nome, perfil in PERFIS.items():
        assert f"| `{nome}` |" in secao, nome
        assert perfil["descricao"] in secao, nome
        assert f"{perfil['limite_ms']} ms" in secao, nome


def test_secao_do_manual_explica_o_que_a_expressao_nao_alcanca():
    """Ressalva na mesma seção, nunca em rodapé: modelo esférico e ausência de rede/outro inquilino."""
    texto = MANUAL.read_text(encoding="utf-8")
    corpo = texto[texto.index("## 25. Linguagem de expressão no navegador") :]
    for frase in ("campo_nao_permitido", "outro inquilino", "esfera", "não para medição legal", "tempo_excedido"):
        assert frase.casefold() in corpo.casefold(), frase
