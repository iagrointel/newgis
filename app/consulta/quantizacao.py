"""`quantizationParameters` (modo "view", obrigatório para o ArcGIS Pro carregar camada grande sem
travar — item L2-04-c): quantiza coordenada float em inteiro dentro da tolerância declarada, a partir
de uma origem (extent.xmin/ymax, upperLeft) e uma escala derivada de `tolerance` (unidades do mapa por
pixel). `x_q = round((x - originX) / tolerance)`; para desquantizar: `x = originX + x_q * tolerance`.
Erro por quantização nunca passa de `tolerance/2` (arredondamento), verificado pelo teste do item."""

from __future__ import annotations

from dataclasses import dataclass

from app.erros import ErroAPI


@dataclass
class Quantizacao:
    origin_x: float
    origin_y: float
    tolerance: float

    def quantizar(self, x: float, y: float) -> tuple[int, int]:
        return round((x - self.origin_x) / self.tolerance), round((self.origin_y - y) / self.tolerance)

    def desquantizar(self, qx: int, qy: int) -> tuple[float, float]:
        return self.origin_x + qx * self.tolerance, self.origin_y - qy * self.tolerance


def parse(obj: dict) -> Quantizacao:
    """`{"mode":"view","originPosition":"upperLeft","tolerance":<num>,"extent":{"xmin","ymin","xmax","ymax"}}`
    — só o modo "view" é suportado (é o único que o Pro pede na prática); "edit" é recusado, declarado."""
    if not isinstance(obj, dict):
        raise ErroAPI(400, "quantizacao_invalida", "quantizationParameters precisa ser objeto JSON")
    modo = obj.get("mode", "view")
    if modo != "view":
        raise ErroAPI(422, "quantizacao_modo_fora", f"modo de quantização não suportado: {modo!r} (só 'view')")
    tol = obj.get("tolerance")
    extent = obj.get("extent") or {}
    if not isinstance(tol, (int, float)) or tol <= 0:
        raise ErroAPI(400, "quantizacao_invalida", "tolerance precisa ser número positivo")
    try:
        xmin, ymax = float(extent["xmin"]), float(extent["ymax"])
    except (KeyError, TypeError, ValueError) as e:
        raise ErroAPI(400, "quantizacao_invalida", "extent.xmin/ymax obrigatórios (originPosition upperLeft)") from e
    return Quantizacao(origin_x=xmin, origin_y=ymax, tolerance=float(tol))
