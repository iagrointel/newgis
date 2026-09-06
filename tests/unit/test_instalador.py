"""Leitura estática do install.sh e dos modelos de deploy: segredo nunca em argv (ADR 0001 seção 8),
PYTHONNOUSERSITE=1 na unidade, HSTS em todo add_header do bloco 443 e removido do bloco :80."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
NGINX = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")
UNIDADE = (ROOT / "deploy" / "plat-api.service").read_text(encoding="utf-8")
UNIDADE_WORKER = (ROOT / "deploy" / "plat-worker.service").read_text(encoding="utf-8")


def test_senha_de_demonstracao_entra_por_stdin_nunca_por_argv():
    assert "gerar_hash(sys.stdin.read())" in INSTALL
    assert "gerar_hash(sys.argv" not in INSTALL
    linha = next(li for li in INSTALL.splitlines() if "gerar_hash(sys.stdin.read())" in li)
    assert linha.strip().startswith("HASH=$(printf '%s' \"$senha\" |"), linha
    assert '"$senha")' not in INSTALL


def test_senha_do_banco_vai_ao_psql_por_stdin():
    padrao = r"printf \"ALTER ROLE plat_app PASSWORD '%s';\\n\" \"\$SENHA\" \| \"\$\{PSQL\[@\]\}\" -f -"
    assert re.search(padrao, INSTALL)


def test_python_do_instalador_roda_sem_site_do_usuario():
    assert 'PY=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/python)' in INSTALL
    assert 'PIP=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/pip)' in INSTALL
    assert "Environment=PYTHONNOUSERSITE=1" in UNIDADE.splitlines()


def test_instalador_grava_plat_git_sha_e_confere_hsts():
    assert 'sed -i "s/^PLAT_GIT_SHA=.*/PLAT_GIT_SHA=$SHA/" .env' in INSTALL
    assert "grep -v 'Strict-Transport-Security'" in INSTALL  # bloco :80 sem HSTS
    assert "grep -q 'max-age=31536000'" in INSTALL  # conferência pública


def test_hsts_em_todo_bloco_de_add_header_do_modelo():
    locais = NGINX.count("location ")
    hsts = NGINX.count('add_header Strict-Transport-Security "max-age=31536000" always;')
    # 5 desde o item L2-01-a (location nova para o PMTiles do mapa-base, deploy/nginx.conf)
    assert locais == 5 and hsts == locais + 1, (locais, hsts)


def test_referrer_policy_em_todo_bloco_de_add_header_do_modelo():
    """Achado do testador do T2: declarado no server{} não chegava às rotas (add_header no bloco cancela o herdado)."""
    locais = NGINX.count("location ")
    assert NGINX.count('add_header Referrer-Policy "strict-origin-when-cross-origin" always;') == locais + 1, locais


def test_instalador_limpa_residuos_de_teste_so_em_dev():
    assert "grep -qE '^PLAT_AMBIENTE=dev$' .env" in INSTALL and "plat.tenant_apagar_interno" in INSTALL


def test_logins_com_limite_por_ip_e_zona_escrita_pelo_instalador():
    for rota in ("location = /api/login {", "location = /api/login/2fa {"):
        bloco = NGINX[NGINX.index(rota) :]
        bloco = bloco[: bloco.index("}")]
        assert "limit_req zone=plat_login burst=10 nodelay;" in bloco and "limit_req_status 429;" in bloco, rota
        assert "proxy_pass http://127.0.0.1:PORTA;" in bloco
    assert NGINX.index("location = /api/login {") < NGINX.index("location / {")
    assert "zone=plat_login:10m rate=10r/m" in INSTALL and "/etc/nginx/conf.d/plat_limites.conf" in INSTALL


def test_instalador_semeia_plataforma_sem_superadmin_nos_demos_e_confere_cryptography():
    # item L7-14: a lista de pacotes apt saiu do install.sh (hardcoded) para deploy/pacotes_apt.txt
    # (lida em tempo de execução, seção "e2"); a conferência de python3-cryptography passou a valer
    # por ali — este teste confere as duas pontas (o arquivo tem a linha, o instalador lê o arquivo).
    assert "python3-cryptography" in (ROOT / "deploy" / "pacotes_apt.txt").read_text(encoding="utf-8")
    assert "deploy/pacotes_apt.txt" in INSTALL and "dpkg -s" in INSTALL
    assert "('$slug' = 'plataforma')" in INSTALL and "('$slug' = 'demo')" not in INSTALL
    assert "rm -f tests/credenciais_totp.txt" in INSTALL
    assert "plat.log_particao_garantir" in INSTALL and "plat.evento_particao_garantir" in INSTALL


# item L7-19-segredos-e-certificados: PLAT_SECRET e PLAT_DSN_WORKER nunca em .env, sempre por
# LoadCredential= do systemd (docs/SEGURANCA.md). Achado do adversário do turno T3: faltava um teste
# automatizado que provasse isso (só tinha `grep` manual) — esta seção fecha a lacuna.


def test_instalacao_do_zero_nunca_escreve_plat_secret_ou_dsn_worker_no_env():
    """O heredoc de instalação do zero (bloco `cat > .env <<ENV ... ENV`) não pode conter as duas
    chaves — hoje elas só existem em /etc/plat/segredos/, geradas na seção d2."""
    inicio = INSTALL.index("cat > .env <<ENV")
    fim = INSTALL.index("\nENV\n", inicio)
    heredoc = INSTALL[inicio:fim]
    assert "PLAT_SECRET=" not in heredoc, heredoc
    assert "PLAT_DSN_WORKER=" not in heredoc, heredoc


def test_instalador_migra_e_remove_os_dois_segredos_do_env_existente():
    """Instalação anterior ao L7-19 (segredo ainda no `.env`): a migração para `/etc/plat/segredos/`
    tem de terminar apagando a linha do `.env` — sem isso o `.env` de quem já tinha o segredo nunca
    fica limpo, mesmo depois de reinstalar."""
    assert "sed -i '/^PLAT_SECRET=/d' .env" in INSTALL
    assert "sed -i '/^PLAT_DSN_WORKER=/d' .env" in INSTALL
    # a remoção vem DEPOIS de gravar o valor no credential (nunca perde o segredo no meio do caminho)
    assert INSTALL.index('install -m 0600 -o root -g root /dev/null "$CRED_DIR/PLAT_SECRET"') < INSTALL.index(
        "sed -i '/^PLAT_SECRET=/d' .env"
    )
    assert INSTALL.index('install -m 0600 -o root -g root /dev/null "$CRED_DIR/PLAT_DSN_WORKER"') < INSTALL.index(
        "sed -i '/^PLAT_DSN_WORKER=/d' .env"
    )


def test_credential_dir_fica_fora_do_repositorio_dono_root_modo_600():
    assert 'install -d -m 0700 -o root -g root "$CRED_DIR"' in INSTALL
    assert 'install -m 0600 -o root -g root /dev/null "$CRED_DIR/PLAT_SECRET"' in INSTALL
    assert 'install -m 0600 -o root -g root /dev/null "$CRED_DIR/PLAT_DSN_WORKER"' in INSTALL
    assert "CRED_DIR=/etc/plat/segredos" in INSTALL  # fora de APP_DIR: settings.py nunca o lê por caminho relativo


def test_unidades_declaram_loadcredential_e_nunca_o_valor_do_segredo():
    assert "LoadCredential=PLAT_SECRET:/etc/plat/segredos/PLAT_SECRET" in UNIDADE
    assert "LoadCredential=PLAT_SECRET:/etc/plat/segredos/PLAT_SECRET" in UNIDADE_WORKER
    assert "LoadCredential=PLAT_DSN_WORKER:/etc/plat/segredos/PLAT_DSN_WORKER" in UNIDADE_WORKER
    # regra do ADR 0001 §8: segredo nunca em Environment=/argv da unidade — só o caminho aparece
    for unidade in (UNIDADE, UNIDADE_WORKER):
        for linha in unidade.splitlines():
            if linha.startswith(("Environment=", "ExecStart=")):
                assert "/etc/plat/segredos/" not in linha, linha  # só em LoadCredential=, nunca aqui


def test_env_exemplo_nao_ensina_a_colocar_os_dois_segredos_no_env():
    exemplo = (ROOT / ".env.exemplo").read_text(encoding="utf-8")
    assert "PLAT_SECRET=" not in exemplo, (
        "achado do adversário T3: .env.exemplo ainda ensinava a colocar PLAT_SECRET no .env"
    )
    assert "PLAT_DSN_WORKER=" not in exemplo, "idem para PLAT_DSN_WORKER"
    assert "PLAT_SECRET" in exemplo and "docs/SEGURANCA.md" in exemplo  # ainda documentado, só que fora do .env


def test_env_real_desta_maquina_nao_tem_mais_os_dois_segredos():
    """Prova viva (não só estática): o `.env` de verdade desta instalação, se existir, não pode conter
    PLAT_SECRET= nem PLAT_DSN_WORKER= — é exatamente o `grep -c` que o portão do item pede, automatizado."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        pytest.skip("sem .env nesta máquina (checkout limpo, nunca instalado)")
    linhas = env_path.read_text(encoding="utf-8").splitlines()
    achados = [li for li in linhas if li.startswith(("PLAT_SECRET=", "PLAT_DSN_WORKER="))]
    assert achados == [], achados


# Conserto do achado 17 do adversário no turno 3 (L7-19): PLAT_DSN (senha da role plat_app) e
# PLAT_GARAGE_ADMIN_TOKEN (credencial raiz do armazenamento) também saem do .env, pelo mesmo mecanismo.
# O valor só sai da máquina de produção quando o dono roda o passo 1 de docs/AMBIENTES.md §5 — o que estes
# testes provam é que o instalador, as unidades e a rotação já estão prontos para esse passo.
SEGREDOS_NOVOS = ("PLAT_DSN", "PLAT_GARAGE_ADMIN_TOKEN")


@pytest.mark.parametrize("segredo", SEGREDOS_NOVOS)
def test_instalador_migra_plat_dsn_e_token_do_garage_para_o_credential(segredo):
    """Mesmo padrão dos dois já migrados: cria o arquivo em $CRED_DIR (0600, dono root), migra o valor que
    estiver no .env e só DEPOIS apaga a linha de lá — nessa ordem, senão a migração perde o valor."""
    criar = f'install -m 0600 -o root -g root /dev/null "$CRED_DIR/{segredo}"'
    apagar = f"sed -i '/^{segredo}=/d' .env"
    assert criar in INSTALL, f"install.sh não cria o credential de {segredo}"
    assert apagar in INSTALL, f"install.sh não remove {segredo} do .env"
    assert INSTALL.index(criar) < INSTALL.index(apagar), f"{segredo}: apaga do .env antes de migrar o valor"


@pytest.mark.parametrize("segredo", SEGREDOS_NOVOS)
def test_unidades_leem_plat_dsn_e_token_do_garage_por_credencial(segredo):
    """As duas unidades leem os dois segredos (o worker também abre conexão de aplicação e fala com o
    armazenamento). Se o arquivo faltar, o systemd recusa iniciar — é de propósito: segredo ausente tem de
    parar a partida, não virar volta silenciosa ao .env."""
    linha = f"LoadCredential={segredo}:/etc/plat/segredos/{segredo}"
    assert linha in UNIDADE, f"plat-api.service não declara {segredo}"
    assert linha in UNIDADE_WORKER, f"plat-worker.service não declara {segredo}"


def test_instalador_alinha_a_senha_de_plat_app_pelo_credential_e_nao_pelo_env():
    """Depois da migração o `.env` não tem mais PLAT_DSN; a seção d3 tem de ler a senha do credential, senão
    a instalação passa a falhar (ou pior: realinha a role com um valor velho)."""
    assert 'sed -nE \'s#^postgresql://plat_app:([^@]+)@.*#\\1#p\' "$CRED_DIR/PLAT_DSN"' in INSTALL
    assert "^PLAT_DSN=postgresql://plat_app:" not in INSTALL
