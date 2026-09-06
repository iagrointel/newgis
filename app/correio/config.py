"""Configuração efetiva de SMTP (item L0-07-d-smtp-convites; ADR 0013): `tenant.config.smtp` quando o
inquilino configurou o próprio (host, porta, tls, usuario, senha_cifrada, remetente, rotulo), senão as chaves
`PLAT_SMTP_*` da instalação (`app/settings.py`), senão nenhum — os fluxos de e-mail caem no caminho manual já
existente (ADR 0002 seção 6.3). Este módulo nunca decifra a senha: `origem_config` devolve a cifra intacta;
só `app/correio/cliente.py::enviar` (dentro do job, ou na rota síncrona de teste) chama `cifra.decifrar`, e
só em memória — nada aqui grava nem loga a senha em claro."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigSMTP:
    host: str
    porta: int
    tls: bool
    usuario: str | None
    senha_cifrada: str | None
    remetente: str
    rotulo: str | None
    origem: str  # 'inquilino' | 'instalacao'


def config_tenant_bruta(config: dict | None) -> dict:
    """`tenant.config.smtp` (pode faltar); só as chaves conhecidas, o resto é ignorado como qualquer chave
    futura de outro item (mesma regra de `app/auth/rotas_org.py`)."""
    smtp = (config or {}).get("smtp")
    return smtp if isinstance(smtp, dict) else {}


def smtp_efetivo(config: dict | None, settings: Any) -> ConfigSMTP | None:
    bruta = config_tenant_bruta(config)
    host = (bruta.get("host") or "").strip()
    if host:
        remetente = (bruta.get("remetente") or "").strip()
        return ConfigSMTP(
            host=host,
            porta=int(bruta.get("porta") or 587),
            tls=bool(bruta.get("tls", True)),
            usuario=(bruta.get("usuario") or "").strip() or None,
            senha_cifrada=bruta.get("senha_cifrada") or None,
            remetente=remetente or (bruta.get("usuario") or "").strip() or "",
            rotulo=(bruta.get("rotulo") or "").strip() or None,
            origem="inquilino",
        )
    if settings.PLAT_SMTP_HOST:
        return ConfigSMTP(
            host=settings.PLAT_SMTP_HOST,
            porta=settings.PLAT_SMTP_PORTA,
            tls=settings.PLAT_SMTP_TLS,
            usuario=settings.PLAT_SMTP_USUARIO,
            # instalação: guardado em claro só no .env/credential do systemd, nunca cifrado (não é por-inquilino)
            senha_cifrada=settings.PLAT_SMTP_SENHA,
            remetente=settings.PLAT_SMTP_REMETENTE or settings.PLAT_SMTP_USUARIO or "",
            rotulo=settings.PLAT_SMTP_ROTULO,
            origem="instalacao",
        )
    return None


def decifrar_senha(cfg: ConfigSMTP, plat_secret: str) -> str | None:
    if not cfg.senha_cifrada:
        return None
    if cfg.origem == "instalacao":
        return cfg.senha_cifrada  # PLAT_SMTP_SENHA nunca passa pela cifra (não há coluna de banco a proteger)
    from app.correio.cifra import decifrar

    return decifrar(cfg.senha_cifrada, plat_secret)
