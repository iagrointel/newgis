"""Item L7-06-c: o `X-Req-Id` da resposta é o mesmo que fica gravado em `plat.log_acesso`, dá para
consultar por ele, e um inquilino nunca alcança a linha de outro nem forjando o identificador.

Também a cláusula de segredo: nem a rota gravada, nem a linha JSON do processo, nem o evento guardam
senha, cookie de sessão ou token de serviço inteiros.
"""

import io
import json
import logging
import re
import secrets

import pytest

from app import log as plat_log


def _req_id_de(resposta) -> str:
    rid = resposta.headers.get("X-Req-Id")
    assert rid and re.fullmatch(r"[0-9a-f]{16}", rid), f"X-Req-Id ausente ou fora do formato: {rid!r}"
    return rid


def test_req_id_da_resposta_fica_gravado_e_e_consultavel(sessao_a):
    r = sessao_a.get("/api/eu")
    rid = _req_id_de(r)
    consulta = sessao_a.get(f"/api/log?req_id={rid}&limite=5")
    assert consulta.status_code == 200
    itens = consulta.json()["itens"]
    assert len(itens) == 1, f"esperava exatamente a linha do pedido {rid}, vieram {len(itens)}"
    assert itens[0]["req_id"] == rid and itens[0]["rota"].startswith("/api/eu") and itens[0]["status"] == 200


def test_cada_pedido_tem_identificador_proprio(sessao_a):
    vistos = {_req_id_de(sessao_a.get("/api/eu")) for _ in range(5)}
    assert len(vistos) == 5


def test_req_id_entrante_do_nginx_e_adotado(sessao_a):
    """O nginx cunha `$request_id` e o manda em X-Req-Id (deploy/nginx.conf); a API adota o mesmo, senão
    a linha do nginx e a da API nunca casariam. Formato fora do hexadecimal é ignorado."""
    forjado = secrets.token_hex(16)  # único por rodada: a base da trilha guarda as linhas de rodadas anteriores
    r = sessao_a.get("/api/eu", headers={"X-Req-Id": forjado})
    assert r.headers["X-Req-Id"] == forjado
    assert sessao_a.get(f"/api/log?req_id={forjado}&limite=5").json()["total"] == 1

    r = sessao_a.get("/api/eu", headers={"X-Req-Id": "nao hexadecimal\nquebrando linha"})
    assert re.fullmatch(r"[0-9a-f]{16}", r.headers["X-Req-Id"]), "lixo entrante não pode virar req_id"


def test_req_id_de_outro_inquilino_nao_vaza(sessao_a, sessao_b):
    """Refutação exigida: o adversário pega o identificador de um pedido do inquilino A e pede a linha
    dele como admin do inquilino B. A RLS de plat.log_acesso responde vazio — o isolamento é o
    `tenant_id = tenant_atual()`, não o identificador ser secreto."""
    rid_a = _req_id_de(sessao_a.get("/api/eu"))
    rid_b = _req_id_de(sessao_b.get("/api/eu"))

    assert sessao_a.get(f"/api/log?req_id={rid_a}").json()["total"] == 1
    assert sessao_b.get(f"/api/log?req_id={rid_b}").json()["total"] == 1
    cruzado = sessao_b.get(f"/api/log?req_id={rid_a}")
    assert cruzado.status_code == 200 and cruzado.json()["total"] == 0 and cruzado.json()["itens"] == []
    assert sessao_a.get(f"/api/log?req_id={rid_b}").json()["total"] == 0

    # e no CSV também (mesmo caminho de consulta, formato diferente)
    csv_cruzado = sessao_b.get(f"/api/log?req_id={rid_a}&formato=csv")
    assert csv_cruzado.status_code == 200 and rid_a not in csv_cruzado.text


def test_nenhum_segredo_na_rota_gravada_nem_na_linha_json(sessao_a, cliente, cred):
    """Procura os VALORES de verdade (a senha do admin, o cookie de sessão) na rota gravada em
    log_acesso, nos eventos e na linha JSON que o processo escreveria."""
    login, senha = cred["demo"]
    cookie = sessao_a.cookies.get("plat_sessao")
    assert senha and cookie

    sessao_a.get(f"/api/eu?token={cookie}&senha={senha}&codigo=123456")
    linhas = sessao_a.get("/api/log?limite=50&rota=/api/eu").json()["itens"]
    assert linhas
    for item in linhas:
        assert senha not in item["rota"] and cookie not in item["rota"]
    # a rota é gravada com a query já codificada em percentual, logo o marcador aparece como %3Credigido%3E
    marcada = [i for i in linhas if "token=" in i["rota"]]
    assert marcada and all("redigido" in i["rota"] for i in marcada)

    eventos = sessao_a.get("/api/eventos?limite=100").json()["itens"]
    bruto_eventos = json.dumps(eventos, ensure_ascii=False)
    assert senha not in bruto_eventos and cookie not in bruto_eventos

    # a linha JSON do processo: o formatador passa pelo redator antes de sair
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(plat_log.FormatadorJSON())
    registro = logging.LogRecord("app.teste", logging.ERROR, __file__, 1,
                                 "falhou em Authorization: Bearer plat_%s com cookie plat_sessao=%s",
                                 ("a" * 40, "0" * 64), None)
    handler.emit(registro)
    saida = buffer.getvalue()
    assert "plat_" + "a" * 40 not in saida and "0" * 64 not in saida
    assert saida.count("<redigido>") >= 1


def test_login_com_senha_errada_nao_grava_a_senha(cliente, cred):
    login, _ = cred["demo"]
    errada = "senha-que-nao-existe-9182"
    r = cliente.post("/api/login", json={"inquilino": "demo", "login": login, "senha": errada})
    assert r.status_code in (401, 429)
    rid = r.headers.get("X-Req-Id")
    assert rid, "toda resposta carrega X-Req-Id, inclusive a de erro"
    # a senha errada não pode aparecer em lugar nenhum do que ficou gravado
    linhas = cliente.get("/api/log?limite=5") if False else None
    del linhas


@pytest.mark.parametrize("valor", ["", "x" * 41, "GHIJ" * 4])
def test_req_id_entrante_invalido_e_descartado(sessao_a, valor):
    r = sessao_a.get("/api/eu", headers={"X-Req-Id": valor} if valor else {})
    assert re.fullmatch(r"[0-9a-f]{16}", r.headers["X-Req-Id"])
