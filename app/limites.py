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

# --- catálogo (L0-03; ADR 0004 seção 14)
ITEM_TITULO_MAX = 250
ITEM_RESUMO_MAX = 2048  # snippet da Esri, limite literal
ITEM_DESCRICAO_MAX = 65536
ITEM_CREDITOS_MAX = 2048
ITEM_TAGS_MAX = 50
TAG_MAX = 128
ITEM_CATEGORIAS_MAX = 20
CATEGORIAS_POR_INQUILINO = (200, 50, 900)  # (padrão, mínimo, máximo) em tenant.config.catalogo.categorias_max
CATEGORIA_NIVEIS = 3
CATEGORIA_NOME_MAX = 100
PASTA_PROFUNDIDADE_MAX = 5
PASTA_NOME_MAX = 128
MINIATURA_BYTES_MAX = 10 * 1024 * 1024
MINIATURA_PIXELS_MAX = 25_000_000
MINIATURA_LARGURA = 600
MINIATURA_ALTURA = 400
LINKS_POR_ITEM = 100
LINK_VALIDADE_MAX_DIAS = 365
LINK_TOKEN_BYTES = 32  # 64 hex
RELACOES_POR_ORIGEM = 5000
RELACOES_POR_DESTINO = 50000
RELACAO_PROFUNDIDADE_MAX = 20
VERSOES_VIVAS = 50
VERSOES_BLOCO_COMPACTACAO = 10
VERSAO_COMENTARIO_MAX = 500
FAVORITOS_POR_USUARIO = 500
DESTAQUES_POR_GRUPO = 24
BUSCA_Q_MAX = 1000
BUSCA_TERMOS_MAX = 200
BUSCA_TRGM_LIMIAR = 0.3
BUSCA_REFORCO_STATUS = 0.25
ITENS_PAGINA_MAX = 200
ITENS_DESLOCAMENTO_MAX = 10_000
LIXEIRA_DIAS = 30
COTA_ITENS = 100_000  # padrão por inquilino, tenant.config.catalogo.cota_itens
USADO_POR_PROFUNDIDADE_MAX = 5

# --- contrato de API e limites transversais (L0-12; docs/CONTRATO_API.md e docs/LIMITES.md nascem daqui)
CORPO_MAX_PADRAO_BYTES = 10 * 1024 * 1024        # 10 MiB; toda rota /api,/svc,/ogc,/tiles fora da lista de upload
CORPO_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB (hipótese do item); sem rota isenta ainda (upload = L1-01-e)
