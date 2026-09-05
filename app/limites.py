"""Limites e faixas da plataforma, um lugar só (ADR 0002 seção 11; docs/LIMITES.md do L0-12 é gerado daqui).
Cada trilha acrescenta a sua seção abaixo da anterior; nenhuma edita a seção de outra."""

# --- identidade (L0-02)
# política de senha, sessão, bloqueio e token: (padrão, mínimo, máximo) por chave de tenant.config.auth
AUTH_PADROES: dict[str, tuple] = {
    "senha_min": (8, 8, 64),
    "senha_maiuscula": (False, None, None),
    "senha_minuscula": (False, None, None),
    "senha_simbolo": (False, None, None),
    "senha_historico": (5, 0, 24),
    "senha_expira_dias": (0, 0, 365),  # 0 = nunca; fora de 0 a faixa válida é 30–365 (politica.py corta)
    "bloqueio_tentativas": (5, 3, 10),
    "bloqueio_minutos": (15, 5, 60),
    "sessao_ociosa_horas": (12, 1, 24),
    "sessao_max_dias": (7, 1, 30),
    "exigir_2fa": (False, None, None),
    "token_max_dias": (365, 1, 365),
    "token_padrao_dias": (90, 1, 365),
    "dominios_email": ([], 0, 20),
    "compartilhar_publico": (False, None, None),
}
SENHA_MAX = 128  # fixo: pbkdf2 sobre 128 bytes evita DoS por senha longa
SENHA_EXPIRA_MIN_DIAS = 30
BLOQUEIO_JANELA_MIN = 15  # fixo (ADR 0002 seção 6.2)
DESAFIO_2FA_MIN = 5
TOTP_JANELA_PASSOS = 1
CODIGOS_RECUPERACAO = 8
SENHA_TEMPORARIA_TAMANHO = 12
TOKENS_POR_USUARIO = 20
GRUPOS_POR_USUARIO = 512
GRUPO_TAGS_MAX = 50
GRUPO_NOME_MAX = 128
GRUPO_RESUMO_MAX = 2048
PAPEL_NOME_MAX = 128
PAPEL_DESCRICAO_MAX = 250
LOTE_MAX = 100
LOG_JANELA_DIAS = 92
LOG_LIMITE_MAX = 1000
LOG_CSV_MAX = 100_000
LOG_RETENCAO_MESES = 12
PAGINA_PADRAO = 50
PAGINA_MAX = 1000
RESTRICAO_MAX = 20
TOKEN_ROTACAO_HORAS = 24
