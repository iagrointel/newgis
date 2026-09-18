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


def _journalctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["journalctl", "--no-pager", *args], capture_output=True, text=True,
                          timeout=15, check=False)


def _le_o_journal_do_sistema() -> bool:
    """`journalctl` SEM `--system` também lê o journal do PRÓPRIO usuário, que quase nunca está vazio:
    medido em 18/09/2026, a sonda ingênua devolvia uma linha de sessão do PAM e o teste concluía, errado,
    que havia permissão. A pergunta certa é sobre o journal do SISTEMA, e aí journalctl responde com
    código != 0 e "No journal files were opened due to insufficient permissions"."""
    r = _journalctl("--system", "-n", "1", "--output", "cat")
    return r.returncode == 0 and "insufficient permissions" not in (r.stdout + r.stderr)


# CONSERTADO (18/09/2026, turno L7 do construtor). O defeito era real e tinha DUAS causas, as duas
# medidas e consertadas:
#  1. nenhuma configuração de nginx escrevia a tag. deploy/nginx.conf ganhou o `access_log syslog:...`
#     com `nohostname`: SEM `nohostname` o nginx manda a linha RFC 3164 com o hostname antes da tag, o
#     journald não a reconhece como SYSLOG_IDENTIFIER, e `journalctl -t plat_nginx` continua devolvendo
#     zero — foi exatamente o que se viu ao ligar a primeira versão, e é a armadilha do item.
#  2. o usuário do serviço não estava no grupo `systemd-journal`. journalctl NÃO dá erro a quem não pode
#     ler o journal do sistema: devolve ZERO linha. A consulta de log não falhava, ela MENTIA — e não só
#     para o nginx: para as quatro fontes. install.sh passou a acrescentar o usuário ao grupo (passo d1b).
#
# Por isso a conferência abaixo separa as duas coisas antes de acusar: se ESTE processo não consegue ler
# o journal do sistema (o lançador de teste da casa roda num escopo que não carrega grupo suplementar),
# o resultado é SKIP com esse motivo, nunca um verde falso; só com leitura confirmada a ausência de
# linha vira reprovação.
@pytest.mark.skipif(not shutil.which("journalctl"), reason="journalctl ausente nesta máquina")
def test_journal_tem_alguma_linha_com_a_tag_plat_nginx():
    if not _le_o_journal_do_sistema():
        pytest.skip(
            "este processo não lê o journal do SISTEMA: sem leitura não dá para distinguir 'fonte "
            "vazia' de 'sem permissão', e journalctl devolve zero linha nos dois casos. Rode com o "
            "usuário no grupo systemd-journal (o lançador de teste da casa abre um escopo que não "
            "carrega grupo suplementar; `sg systemd-journal -c ...` resolve)."
        )
    saida = _journalctl("--system", "-t", "plat_nginx", "-n", "5", "--output", "cat").stdout.strip()
    assert saida, "journalctl -t plat_nginx não tem NENHUMA linha, e este processo LÊ o journal"
    assert "/svc/<token>/" in saida or "/svc/" not in saida, (
        f"o token de serviço saiu em texto claro no log do nginx: {saida[:200]}"
    )


# CONSERTADO (17/09/2026, turno L7 do construtor): a marca xfail saiu junto com o defeito.
def test_log_format_plat_tiles_nao_expoe_o_caminho_bruto():
    texto = (DEPLOY / "nginx-log-formats.conf").read_text(encoding="utf-8")
    assert '"$request"' not in texto, "plat_tiles loga $request inteiro (inclui /svc/<token>/... sem redação)"
