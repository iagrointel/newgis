"""Evento(s) de domínio que cada rota de escrita do L0-02 registra (ADR 0002 seção 9.4). Rota de escrita no
OpenAPI sem entrada aqui = falha em test_eventos.py. Lista vazia = a rota, por decisão, não gera evento
(login falho comum, logout sem sessão, leituras) e o motivo está ao lado."""

EVENTOS_POR_ROTA: dict[tuple[str, str], list[str]] = {
    ("POST", "/api/login"): ["usuarios/entrar", "usuarios/falha_login"],
    ("POST", "/api/login/2fa"): ["usuarios/entrar", "usuarios/falha_login"],
    ("POST", "/api/logout"): ["usuarios/sair"],
    ("PUT", "/api/eu"): ["usuarios/atualizar"],
    ("PUT", "/api/eu/senha"): ["usuarios/trocar_senha"],
    ("DELETE", "/api/eu/sessoes"): ["sessoes/revogar"],
    ("DELETE", "/api/eu/sessoes/{id}"): ["sessoes/revogar"],
    ("POST", "/api/eu/2fa/iniciar"): [],  # só liga no confirmar; iniciar sem confirmar não muda o estado da conta
    ("POST", "/api/eu/2fa/confirmar"): ["usuarios/2fa_ligar"],
    ("POST", "/api/eu/2fa/desativar"): ["usuarios/2fa_desligar"],
    ("POST", "/api/eu/2fa/codigos"): ["usuarios/2fa_codigos"],
    ("POST", "/api/papeis"): ["papeis/criar"],
    ("PUT", "/api/papeis/{id}"): ["papeis/atualizar"],
    ("DELETE", "/api/papeis/{id}"): ["papeis/apagar"],
    ("POST", "/api/usuarios"): ["usuarios/criar"],
    ("POST", "/api/usuarios/lote"): ["usuarios/papel", "usuarios/desabilitar", "usuarios/reabilitar"],
    ("PUT", "/api/usuarios/{id}"): [
        "usuarios/atualizar",
        "usuarios/papel",
        "usuarios/desabilitar",
        "usuarios/reabilitar",
    ],
    ("DELETE", "/api/usuarios/{id}"): ["usuarios/apagar"],
    ("POST", "/api/usuarios/{id}/senha"): ["usuarios/redefinir_senha"],
    ("POST", "/api/usuarios/{id}/2fa/desativar"): ["usuarios/2fa_desligar"],
    ("POST", "/api/usuarios/{id}/desbloquear"): ["usuarios/desbloquear"],
    ("POST", "/api/grupos"): ["grupos/criar"],
    ("PUT", "/api/grupos/{id}"): ["grupos/atualizar", "grupos/transferir"],
    ("DELETE", "/api/grupos/{id}"): ["grupos/apagar"],
    ("POST", "/api/grupos/{id}/membros"): ["grupos/convidar"],
    ("POST", "/api/grupos/{id}/entrar"): ["grupos/entrar", "grupos/pedir"],
    ("POST", "/api/grupos/{id}/aceitar"): ["grupos/entrar"],
    ("POST", "/api/grupos/{id}/recusar"): ["grupos/recusar"],
    ("POST", "/api/grupos/{id}/membros/{uid}/aprovar"): ["grupos/aprovar"],
    ("PUT", "/api/grupos/{id}/membros/{uid}"): ["grupos/papel"],
    ("DELETE", "/api/grupos/{id}/membros/{uid}"): ["grupos/sair", "grupos/remover"],
    ("POST", "/api/tokens"): ["tokens/criar"],
    ("POST", "/api/tokens/{id}/renovar"): ["tokens/renovar"],
    ("DELETE", "/api/tokens/{id}"): ["tokens/revogar"],
    ("POST", "/api/plataforma/inquilinos"): ["inquilinos/criar"],
    ("POST", "/api/plataforma/inquilinos/{id}/suspender"): ["inquilinos/suspender"],
    ("POST", "/api/plataforma/inquilinos/{id}/reativar"): ["inquilinos/reativar"],
    ("DELETE", "/api/plataforma/inquilinos/{id}"): ["inquilinos/apagar"],
    # ---- fila de jobs (L0-05; vocabulário na migração 007)
    ("POST", "/api/jobs"): ["jobs/criar"],
    ("POST", "/api/jobs/{job_id}/cancelar"): ["jobs/cancelar"],
    ("POST", "/api/jobs/{job_id}/repetir"): ["jobs/criar"],
    ("POST", "/api/agendas"): ["agendas/criar"],
    ("PUT", "/api/agendas/{agenda_id}"): ["agendas/atualizar"],
    ("DELETE", "/api/agendas/{agenda_id}"): ["agendas/apagar"],
    ("POST", "/api/agendas/{agenda_id}/pausar"): ["agendas/pausar"],
    ("POST", "/api/agendas/{agenda_id}/retomar"): ["agendas/retomar"],
    ("POST", "/api/agendas/{agenda_id}/rodar-agora"): ["jobs/criar"],
    # ---- catálogo (L0-03; vocabulário na migração 011)
    ("POST", "/api/itens"): ["itens/adicionar"],
    ("POST", "/api/acervo/{fonte_id}/adicionar"): ["itens/adicionar", "acervo/adicionar_recusado_pii"],
    ("PUT", "/api/itens/{id}"): ["itens/atualizar", "itens/status", "itens/proteger", "itens/desproteger"],
    ("PATCH", "/api/itens/{id}"): ["itens/atualizar", "itens/status", "itens/proteger", "itens/desproteger"],
    ("DELETE", "/api/itens/{id}"): ["itens/apagar"],
    ("POST", "/api/itens/lote"): ["itens/apagar", "itens/restaurar", "itens/mover", "itens/atualizar", "itens/proteger",
                                  "itens/desproteger", "itens/status", "compartilhamento/alterar"],
    ("POST", "/api/itens/transferir"): ["itens/transferir"],
    ("POST", "/api/itens/{id}/mover"): ["itens/mover"],
    ("POST", "/api/itens/{id}/miniatura"): ["itens/miniatura"],
    ("POST", "/api/itens/{id}/miniatura/gerar"): ["itens/miniatura"],
    ("DELETE", "/api/itens/{id}/miniatura"): ["itens/miniatura"],
    ("POST", "/api/itens/{id}/versoes/{n}/restaurar"): ["itens/atualizar", "itens/versao_restaurar"],
    ("POST", "/api/itens/{id}/versoes/{n}/publicar"): ["itens/versao_publicar"],
    ("PUT", "/api/itens/{id}/relacoes"): ["itens/relacoes"],
    ("PUT", "/api/itens/{id}/compartilhamento"): ["compartilhamento/alterar"],
    ("POST", "/api/itens/{id}/links"): ["compartilhamento/link_criar"],
    ("DELETE", "/api/itens/{id}/links/{lid}"): ["compartilhamento/link_revogar"],
    ("POST", "/api/pastas"): ["pastas/criar"],
    ("PUT", "/api/pastas/{id}"): ["pastas/renomear", "pastas/mover"],
    ("DELETE", "/api/pastas/{id}"): ["pastas/apagar"],
    ("PUT", "/api/categorias"): ["categorias/alterar"],
    ("POST", "/api/categorias/importar"): ["categorias/importar"],
    ("PUT", "/api/favoritos/{item_id}"): ["favoritos/adicionar"],
    ("DELETE", "/api/favoritos/{item_id}"): ["favoritos/remover"],
    ("POST", "/api/lixeira/{id}/restaurar"): ["itens/restaurar"],
    ("POST", "/api/lixeira/esvaziar"): ["lixeira/esvaziar"],
    # ---- arquivos/objetos (L0-11): sem dono humano (usuário/grupo/token) para narrar num evento de domínio; a
    # auditoria do objeto é a própria linha em plat.arquivo (quem gravou, quando, sha256) + plat.log_acesso da
    # requisição (rota, ip, bytes, token_id) — o mesmo padrão de decisão já usado acima em /api/eu/2fa/iniciar
    ("POST", "/api/arquivos"): [],
    ("DELETE", "/api/arquivos/{sha256}"): [],
    # ---- rede de rota (L2-11-c): cálculo sobre dado aberto (OSM), sem escrita em `plat.*` e sem dono humano —
    # não há o que narrar num evento de domínio (mesma decisão de /api/arquivos acima)
    ("POST", "/api/rota"): [],
    ("POST", "/api/matriz"): [],
    ("POST", "/api/isocrona"): [],
    # ---- LDAP/Active Directory (L0-08-d): login registra a MESMA sequência do login local, reaproveitada de
    # _abrir_sessao ("usuarios/entrar"), mais o provisionamento automático (criação ou sincronização do
    # usuário a partir do diretório); administração do provedor tem vocabulário próprio ("org/*")
    ("POST", "/api/login/ldap"): ["usuarios/criar", "usuarios/atualizar", "usuarios/entrar"],
    ("PUT", "/api/org/ldap"): ["org/ldap_configurar"],
    ("POST", "/api/org/ldap/importar"): ["org/ldap_importar"],
    # ---- configurações da organização (L0-07-a-configuracoes-org)
    ("PUT", "/api/org"): ["org/configurar"],
    ("POST", "/api/org/logo"): ["org/logo_enviar"],
    ("DELETE", "/api/org/logo"): ["org/logo_remover"],
    # ---- trilha de auditoria (L7-20-trilha-auditoria)
    ("PUT", "/api/auditoria/config"): ["auditoria/retencao"],
    # ---- BLOCO ACRESCENTADO NO L7-20 (rotas que já existiam no código e nunca entraram aqui).
    # `docs/openapi.json` estava parado em 94 rotas de escrita enquanto a aplicação já publicava 112, e por
    # isso este teste já reprovava em master com 10 rotas faltando. Ao regerar o arquivo (P9: rota nova exige
    # openapi atualizado) as que faltavam passaram a 27. O evento de cada uma foi LIDO no código, uma a uma,
    # com `grep -n registrar_evento` no módulo da rota — não é chute. Bloco contíguo de propósito: se outra
    # trilha declarar as mesmas, o conflito é um pedaço só.
    # conexões externas (L6-02, app/conexao/rotas.py)
    ("POST", "/api/conexoes"): ["conexoes/criar"],
    ("PATCH", "/api/conexoes/{id}"): ["conexoes/editar"],
    ("DELETE", "/api/conexoes/{id}"): ["conexoes/apagar"],
    ("POST", "/api/conexoes/{id}/testar"): ["conexoes/testar"],
    ("POST", "/api/conexoes/{id}/publicar"): ["conexoes/publicar_camada"],
    # convites de membro (L0-07-d, app/auth/rotas_convites.py)
    ("POST", "/api/convites"): ["convites/criar"],
    ("DELETE", "/api/convites/{id}"): ["convites/cancelar"],
    ("POST", "/api/convites/aceitar"): ["usuarios/convite_aceito"],
    # foto do próprio usuário (app/auth/rotas_eu.py)
    ("POST", "/api/eu/foto"): ["usuarios/foto_enviar"],
    ("DELETE", "/api/eu/foto"): ["usuarios/foto_remover"],
    # ingestão vetorial (L0-04, app/ingestao/rotas.py)
    ("POST", "/api/importacoes"): ["importacoes/criar"],
    ("PUT", "/api/importacoes/{id}/confirmar"): ["importacoes/confirmar"],
    # apagar importação ainda não confirmada é descartar rascunho do próprio autor, sem efeito no catálogo: a
    # linha em plat.importacao e o log_acesso já contam a história (mesma decisão de /api/arquivos acima)
    ("DELETE", "/api/importacoes/{id}"): [],
    # upload retomável (L0-04-a, app/uploads/rotas.py)
    ("POST", "/api/uploads"): ["uploads/iniciar"],
    ("POST", "/api/uploads/{id}/concluir"): ["uploads/concluir"],
    ("DELETE", "/api/uploads/{id}"): ["uploads/abortar"],
    # parte de upload: pedaço de bytes de um upload que já tem evento de início e de conclusão; um evento por
    # parte encheria a trilha sem acrescentar fato novo
    ("PUT", "/api/uploads/{id}/partes/{n}"): [],
    # SMTP do inquilino (L0-07-d, app/correio/rotas_smtp.py)
    ("PUT", "/api/org/smtp"): ["org/smtp_configurar", "org/smtp_remover"],
    ("POST", "/api/org/smtp/testar"): ["org/smtp_testar"],
    # redefinição de senha por e-mail (app/auth/rotas_redefinicao.py). Solicitar é PÚBLICO e responde igual
    # exista ou não a conta; registrar evento ali diria, para quem lesse a trilha, que o login existe
    ("POST", "/api/senha/redefinir/solicitar"): [],
    ("POST", "/api/senha/redefinir/aplicar"): ["usuarios/redefinir_senha_email"],
    # geocodificação (L2-11-b): consulta sobre dado aberto (CNEFE), POST só por causa do tamanho do corpo;
    # não muda estado e não tem dono humano — mesma decisão de /api/rota e /api/matriz acima
    ("POST", "/api/geocodificar"): [],
    ("POST", "/api/reverso"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer/reverseGeocode"): [],
}
