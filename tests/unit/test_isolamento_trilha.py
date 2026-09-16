"""Isolamento de credencial entre PRODUÇÃO e as TRILHAS de teste/homologação no armazenamento de objetos
(D26, item F2/garage2). Até 15/09 as trilhas vivas (`uniao`, `lancamento`) liam `PLAT_GARAGE_ADMIN_TOKEN` do
mesmo cofre/`.env` de produção (`laco/trilha_ambiente.sh`, achado igual ao L7-31 de homologação, mas para o
Garage: quem tivesse esse token administrava TODOS os buckets do Garage, inclusive os de produção).

O conserto aqui é estrutural, não uma chave escopada dentro do MESMO servidor (como em homologação): existe
agora uma SEGUNDA INSTÂNCIA de Garage, só para trilhas (unidade `plataforma-garage-trilhas.service`, S3 :3910,
admin :3913, dados em `/mnt/pgdata/garage-trilhas/`), com token de administração PRÓPRIO gerado com
`openssl rand -hex 32` e guardado em `laco/var/garage-trilhas.segredos` (fora do repo, umask 077) — nunca mais
em `/etc/plat/segredos` nem no `.env` de produção. Este arquivo prova o isolamento contra a máquina viva e SÓ
POR LEITURA (GET) nas duas APIs administrativas; nada aqui cria, apaga ou altera bucket, chave ou objeto.
Pula com motivo quando alguma das duas instâncias de Garage não está de pé ou quando a trilha não está
instalada."""

import hashlib
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[2]
RAIZ_INSTALADA = Path("/home/dev/plataforma/enterprise")
LACO = Path("/home/dev/plataforma/laco")
TEMPO_LIMITE_S = 10.0


def _instalado(relativo: str) -> Path:
    """O `.env` de produção vive na árvore INSTALADA quando o teste roda de um worktree."""
    proprio = RAIZ / relativo
    return proprio if proprio.exists() else RAIZ_INSTALADA / relativo


ENV_PRODUCAO = _instalado(".env")
ENV_TRILHA = LACO / "var" / "trilha" / "uniao.env"
SEGREDO_GARAGE_TRILHAS = LACO / "var" / "garage-trilhas.segredos"


def _ler(caminho: Path) -> dict[str, str]:
    return {c: (v or "") for c, v in dotenv_values(caminho).items()}


def _impressao(valor: str) -> str:
    """sha256 truncado: identifica o valor em mensagem de erro sem nunca imprimir o segredo."""
    return hashlib.sha256(valor.encode()).hexdigest()[:16]


def _nomes_de_segredo() -> set[str]:
    """Mesma fonte de verdade do L7-31 (ver test_isolamento_homologacao.py): os nomes que as unidades
    systemd versionadas declaram como `LoadCredential=`, hoje {PLAT_DSN, PLAT_DSN_LEITOR, PLAT_DSN_WORKER,
    PLAT_GARAGE_ADMIN_TOKEN, PLAT_SECRET, PLAT_SECRET_ANTERIOR}."""
    nomes = set()
    for unidade in (RAIZ / "deploy").glob("*.service"):
        for linha in unidade.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha.startswith("LoadCredential="):
                nomes.add(linha.removeprefix("LoadCredential=").split(":", 1)[0])
    return nomes


@pytest.fixture(scope="module")
def ambientes():
    if not ENV_PRODUCAO.is_file():
        pytest.skip(f"sem .env de produção em {ENV_PRODUCAO}")
    if not ENV_TRILHA.is_file():
        pytest.skip(f"trilha 'uniao' não está instalada (sem {ENV_TRILHA}); rode laco/trilha_ambiente.sh uniao")
    return _ler(ENV_PRODUCAO), _ler(ENV_TRILHA)


@pytest.fixture(scope="module")
def garage_producao(ambientes):
    producao, _ = ambientes
    url = (producao.get("PLAT_GARAGE_ADMIN_URL") or "http://127.0.0.1:3903").rstrip("/")
    try:
        requests.get(f"{url}/health", timeout=TEMPO_LIMITE_S)
    except requests.RequestException as e:
        pytest.skip(f"admin do Garage de produção não está de pé em {url} ({type(e).__name__})")
    return url


@pytest.fixture(scope="module")
def garage_trilhas(ambientes):
    _, trilha = ambientes
    url = (trilha.get("PLAT_GARAGE_ADMIN_URL") or "http://127.0.0.1:3913").rstrip("/")
    try:
        requests.get(f"{url}/health", timeout=TEMPO_LIMITE_S)
    except requests.RequestException as e:
        pytest.skip(f"admin do Garage de trilhas não está de pé em {url} ({type(e).__name__})")
    return url


def test_a_trilha_tem_instancia_de_garage_propria_nao_a_de_producao(ambientes):
    """A raiz do achado: a URL administrativa da trilha não pode ser a mesma porta da de produção — senão
    não importa o token, é o MESMO servidor."""
    producao, trilha = ambientes
    url_prod = (producao.get("PLAT_GARAGE_ADMIN_URL") or "").strip()
    url_trilha = (trilha.get("PLAT_GARAGE_ADMIN_URL") or "").strip()
    assert url_trilha, "var/trilha/uniao.env sem PLAT_GARAGE_ADMIN_TOKEN/URL"
    assert url_trilha != url_prod, (
        f"a trilha aponta para a MESMA admin API de produção ({url_trilha!r}): "
        "isso anula qualquer separação de token"
    )


def test_token_de_administracao_da_trilha_nao_e_o_de_producao(ambientes):
    """Comparação por VALOR (não por nome): o token de administração do Garage da trilha tem de divergir
    byte a byte do de produção. O valor real de produção não vive em `.env` (conserto G6, achado 11):
    `deploy/plat-api.service`/`plat-worker.service` o carregam via `LoadCredential=` a partir de
    `/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN`, arquivo que esta suíte nunca lê (regra dura da máquina:
    nenhum `cat`/`grep` sobre `/etc/plat/segredos/*`). Quando o valor não está no `.env` a comparação por
    valor não é possível aqui; a garantia que IMPORTA (uma trilha comprometida nunca alcança produção) é
    coberta, sem precisar do valor de produção, por
    `test_token_da_trilha_nao_administra_a_instancia_de_producao` abaixo."""
    producao, trilha = ambientes
    tok_trilha = (trilha.get("PLAT_GARAGE_ADMIN_TOKEN") or "").strip()
    assert tok_trilha, "var/trilha/uniao.env sem PLAT_GARAGE_ADMIN_TOKEN (trilha ficaria sem Garage)"
    tok_prod = (producao.get("PLAT_GARAGE_ADMIN_TOKEN") or "").strip()
    if not tok_prod:
        pytest.skip(
            f"{ENV_PRODUCAO} não tem PLAT_GARAGE_ADMIN_TOKEN em texto plano (vem de "
            "/etc/plat/segredos via LoadCredential; esta suíte não lê esse arquivo por regra dura)"
        )
    assert tok_trilha != tok_prod, (
        f"PLAT_GARAGE_ADMIN_TOKEN da trilha é IGUAL ao de produção (sha256 {_impressao(tok_prod)}): "
        "quem tiver esse token administra o Garage de produção inteiro"
    )


def test_nenhum_segredo_de_producao_aparece_no_ambiente_da_trilha(ambientes):
    """Cláusula literal do portão do L7-31, estendida às trilhas: produção e trilha nunca compartilham
    banco, bucket, chave ou segredo. Comparação por valor; corte de 16 caracteres (porta/'dev'/'sim' não
    são segredo)."""
    producao, trilha = ambientes

    def credencial(valor: str) -> bool:
        return len(valor) >= 16 and not valor.startswith(("http://", "https://"))

    valores_trilha = {v for v in trilha.values() if credencial(v)}
    repetidos = sorted(
        f"{chave} (sha256 {_impressao(valor)})"
        for chave, valor in producao.items()
        if credencial(valor) and valor in valores_trilha
    )
    assert repetidos == [], f"valor de produção repetido na trilha: {repetidos}"
    for nome in _nomes_de_segredo():
        valor = (producao.get(nome) or "").strip()
        if valor:
            assert valor not in valores_trilha, f"{nome} é o MESMO em produção e na trilha (sha256 {_impressao(valor)})"


def test_prefixo_de_bucket_difere_entre_producao_e_trilha(ambientes):
    """Defesa em profundidade: mesmo que os tokens fossem iguais, o prefixo separaria o NOME do bucket. Não
    é o isolamento (isso é o servidor+token separados acima), mas evita colisão silenciosa de nome."""
    producao, trilha = ambientes
    p = producao.get("PLAT_GARAGE_BUCKET_PREFIXO") or "plat-"
    t = trilha.get("PLAT_GARAGE_BUCKET_PREFIXO") or "plat-"
    assert p != t, f"prefixo de bucket igual em produção e na trilha: {p!r}"


def test_segredo_gravado_em_arquivo_proprio_fora_do_etc_plat_segredos(ambientes):
    """O ponto do achado 11 (adaptado): o valor não pode vir mais do cofre de produção
    `/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN`. Prova direta: o arquivo próprio da trilha
    (`laco/var/garage-trilhas.segredos`) existe e o valor nele é exatamente o que está em uniao.env."""
    _, trilha = ambientes
    if not SEGREDO_GARAGE_TRILHAS.is_file():
        pytest.skip(f"sem {SEGREDO_GARAGE_TRILHAS} (instância de trilhas ainda não provisionada)")
    proprio = _ler(SEGREDO_GARAGE_TRILHAS)
    tok_proprio = (proprio.get("PLAT_GARAGE_ADMIN_TOKEN") or "").strip()
    tok_trilha = (trilha.get("PLAT_GARAGE_ADMIN_TOKEN") or "").strip()
    assert tok_proprio and tok_proprio == tok_trilha, (
        "PLAT_GARAGE_ADMIN_TOKEN de uniao.env não bate com laco/var/garage-trilhas.segredos "
        "(a trilha não está lendo do cofre próprio da instância de trilhas)"
    )


def test_token_da_trilha_nao_administra_a_instancia_de_producao(ambientes, garage_producao):
    """Simétrico: o token da trilha não pode administrar o Garage de PRODUÇÃO — é essa a garantia que
    interessa de verdade (uma trilha comprometida nunca alcança produção)."""
    _, trilha = ambientes
    tok_trilha = (trilha.get("PLAT_GARAGE_ADMIN_TOKEN") or "").strip()
    if not tok_trilha:
        pytest.skip("sem PLAT_GARAGE_ADMIN_TOKEN na trilha para testar")
    r = requests.get(
        f"{garage_producao}/v2/ListBuckets", headers={"Authorization": f"Bearer {tok_trilha}"}, timeout=TEMPO_LIMITE_S
    )
    assert r.status_code in (401, 403), (
        f"o token de administração da TRILHA foi aceito pela admin API de produção: "
        f"{r.status_code} {r.text[:200]}"
    )
