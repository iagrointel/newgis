"""Evento(s) de domínio que cada rota de escrita do L0-02 registra (ADR 0002 seção 9.4).

Duas listas, e nenhuma das duas aceita silêncio (achado G4-03 do ataque ao grupo G4: a lista VAZIA era aceita,
e `POST`/`DELETE /api/arquivos` — que criam e destroem objeto do inquilino — estavam declarados como "sem
evento", de modo que o guardião aprovava destruição de dado sem rastro):

- `EVENTOS_POR_ROTA`: rota que altera estado. **Lista vazia é proibida** (`test_eventos.py` reprova); toda
  entrada tem pelo menos um tipo, e todo tipo citado tem de existir como literal no código de `app/` e como
  linha em `plat.evento_tipo`.
- `ROTAS_SEM_EVENTO`: as poucas rotas de verbo de escrita que NÃO alteram estado (cálculo puro, protocolo Esri
  que usa POST para leitura, parte de um envio que já é narrado pelo início e pela conclusão). Cada entrada
  carrega o MOTIVO escrito, e `test_eventos.py` reprova motivo curto ou ausente, entrada repetida nas duas
  listas, e rota que aparece aqui apesar de o seu módulo chamar `registrar_evento`.

Rota de escrita do OpenAPI que não esteja em uma das duas = falha em `test_eventos.py`. E, desde o mesmo
conserto, `tests/api/test_openapi_contrato.py` garante que o OpenAPI comitado é o da aplicação viva — sem ele
a cobertura media um arquivo velho (achado G4-01).
"""

EVENTOS_POR_ROTA: dict[tuple[str, str], list[str]] = {
    ("POST", "/api/login"): ["usuarios/entrar", "usuarios/falha_login"],
    ("POST", "/api/login/2fa"): ["usuarios/entrar", "usuarios/falha_login"],
    ("POST", "/api/logout"): ["usuarios/sair"],
    ("PUT", "/api/eu"): ["usuarios/atualizar"],
    ("PUT", "/api/eu/senha"): ["usuarios/trocar_senha"],
    ("DELETE", "/api/eu/sessoes"): ["sessoes/revogar"],
    ("DELETE", "/api/eu/sessoes/{id}"): ["sessoes/revogar"],
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
    # ---- arquivos/objetos (L0-11): gravar e apagar objeto do inquilino são eventos de domínio. A decisão
    # anterior ("sem dono humano para narrar") deixava a destruição de dado sem rastro — foi o achado G4-08.
    ("POST", "/api/arquivos"): ["arquivos/enviar"],
    ("DELETE", "/api/arquivos/{sha256}"): ["arquivos/apagar"],
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
    # ---- teto de cota, escrito só pela plataforma (conserto dos achados G4-04/G4-05)
    ("PUT", "/api/plataforma/inquilinos/{id}/cotas"): ["inquilinos/cotas_teto"],
    # ---- convite de membro por e-mail (L0-07-d-smtp-convites)
    ("POST", "/api/convites"): ["convites/criar"],
    ("DELETE", "/api/convites/{id}"): ["convites/cancelar"],
    ("POST", "/api/convites/aceitar"): ["usuarios/convite_aceito"],
    # ---- redefinição de senha por e-mail (L0-07-d-smtp-convites)
    ("POST", "/api/senha/redefinir/solicitar"): ["usuarios/redefinir_senha_pedido"],
    ("POST", "/api/senha/redefinir/aplicar"): ["usuarios/redefinir_senha_email"],
    # ---- SMTP por inquilino (L0-07-d-smtp-convites)
    ("PUT", "/api/org/smtp"): ["org/smtp_configurar", "org/smtp_remover"],
    ("POST", "/api/org/smtp/testar"): ["org/smtp_testar"],
    # ---- foto do próprio perfil (L0-02)
    ("POST", "/api/eu/foto"): ["usuarios/foto_enviar"],
    ("DELETE", "/api/eu/foto"): ["usuarios/foto_remover"],
    # ---- 2FA: iniciar não muda a conta, mas registra a tentativa (não há mais declaração vazia)
    ("POST", "/api/eu/2fa/iniciar"): ["usuarios/2fa_iniciar"],
    # ---- envio retomável em partes (L0-04-a-upload-arquivo)
    ("POST", "/api/uploads"): ["uploads/iniciar"],
    ("POST", "/api/uploads/{id}/concluir"): ["uploads/concluir"],
    ("DELETE", "/api/uploads/{id}"): ["uploads/abortar"],
    # ---- fontes externas registradas (conexões)
    ("POST", "/api/conexoes"): ["conexoes/criar"],
    ("PATCH", "/api/conexoes/{id}"): ["conexoes/editar"],
    ("DELETE", "/api/conexoes/{id}"): ["conexoes/apagar"],
    ("POST", "/api/conexoes/{id}/testar"): ["conexoes/testar"],
    ("POST", "/api/conexoes/{id}/publicar"): ["conexoes/publicar_camada"],
    # ---- importação de arquivo vetorial
    ("POST", "/api/importacoes"): ["importacoes/criar"],
    ("PUT", "/api/importacoes/{id}/confirmar"): ["importacoes/confirmar"],
    ("DELETE", "/api/importacoes/{id}"): ["importacoes/apagar"],
}

# Verbo de escrita que NÃO altera estado. Cada motivo é conferido por test_eventos.py (tamanho mínimo, sem
# repetição na outra lista, e o módulo da rota não pode chamar registrar_evento). Esta lista é curta de
# propósito: crescer aqui é a forma mais fácil de reabrir o buraco do G4-03.
ROTAS_SEM_EVENTO: dict[tuple[str, str], str] = {
    ("POST", "/api/rota"):
        "cálculo de rota sobre dado aberto (OSM) pelo OSRM: nenhuma escrita em plat.*, nenhum objeto criado; "
        "o uso fica em plat.log_acesso (rota, ip, tempo, token_id)",
    ("POST", "/api/matriz"):
        "matriz de distância pelo OSRM: mesmo caso do POST /api/rota, cálculo sem escrita",
    ("POST", "/api/isocrona"):
        "isócrona pelo OSRM: mesmo caso do POST /api/rota, cálculo sem escrita",
    ("POST", "/api/geocodificar"):
        "consulta ao gazetteer: leitura pura, é POST só porque o pedido é um corpo JSON grande demais para a "
        "linha de consulta; o uso fica em plat.log_acesso",
    ("POST", "/api/reverso"):
        "geocodificação reversa: leitura pura, mesmo caso do POST /api/geocodificar",
    ("POST", "/rest/services/Geocodificador/GeocodeServer"):
        "descritor do serviço no protocolo Esri: o mesmo documento do GET, que o cliente ArcGIS também pede "
        "por POST; nenhuma escrita",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"):
        "busca de endereço no protocolo Esri: leitura pura, o cliente ArcGIS usa GET ou POST conforme o "
        "tamanho do pedido",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/reverseGeocode"):
        "geocodificação reversa no protocolo Esri: leitura pura, mesmo caso de findAddressCandidates",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses"):
        "geocodificação em lote no protocolo Esri: leitura pura, só existe como POST porque o lote vai no corpo",
    ("PUT", "/api/uploads/{id}/partes/{n}"):
        "uma parte de um envio retomável: o envio inteiro já é narrado por uploads/iniciar, uploads/concluir e "
        "uploads/abortar; um evento por parte encheria a auditoria de ruído (um arquivo de 1 GiB são 128 partes)",
}
