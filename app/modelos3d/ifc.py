"""Leitor de arquivo IFC no formato STEP (ISO 10303-21), em Python puro.

O que este módulo faz e o que ele NÃO faz — a parte honesta primeiro:

FAZ: lê o arquivo, monta o grafo de entidades, e devolve a lista de ELEMENTOS do modelo (parede, laje,
elemento genérico, etc.) com identificador global (GUID), tipo IFC, nome, o pavimento que os contém e as
propriedades declaradas (conjuntos de propriedade e quantidades). Para a geometria, converte os dois
tipos de representação que a amostra aberta da buildingSMART usa e que cobrem a maior parte do que sai
de ferramenta de autoria hoje: malha já tesselada (`IfcTriangulatedFaceSet`, a forma do Reference View
do IFC4) e sólido de extrusão (`IfcExtrudedAreaSolid`) sobre perfil retangular, circular ou de polilinha
fechada.

NÃO FAZ: geometria de fronteira genérica (`IfcFacetedBrep`, `IfcAdvancedBrep`), booleanas (`IfcBoolean
Result`), varredura ao longo de curva, nem revolução. Elemento com representação que este módulo não sabe
converter ENTRA na tabela de elementos assim mesmo (com GUID, tipo, pavimento e propriedades) e sai
marcado `geometria=False`: é melhor ter o elemento sem forma do que fingir que o modelo tem 10 elementos
quando tem 40. Converter o resto exige o IfcOpenShell, que a casa tem no servidor de GPU e esta máquina
não tem (decisão D32, ADR do item); o campo `sem_geometria` do resultado é exatamente a fila desse job.

Unidades: o comprimento sai SEMPRE em metros. O fator vem do `IfcUnitAssignment` do projeto (prefixo SI:
milímetro na amostra aberta), nunca de suposição.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

MAX_BYTES_PADRAO = 200 * 1024 * 1024

# tipos que estruturam o espaço, não são elementos construídos: ficam fora da tabela de elementos
ESPACIAIS = {
    "IFCPROJECT", "IFCSITE", "IFCBUILDING", "IFCBUILDINGSTOREY", "IFCSPACE", "IFCZONE", "IFCSPATIALZONE",
    "IFCSPATIALELEMENT", "IFCEXTERNALSPATIALELEMENT", "IFCANNOTATION", "IFCGRID", "IFCOPENINGELEMENT",
    "IFCVOIDINGFEATURE",
}

PREFIXOS_SI = {
    "EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9, "MEGA": 1e6, "KILO": 1e3, "HECTO": 1e2,
    "DECA": 1e1, "DECI": 1e-1, "CENTI": 1e-2, "MILLI": 1e-3, "MICRO": 1e-6, "NANO": 1e-9, "PICO": 1e-12,
    "FEMTO": 1e-15, "ATTO": 1e-18,
}


class IfcInvalido(ValueError):
    """Arquivo que não é um IFC no formato STEP, ou cujo cabeçalho não declara esquema IFC."""


@dataclass
class Entidade:
    id: int
    nome: str
    args: list


@dataclass
class Elemento:
    guid: str
    tipo: str
    nome: str | None
    descricao: str | None
    pavimento: str | None
    propriedades: dict
    vertices: list[float] = field(default_factory=list)  # x,y,z em metros, no sistema do projeto
    indices: list[int] = field(default_factory=list)

    @property
    def tem_geometria(self) -> bool:
        return bool(self.indices)


@dataclass
class Modelo:
    esquema: str
    unidade_m: float
    elementos: list[Elemento]

    @property
    def sem_geometria(self) -> list[str]:
        return [e.guid for e in self.elementos if not e.tem_geometria]


# ------------------------------------------------------------------ analisador do STEP
_LINHA = re.compile(r"#(\d+)\s*=\s*([A-Za-z0-9_]+)\s*\(", re.ASCII)


def _partir_argumentos(texto: str) -> list:
    """Divide a lista de argumentos de uma entidade respeitando parênteses e cadeias com aspas simples."""
    saida: list = []
    pilha: list[list] = [saida]
    atual = []
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if c == "'":
            j = i + 1
            partes = []
            while j < n:
                if texto[j] == "'":
                    if j + 1 < n and texto[j + 1] == "'":
                        partes.append("'")
                        j += 2
                        continue
                    break
                partes.append(texto[j])
                j += 1
            atual.append("'" + "".join(partes))
            i = j + 1
            continue
        if c == "(":
            novo: list = []
            pilha[-1].append(novo)
            pilha.append(novo)
            atual = []
            i += 1
            continue
        if c in ",)":
            bruto = "".join(atual).strip()
            if bruto:
                pilha[-1].append(_valor(bruto))
            atual = []
            if c == ")":
                if len(pilha) > 1:
                    pilha.pop()
            i += 1
            continue
        atual.append(c)
        i += 1
    bruto = "".join(atual).strip()
    if bruto:
        pilha[-1].append(_valor(bruto))
    return saida


def _valor(bruto: str):
    if bruto.startswith("'"):
        return bruto[1:]
    if bruto in ("$", "*"):
        return None
    if bruto.startswith("#"):
        return Ref(int(bruto[1:]))
    if bruto.startswith(".") and bruto.endswith("."):
        return Simbolo(bruto[1:-1])
    try:
        return int(bruto)
    except ValueError:
        pass
    try:
        return float(bruto)
    except ValueError:
        return bruto


class Ref(int):
    """Referência a outra entidade (`#123`). É um int para poder indexar direto o dicionário."""

    __slots__ = ()


class Simbolo(str):
    """Enumeração do STEP (`.TRUE.`, `.AREA.`)."""

    __slots__ = ()


def analisar(texto: str) -> tuple[str, dict[int, Entidade]]:
    """Devolve (esquema declarado, entidades por id). Aceita entidade quebrada em várias linhas."""
    cabecalho = texto[:4000]
    if "ISO-10303-21" not in cabecalho:
        raise IfcInvalido("arquivo sem a assinatura ISO-10303-21: não é um IFC no formato STEP")
    m = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", texto, re.IGNORECASE)
    esquema = m.group(1) if m else ""
    if not esquema.upper().startswith("IFC"):
        raise IfcInvalido(f"esquema declarado não é IFC: {esquema or 'ausente'}")
    corte = texto.find("DATA;")
    dados = texto[corte + 5:] if corte >= 0 else texto
    entidades: dict[int, Entidade] = {}
    for m in _LINHA.finditer(dados):
        inicio = m.end()
        profundidade = 1
        i = inicio
        n = len(dados)
        while i < n and profundidade:
            c = dados[i]
            if c == "'":
                i += 1
                while i < n:
                    if dados[i] == "'":
                        if i + 1 < n and dados[i + 1] == "'":
                            i += 2
                            continue
                        break
                    i += 1
            elif c == "(":
                profundidade += 1
            elif c == ")":
                profundidade -= 1
            i += 1
        entidades[int(m.group(1))] = Entidade(int(m.group(1)), m.group(2).upper(),
                                              _partir_argumentos(dados[inicio:i - 1]))
    if not entidades:
        raise IfcInvalido("nenhuma entidade na seção DATA")
    return esquema, entidades


# ------------------------------------------------------------------ leitura do grafo
class Leitor:
    def __init__(self, esquema: str, entidades: dict[int, Entidade]):
        self.esquema = esquema
        self.ent = entidades
        self.por_nome: dict[str, list[Entidade]] = {}
        for e in entidades.values():
            self.por_nome.setdefault(e.nome, []).append(e)
        self.unidade_m = self._unidade_de_comprimento()
        self._cache_placement: dict[int, list[float]] = {}

    def de(self, ref) -> Entidade | None:
        return self.ent.get(int(ref)) if isinstance(ref, int) else None

    def _unidade_de_comprimento(self) -> float:
        for e in self.por_nome.get("IFCSIUNIT", []):
            tipo = next((a for a in e.args if isinstance(a, Simbolo) and a.endswith("UNIT")), None)
            if tipo != "LENGTHUNIT":
                continue
            prefixo = next((a for a in e.args if isinstance(a, Simbolo) and a in PREFIXOS_SI), None)
            return PREFIXOS_SI.get(prefixo, 1.0) if prefixo else 1.0
        for e in self.por_nome.get("IFCCONVERSIONBASEDUNIT", []):
            fator = self.de(e.args[3]) if len(e.args) > 3 else None
            if fator and fator.nome == "IFCMEASUREWITHUNIT" and isinstance(fator.args[0], (int, float)):
                return float(fator.args[0])
        return 1.0

    # ---- geometria: placements
    def _direcao(self, ref) -> tuple[float, float, float] | None:
        e = self.de(ref)
        if not e or not e.args or not isinstance(e.args[0], list):
            return None
        v = [float(x) for x in e.args[0]] + [0.0, 0.0, 0.0]
        return (v[0], v[1], v[2])

    def _ponto(self, ref) -> tuple[float, float, float]:
        e = self.de(ref)
        if not e or not e.args or not isinstance(e.args[0], list):
            return (0.0, 0.0, 0.0)
        v = [float(x) for x in e.args[0]] + [0.0, 0.0, 0.0]
        return (v[0], v[1], v[2])

    def matriz_axis2(self, ref) -> list[float]:
        """IfcAxis2Placement3D -> 4x4 em ordem de coluna. Eixo Z do 2º argumento, X do 3º (norma 4.3)."""
        e = self.de(ref)
        if not e:
            return _IDENT[:]
        if e.nome == "IFCAXIS2PLACEMENT2D":
            o = self._ponto(e.args[0])
            eixo_x = self._direcao(e.args[1]) if len(e.args) > 1 else None
            eixo_x = eixo_x or (1.0, 0.0, 0.0)
            return _monta(( eixo_x[0], eixo_x[1], 0.0), (-eixo_x[1], eixo_x[0], 0.0), (0.0, 0.0, 1.0),
                          (o[0], o[1], 0.0))
        o = self._ponto(e.args[0])
        z = self._direcao(e.args[1]) if len(e.args) > 1 else None
        x = self._direcao(e.args[2]) if len(e.args) > 2 else None
        z = _normalizar(z or (0.0, 0.0, 1.0))
        x = x or (1.0, 0.0, 0.0)
        # ortogonaliza X contra Z (Gram-Schmidt), como a norma define o sistema de referência
        d = sum(x[i] * z[i] for i in range(3))
        x = _normalizar(tuple(x[i] - d * z[i] for i in range(3))) or (1.0, 0.0, 0.0)
        y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
        return _monta(x, y, z, o)

    def matriz_placement(self, ref) -> list[float]:
        """IfcLocalPlacement encadeado até a raiz, com memória (a mesma cadeia se repete em cada elemento)."""
        if ref is None:
            return _IDENT[:]
        chave = int(ref)
        if chave in self._cache_placement:
            return self._cache_placement[chave]
        e = self.de(ref)
        if not e:
            return _IDENT[:]
        if e.nome == "IFCLOCALPLACEMENT":
            pai = self.matriz_placement(e.args[0]) if e.args and e.args[0] is not None else _IDENT[:]
            m = _mult(pai, self.matriz_axis2(e.args[1]))
        else:
            m = self.matriz_axis2(ref)
        self._cache_placement[chave] = m
        return m

    # ---- geometria: itens de representação
    def _malha_tesselada(self, e: Entidade) -> tuple[list[float], list[int]]:
        lista = self.de(e.args[0])
        if not lista or not lista.args or not isinstance(lista.args[0], list):
            return [], []
        pontos = [tuple(float(v) for v in p) for p in lista.args[0]]
        vertices = [c for p in pontos for c in p]
        indices: list[int] = []
        bruto = next((a for a in e.args[1:] if isinstance(a, list) and a and isinstance(a[0], list)), None)
        # CoordIndex é o 4º argumento no IFC4 (Closed, Normals, CoordIndex, PnIndex); a busca acima pega a
        # primeira lista de listas de inteiros que não sejam as normais (que são de reais)
        for a in e.args[1:]:
            if isinstance(a, list) and a and isinstance(a[0], list) and all(isinstance(v, int) for v in a[0]):
                bruto = a
                break
        for face in bruto or []:
            if len(face) >= 3:
                for k in range(1, len(face) - 1):
                    indices += [int(face[0]) - 1, int(face[k]) - 1, int(face[k + 1]) - 1]
        return vertices, indices

    def _perfil(self, ref) -> list[tuple[float, float]] | None:
        """Contorno do perfil no plano do próprio perfil, já com a posição dele aplicada."""
        e = self.de(ref)
        if not e:
            return None
        if e.nome == "IFCARBITRARYCLOSEDPROFILEDEF":
            curva = self.de(e.args[2]) if len(e.args) > 2 else None
            if not curva or curva.nome != "IFCPOLYLINE":
                return None
            pontos = [self._ponto(p)[:2] for p in curva.args[0]]
            if len(pontos) > 2 and pontos[0] == pontos[-1]:
                pontos = pontos[:-1]
            return pontos if len(pontos) >= 3 else None
        if e.nome in ("IFCRECTANGLEPROFILEDEF", "IFCROUNDEDRECTANGLEPROFILEDEF"):
            larg, alt = float(e.args[3] or 0), float(e.args[4] or 0)
            base = [(-larg / 2, -alt / 2), (larg / 2, -alt / 2), (larg / 2, alt / 2), (-larg / 2, alt / 2)]
            return _no_plano(self.matriz_axis2(e.args[2]), base)
        if e.nome == "IFCCIRCLEPROFILEDEF":
            raio = float(e.args[3] or 0)
            lados = 24
            base = [(raio * math.cos(2 * math.pi * i / lados), raio * math.sin(2 * math.pi * i / lados))
                    for i in range(lados)]
            return _no_plano(self.matriz_axis2(e.args[2]), base)
        return None

    def _extrusao(self, e: Entidade) -> tuple[list[float], list[int]]:
        contorno = self._perfil(e.args[0])
        if not contorno:
            return [], []
        posicao = self.matriz_axis2(e.args[1]) if e.args[1] is not None else _IDENT[:]
        direcao = _normalizar(self._direcao(e.args[2]) or (0.0, 0.0, 1.0))
        profundidade = float(e.args[3] or 0)
        if profundidade <= 0:
            return [], []
        n = len(contorno)
        base = [_aplicar(posicao, (x, y, 0.0)) for x, y in contorno]
        deslocamento = _aplicar(posicao, (direcao[0] * profundidade, direcao[1] * profundidade,
                                          direcao[2] * profundidade))
        origem = _aplicar(posicao, (0.0, 0.0, 0.0))
        d = tuple(deslocamento[i] - origem[i] for i in range(3))
        topo = [tuple(p[i] + d[i] for i in range(3)) for p in base]
        vertices = [c for p in base for c in p] + [c for p in topo for c in p]
        indices: list[int] = []
        for i in range(n):  # lateral
            j = (i + 1) % n
            indices += [i, j, n + j, i, n + j, n + i]
        for k in range(1, n - 1):  # tampas (leque; perfil convexo ou simples)
            indices += [0, k + 1, k]
            indices += [n, n + k, n + k + 1]
        return vertices, indices

    def geometria(self, produto: Entidade) -> tuple[list[float], list[int]]:
        """Malha do produto no sistema do PROJETO, em metros. Vazia quando a representação não é suportada."""
        forma = self.de(produto.args[6]) if len(produto.args) > 6 else None
        if not forma or forma.nome != "IFCPRODUCTDEFINITIONSHAPE":
            return [], []
        colocacao = self.matriz_placement(produto.args[5]) if len(produto.args) > 5 else _IDENT[:]
        vertices: list[float] = []
        indices: list[int] = []
        for ref_rep in (forma.args[2] if len(forma.args) > 2 and isinstance(forma.args[2], list) else []):
            rep = self.de(ref_rep)
            if not rep or rep.nome != "IFCSHAPEREPRESENTATION":
                continue
            if rep.args[1] not in (None, "Body"):
                continue
            for ref_item in (rep.args[3] if len(rep.args) > 3 and isinstance(rep.args[3], list) else []):
                item = self.de(ref_item)
                if not item:
                    continue
                if item.nome == "IFCTRIANGULATEDFACESET":
                    v, i = self._malha_tesselada(item)
                elif item.nome == "IFCEXTRUDEDAREASOLID":
                    v, i = self._extrusao(item)
                else:
                    continue
                base = len(vertices) // 3
                vertices += v
                indices += [base + k for k in i]
        if not indices:
            return [], []
        u = self.unidade_m
        fora: list[float] = []
        for k in range(0, len(vertices), 3):
            p = _aplicar(colocacao, (vertices[k], vertices[k + 1], vertices[k + 2]))
            fora += [p[0] * u, p[1] * u, p[2] * u]
        return fora, indices

    # ---- semântica: pavimento e propriedades
    def _pavimentos(self) -> dict[int, str]:
        mapa: dict[int, str] = {}
        estrutura_de: dict[int, int] = {}
        for e in self.por_nome.get("IFCRELCONTAINEDINSPATIALSTRUCTURE", []):
            alvo = e.args[5] if len(e.args) > 5 else None
            if alvo is None:
                continue
            for ref in (e.args[4] if isinstance(e.args[4], list) else []):
                estrutura_de[int(ref)] = int(alvo)
        # do container até achar um pavimento, subindo os agregados
        pai_de: dict[int, int] = {}
        for e in self.por_nome.get("IFCRELAGGREGATES", []):
            pai = e.args[4] if len(e.args) > 4 else None
            for ref in (e.args[5] if len(e.args) > 5 and isinstance(e.args[5], list) else []):
                if pai is not None:
                    pai_de[int(ref)] = int(pai)
        for produto, estrutura in estrutura_de.items():
            atual = estrutura
            visitados = set()
            while atual is not None and atual not in visitados:
                visitados.add(atual)
                ent = self.de(atual)
                if ent and ent.nome == "IFCBUILDINGSTOREY":
                    mapa[produto] = ent.args[2] if isinstance(ent.args[2], str) else f"#{ent.id}"
                    break
                atual = pai_de.get(atual)
            if produto not in mapa:
                ent = self.de(estrutura)
                if ent and isinstance(ent.args[2], str):
                    mapa[produto] = ent.args[2]
        return mapa

    def _valor_simples(self, bruto):
        """IFCLABEL('x'), IFCBOOLEAN(.T.), IFCREAL(1.) -> 'x', True, 1.0. Já vem como lista aninhada."""
        if isinstance(bruto, list):
            return self._valor_simples(bruto[0]) if bruto else None
        if isinstance(bruto, Simbolo):
            return {"T": True, "F": False, "U": None}.get(str(bruto), str(bruto))
        if isinstance(bruto, Ref):
            e = self.de(bruto)
            return e.args[0] if e and e.args else None
        return bruto

    def _propriedades_de(self, ref_conjunto) -> tuple[str, dict]:
        e = self.de(ref_conjunto)
        if not e:
            return "", {}
        nome = e.args[2] if len(e.args) > 2 and isinstance(e.args[2], str) else e.nome
        campos: dict = {}
        if e.nome == "IFCPROPERTYSET":
            for ref in (e.args[4] if len(e.args) > 4 and isinstance(e.args[4], list) else []):
                p = self.de(ref)
                if p and p.nome == "IFCPROPERTYSINGLEVALUE":
                    campos[str(p.args[0])] = self._valor_simples(p.args[2])
        elif e.nome == "IFCELEMENTQUANTITY":
            for ref in (e.args[5] if len(e.args) > 5 and isinstance(e.args[5], list) else []):
                q = self.de(ref)
                if not q or not q.nome.startswith("IFCQUANTITY"):
                    continue
                valor = next((a for a in q.args[3:] if isinstance(a, (int, float))), None)
                campos[str(q.args[0])] = valor
        return nome, campos

    def elementos(self) -> list[Elemento]:
        pavimentos = self._pavimentos()
        conjuntos: dict[int, list] = {}
        for e in self.por_nome.get("IFCRELDEFINESBYPROPERTIES", []):
            alvo = e.args[5] if len(e.args) > 5 else None
            for ref in (e.args[4] if len(e.args) > 4 and isinstance(e.args[4], list) else []):
                conjuntos.setdefault(int(ref), []).append(alvo)
        fora: list[Elemento] = []
        for nome, lista in self.por_nome.items():
            if nome in ESPACIAIS or not nome.startswith("IFC"):
                continue
            for e in lista:
                if len(e.args) < 8 or not isinstance(e.args[0], str) or len(e.args[0]) != 22:
                    continue  # não é um IfcRoot com GlobalId de 22 caracteres
                if len(e.args) < 7 or not isinstance(e.args[5], (Ref, type(None))):
                    continue
                if e.args[6] is None and e.args[5] is None:
                    continue  # sem forma e sem colocação: é relação ou tipo, não produto
                props: dict = {}
                for ref in conjuntos.get(e.id, []):
                    titulo, campos = self._propriedades_de(ref)
                    if campos:
                        props[titulo] = campos
                vertices, indices = self.geometria(e)
                fora.append(Elemento(
                    guid=e.args[0],
                    tipo=nome,
                    nome=e.args[2] if isinstance(e.args[2], str) else None,
                    descricao=e.args[3] if isinstance(e.args[3], str) else None,
                    pavimento=pavimentos.get(e.id),
                    propriedades=props,
                    vertices=vertices,
                    indices=indices,
                ))
        fora.sort(key=lambda x: (x.tipo, x.guid))
        return fora


def carregar(dados: bytes | str, max_bytes: int = MAX_BYTES_PADRAO) -> Modelo:
    """Ponto de entrada: bytes do arquivo IFC -> `Modelo` com elementos, propriedades e malhas."""
    if isinstance(dados, bytes):
        if len(dados) > max_bytes:
            raise IfcInvalido(f"arquivo de {len(dados)} bytes acima do teto de {max_bytes}")
        texto = dados.decode("utf-8", errors="replace")
    else:
        texto = dados
    esquema, entidades = analisar(texto)
    leitor = Leitor(esquema, entidades)
    return Modelo(esquema=esquema, unidade_m=leitor.unidade_m, elementos=leitor.elementos())


# ------------------------------------------------------------------ álgebra 4x4 (ordem de coluna)
_IDENT = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def _monta(x, y, z, o) -> list[float]:
    return [x[0], x[1], x[2], 0.0, y[0], y[1], y[2], 0.0, z[0], z[1], z[2], 0.0, o[0], o[1], o[2], 1.0]


def _mult(a: list[float], b: list[float]) -> list[float]:
    fora = [0.0] * 16
    for c in range(4):
        for l in range(4):  # noqa: E741
            fora[c * 4 + l] = sum(a[k * 4 + l] * b[c * 4 + k] for k in range(4))
    return fora


def _aplicar(m: list[float], p) -> tuple[float, float, float]:
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def _normalizar(v):
    if v is None:
        return None
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n else None


def _no_plano(m: list[float], pontos) -> list[tuple[float, float]]:
    return [_aplicar(m, (x, y, 0.0))[:2] for x, y in pontos]


__all__ = ["IfcInvalido", "Elemento", "Modelo", "carregar", "analisar", "Leitor"]
