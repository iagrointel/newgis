"""Busca do catálogo (ADR 0004 seção 7): gramática própria (analisador descendente) que traduz `q` em SQL
parametrizado. Texto livre e campos de texto viram `websearch_to_tsquery('plat.pt_sem_acento', %s)` (nunca
`to_tsquery` com texto do usuário); campos exatos viram predicados; intervalos `[a TO b]`; operadores AND/OR/NOT/-,
aspas e parênteses. `:` sem campo ou campo desconhecido = 422 campo_invalido; > 200 termos = 422 busca_complexa.
Também aqui: ordenação (título exato → rank + reforço de status → modificado_em → id), cursor opaco e
filtros laterais."""

import base64
import datetime
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field

from app import limites
from app.erros import ErroAPI

CFG = "'plat.pt_sem_acento'::regconfig"
CAMPOS_TEXTO = {
    "titulo": "to_tsvector({cfg}, coalesce(i.titulo, ''))",
    "tags": "to_tsvector({cfg}, coalesce(plat.tags_texto(i.tags), ''))",
    "resumo": "to_tsvector({cfg}, coalesce(i.resumo, ''))",
    "descricao": "to_tsvector({cfg}, coalesce(i.descricao, ''))",
}
CAMPOS_EXATOS = {"dono", "tipo", "familia", "status", "acesso", "pasta", "categoria", "grupo", "id", "origem",
                 "licenca"}
CAMPOS_INTERVALO = {"criado": "i.criado_em", "modificado": "i.modificado_em"}
# item L0-09-a: intervalo NUMÉRICO (0-10), não de data — a pontuação de procedência é a mesma régua da
# acervo.v_completude, calculada em SQL por plat.procedencia_pontuacao(dados)
CAMPOS_INTERVALO_NUMERO = {"procedencia": "plat.procedencia_pontuacao(i.dados)"}
STATUS = {"autoritativo", "obsoleto", "nenhum"}
ACESSOS = {"privado", "inquilino", "publico"}
ORIGENS = {"hospedado", "referenciado"}
ORDENACOES = {
    "titulo": ("lower(i.titulo)", "asc"),
    "modificado_em": ("i.modificado_em", "desc"),
    "criado_em": ("i.criado_em", "desc"),
    "tipo": ("i.tipo", "asc"),
    "dono": ("d.login", "asc"),
    "tamanho_bytes": ("i.tamanho_bytes", "desc"),
    "pontuacao": ("i.pontuacao", "desc"),
}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
DATA_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?Z?)?$")


class ErroSintaxe(Exception):
    def __init__(self, codigo: str, mensagem: str, detalhe=None):
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.detalhe = codigo, mensagem, detalhe


# ---------------------------------------------------------------- tokens
@dataclass
class Token:
    tipo: str  # palavra | frase | campo | abre | fecha | OR | AND | NOT | menos
    valor: str = ""
    campo: str = ""
    intervalo: tuple | None = None


def _tokenizar(q: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            tokens.append(Token("abre"))
            i += 1
            continue
        if c == ")":
            tokens.append(Token("fecha"))
            i += 1
            continue
        if c == "-" and i + 1 < n and not q[i + 1].isspace() and q[i + 1] not in "()":
            tokens.append(Token("menos"))
            i += 1
            continue
        if c == '"':
            j = q.find('"', i + 1)
            if j < 0:
                j = n
            tokens.append(Token("frase", q[i + 1 : j]))
            i = j + 1
            continue
        # palavra ou campo:valor
        j = i
        while j < n and not q[j].isspace() and q[j] not in '()"':
            if q[j] == ":":
                break
            j += 1
        palavra = q[i:j]
        if j < n and q[j] == ":":
            campo = palavra.lower()
            if not campo:
                raise ErroSintaxe("campo_invalido", "':' sem nome de campo", {"campo": "", "valor": q[j : j + 20]})
            k = j + 1
            if k < n and q[k] == "[":
                m = q.find("]", k)
                if m < 0:
                    raise ErroSintaxe("campo_invalido", "intervalo sem ']'", {"campo": campo, "valor": q[k : k + 40]})
                dentro = q[k + 1 : m]
                partes = re.split(r"\s+TO\s+", dentro.strip(), flags=re.I)
                if len(partes) != 2:
                    raise ErroSintaxe("campo_invalido", "intervalo exige [a TO b]", {"campo": campo, "valor": dentro})
                tokens.append(Token("campo", campo=campo, intervalo=(partes[0].strip(), partes[1].strip())))
                i = m + 1
                continue
            if k < n and q[k] == '"':
                m = q.find('"', k + 1)
                if m < 0:
                    m = n
                tokens.append(Token("campo", q[k + 1 : m], campo=campo))
                i = m + 1
                continue
            m = k
            while m < n and not q[m].isspace() and q[m] not in '()"':
                m += 1
            valor = q[k:m]
            if not valor:
                raise ErroSintaxe("campo_invalido", f"campo '{campo}' sem valor", {"campo": campo, "valor": ""})
            tokens.append(Token("campo", valor, campo=campo))
            i = m
            continue
        if palavra.upper() in ("OR", "AND", "NOT") and palavra.isupper():
            tokens.append(Token(palavra.upper()))
        else:
            tokens.append(Token("palavra", palavra))
        i = j
    return tokens


# ---------------------------------------------------------------- árvore
@dataclass
class Consulta:
    sql: str
    params: list = field(default_factory=list)
    texto_rank: list[str] = field(default_factory=list)  # folhas de texto livre positivas (ordenação)
    ultimo_livre: str | None = None  # último termo livre (prefixo)
    termos: int = 0


class _Parser:
    def __init__(self, tokens: list[Token], tipos: set[str]):
        self.t = tokens
        self.i = 0
        self.tipos = tipos
        self.params: list = []
        self.texto_rank: list[str] = []
        self.ultimo_livre: str | None = None
        self.termos = 0

    def _olha(self) -> Token | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def _come(self) -> Token:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expr(self) -> str:
        partes = [self.conj()]
        while (tok := self._olha()) is not None and tok.tipo == "OR":
            self._come()
            partes.append(self.conj())
        return "(" + " OR ".join(partes) + ")" if len(partes) > 1 else partes[0]

    def conj(self) -> str:
        partes = []
        while (tok := self._olha()) is not None and tok.tipo not in ("OR", "fecha"):
            if tok.tipo == "AND":
                self._come()
                continue
            partes.append(self.unario())
        if not partes:
            return "true"
        return "(" + " AND ".join(partes) + ")" if len(partes) > 1 else partes[0]

    def unario(self, negado: bool = False) -> str:
        tok = self._come()
        if tok.tipo in ("NOT", "menos"):
            return "NOT " + self.unario(negado=True)
        if tok.tipo == "abre":
            interno = self.expr()
            if (f := self._olha()) is not None and f.tipo == "fecha":
                self._come()
            return "(" + interno + ")"
        if tok.tipo == "fecha":
            return "true"
        if tok.tipo in ("OR", "AND"):
            return "true"
        self.termos += 1
        if tok.tipo == "palavra":
            if not negado:
                self.texto_rank.append(tok.valor)
                self.ultimo_livre = tok.valor
            self.params.append(tok.valor)
            return f"i.busca @@ websearch_to_tsquery({CFG}, %s)"
        if tok.tipo == "frase":
            if not negado:
                self.texto_rank.append('"' + tok.valor.replace('"', "") + '"')
                self.ultimo_livre = None
            self.params.append('"' + tok.valor.replace('"', "") + '"')
            return f"i.busca @@ websearch_to_tsquery({CFG}, %s)"
        return self.campo(tok)

    def campo(self, tok: Token) -> str:
        c = tok.campo
        self.ultimo_livre = None
        if c in CAMPOS_TEXTO:
            if tok.intervalo:
                raise ErroSintaxe("campo_invalido", f"campo '{c}' não aceita intervalo", {"campo": c, "valor": ""})
            self.params.append(tok.valor)
            return CAMPOS_TEXTO[c].format(cfg=CFG) + f" @@ websearch_to_tsquery({CFG}, %s)"
        if c in CAMPOS_INTERVALO_NUMERO:
            col = CAMPOS_INTERVALO_NUMERO[c]
            if tok.intervalo:
                a, b = tok.intervalo
                partes = []
                if a != "*":
                    self.params.append(_numero(c, a))
                    partes.append(f"{col} >= %s")
                if b != "*":
                    self.params.append(_numero(c, b))
                    partes.append(f"{col} <= %s")
                return "(" + " AND ".join(partes) + ")" if partes else f"{col} IS NOT NULL"
            if tok.valor.lower() in ("nenhuma", "ausente"):
                return f"{col} IS NULL"
            self.params.append(_numero(c, tok.valor))
            return f"{col} >= %s"
        if c in CAMPOS_INTERVALO:
            if not tok.intervalo:
                raise ErroSintaxe(
                    "campo_invalido", f"campo '{c}' exige intervalo [a TO b]", {"campo": c, "valor": tok.valor}
                )
            a, b = tok.intervalo
            col = CAMPOS_INTERVALO[c]
            partes = []
            if a != "*":
                self.params.append(_data(c, a, fim=False))
                partes.append(f"{col} >= %s")
            if b != "*":
                self.params.append(_data(c, b, fim=True))
                partes.append(f"{col} < %s")
            return "(" + " AND ".join(partes) + ")" if partes else "true"
        if c not in CAMPOS_EXATOS:
            raise ErroSintaxe("campo_invalido", f"campo desconhecido: {c}", {"campo": c, "valor": tok.valor})
        if tok.intervalo:
            raise ErroSintaxe("campo_invalido", f"campo '{c}' não aceita intervalo", {"campo": c, "valor": ""})
        v = tok.valor
        if c == "dono":
            self.params.append(v.lower())
            return "i.dono_id IN (SELECT u.id FROM plat.usuario u WHERE u.login = %s)"
        if c == "tipo":
            if v not in self.tipos:
                raise ErroSintaxe("campo_invalido", f"tipo inexistente: {v}", {"campo": c, "valor": v})
            self.params.append(v)
            return "i.tipo = %s"
        if c == "familia":
            self.params.append(v)
            return "t.familia = %s"
        if c == "status":
            if v not in STATUS:
                raise ErroSintaxe("campo_invalido", f"status inválido: {v}", {"campo": c, "valor": v})
            if v == "nenhum":
                return "i.status IS NULL"
            self.params.append(v)
            return "i.status = %s"
        if c == "acesso":
            if v not in ACESSOS:
                raise ErroSintaxe("campo_invalido", f"acesso inválido: {v}", {"campo": c, "valor": v})
            self.params.append(v)
            return "i.acesso = %s"
        if c == "origem":
            if v not in ORIGENS:
                raise ErroSintaxe("campo_invalido", f"origem inválida: {v}", {"campo": c, "valor": v})
            self.params.append(v)
            return "i.origem = %s"
        if c == "licenca":
            # licença registrada NO BLOCO de procedência (item L0-09-a), não o campo livre `termos_de_uso`:
            # texto vazio já virou NULL na escrita, então `licenca:nenhuma` é de fato "não registrada"
            if v.lower() in ("nenhuma", "ausente"):
                return "plat.procedencia_licenca(i.dados) IS NULL"
            self.params.append(v)
            return "plat.procedencia_licenca(i.dados) ILIKE '%%' || %s || '%%'"
        if c == "id":
            if not UUID_RE.match(v):
                raise ErroSintaxe("campo_invalido", "id exige uuid", {"campo": c, "valor": v})
            self.params.append(v.lower())
            return "i.id = %s::uuid"
        if c == "grupo":
            if not UUID_RE.match(v):
                raise ErroSintaxe("campo_invalido", "grupo exige uuid", {"campo": c, "valor": v})
            self.params.append(v.lower())
            return "EXISTS (SELECT 1 FROM plat.item_grupo ig WHERE ig.item_id = i.id AND ig.grupo_id = %s::uuid)"
        if c == "pasta":
            if UUID_RE.match(v):
                self.params.append(v.lower())
                return "i.pasta_id = %s::uuid"
            self.params.append(v.lower())
            return "i.pasta_id IN (SELECT p.id FROM plat.pasta p WHERE lower(p.nome) = %s)"
        if c == "categoria":
            if UUID_RE.match(v):
                self.params.extend([v.lower(), v.lower()])
                return (
                    "i.categorias && ARRAY(SELECT k.id FROM plat.categoria k WHERE k.id = %s::uuid OR k.caminho LIKE "
                    "(SELECT caminho FROM plat.categoria WHERE id = %s::uuid) || '/%%')"
                )
            self.params.extend([v.lower(), v.lower()])
            return (
                "i.categorias && ARRAY(SELECT k.id FROM plat.categoria k WHERE lower(k.caminho) = %s "
                "OR lower(k.caminho) LIKE %s || '/%%')"
            )
        raise ErroSintaxe("campo_invalido", f"campo desconhecido: {c}", {"campo": c, "valor": v})


def _numero(campo: str, valor: str) -> float:
    """Valor numérico de um campo de intervalo numérico (item L0-09-a: `procedencia:[5 TO 10]`)."""
    try:
        n = float(valor.replace(",", "."))
    except ValueError as e:
        raise ErroSintaxe(
            "campo_invalido", f"número inválido em {campo}: {valor}", {"campo": campo, "valor": valor}
        ) from e
    if not 0 <= n <= 10:
        raise ErroSintaxe(
            "campo_invalido", f"{campo} vai de 0 a 10", {"campo": campo, "valor": valor}
        )
    return n


def _data(campo: str, valor: str, fim: bool) -> datetime.datetime:
    m = DATA_RE.match(valor)
    if not m:
        raise ErroSintaxe(
            "campo_invalido", f"data inválida em {campo}: {valor} (ISO 8601)", {"campo": campo, "valor": valor}
        )
    ano, mes, dia, h, mi, s = m.groups()
    try:
        if fim:
            if dia is None and mes is None:
                d = datetime.datetime(int(ano) + 1, 1, 1)
            elif dia is None:
                a, me = int(ano), int(mes)
                d = datetime.datetime(a + (me == 12), 1 if me == 12 else me + 1, 1)
            elif h is None:
                d = datetime.datetime(int(ano), int(mes), int(dia)) + datetime.timedelta(days=1)
            else:
                d = datetime.datetime(int(ano), int(mes), int(dia), int(h), int(mi), int(s or 0)) + datetime.timedelta(
                    seconds=1
                )
        else:
            d = datetime.datetime(int(ano), int(mes or 1), int(dia or 1), int(h or 0), int(mi or 0), int(s or 0))
    except ValueError as e:
        raise ErroSintaxe(
            "campo_invalido", f"data inválida em {campo}: {valor}", {"campo": campo, "valor": valor}
        ) from e
    return d.replace(tzinfo=datetime.UTC)


def traduzir(q: str, tipos: set[str]) -> Consulta:
    """q → Consulta(sql com %s, params, texto_rank). Levanta ErroSintaxe (a rota converte em ErroAPI 422)."""
    q = (q or "").strip()
    if len(q) > limites.BUSCA_Q_MAX:
        raise ErroSintaxe("busca_complexa", f"consulta com mais de {limites.BUSCA_Q_MAX} caracteres")
    if not q:
        return Consulta("true")
    tokens = _tokenizar(q)
    termos = sum(1 for t in tokens if t.tipo in ("palavra", "frase", "campo"))
    if termos > limites.BUSCA_TERMOS_MAX:
        raise ErroSintaxe(
            "busca_complexa", f"consulta com mais de {limites.BUSCA_TERMOS_MAX} termos", {"termos": termos}
        )
    p = _Parser(tokens, tipos)
    sql = p.expr()
    while p._olha() is not None:  # ')' sobrando
        p._come()
        resto = p.expr()
        if resto != "true":
            sql = f"({sql} AND {resto})"
    return Consulta(sql, p.params, p.texto_rank, p.ultimo_livre, termos)


def erro_api(e: ErroSintaxe) -> ErroAPI:
    return ErroAPI(422, e.codigo, e.mensagem, e.detalhe)


# ---------------------------------------------------------------- cursor
def _assinatura_consulta(partes: dict) -> str:
    return hashlib.sha256(json.dumps(partes, sort_keys=True, default=str).encode()).hexdigest()[:16]


def cursor_codificar(ordenar: str, direcao: str, valores: list, item_id: str, assinatura: str) -> str:
    corpo = {"o": ordenar, "d": direcao, "v": valores, "id": item_id, "q": assinatura}
    return base64.urlsafe_b64encode(json.dumps(corpo, default=str).encode()).decode().rstrip("=")


def cursor_decodificar(cursor: str, assinatura: str) -> dict:
    try:
        recheio = "=" * (-len(cursor) % 4)
        corpo = json.loads(base64.urlsafe_b64decode(cursor + recheio).decode())
        if corpo.get("q") != assinatura or "v" not in corpo or "id" not in corpo:
            raise ValueError("assinatura")
        uuid.UUID(corpo["id"])
        return corpo
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise ErroAPI(400, "cursor_invalido", "cursor inválido ou de outra consulta; refaça sem cursor") from e


def assinatura(filtros: dict) -> str:
    return _assinatura_consulta(filtros)
