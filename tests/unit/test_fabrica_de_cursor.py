"""Trava de classe: toda conexão psycopg2 do produto nasce com `cursor_factory=CursorSchemaAmbiente`.

Sem a fábrica, o nome do schema não é reescrito e o módulo escreve no `plat` de PRODUÇÃO mesmo rodando
dentro de uma trilha isolada — o módulo inteiro ignora PLAT_SCHEMA, por mais correto que o reescritor
esteja. Achado F9 do adversário do reescritor de schema (laco/handoffs/T4/ADVERSARIO-reescritor-schema.md),
confirmado no mesmo dia pelo agente do item de multi-servidor sem conhecer o laudo.

Dois portões aqui:
  1. cinco testes de caminho: cada um dos módulos que tinham o defeito abre a conexão pela fábrica;
  2. a varredura da árvore de sintaxe, que reprova qualquer módulo NOVO com o mesmo defeito.

A varredura é a parte que conserta a classe, não o caso. A lista de exceções abaixo é declarada e
justificada uma a uma: exceção sem motivo escrito é reprovação.
"""

import ast
import importlib.util
import sys
from pathlib import Path

from app.schema_ambiente import CursorSchemaAmbiente

RAIZ = Path(__file__).resolve().parents[2]
DIRS = ("app", "scripts", "docs", "db")
FABRICA = "CursorSchemaAmbiente"

# Exceção = arquivo:função onde a conexão NÃO precisa da fábrica, com o motivo. Só entra aqui quem não
# manda SQL com nome de objeto do schema da plataforma. Acrescentar linha sem motivo é reprovar a trava.
EXCECOES_DECLARADAS: dict[str, str] = {
    "scripts/amc_hash_independente.py:conferir_banco":
        "recomputação INDEPENDENTE do hash do modelo multicritério (item L3-01-a): o script existe para "
        "conferir, de fora, o que a aplicação gravou. Usar a fábrica da casa faria a conferência passar pelo "
        "mesmo código que ela deveria vigiar. O schema entra por argumento de linha de comando, escrito por "
        "quem roda, e não por reescrita.",
    "scripts/acervo_publicar.py:publicar":
        "publicador do acervo (item L6-04): roda como `postgres`, faz DDL (CREATE SCHEMA, GRANT) e recebe o "
        "schema de destino em argumento de linha de comando, montando cada nome com psycopg2.sql.Identifier. "
        "Não escreve `plat.` na mão em lugar nenhum, logo não há o que reescrever.",
}


def _modulo(caminho_relativo: str):
    """Carrega um script solto (scripts/, docs/) como módulo, pelo caminho — não são pacotes."""
    caminho = RAIZ / caminho_relativo
    nome = "f9_" + caminho.stem
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


class _ConexaoFalsa:
    """Registra os argumentos de psycopg2.connect sem tocar em banco nenhum."""

    def __init__(self):
        self.kwargs = None

    def __call__(self, *args, **kwargs):
        self.kwargs = kwargs
        return object()


def _espiar(monkeypatch, mod) -> _ConexaoFalsa:
    falsa = _ConexaoFalsa()
    monkeypatch.setattr(mod.psycopg2, "connect", falsa)
    return falsa


def _conferir(falsa: _ConexaoFalsa, onde: str):
    assert falsa.kwargs is not None, f"{onde}: nem chamou psycopg2.connect"
    fabrica = falsa.kwargs.get("cursor_factory")
    assert fabrica is CursorSchemaAmbiente, (
        f"{onde}: cursor_factory={fabrica!r}; sem CursorSchemaAmbiente o módulo ignora PLAT_SCHEMA "
        f"e escreve no `plat` de produção"
    )


def test_eventos_abre_a_conexao_do_listen_com_a_fabrica(monkeypatch):
    from app.jobs import eventos

    falsa = _espiar(monkeypatch, eventos)
    eventos._conectar()
    _conferir(falsa, "app/jobs/eventos.py")


def test_acervo_sync_abre_a_conexao_com_a_fabrica(monkeypatch):
    mod = _modulo("scripts/acervo_sync.py")
    falsa = _espiar(monkeypatch, mod)
    mod._conectar({"dbname": "iagro_sat"})
    _conferir(falsa, "scripts/acervo_sync.py")


def test_acervo_licenca_sync_abre_a_conexao_com_a_fabrica(monkeypatch):
    mod = _modulo("scripts/acervo_licenca_sync.py")
    falsa = _espiar(monkeypatch, mod)
    mod._conectar({"dbname": "iagro_sat"})
    _conferir(falsa, "scripts/acervo_licenca_sync.py")


def test_geocodificador_abre_a_conexao_com_a_fabrica(monkeypatch):
    mod = _modulo("scripts/geocodificador_instalar_uf.py")
    monkeypatch.setattr(mod, "_dsn", lambda: "postgresql://nao/usada")
    falsa = _espiar(monkeypatch, mod)
    mod._conectar()
    _conferir(falsa, "scripts/geocodificador_instalar_uf.py")


def test_gerar_privilegios_abre_a_conexao_com_a_fabrica(monkeypatch):
    mod = _modulo("docs/gerar_privilegios.py")
    monkeypatch.setattr(mod, "_dsn", lambda: "postgresql://nao/usada")
    falsa = _espiar(monkeypatch, mod)
    mod._conectar()
    _conferir(falsa, "docs/gerar_privilegios.py")


def _funcao_que_contem(arvore: ast.AST, linha: int) -> str:
    nome = "<módulo>"
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.lineno <= linha:
            fim = getattr(no, "end_lineno", no.lineno)
            if linha <= fim:
                nome = no.name
    return nome


def conexoes_sem_fabrica() -> list[str]:
    """Varredura da árvore de sintaxe: chamadas a psycopg2.connect sem `cursor_factory=CursorSchemaAmbiente`
    em arquivo que escreve `plat.` na mão. Enumera os caminhos em vez de esperar um agente tropeçar."""
    achados = []
    for d in DIRS:
        for arq in sorted((RAIZ / d).rglob("*.py")):
            fonte = arq.read_text(encoding="utf-8")
            if "psycopg2" not in fonte or "plat." not in fonte:
                continue
            try:
                arvore = ast.parse(fonte)
            except SyntaxError:  # pragma: no cover
                continue
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Call):
                    continue
                alvo = ast.unparse(no.func)
                if not (alvo.endswith("psycopg2.connect") or alvo == "connect"):
                    continue
                fabrica = next((k for k in no.keywords if k.arg == "cursor_factory"), None)
                if fabrica is not None and FABRICA in ast.unparse(fabrica.value):
                    continue
                chave = f"{arq.relative_to(RAIZ)}:{_funcao_que_contem(arvore, no.lineno)}"
                if chave in EXCECOES_DECLARADAS:
                    continue
                achados.append(
                    f"{arq.relative_to(RAIZ)}:{no.lineno} (em {_funcao_que_contem(arvore, no.lineno)}) "
                    f"cursor_factory={ast.unparse(fabrica.value) if fabrica else 'ausente'}"
                )
    return achados


def test_nenhum_modulo_novo_abre_conexao_sem_a_fabrica():
    achados = conexoes_sem_fabrica()
    assert not achados, (
        "conexão psycopg2 sem CursorSchemaAmbiente em módulo que escreve `plat.` na mão — o módulo vai "
        "escrever no schema de PRODUÇÃO mesmo numa trilha isolada (achado F9). Use a fábrica, ou declare "
        "a exceção COM MOTIVO em EXCECOES_DECLARADAS:\n  " + "\n  ".join(achados)
    )


def test_toda_excecao_declarada_tem_motivo_escrito():
    sem_motivo = [k for k, v in EXCECOES_DECLARADAS.items() if not (v or "").strip()]
    assert not sem_motivo, f"exceção sem motivo escrito: {sem_motivo}"


def test_a_fabrica_reescreve_tambem_o_que_nao_passa_por_execute():
    """`executemany` e `copy_expert` são do C do psycopg2 e não chamavam o `execute` desta subclasse —
    um módulo podia ter a fábrica e ainda assim mandar `INSERT INTO plat....` cru (F1/F2)."""
    # a pergunta é se o método RESOLVE para a reescrita da casa, não em que classe da hierarquia ele está
    # escrito: desde que a reescrita virou um mixin com lista declarada (`MixinReescritaSchema`, cuja trava é
    # tests/unit/test_schema_ambiente.py) os métodos não estão mais no __dict__ da subclasse, e continuam
    # todos cobertos. Comparar com o cursor cru do driver pega as duas formas.
    import psycopg2.extensions

    for metodo in ("execute", "executemany", "copy_expert", "callproc"):
        assert getattr(CursorSchemaAmbiente, metodo) is not getattr(psycopg2.extensions.cursor, metodo), \
            f"{metodo} não é sobrescrito pela fábrica"


if __name__ == "__main__":  # varredura solta
    for linha in conexoes_sem_fabrica():
        print(linha)
