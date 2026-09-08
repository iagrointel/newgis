"""As duas gramáticas em que a MESMA ferramenta grande é escrita (item L2-15-b-consultas-duckdb-em-escala).

Uma ferramenta grande não tem dois códigos: tem um construtor de SQL que recebe um destes dois dialetos. O que
muda entre eles é pouco e está todo aqui — nome da relação, transformação de sistema de referência e
distância entre pontos. É isso que torna a comparação PostGIS × DuckDB uma comparação da MESMA
pergunta, e não de duas implementações parecidas.

**Área e comprimento.** O `spatial` do DuckDB calcula em coordenadas planas: `ST_Area` sobre geometria em graus
devolve graus quadrados, não metros quadrados. Por isso toda medida de tamanho passa por
`transformar`, que projeta para o EPSG métrico DECLARADO pelo usuário (padrão SIRGAS 2000 / Polyconic do
Brasil, EPSG:5880) — nunca por uma constante escondida. Distância entre dois pontos é a exceção: os dois
motores medem sobre uma ESFERA (`ST_Distance_Sphere` no DuckDB, `ST_DistanceSphere` no PostGIS). A escolha da
esfera, e não do elipsoide, é para que a mesma pergunta tenha a mesma forma nos dois lados: o
`ST_Distance_Spheroid` do DuckDB só aceita `POINT_2D`, não `GEOMETRY` (MEDIDO em 08/09/2026: BinderException),
e o `geography` do PostGIS não tem equivalente. Sobre esfera as duas contas diferem no último metro por causa
do raio adotado em cada motor; para distância entre posições isso não muda nenhuma decisão, e onde a diferença
importasse a resposta seria projetar, como faz `transformar`.

**Ordem dos eixos.** O `ST_Transform` do DuckDB respeita a ordem declarada pela autoridade, e a do EPSG:4326 é
(latitude, longitude): sem `always_xy := true` um ponto de São Paulo sai do outro lado do mundo (MEDIDO em
08/09/2026). O PostGIS sempre usa (x, y). O dialeto do DuckDB passa `always_xy := true` em toda chamada.
"""

from __future__ import annotations

EPSG_METRICO_PADRAO = 5880  # SIRGAS 2000 / Brazil Polyconic


class Dialeto:
    nome = ""

    def relacao(self, fonte: dict) -> str:
        raise NotImplementedError

    def transformar(self, expressao: str, de_srid: int, para_srid: int) -> str:
        raise NotImplementedError

    def distancia_esferica(self, a: str, b: str) -> str:
        raise NotImplementedError

    def ponto(self, x: str, y: str) -> str:
        return f"ST_Point({x}, {y})"

    def envelope(self, x1: str, y1: str, x2: str, y2: str) -> str:
        return f"ST_MakeEnvelope({x1}, {y1}, {x2}, {y2})"

    def coluna(self, nome: str) -> str:
        return '"' + nome.replace('"', '""') + '"'

    def periodo(self, coluna: str, grao: str) -> str:
        return f"date_trunc('{grao}', {coluna})"


class DuckDB(Dialeto):
    nome = "duckdb"

    def relacao(self, fonte: dict) -> str:
        return '"' + fonte["view"] + '"'

    def transformar(self, expressao: str, de_srid: int, para_srid: int) -> str:
        if int(de_srid) == int(para_srid):
            return expressao
        return (f"ST_Transform({expressao}, 'EPSG:{int(de_srid)}', 'EPSG:{int(para_srid)}', "
                "always_xy := true)")

    def distancia_esferica(self, a: str, b: str) -> str:
        return f"ST_Distance_Sphere({a}, {b})"


class PostGIS(Dialeto):
    nome = "postgis"

    def relacao(self, fonte: dict) -> str:
        return f'"{fonte["schema"]}"."{fonte["tabela"]}"'

    def transformar(self, expressao: str, de_srid: int, para_srid: int) -> str:
        if int(de_srid) == int(para_srid):
            return expressao
        return f"ST_Transform({expressao}, {int(para_srid)})"

    def distancia_esferica(self, a: str, b: str) -> str:
        return f"ST_DistanceSphere({a}, {b})"


DUCKDB = DuckDB()
POSTGIS = PostGIS()
GRAOS = ("dia", "mes", "ano")
GRAO_SQL = {"dia": "day", "mes": "month", "ano": "year"}
