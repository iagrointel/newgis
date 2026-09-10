"""Configuração do notebook por inquilino (L2-16-b), lida do ambiente a cada consulta (barato:
strings de ambiente), para que testes e a unidade systemd consigam mudar um parâmetro sem tocar
em app/settings.py — o gateway e os contêineres são RECURSO DE MÁQUINA, não de aplicação.

Defaults: 1 contêiner ativo por vez (a máquina tem ~3 GB livres medidos), CPU 2, RAM 2 GiB,
disco nominal 5 GiB em volume próprio (o driver local do Docker não aplica cota de volume;
o teto aplicado de verdade e testado é o de RAM), ociosidade 30 min, teto de vida 12 h,
partida esperada em até 20 s."""

import os

IMAGEM = "plat-notebook:latest"  # construída por install.sh --imagem-notebook (deploy/notebook/)
REDE = "plat_notebooks"
MEMORIA = "2g"
CPUS = "2"
DISCO = "5g"  # nominal: ver PARIDADE (driver local não cota volume; RAM é o teto aplicado)
OCIOSIDADE_MIN = 30.0  # minutos sem passagem pelo proxy até o ceifador encerrar o contêiner
TETO_HORAS = 12.0  # teto de vida do contêiner, ocioso ou não
ATIVOS_MAX = 1  # padrão 1 contêiner ativo por vez (RAM da máquina); a fila espera ESPERA_FILA_S
ESPERA_FILA_S = 20
PARTIDA_S = 20  # cláusula do portão: contêiner pronto em <= 20 s
PORTA_INTERNA = 8000  # porta do gateway DENTRO da rede docker (nome do contêiner resolve por DNS)
ESCOPOS_TOKEN = ["catalogo:ler", "camada:ler"]  # token de serviço injetado no contêiner
VALIDADE_TOKEN_DIAS = 1


def sufixo() -> str:
    """Sufixo por instalação/trilha, derivado do schema: plat_til216bjupyt -> til216bjupyt,
    plat -> prod. Separa as trilhas entre si (rede, contêiner vigia, socket)."""
    s = (os.environ.get("PLAT_SCHEMA") or "").strip()
    if not s or s == "plat":
        return "prod"
    return s.removeprefix("plat_")


def obter() -> dict:
    """Dicionário de configuração corrente; chaves de ambiente sobrepõem os defaults."""
    s = sufixo()
    return {
        "imagem": os.environ.get("PLAT_NOTEBOOK_IMAGEM") or IMAGEM,
        "rede": os.environ.get("PLAT_NOTEBOOK_REDE") or f"{REDE}-{s}",
        "memoria": os.environ.get("PLAT_NOTEBOOK_MEMORIA") or MEMORIA,
        "cpus": os.environ.get("PLAT_NOTEBOOK_CPUS") or CPUS,
        "disco": os.environ.get("PLAT_NOTEBOOK_DISCO") or DISCO,
        "ociosidade_min": float(os.environ.get("PLAT_NOTEBOOK_OCIOSIDADE_MIN") or OCIOSIDADE_MIN),
        "teto_horas": float(os.environ.get("PLAT_NOTEBOOK_TETO_HORAS") or TETO_HORAS),
        "ativos_max": int(os.environ.get("PLAT_NOTEBOOK_ATIVOS_MAX") or ATIVOS_MAX),
        "espera_fila_s": int(os.environ.get("PLAT_NOTEBOOK_ESPERA_FILA_S") or ESPERA_FILA_S),
        "partida_s": int(os.environ.get("PLAT_NOTEBOOK_PARTIDA_S") or PARTIDA_S),
        "gateway_nome": os.environ.get("PLAT_NOTEBOOK_GATEWAY_NOME") or f"plat-nb-gw-{s}",
        "gateway_porta": int(os.environ.get("PLAT_NOTEBOOK_GATEWAY_PORTA") or PORTA_INTERNA),
        "gateway_uds": os.environ.get("PLAT_NOTEBOOK_GATEWAY_UDS") or f"/tmp/plat-nb-gw-{s}/api.sock",
        # URL da API vista de DENTRO da rede docker. Vazia = o gateway local é levantado sozinho
        # (rede interna + rele por nsenter); quem tem outro arranjo aponta a URL direto.
        "url_api": (os.environ.get("PLAT_NOTEBOOK_URL_API") or "").strip() or None,
        "escopos_token": ESCOPOS_TOKEN,
        "validade_token_dias": VALIDADE_TOKEN_DIAS,
    }


def nome_contenedor(slug: str) -> str:
    return f"plat-nb-{slug}"


def volume(slug: str) -> str:
    return f"plat-nb-{slug}-trabalho"


def base_url(slug: str) -> str:
    # COM a barra final: o jupyter-server exige base_url começando e terminando em "/", e os
    # pontos de frente (proxy, /api/status do levantar) concatenam o caminho direto nela —
    # sem a barra o pedido virava /notebooks/demoapi/status (404 medido na suíte).
    return f"/notebooks/{slug}/"
