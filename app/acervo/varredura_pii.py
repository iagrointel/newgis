"""Varredura de dado pessoal por CONTEÚDO nas views expostas do acervo (item L6-01-f-lgpd).

O que já existia era a rede GROSSA por NOME de coluna (`scripts/acervo_sync.py::_e_pii_por_nome`, corrigida
em 17/09/2026 para comparar por TERMO e não pelo nome inteiro) mais a curadoria MANUAL por fonte
(`plat.acervo_lgpd.risco_pii`). O que faltava — e o próprio docstring de `acervo_sync.py` prometia — é a rede
FINA: olhar o CONTEÚDO de uma amostra e recusar coluna que carrega CPF ou CNPJ mesmo quando o nome dela não
denuncia nada (`doc`, `ni`, `codigo`, `identificacao`).

Regra de decisão, escrita para ser conservadora nos dois sentidos:

  - CPF/CNPJ COM pontuação (`123.456.789-09`, `12.345.678/0001-95`) conta sempre: escrever a máscara é uma
    declaração de intenção, e nenhum código de cadastro público brasileiro usa esse formato para outra coisa.
  - Sequência NUA de 11 ou 14 dígitos só conta quando o DÍGITO VERIFICADOR fecha. Sem isso a varredura
    acusaria metade do acervo: código do IBGE, matrícula do INCRA, protocolo de processo e chave de CAR são
    sequências longas de dígito, e a probabilidade de uma sequência arbitrária de 11 dígitos fechar os dois
    dígitos verificadores de CPF é 1 em 100. O preço é conhecido e está escrito: CPF gravado com dígito
    errado escapa da rede fina — por isso ela NÃO substitui a rede por nome nem a curadoria manual, soma-se
    às duas.
  - Sequência de dígito todos iguais (00000000000, 111...) nunca conta: é enchimento, não documento.

Nada do valor encontrado é devolvido ao chamador: o achado carrega só a máscara (`***.***.**9-09`), a
coluna e a contagem. A regra da casa é não publicar dado identificado, e um relatório de varredura que
imprime o CPF que achou seria o próprio vazamento.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# com pontuação: a máscara é declaração de intenção e conta sozinha
RE_CPF_MASCARA = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
RE_CNPJ_MASCARA = re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\d)")
# nu: só conta com dígito verificador válido (ver docstring)
RE_11_NUS = re.compile(r"(?<!\d)\d{11}(?!\d)")
RE_14_NUS = re.compile(r"(?<!\d)\d{14}(?!\d)")

AMOSTRA_PADRAO = 1000


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def cpf_valido(numero: str) -> bool:
    """Dígito verificador do CPF (módulo 11). Sequência de dígito repetido nunca é válida."""
    n = _digitos(numero)
    if len(n) != 11 or len(set(n)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(n[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        digito = 0 if resto == 10 else resto
        if digito != int(n[tamanho]):
            return False
    return True


def cnpj_valido(numero: str) -> bool:
    """Dígito verificador do CNPJ (módulo 11 com os pesos 5..2 / 6..2)."""
    n = _digitos(numero)
    if len(n) != 14 or len(set(n)) == 1:
        return False
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        corte = len(pesos)
        soma = sum(int(n[i]) * pesos[i] for i in range(corte))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(n[corte]):
            return False
    return True


def mascarar(numero: str) -> str:
    """Só os dois últimos dígitos sobrevivem — o bastante para o operador achar a linha na origem, longe do
    bastante para o relatório não ser ele próprio um vazamento."""
    n = _digitos(numero)
    return "*" * (len(n) - 2) + n[-2:]


def achar_documento(valor) -> tuple[str, str] | None:
    """(regra, máscara) do primeiro CPF/CNPJ encontrado no valor; None quando não há nenhum."""
    if valor is None:
        return None
    texto = valor if isinstance(valor, str) else str(valor)
    if len(texto) > 4096:  # campo de texto longo: olha só o começo, para a varredura não virar um job
        texto = texto[:4096]
    m = RE_CPF_MASCARA.search(texto)
    if m and cpf_valido(m.group()):
        return "cpf_com_mascara", mascarar(m.group())
    m = RE_CNPJ_MASCARA.search(texto)
    if m and cnpj_valido(m.group()):
        return "cnpj_com_mascara", mascarar(m.group())
    for bruto in RE_11_NUS.findall(texto):
        if cpf_valido(bruto):
            return "cpf_nu", mascarar(bruto)
    for bruto in RE_14_NUS.findall(texto):
        if cnpj_valido(bruto):
            return "cnpj_nu", mascarar(bruto)
    return None


def _e_pii_por_nome(coluna: str) -> bool:
    """A MESMA regra de nome do sincronizador, carregada de `scripts/acervo_sync.py` em vez de reescrita: o
    item L6-01-a é o dono dela (e tem o próprio par de provas em tests/seguranca/
    test_acervo_sync_coluna_pii.py). Duas cópias da regra divergem no primeiro conserto que só uma receber."""
    spec = importlib.util.spec_from_file_location("acervo_sync_regra", RAIZ / "scripts" / "acervo_sync.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo._e_pii_por_nome(coluna)


def _colunas_de_texto(cur, schema: str, view: str) -> list[str]:
    """Só coluna em que um documento pode estar escrito: texto e numérico inteiro/decimal. Geometria, data,
    booleano e binário ficam de fora — não carregam CPF e varrer todas multiplicaria o custo à toa."""
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, view),
    )
    tipos_uteis = {"text", "character varying", "character", "citext", "name",
                   "bigint", "integer", "numeric", "double precision", "real"}
    return [r["column_name"] for r in cur.fetchall() if r["data_type"] in tipos_uteis]


def varrer_view(cur, schema: str, view: str, amostra: int = AMOSTRA_PADRAO) -> list[dict]:
    """Achados de uma view. Dois tipos: `nome_de_coluna` (rede grossa, aplicada de novo AQUI porque a view já
    publicada pode ter sido criada antes do conserto da regra) e `conteudo` (rede fina, amostra de `amostra`
    linhas). Identificadores são citados com `quote_ident` do próprio Postgres, nunca interpolados crus."""
    import psycopg2.extensions as _ext

    achados: list[dict] = []
    colunas = _colunas_de_texto(cur, schema, view)
    for c in colunas:
        if _e_pii_por_nome(c):
            achados.append({"schema": schema, "view": view, "coluna": c, "regra": "nome_de_coluna",
                            "linhas_amostradas": 0, "exemplo_mascarado": None})
    if not colunas:
        return achados
    con = cur.connection
    ident = _ext.quote_ident(schema, con) + "." + _ext.quote_ident(view, con)
    lista = ", ".join(_ext.quote_ident(c, con) for c in colunas)
    cur.execute(f"SELECT {lista} FROM {ident} LIMIT %s", (amostra,))  # noqa: S608 — identificadores citados
    linhas = cur.fetchall()
    por_coluna: dict[str, tuple[str, str]] = {}
    for linha in linhas:
        for c in colunas:
            if c in por_coluna:
                continue
            achado = achar_documento(linha[c])
            if achado is not None:
                por_coluna[c] = achado
    for c, (regra, mascara) in sorted(por_coluna.items()):
        achados.append({"schema": schema, "view": view, "coluna": c, "regra": f"conteudo:{regra}",
                        "linhas_amostradas": len(linhas), "exemplo_mascarado": mascara})
    return achados


def views_expostas(cur, schema: str) -> list[str]:
    cur.execute("SELECT viewname FROM pg_views WHERE schemaname = %s ORDER BY viewname", (schema,))
    return [r["viewname"] for r in cur.fetchall()]


def varrer_schema(cur, schema: str, amostra: int = AMOSTRA_PADRAO) -> list[dict]:
    """Todos os achados de todas as views expostas do schema de publicação do acervo."""
    saida: list[dict] = []
    for v in views_expostas(cur, schema):
        saida.extend(varrer_view(cur, schema, v, amostra))
    return saida


def relatorio(achados: list[dict]) -> str:
    if not achados:
        return "nenhum achado"
    return "; ".join(
        f"{a['schema']}.{a['view']}.{a['coluna']} [{a['regra']}"
        + (f" {a['exemplo_mascarado']}" if a["exemplo_mascarado"] else "")
        + "]"
        for a in achados
    )
