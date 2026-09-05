"""Logging JSON por linha em stdout (journal do systemd), sem dependência externa (ADR 0001 seção 9).
Leitura: `journalctl -u plat-api -o cat | jq`."""

import datetime
import json
import logging
import secrets
import sys

CAMPOS_REQ = ("req_id", "metodo", "rota", "status", "tempo_ms", "ip", "tenant_id", "usuario_id", "token_id")


class FormatadorJSON(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        linha = {
            "ts": datetime.datetime.fromtimestamp(registro.created, datetime.UTC).isoformat(timespec="milliseconds"),
            "nivel": registro.levelname,
            "msg": registro.getMessage(),
            "logger": registro.name,
        }
        for campo in CAMPOS_REQ:
            valor = getattr(registro, campo, None)
            if valor is not None:
                linha[campo] = valor
        if registro.exc_info:
            linha["exc"] = self.formatException(registro.exc_info)
        return json.dumps(linha, ensure_ascii=False, default=str)


def configurar(nivel: str = "INFO") -> None:
    """Instala um único handler JSON na raiz; chamadas repetidas só ajustam o nível."""
    raiz = logging.getLogger()
    if not any(getattr(h, "_plat_json", False) for h in raiz.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(FormatadorJSON())
        handler._plat_json = True  # type: ignore[attr-defined]
        raiz.addHandler(handler)
    raiz.setLevel(nivel)
    for ruidoso in ("uvicorn.access",):
        logging.getLogger(ruidoso).setLevel("WARNING")


def req_id() -> str:
    """Identificador de requisição: 16 caracteres hexadecimais."""
    return secrets.token_hex(8)
