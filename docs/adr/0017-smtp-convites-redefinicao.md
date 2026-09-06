# ADR 0017 — SMTP, convite de membro por e-mail e redefinição de senha (item L0-07-d-smtp-convites)

Contexto: o ADR 0002 (seções 6.3 e 14) já previa este item como o que falta para dois fluxos que hoje só
existem no caminho manual — "sem e-mail (L0-07-d)" no reset feito pelo admin, e "não há 'esqueci a senha'
público neste item... e-mail depende do SMTP (L0-07-d)". O privilégio `org.integracoes` ("SSO, SMTP,
webhooks, CORS") já estava semeado na migração 003 para isto. Este ADR fecha o item.

## D1. SMTP configurável em dois níveis, nunca obrigatório

`.env` (`PLAT_SMTP_*`, `app/settings.py`) é o padrão da instalação; `tenant.config->'smtp'` (mesma coluna
jsonb que o L0-07-a já usa) é o override por inquilino, resolvido em `app/correio/config.py::smtp_efetivo`
(inquilino vence; sem os dois, `None`). Sem SMTP em lugar nenhum, os fluxos existentes de senha temporária
(`POST /api/usuarios/{id}/senha`) continuam intactos — nada neste item os torna obrigatórios. A senha do
inquilino é cifrada (`app/correio/cifra.py`, AES-GCM com AAD próprio `plat-smtp`, chave derivada de
`PLAT_SECRET`, mesmo desenho do segredo TOTP do L0-02 mas nunca a mesma derivação — um vazamento não abre o
outro); a senha da instalação fica só no `.env`/credential do systemd, como sempre esteve.

## D2. E-mail como job `correio.enviar`, `somente_sistema=True`

Reusa a fila do L0-05 (retentativa, log, progresso) em vez de enviar inline na rota HTTP — a rota devolve
antes de o SMTP responder, e uma falha de rede não vira 500 na ação do admin. A tarefa lê a configuração de
SMTP FRESCA do banco a cada tentativa (nunca grava host/porta/senha nos parâmetros do job, que são visíveis
em `GET /api/jobs/{id}`): a senha só existe em memória entre a leitura e o envio.

`somente_sistema=True` é campo NOVO em `app/jobs/registro.py::Tarefa` (e checado em
`app/jobs/servico.py::criar`, que agora recusa 403 `tipo_somente_sistema` antes do resto). Sem essa marca,
qualquer usuário com `jobs.executar` poderia `POST /api/jobs {"tipo":"correio.enviar", "parametros":
{"destinatario":"...", "assunto":"...", "texto":"..."}}` livremente — usando o SMTP do PRÓPRIO inquilino
como canhão de e-mail arbitrário contra qualquer destinatário. Achado desta sessão ao desenhar o item, não
do adversário; registrado aqui para não se repetir com o próximo tipo de job que precisar do mesmo desenho
(`app/jobs/sistema.py::enfileirar` é o único caminho de criação, chamado pelo próprio backend, nunca pela
rota genérica da fila).

## D3. Convite: o link nunca carrega o e-mail — só o token

`plat.convite` (tenant_id, email, perfil, papel_id, token_hash, expira_em, usado_em, cancelado_em). O link
(`/aceitar-convite?token=...`) tem SÓ o token; `GET /api/convites/resolver` e `POST /api/convites/aceitar`
leem o e-mail/perfil do CONVITE, nunca de um parâmetro da URL ou do corpo — os dois modelos de entrada
(`ConviteAceitarEntrada`, `extra="forbid"`) nem aceitam um campo `email`. Isso fecha por construção (não por
checagem posterior) a refutação "altera o e-mail no link": não há e-mail no link para alterar, e um `email`
extra no corpo do POST vira `422` antes de a rota rodar.

Token de uso único, sha256 guardado (nunca o valor em claro, mesmo padrão de `plat.sessao`/
`plat.token_servico`); validade 7 dias (`CONVITE_VALIDADE_DIAS`); reenviar substitui (cancela) o convite
pendente anterior do mesmo e-mail — nunca acumula tokens vivos para o mesmo destino. Aceitar roda numa única
função SQL `SECURITY DEFINER` (`plat.convite_aceitar`, `FOR UPDATE` na linha do convite) que resolve o
motivo (`ok`/`usado`/`cancelado`/`expirado`/`invalido`/`inquilino_suspenso`) e, só em `ok`, insere
`plat.usuario` e marca o convite usado NA MESMA transação — fecha a corrida de duplo-clique no link.
Motivo diferente de `ok` sempre vira HTTP 410 (portão do item: usado e expirado dão o MESMO status).

Sem SMTP configurado, a rota devolve `link_manual` no corpo da resposta de `POST /api/convites` (mesmo
padrão de "senha temporária mostrada uma vez" que `POST /api/usuarios` já usa) — o admin repassa por outro
canal. Com SMTP, `link_manual` é sempre `null` (o link só existe no e-mail).

## D4. Redefinição de senha: resposta genérica + limite de taxa (refutação do item)

`POST /api/senha/redefinir/solicitar {inquilino, email}` sempre devolve `202 {"ok": true}`, exista ou não a
conta — só `429` quando o limite de taxa estoura. O limite (`plat.redefinicao_solicitar`, SQL
`SECURITY DEFINER`) é por chave `inquilino|e-mail` (não por usuário: teria de existir a conta para contar, e
a contagem em si não pode revelar existência por timing), `REDEFINICAO_MAX_JANELA=5` a cada
`REDEFINICAO_JANELA_MIN=15` minutos — testado disparando 12 pedidos seguidos para o mesmo e-mail
(`tests/api/test_smtp_convites.py::test_redefinicao_ponta_a_ponta_e_limite_de_taxa`), que estoura antes do
fim. `plat.redefinicao_pedido` grava a tentativa MESMO quando o e-mail/inquilino não existe (sem FK de
propósito) — sem isso, o limite de taxa em si vazaria existência (só conta quando a conta existe).

Token de 1 hora (`REDEFINICAO_VALIDADE_HORAS`, mesma validade que o ADR 0002 seção 6.3 já previa), aplicar
reusa a MESMA lógica de troca de senha/histórico/encerramento de sessões de
`app/auth/rotas_eu.py::trocar_senha` (não duplicada: `app/auth/rotas_redefinicao.py::aplicar` abre um
`db.Contexto` normal do usuário-alvo, resolvido por `plat.redefinicao_contexto`, e roda o mesmo SQL) — a
única peça nova é `plat.redefinicao_marcar_usada` (`FOR UPDATE`, compare-and-set), que fecha a corrida de
duplo-envio do mesmo link.

## D5. O que ficou de fora deste turno (registrado, não fingido)

A hipótese original também citava avisos de expiração de token (90/30/7/1 dia, como a Esri) e notificações de
grupo opcionais. Nenhum dos dois está no portão de pronto literal do item — não foram construídos: exigiriam
um periódico cross-tenant (a infraestrutura de periódicos hoje só roda sob o inquilino técnico `plataforma`,
ADR 0003 seção 7) ou tocar a tela de grupos de outra trilha. Ficam como continuação natural do item, usando o
MESMO job `correio.enviar` já pronto — só falta o gatilho.

## Custo de mudar

Trocar o provedor de e-mail (outro serviço transacional em vez de SMTP puro) trocaria só
`app/correio/cliente.py::enviar`; nada em `app/correio/tarefas.py`, nas rotas ou no banco assume SMTP
especificamente além do nome dos campos de configuração. Adicionar SSO/OIDC (L0-08) não colide: usa a MESMA
tabela `tenant.config`, chave diferente.
