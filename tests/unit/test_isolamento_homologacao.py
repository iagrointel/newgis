"""Isolamento de credencial entre PRODUÇÃO e HOMOLOGAÇÃO no armazenamento de objetos (item L7-31; conserto
do achado 11 do adversário no turno 3, `handoffs/T3/ataque-g6-ADVERSARIO.md`).

O achado: `PLAT_GARAGE_ADMIN_TOKEN` era byte a byte o mesmo nos dois ambientes, e com o token lido do
arquivo de homologação o adversário listou e leu os buckets de produção `plat-demo` (84 objetos, 127 MB) e
`plat-demo2` pela API de administração do Garage. O conserto: homologação passa a ter uma CHAVE S3 própria,
sem nenhum poder de administração, dona só dos buckets que ela mesma cria (alias local da chave).

Este arquivo prova o conserto contra a máquina viva e SÓ POR LEITURA. Nada aqui escreve, cria ou apaga
objeto, bucket ou chave; nenhuma chamada usa método diferente de GET. Pula com motivo quando o Garage não
está de pé ou quando o ambiente de homologação não está instalado."""

import hashlib
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[2]
RAIZ_INSTALADA = Path("/home/dev/plataforma/enterprise")
BUCKETS_DE_PRODUCAO = ("plat-demo", "plat-demo2")
TEMPO_LIMITE_S = 10.0


def _instalado(relativo: str) -> Path:
    """O `.env` e o ambiente de homologação vivem na árvore INSTALADA quando o teste roda de um worktree."""
    proprio = RAIZ / relativo
    return proprio if proprio.exists() else RAIZ_INSTALADA / relativo


ENV_PRODUCAO = _instalado(".env")
ENV_HOMOLOG = _instalado("var/homolog/homolog.env")


def _ler(caminho: Path) -> dict[str, str]:
    return {c: (v or "") for c, v in dotenv_values(caminho).items()}


def _impressao(valor: str) -> str:
    """sha256 truncado: identifica o valor em mensagem de erro sem nunca imprimir o segredo."""
    return hashlib.sha256(valor.encode()).hexdigest()[:16]


@pytest.fixture(scope="module")
def ambientes():
    if not ENV_PRODUCAO.is_file():
        pytest.skip(f"sem .env de produção em {ENV_PRODUCAO}")
    if not ENV_HOMOLOG.is_file():
        pytest.skip(f"ambiente de homologação não instalado (sem {ENV_HOMOLOG}); rode db/homolog_bootstrap.sh")
    return _ler(ENV_PRODUCAO), _ler(ENV_HOMOLOG)


@pytest.fixture(scope="module")
def garage(ambientes):
    """URL do S3 do Garage, só se o daemon responder. Caso contrário o módulo inteiro pula com motivo."""
    _, homolog = ambientes
    url = (homolog.get("PLAT_GARAGE_URL") or "http://127.0.0.1:3900").rstrip("/")
    try:
        requests.get(url, timeout=TEMPO_LIMITE_S)
    except requests.RequestException as e:
        pytest.skip(f"Garage não está de pé em {url} ({type(e).__name__}); nada a medir")
    return url


@pytest.fixture(scope="module")
def cliente_homolog(ambientes, garage):
    """Cliente S3 assinando com a credencial DE HOMOLOGAÇÃO, e só com ela."""
    from app.garage import ClienteS3

    _, homolog = ambientes
    chave_id = homolog.get("PLAT_GARAGE_CHAVE_ID") or ""
    segredo = homolog.get("PLAT_GARAGE_CHAVE_SEGREDO") or ""
    if not (chave_id and segredo):
        pytest.fail(
            "homologação não tem credencial própria de armazenamento (PLAT_GARAGE_CHAVE_ID/"
            "PLAT_GARAGE_CHAVE_SEGREDO ausentes em var/homolog/homolog.env): rode "
            "scripts/garage_homolog_provisionar.sh"
        )
    return ClienteS3(garage, chave_id, segredo, homolog.get("PLAT_GARAGE_REGIAO") or "garage")


def test_homologacao_nao_recebe_token_de_administracao(ambientes):
    """A raiz do achado 11: o arquivo de homologação não pode ter token de administração nenhum — nem o de
    produção nem outro. Sem ele a aplicação entra sozinha no modo de chave própria (app/objetos.py)."""
    _, homolog = ambientes
    assert not (homolog.get("PLAT_GARAGE_ADMIN_TOKEN") or "").strip(), (
        "var/homolog/homolog.env voltou a ter PLAT_GARAGE_ADMIN_TOKEN: com ele homologação administra o "
        "armazenamento inteiro, inclusive os buckets de produção"
    )


def test_nenhum_segredo_de_producao_aparece_no_ambiente_de_homologacao(ambientes):
    """Cláusula literal do portão do item L7-31: 'produção e homologação nunca compartilham banco, bucket,
    chave ou segredo'. A comparação é por VALOR, não por nome: um segredo renomeado continua sendo o mesmo
    segredo. Valores curtos (porta, 'dev', 'sim') não são segredo e sairiam em falso — o corte é 16
    caracteres, abaixo disso nada aqui é credencial. Endereço de serviço em http(s) também não é segredo e
    é compartilhado de propósito (o daemon do Garage é um só nesta máquina), então sai da comparação; o DSN
    do Postgres, que começa com `postgresql://` e carrega a senha da role, continua dentro."""
    from app.settings import SEGREDOS

    producao, homolog = ambientes

    def credencial(valor: str) -> bool:
        return len(valor) >= 16 and not valor.startswith(("http://", "https://"))

    valores_homolog = {v for v in homolog.values() if credencial(v)}
    repetidos = sorted(
        f"{chave} (sha256 {_impressao(valor)})"
        for chave, valor in producao.items()
        if credencial(valor) and valor in valores_homolog
    )
    assert repetidos == [], f"valor de produção repetido em homologação: {repetidos}"
    # e, explicitamente, nenhum dos segredos nomeados do produto
    for nome in SEGREDOS:
        valor = (producao.get(nome) or "").strip()
        if valor:
            assert valor not in valores_homolog, f"{nome} é o MESMO nos dois ambientes (sha256 {_impressao(valor)})"


def test_configuracao_efetiva_de_homologacao_nao_tem_administracao(ambientes):
    """Não basta o token sumir do arquivo de homologação. `app/settings.py::valores_do_ambiente` lê primeiro o
    `.env` da raiz do repositório — que na máquina instalada é o de PRODUÇÃO — e só depois o ambiente do
    processo por cima. Este teste monta a configuração EFETIVA na mesma ordem e exige que ela caia no modo de
    chave própria: sem token de administração e com a chave S3 do ambiente."""
    from app.settings import carregar

    producao, homolog = ambientes
    valores = dict(producao)
    valores.update(homolog)
    efetiva = carregar(valores)
    assert efetiva.PLAT_GARAGE_ADMIN_TOKEN is None, (
        "a configuração efetiva de homologação recebe token de administração vindo do .env de produção; "
        "var/homolog/homolog.env precisa declarar PLAT_GARAGE_ADMIN_TOKEN= (vazio) para anular a herança"
    )
    assert efetiva.PLAT_GARAGE_CHAVE_ID and efetiva.PLAT_GARAGE_CHAVE_SEGREDO
    assert efetiva.PLAT_SCHEMA != "plat", "homologação não pode rodar no schema de produção"


def test_credencial_de_homologacao_nao_lista_bucket_de_producao(cliente_homolog):
    """`ListBuckets` do S3 assinado com a chave de homologação: a resposta é o universo que essa credencial
    enxerga. Nenhum bucket de produção pode estar nela. (Leitura pura: um GET, nada é criado.)"""
    r = cliente_homolog._requisicao("GET", "")
    assert r.status_code == 200, f"ListBuckets com a chave de homologação: {r.status_code} {r.text[:200]}"
    vistos = [n for n in BUCKETS_DE_PRODUCAO if f"<Name>{n}</Name>" in r.text]
    assert vistos == [], f"a credencial de homologação enxerga bucket de produção em ListBuckets: {vistos}"


@pytest.mark.parametrize("bucket", BUCKETS_DE_PRODUCAO)
def test_credencial_de_homologacao_nao_le_bucket_de_producao(cliente_homolog, bucket):
    """Enumerar o conteúdo de `plat-demo`/`plat-demo2` foi exatamente o que o adversário fez. Com a
    credencial de homologação tem de dar 403. Só `GET` com `list-type=2&max-keys=1`: pedido de LEITURA, e
    o que se espera dele é a recusa."""
    r = cliente_homolog._requisicao("GET", bucket, query="list-type=2&max-keys=1")
    assert r.status_code == 403, (
        f"a credencial de homologação listou o bucket de produção {bucket}: {r.status_code} {r.text[:200]}"
    )
    assert "AccessDenied" in r.text


def test_credencial_de_homologacao_nao_e_token_de_administracao(ambientes, garage):
    """O caminho do achado 11 foi a API de administração (:3903), não o S3. Aqui a prova é que o segredo de
    homologação não vale como Bearer nela: `GET /v2/ListBuckets` tem de recusar. É a mesma chamada que o
    adversário usou para enumerar produção, agora com a credencial nova."""
    _, homolog = ambientes
    url = (homolog.get("PLAT_GARAGE_ADMIN_URL") or "http://127.0.0.1:3903").rstrip("/")
    try:
        requests.get(url, timeout=TEMPO_LIMITE_S)
    except requests.RequestException as e:
        pytest.skip(f"API de administração do Garage não está de pé em {url} ({type(e).__name__})")
    for nome in ("PLAT_GARAGE_CHAVE_SEGREDO", "PLAT_GARAGE_CHAVE_ID"):
        valor = (homolog.get(nome) or "").strip()
        if not valor:
            continue
        r = requests.get(
            f"{url}/v2/ListBuckets", headers={"Authorization": f"Bearer {valor}"}, timeout=TEMPO_LIMITE_S
        )
        assert r.status_code in (401, 403), (
            f"{nome} de homologação foi aceito pela API de administração do Garage: {r.status_code} "
            f"{r.text[:200]}"
        )


def test_prefixo_de_bucket_difere_entre_os_dois_ambientes(ambientes):
    """Defesa em profundidade, não isolamento: mesmo que as credenciais fossem iguais o prefixo separaria o
    NOME. O item L7-31 tratava isso como a separação; o adversário mostrou que separa o caminho e não o
    poder. Fica registrado porque continua valendo — e porque o dia em que os dois prefixos coincidirem, a
    colisão de nome de bucket vira erro silencioso."""
    producao, homolog = ambientes
    p = producao.get("PLAT_GARAGE_BUCKET_PREFIXO") or "plat-"
    h = homolog.get("PLAT_GARAGE_BUCKET_PREFIXO") or "plat-"
    assert p != h, f"prefixo de bucket igual nos dois ambientes: {p!r}"
