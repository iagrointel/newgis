import json
import logging
import re

from app.log import FormatadorJSON, req_id


def test_req_id_16_hex():
    assert re.fullmatch(r"[0-9a-f]{16}", req_id())
    assert req_id() != req_id()


def test_linha_json_com_campos_fixos_e_de_requisicao():
    registro = logging.LogRecord("plat.teste", logging.INFO, __file__, 1, "acesso", None, None)
    registro.req_id = "0123456789abcdef"
    registro.status = 200
    linha = json.loads(FormatadorJSON().format(registro))
    assert {"ts", "nivel", "msg", "logger"} <= set(linha)
    assert linha["req_id"] == "0123456789abcdef" and linha["status"] == 200
    assert linha["ts"].endswith("+00:00")
