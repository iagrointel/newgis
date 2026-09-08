"""Traduz um subconjunto da linguagem de expressão própria (item L2-10-c, `app/expressao/avaliador_py.py`) para
SQL do PostgreSQL parametrizado — o "subconjunto que permite tradução" do item L2-03-f-edicao-em-lote-calculo-campo
(hipótese: "calcular campo por expressão traduzida para SQL quando o subconjunto permite e avaliada linha a linha no
servidor quando não"). Só a AST entra aqui (quem chama já rodou `analisar(texto)`); a saída é `(sql, parametros)`
com `%s` do psycopg2 — nunca texto do usuário interpolado no SQL. Nome de coluna só sai daqui entre aspas duplas e
só se estiver na lista BRANCA `colunas` (o mesmo princípio do `contexto` do avaliador: `$campo` fora da lista é
`campo_nao_permitido`, nunca uma coluna descoberta em tempo de execução).

O QUE TRADUZ (semântica igual à do avaliador, conferida por `tests/api/test_edicao_lote.py`, que grava o mesmo
campo pelos dois caminhos e compara): literais; `$campo` (coluna da camada, tipos text/integer/bigint/double
precision/real/boolean) e os campos DERIVADOS de geometria que o lote oferece (`$area_m2`, `$comprimento_m`,
`$perimetro_m`, `$x`, `$y` — ver `app/edicao/lote.py::DERIVADOS`); aritmética `+ - * / % ^` (número sempre em
double precision, `/` é divisão real e por zero é erro nomeado nos dois lados, `%` é `mod` com o sinal do dividendo
como no avaliador); comparação `== !=` (IS NOT DISTINCT FROM: nulo == nulo é verdadeiro e nulo == x é falso, como
`_igual` do avaliador) e `< <= > >=` (nulo propaga, como lá); lógica `&& || !`; `Se` (CASE), `SeNulo` (coalesce),
`EhNulo` (IS NULL); `Maiuscula`/`Minuscula`; `Concatenar` só de textos (número em texto passa pela formatação do
avaliador, que não tem tradução 1:1); `Arredondar` (round numeric = meio-para-longe-de-zero, como lá);
`Absoluto`, `Floor`, `Ceil`, `Sqrt`, `Potencia`, `Minimo`, `Maximo`; `Trim` (espaços ASCII), `Left`, `Right`;
`Numero` de texto (mesma expressão regular do avaliador).

O QUE NÃO TRADUZ (levanta `NaoTraduzivel` com o motivo; o lote cai para a avaliação linha a linha): `Texto` de
número, `Concatenar` com número, `Texto*`/`TextoNumero`/`TextoData`, data (`AgoraUTC`, `Ano`, `Mes`, `Dia`,
`DiferencaDias`, `Weekday`), `Mid`/`Find`/`Split`/`Replace`/`Decode`, coleções (`Lista`… `Juntar`), coluna de
data/hora/bytea, e qualquer coisa que a tabela de funções do avaliador ainda não conheça."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.expressao.avaliador_py import Binario, Campo, Chamada, Literal, Unario

TIPOS_NUMERICOS = {"integer", "bigint", "double precision", "real", "smallint", "numeric"}
TIPOS_TEXTO = {"text", "character varying", "varchar"}
_RE_NUMERO_SQL = r"^-?[0-9]+(\.[0-9]+)?$"  # mesma forma aceita por `Numero` no avaliador (inteiro ou decimal)


class NaoTraduzivel(Exception):
    """Parte da expressão sem tradução SQL; `motivo` vai para `avisos`/`traducao_motivo` da resposta do lote."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


@dataclass
class Fragmento:
    sql: str
    tipo: str  # numero | texto | booleano | nulo | qualquer
    params: list = field(default_factory=list)  # na ordem dos %s de `sql`; um fragmento repetido repete-os


def _f(sql: str, tipo: str, *partes: Fragmento, extra: list | None = None) -> Fragmento:
    """Monta um fragmento cujo SQL cita `partes` NA ORDEM dada (os parâmetros seguem a mesma ordem)."""
    params: list = []
    for p in partes:
        params.extend(p.params)
    if extra:
        params.extend(extra)
    return Fragmento(sql, tipo, params)


class _Compilador:
    def __init__(self, colunas: dict[str, str], derivados: dict[str, str]):
        self.colunas = colunas
        self.derivados = derivados

    # ------------------------------------------------------------------ apoio: exigem o tipo e devolvem o fragmento
    def _num(self, f: Fragmento, onde: str) -> Fragmento:
        if f.tipo in ("numero", "nulo", "qualquer"):
            return f
        raise NaoTraduzivel(f"{onde} espera número, recebeu {f.tipo}")

    def _txt(self, f: Fragmento, onde: str) -> Fragmento:
        if f.tipo in ("texto", "nulo", "qualquer"):
            return f
        raise NaoTraduzivel(f"{onde} espera texto, recebeu {f.tipo}")

    def _bool(self, f: Fragmento, onde: str) -> Fragmento:
        if f.tipo in ("booleano", "nulo", "qualquer"):
            return f
        raise NaoTraduzivel(f"{onde} espera booleano, recebeu {f.tipo}")

    # ------------------------------------------------------------------ nós
    def no(self, n) -> Fragmento:
        if isinstance(n, Literal):
            return self.literal(n)
        if isinstance(n, Campo):
            return self.campo(n)
        if isinstance(n, Unario):
            return self.unario(n)
        if isinstance(n, Binario):
            return self.binario(n)
        if isinstance(n, Chamada):
            return self.chamada(n)
        raise NaoTraduzivel(f"nó desconhecido: {type(n).__name__}")

    def literal(self, n: Literal) -> Fragmento:
        if n.tipo_valor == "nulo":
            return Fragmento("NULL", "nulo")
        if n.tipo_valor == "numero":
            return Fragmento("(%s::double precision)", "numero", [float(n.valor)])
        if n.tipo_valor == "texto":
            return Fragmento("(%s::text)", "texto", [str(n.valor)])
        if n.tipo_valor == "booleano":
            return Fragmento("(%s::boolean)", "booleano", [bool(n.valor)])
        raise NaoTraduzivel(f"literal de tipo desconhecido: {n.tipo_valor}")

    def campo(self, n: Campo) -> Fragmento:
        nome = n.nome
        if nome in self.derivados:
            return Fragmento(f"({self.derivados[nome]})::double precision", "numero")
        if nome not in self.colunas:
            # mesma regra do avaliador: nunca uma coluna fora da lista branca, e o erro é o mesmo nome
            from app.expressao.avaliador_py import ErroExpressao

            raise ErroExpressao("campo_nao_permitido", f"campo não permitido: ${nome}", {"campo": nome})
        tipo = self.colunas[nome]
        ident = '"' + nome.replace('"', '""') + '"'
        if tipo in TIPOS_NUMERICOS:
            return Fragmento(f"({ident}::double precision)", "numero")
        if tipo in TIPOS_TEXTO:
            return Fragmento(ident, "texto")
        if tipo == "boolean":
            return Fragmento(ident, "booleano")
        raise NaoTraduzivel(f"coluna ${nome} de tipo {tipo} sem tradução SQL (data/hora/bytea ficam linha a linha)")

    def unario(self, n: Unario) -> Fragmento:
        f = self.no(n.operando)
        if n.operador == "-":
            return _f(f"(-({self._num(f, 'operador -').sql}))", "numero", f)
        if n.operador == "!":
            return _f(f"(NOT ({self._bool(f, 'operador !').sql}))", "booleano", f)
        raise NaoTraduzivel(f"operador unário desconhecido: {n.operador}")

    def binario(self, n: Binario) -> Fragmento:
        op = n.operador
        a = self.no(n.esquerda)
        b = self.no(n.direita)
        if op in ("+", "-", "*", "/"):
            self._num(a, f"operador {op}"), self._num(b, f"operador {op}")
            return _f(f"({a.sql} {op} {b.sql})", "numero", a, b)
        if op == "%":
            self._num(a, "operador %"), self._num(b, "operador %")
            # mod(numeric, numeric) tem o sinal do DIVIDENDO (a convenção fixada do avaliador); divisor zero é
            # erro `division_by_zero` no banco, o mesmo nome que o avaliador dá
            return _f(f"(mod(({a.sql})::numeric, ({b.sql})::numeric)::double precision)", "numero", a, b)
        if op == "^":
            self._num(a, "operador ^"), self._num(b, "operador ^")
            return _f(f"power({a.sql}, {b.sql})", "numero", a, b)
        if op in ("==", "!="):
            conhecidos = {a.tipo, b.tipo} - {"nulo", "qualquer"}
            if len(conhecidos) > 1:
                raise NaoTraduzivel(f"comparação {op} entre {a.tipo} e {b.tipo} (o avaliador devolve falso)")
            palavra = "IS NOT DISTINCT FROM" if op == "==" else "IS DISTINCT FROM"
            return _f(f"({a.sql} {palavra} {b.sql})", "booleano", a, b)
        if op in ("<", "<=", ">", ">="):
            if a.tipo == "texto" or b.tipo == "texto":
                self._txt(a, f"operador {op}"), self._txt(b, f"operador {op}")
                # o avaliador compara texto por ponto de código: COLLATE "C" é a ordem binária do UTF-8, que
                # coincide com a ordem por ponto de código
                return _f(f'(({a.sql}) COLLATE "C" {op} ({b.sql}) COLLATE "C")', "booleano", a, b)
            self._num(a, f"operador {op}"), self._num(b, f"operador {op}")
            return _f(f"({a.sql} {op} {b.sql})", "booleano", a, b)
        if op in ("&&", "||"):
            self._bool(a, f"operador {op}"), self._bool(b, f"operador {op}")
            return _f(f"({a.sql} {'AND' if op == '&&' else 'OR'} {b.sql})", "booleano", a, b)
        raise NaoTraduzivel(f"operador desconhecido: {op}")

    def chamada(self, n: Chamada) -> Fragmento:
        nome = n.nome
        args = n.argumentos
        if nome == "Se":
            if len(args) != 3:
                raise NaoTraduzivel("Se espera 3 argumentos")
            c = self._bool(self.no(args[0]), "Se")
            a, b = self.no(args[1]), self.no(args[2])
            tipo = a.tipo if a.tipo != "nulo" else b.tipo
            if a.tipo != "nulo" and b.tipo != "nulo" and a.tipo != b.tipo:
                raise NaoTraduzivel("Se com ramos de tipos diferentes não tem tradução SQL")
            return _f(f"(CASE WHEN {c.sql} THEN {a.sql} ELSE {b.sql} END)", tipo, c, a, b)
        if nome == "SeNulo":
            if len(args) != 2:
                raise NaoTraduzivel("SeNulo espera 2 argumentos")
            a, b = self.no(args[0]), self.no(args[1])
            tipo = a.tipo if a.tipo != "nulo" else b.tipo
            if a.tipo != "nulo" and b.tipo != "nulo" and a.tipo != b.tipo:
                raise NaoTraduzivel("SeNulo com tipos diferentes não tem tradução SQL")
            return _f(f"coalesce({a.sql}, {b.sql})", tipo, a, b)
        if nome == "EhNulo":
            a = self.no(args[0])
            return _f(f"(({a.sql}) IS NULL)", "booleano", a)
        if nome in ("Maiuscula", "Minuscula"):
            a = self._txt(self.no(args[0]), nome)
            return _f(f"{'upper' if nome == 'Maiuscula' else 'lower'}({a.sql})", "texto", a)
        if nome == "Concatenar":
            partes = []
            for a in args:
                f = self.no(a)
                if f.tipo not in ("texto", "nulo"):
                    raise NaoTraduzivel("Concatenar com número/booleano usa a formatação do avaliador (sem tradução)")
                partes.append(f)
            return _f("(" + " || ".join(f"coalesce({f.sql}, '')" for f in partes) + ")", "texto", *partes)
        if nome == "Trim":
            a = self._txt(self.no(args[0]), "Trim")
            return _f(f"btrim({a.sql}, ' ')", "texto", a)
        if nome in ("Left", "Right"):
            a = self._txt(self.no(args[0]), nome)
            k = self._num(self.no(args[1]), nome)
            return _f(f"{nome.lower()}({a.sql}, ({k.sql})::int)", "texto", a, k)
        if nome == "Arredondar":
            v = self._num(self.no(args[0]), "Arredondar")
            if len(args) == 1:
                return _f(f"(round(({v.sql})::numeric, 0)::double precision)", "numero", v)
            k = self._num(self.no(args[1]), "Arredondar")
            return _f(f"(round(({v.sql})::numeric, ({k.sql})::int)::double precision)", "numero", v, k)
        if nome in ("Absoluto", "Floor", "Ceil", "Sqrt"):
            v = self._num(self.no(args[0]), nome)
            fn = {"Absoluto": "abs", "Floor": "floor", "Ceil": "ceil", "Sqrt": "sqrt"}[nome]
            return _f(f"{fn}({v.sql})", "numero", v)
        if nome == "Potencia":
            a, b = self._num(self.no(args[0]), nome), self._num(self.no(args[1]), nome)
            return _f(f"power({a.sql}, {b.sql})", "numero", a, b)
        if nome in ("Minimo", "Maximo"):
            vals = [self._num(self.no(a), nome) for a in args]
            fn = "least" if nome == "Minimo" else "greatest"
            # least/greatest ignoram nulo; o avaliador recusa nulo (tipo_invalido) — a tradução só vale quando
            # nenhum argumento é nulo, por isso o CASE devolve nulo se algum for (a linha nula é reprovada
            # pela validação de domínio/obrigatório como nos dois caminhos). Cada fragmento aparece DUAS vezes
            # no SQL, então os parâmetros também vão duas vezes (ordem: os do CASE, depois os do least/greatest).
            nulos = " OR ".join(f"({v.sql}) IS NULL" for v in vals)
            return _f(f"(CASE WHEN {nulos} THEN NULL ELSE {fn}({', '.join(v.sql for v in vals)}) END)", "numero",
                      *vals, *vals)
        if nome == "Numero":
            f = self.no(args[0])
            if f.tipo == "numero":
                return f
            if f.tipo == "booleano":
                return _f(f"(CASE WHEN {f.sql} THEN 1.0 ELSE 0.0 END)::double precision", "numero", f)
            s = self._txt(f, "Numero")
            # `s` aparece duas vezes: parâmetros de s, a expressão regular, parâmetros de s de novo
            return Fragmento(
                f"(CASE WHEN btrim({s.sql}) ~ %s THEN btrim({s.sql})::double precision END)", "numero",
                [*s.params, _RE_NUMERO_SQL, *s.params],
            )
        raise NaoTraduzivel(f"função {nome} sem tradução SQL")


def compilar(no, colunas: dict[str, str], derivados: dict[str, str] | None = None) -> tuple[str, list, str]:
    """AST → `(sql, parametros, tipo)` com tipo ∈ numero | texto | booleano | nulo. `colunas` = {nome: tipo_pg} da
    camada (lista branca); `derivados` = {nome: expressão SQL sobre `geom`} que o lote oferece. Levanta
    `NaoTraduzivel` (cai para linha a linha) ou `ErroExpressao('campo_nao_permitido')` (erro do usuário, o mesmo
    nos dois caminhos)."""
    f = _Compilador(colunas, derivados or {}).no(no)
    return f.sql, f.params, f.tipo
