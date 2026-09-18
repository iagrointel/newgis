"""Adversário de linha L7 operação (parte 2) — item `L7-06-c-logs-consulta-req-id`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-2.md`).

`app/logs_consulta.py::FONTES_PADRAO` lê a fonte "nginx" pela tag de journal `plat_nginx`
(`journalctl -t plat_nginx`). Nenhum arquivo de `deploy/` (o que `install.sh` de fato copia para
`/etc/nginx/`) configura essa tag: não existe `access_log syslog:...,tag=plat_nginx` em lugar
nenhum do repositório, e o `log_format plat_json` que o docstring do próprio módulo cita como
existente em `deploy/nginx.conf` também não existe — o único `log_format` real
(`deploy/nginx-log-formats.conf::plat_tiles`) vai para ARQUIVO (`access_log
/var/log/nginx/plat_tiles_access.log plat_tiles;`, visto em `/etc/nginx/sites-enabled/
plat.iagrointel.com`), nunca para journal com essa tag. Confirmado ao vivo nesta máquina (nginx
rodando a >24h, servindo a trilha `uniao` em `sistema.iagrointel.com`, `plat-sistema` sem NENHUM
`access_log` próprio — herda o `access_log /var/log/nginx/access.log;` global de
`/etc/nginx/nginx.conf`, também arquivo, também sem a tag): `journalctl -t plat_nginx` (com e sem
sudo) devolve `-- No entries --`, e o único identificador de journal que o nginx desta máquina usa
é `nginx` (plano), nunca `plat_nginx`.

A "banca real" que o ledger do item cita como prova (`tests/banca_l706c_logs_req_id.py`) NÃO
exercita este caminho: ela sobe um nginx efêmero PRÓPRIO com um `access_log` de ARQUIVO e chama
`logs_consulta.reunir(..., especificacao=...)` apontando para esses arquivos — nunca usa
`FONTES_PADRAO`. Ou seja, a prova existe para o mecanismo de junção, não para o fio de produção:
um operador que rode `plat logs --req-id <id>` sem `--fonte` (o uso documentado no `--help` do
próprio `scripts/plat.py`) nunca vai ver a linha do nginx, para requisição nenhuma, em ambiente
nenhum hoje instalado por `install.sh`.

Achado adicional (mesma cláusula do portão, "nenhum segredo... em log"): o único `log_format` que
JÁ está em produção (`plat_tiles`) loga `"$request"` sem qualquer redação — e o token de serviço
dos tiles vetoriais/raster (`app/tiles/autorizacao.py`, "o token vem no CAMINHO da URL... nunca em
parâmetro que expira") é um segmento de PATH (`/svc/<token>/...`), logo cai inteiro, em texto
claro, dentro de `$request`. Não há `map`/mascaramento em nenhum arquivo de `deploy/`."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DEPLOY = RAIZ / "deploy"


def _grep_recursivo(padrao_substr: str) -> list[str]:
    achados = []
    for caminho in DEPLOY.rglob("*.conf"):
        try:
            texto = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if padrao_substr in texto:
            achados.append(str(caminho.relative_to(RAIZ)))
    return achados


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_algum_arquivo_de_deploy_liga_a_tag_plat_nginx_ao_journal():
    achados = _grep_recursivo("plat_nginx")
    assert achados, "nenhum deploy/*.conf referencia a tag de journal 'plat_nginx' (fonte fantasma)"


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_log_format_plat_json_existe_em_algum_deploy_conf():
    achados = _grep_recursivo("log_format plat_json")
    assert achados, "log_format plat_json citado no docstring não existe em deploy/"


@pytest.mark.skipif(not shutil.which("journalctl"), reason="journalctl ausente nesta máquina")
@pytest.mark.xfail(
    strict=True,
    reason=(
        "journalctl -t plat_nginx nesta máquina (nginx rodando >24h, servindo a trilha uniao) "
        "devolve zero linhas — a fonte 'nginx' de FONTES_PADRAO está estruturalmente vazia, não "
        "é questão de o req_id específico não bater. Item L7-06-c-logs-consulta-req-id."
    ),
)
def test_journal_tem_alguma_linha_com_a_tag_plat_nginx():
    resultado = subprocess.run(
        ["journalctl", "-t", "plat_nginx", "--no-pager", "-n", "5", "--output", "cat"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert resultado.stdout.strip(), "journalctl -t plat_nginx não tem NENHUMA linha nesta máquina"


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_log_format_plat_tiles_nao_expoe_o_caminho_bruto():
    texto = (DEPLOY / "nginx-log-formats.conf").read_text(encoding="utf-8")
    assert '"$request"' not in texto, "plat_tiles loga $request inteiro (inclui /svc/<token>/... sem redação)"
