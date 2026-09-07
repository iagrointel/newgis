"""Receptor de webhook de homologação do item L7-06-b-alertas: guarda, com hora de chegada, cada
mensagem que o Alertmanager entrega. É a EVIDÊNCIA de prazo do portão ("o alerta chega ao canal de
teste em <= 2 min, com evidência de hora de envio") — sem ele o prazo seria uma afirmação, não uma
medida.

Não é código de produção e não faz parte da aplicação: roda só durante `deploy/alertas_homologacao.sh`.

    python3 deploy/alertas_receptor_teste.py <porta> <arquivo.jsonl>

Cada linha do arquivo é um objeto JSON com:
  recebido_em   — hora de chegada no receptor, ISO 8601 UTC (relógio desta máquina)
  receptor      — nome do receptor do Alertmanager que entregou (campo `receiver` do corpo)
  estado        — firing | resolved
  alertas       — lista de {alertname, severidade, servico, comeca_em}
"""

import datetime
import http.server
import json
import sys


def principal(porta: int, caminho: str) -> None:
    class Manipulador(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 — nome imposto por BaseHTTPRequestHandler
            bruto = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            agora = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            try:
                corpo = json.loads(bruto or b"{}")
            except json.JSONDecodeError:
                corpo = {"erro_de_json": bruto.decode("utf-8", "replace")}
            linha = {
                "recebido_em": agora,
                "receptor": corpo.get("receiver"),
                "estado": corpo.get("status"),
                "autorizacao_presente": "authorization" in {k.lower() for k in self.headers},
                "alertas": [
                    {
                        "alertname": a.get("labels", {}).get("alertname"),
                        "severidade": a.get("labels", {}).get("severidade"),
                        "servico": a.get("labels", {}).get("servico"),
                        "runbook": a.get("labels", {}).get("runbook"),
                        "comeca_em": a.get("startsAt"),
                    }
                    for a in corpo.get("alerts", [])
                ],
            }
            with open(caminho, "a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            return

    http.server.HTTPServer(("127.0.0.1", porta), Manipulador).serve_forever()


if __name__ == "__main__":
    principal(int(sys.argv[1]), sys.argv[2])
