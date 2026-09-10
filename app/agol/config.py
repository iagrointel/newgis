"""Configuração efetiva da integração AGOL (item L2-08-migracao-agol): `tenant.config.agol` (portal, usuario,
tipo de credencial — 'senha' ou 'token' —, credencial_cifrada, rotulo). Um inquilino, uma credencial (mesmo
recorte de `app/correio/config.py` para SMTP: sem fallback de instalação aqui — não existe conta AGOL "da
casa", cada cliente mantém a própria organização). Este módulo nunca decifra a credencial: `config_tenant_bruta`
devolve a cifra intacta; só `decifrar_credencial` (chamado dentro da rota de teste síncrona ou dentro do job
de publicação) decifra, em memória, sem nunca gravar nem logar o valor em claro."""

from dataclasses import dataclass

PORTAL_PADRAO = "https://www.arcgis.com"


@dataclass(frozen=True)
class ConfigAGOL:
    portal: str
    usuario: str | None
    tipo: str  # 'senha' | 'token'
    credencial_cifrada: str
    rotulo: str | None


def config_tenant_bruta(config: dict | None) -> dict:
    """`tenant.config.agol` (pode faltar); só as chaves conhecidas, o resto é ignorado (mesma regra de
    `app/correio/config.py::config_tenant_bruta` e `app/auth/rotas_org.py`)."""
    agol = (config or {}).get("agol")
    return agol if isinstance(agol, dict) else {}


def agol_efetivo(config: dict | None) -> ConfigAGOL | None:
    bruta = config_tenant_bruta(config)
    cifrada = bruta.get("credencial_cifrada")
    tipo = bruta.get("tipo")
    if not cifrada or tipo not in ("senha", "token"):
        return None
    return ConfigAGOL(
        portal=(bruta.get("portal") or PORTAL_PADRAO).rstrip("/"),
        usuario=(bruta.get("usuario") or None),
        tipo=tipo,
        credencial_cifrada=cifrada,
        rotulo=(bruta.get("rotulo") or None),
    )


def decifrar_credencial(cfg: ConfigAGOL, plat_secret: str, plat_secret_anterior: str | None = None) -> str:
    """Senha da organização ou token, conforme `cfg.tipo`. `plat_secret_anterior` (item L7-19): dupla-chave de
    24h depois de `plat segredo rotacionar PLAT_SECRET` — a credencial cifrada antes da rotação ainda decifra
    com o valor antigo."""
    from app.agol.cifra import decifrar
    from app.seguranca_rotacao import decifrar_com_rotacao

    return decifrar_com_rotacao(decifrar, cfg.credencial_cifrada, plat_secret, plat_secret_anterior)
