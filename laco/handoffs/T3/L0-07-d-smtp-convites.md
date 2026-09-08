# L0-07-d-smtp-convites — SMTP, convite de membro por e-mail e redefinição de senha por e-mail

Papel: backend + frontend + testador + adversário (uma sessão, item completo). Turno 3.

## Veredito

**PARCIAL** — mecanismo inteiro construído, corrigido e verificado de PONTA A PONTA contra o serviço
real (`plat-api`/`plat-worker` em `https://plat.iagrointel.com`, schema `plat` de produção); todas as
cláusulas do portão literal foram exercitadas e passam, EXCETO a captura de tela via navegador (Playwright),
que não foi executada por segurança de RAM da máquina no fechamento do turno (nomeado abaixo, não é
defeito de código). Rebaixado de "entregue" para "parcial" só por essa pendência nomeada.

## Commits (sha, na ordem)

1. `2132603` — SMTP por inquilino, convite de membro, redefinição de senha (implementação completa: schema,
   rotas, job, telas, testes, ADR 0017, docs). 40 arquivos.
2. `3f3c39c` — correção de 3 defeitos reais achados na primeira verificação manual contra o serviço real
   (coluna ambígua em PL/pgSQL, `evento_tipo` faltando, EXECUTE aberto a PUBLIC, RLS sem contexto em duas
   rotas públicas, `memoria_mb` insuficiente do job). Migrações 048 e 049.
3. `00d619a` — correção de 4 defeitos de TESTE achados rodando a suíte de verdade (RLS sem contexto nos
   helpers de teste, destinatário ausente, papel administrativo com perfil errado, pendência de senha).
4. `b0ab3f4` — CHANGELOG do turno.
5. `2fe849d` — renomeia `Convite`/`ConviteEntrada` (meus) para `ConviteMembro`/`ConviteMembroEntrada`:
   colidiam com `Convite`/`ConviteEntrada` já existentes em `app/auth/modelos.py` (convite de GRUPO, ADR
   0002) no componente do OpenAPI. `docs/openapi.json` NÃO foi regenerado neste turno (ver seção própria
   abaixo).

## O que foi construído

- **SMTP por inquilino** (`app/correio/`): `.env` (`PLAT_SMTP_*`, instalação) e `tenant.config->'smtp'`
  (override por inquilino, senha cifrada AES-GCM em `app/correio/cifra.py`, rótulo `plat-smtp` — nunca a
  mesma derivação do TOTP). `GET/PUT /api/org/smtp`, `POST /api/org/smtp/testar` (síncrono, erro legível,
  nunca a senha).
- **E-mail como job** `correio.enviar` (`app/correio/tarefas.py`), campo NOVO `somente_sistema=True` em
  `app/jobs/registro.py` (+ guarda em `app/jobs/servico.py::criar`): impede criação via `POST /api/jobs`
  mesmo por admin — sem isso, qualquer editor com `jobs.executar` usaria o SMTP do inquilino como canhão de
  e-mail arbitrário. Só `app/jobs/sistema.py::enfileirar` (novo) cria o job, chamado pelo próprio backend.
- **Convite de membro** (`plat.convite`, migração 047 + 048 + 049; `app/auth/rotas_convites.py`,
  `app/auth/modelos_convite.py`): link com token de uso único (sha256), validade 7 dias; aceitar roda numa
  função SQL `SECURITY DEFINER` (`FOR UPDATE`) que cria a conta e marca o convite usado na mesma transação;
  o e-mail da conta é SEMPRE o do convite (o corpo do aceite não aceita um campo `email` — `extra="forbid"`).
  Sem SMTP, a resposta devolve `link_manual`.
- **Redefinição de senha por e-mail** (`plat.redefinicao_senha` + `plat.redefinicao_pedido`;
  `app/auth/rotas_redefinicao.py`, `app/auth/modelos_redefinicao.py`): resposta sempre genérica
  (`202 {"ok":true}`), token de 1 hora; limite de taxa por (inquilino, e-mail) — 5 pedidos/15 min, contado
  mesmo para e-mail inexistente. Aplicar reusa a MESMA rotina de troca de senha/histórico/sessões de
  `app/auth/rotas_eu.py::trocar_senha`.
- **Telas**: `/admin/organizacao` (seção SMTP), `/admin/usuarios` (convidar + lista de pendentes),
  `/aceitar-convite` e `/redefinir-senha` (públicas, sem sessão).
- **Documentação**: ADR 0017 (`docs/adr/0017-smtp-convites-redefinicao.md`), MANUAL.md §21,
  docs/PARIDADE.md (nova seção), docs/LIMITES.md (regenerado), CHANGELOG.md.

## Portão de pronto — cláusula por cláusula

Servidor SMTP de captura em stdlib puro (`asyncio`, `tests/api/util_smtp_captura.py` — `aiosmtpd` está
ausente, confirmado antes de escrever qualquer linha).

| cláusula | evidência | estado |
|---|---|---|
| convite chega | `tests/api/test_smtp_convites.py::test_convite_ponta_a_ponta_chega_aceita_cria_conta` (worker REAL processa o job e entrega no capture server) + verificação manual contra `https://plat.iagrointel.com` (script abaixo) | passa |
| link aceita e cria conta | mesmo teste; conta aparece em `GET /api/usuarios`, e-mail da conta = e-mail do convite (não o de um corpo malicioso), login funciona com a senha escolhida | passa |
| link usado de novo = 410 | mesmo teste (`convite_usado`) | passa |
| link após 7 dias = 410 | `test_convite_expirado_apos_7_dias_e_410` (expira por UPDATE direto, RLS com contexto correto) + verificação manual (`convite_expirado`) | passa |
| redefinição chega e troca a senha | `test_redefinicao_ponta_a_ponta_e_limite_de_taxa` (worker real) + verificação manual | passa |
| "testar envio" com host errado devolve erro legível | `test_smtp_testar_com_host_errado_devolve_erro_legivel` (`smtp_falhou`, mensagem cita host, <10 s) | passa |
| senha SMTP nunca aparece em log | `test_senha_smtp_nunca_aparece_no_log_do_worker` (grep no `journalctl` REAL de `plat-worker`+`plat-api`) + verificação manual (grep real) | passa |
| e2e do convite ponta a ponta com captura de tela | `tests/e2e/test_convite.py` ESCRITO, ruff limpo, lógica espelha o que já passou em API — **NÃO EXECUTADO** neste turno | **pendente, nomeado abaixo** |

## Refutação (papel de adversário, rodado por mim mesmo ao fim)

- **Convite expirado**: coberto (`test_convite_expirado_apos_7_dias_e_410` + verificação manual).
- **Convite de outro inquilino / isolamento cruzado**: `test_convite_cancelado_por_outro_inquilino_e_404`
  (RLS: admin de `demo` recebe 404 ao tentar cancelar convite do inquilino temporário) + script manual
  `verif2.py` contra o serviço real (dois inquilinos `zt-verif2a-*`/`zt-verif2b-*`: admin de B recebe 404 ao
  cancelar convite de A, não vê o convite de A na própria lista). PASSA nos dois.
- **Alterar o e-mail do convite no link**: fechado POR CONSTRUÇÃO, não por checagem — o link só carrega o
  token; `ConviteAceitarEntrada` é `extra="forbid"` (Pydantic recusa 422 um campo `email` extra antes de
  qualquer lógica rodar); a conta criada usa sempre `convite.email`, nunca algo vindo da requisição.
  Verificado (`aceitar com email extra no corpo -> 422`, e depois `e-mail da conta = e-mail do CONVITE`).
- **1.000 redefinições/min para o mesmo e-mail**: `plat.redefinicao_solicitar` limita a 5 por (inquilino,
  e-mail) a cada 15 min, contado mesmo para e-mail inexistente (`plat.redefinicao_pedido`, sem FK).
  Verificado com 12 pedidos seguidos: os 5 primeiros `202`, o resto `429` (`test_redefinicao_ponta_a_ponta_e_
  limite_de_taxa` + verificação manual). Refutação PASSA (a defesa se sustenta).
- **`correio.enviar` como canhão de spam via `/api/jobs`** (achado MEU, antes de qualquer refutação externa
  ser necessária): `somente_sistema=True` bloqueia com 403 `tipo_somente_sistema` mesmo para admin
  (`test_correio_enviar_nao_e_criavel_por_post_jobs` + verificação manual).

Nenhuma cláusula da refutação sobreviveu sem defesa.

## Defeitos reais achados (registrados para não se repetirem)

Todos achados rodando de VERDADE contra o serviço real, nunca por leitura de código:

1. `plat.redefinicao_solicitar`: variável PL/pgSQL `chave` colidia com a coluna `redefinicao_pedido.chave`
   ("column reference is ambiguous") — 500 em todo `POST /api/senha/redefinir/solicitar`. Migração 048.
2. 7 tipos de evento novos nunca inseridos em `plat.evento_tipo` — toda `registrar_evento` correspondente
   violava a FK (500 em `PUT/DELETE /api/org/smtp`, `POST /api/convites`, aceitar convite, aplicar
   redefinição). Migração 048.
3. As 6 funções da migração 047 nasceram com `EXECUTE` aberto a `PUBLIC` (ACL padrão do Postgres) —
   `REVOKE`/`GRANT` corrigidos na migração 048 (mesmo padrão de toda função da casa, ex. migração 034).
4. `app/auth/rotas_redefinicao.py` e `rotas_convites.py` buscavam `tenant.config` numa consulta SEM
   contexto de inquilino (a conta ainda não existe) — RLS filtra a linha, `cur.fetchone()` volta `None`,
   500. Corrigido: redefinição usa o `usuario_id` já resolvido para montar um `Contexto`; convite usa o
   `config` que `plat.convite_resolver` já devolve (migração 049 acrescenta a coluna).
5. `correio.enviar` com `memoria_mb=192` (depois `256`) estourava de verdade o `RLIMIT_DATA` do filho —
   `cryptography` é importado pela primeira vez DEPOIS do fork neste tipo de job. Subiu para `512`.
6. `tests/api/util_smtp_captura.py::Mensagem` lia o corpo cru como string ingênua — texto em português
   força `quoted-printable` (acentos), e a dobra de linha em 76 colunas partia o LINK no meio do token,
   acusando um bug que não existe do lado do produto (um cliente de e-mail de verdade decodifica MIME).
   Corrigido com `email.message_from_string(policy=email.policy.default)`.
7. `ConviteEntrada`/`Convite` (meus, `app/auth/modelos_convite.py`) colidiam em nome com os modelos JÁ
   EXISTENTES do convite de GRUPO (`app/auth/modelos.py`, ADR 0002) no mesmo componente OpenAPI — um
   sobrescrevia o outro silenciosamente na documentação gerada. Renomeados para
   `ConviteMembro`/`ConviteMembroEntrada` (commit `2fe849d`).
8. Quatro defeitos DE TESTE (não de produto): RLS sem contexto nos helpers `_expirar_convite`/
   `_expirar_redefinicao` (o UPDATE "passava" sem nunca expirar nada de verdade); `POST /api/org/smtp/testar`
   sem `destinatario` explícito quando o admin de teste não tem e-mail; papel de teste com privilégio
   administrativo (`membros.gerir`) exigindo `perfil_minimo=admin`, mas o usuário de teste nascia `editor`;
   pendência `trocar_senha` bloqueando a ação seguinte por faltar `PUT /api/eu/senha` no fluxo do teste.

## Como foi verificado (dois métodos independentes)

1. **`pytest` formal, sob `flock /home/dev/plataforma/laco/.pytest.lock`** (congestão real do laço — múltiplas
   sessões concorrentes disputando o mesmo lock por dezenas de minutos neste turno; documentado, não é
   bloqueio deste item): `tests/api/test_smtp_convites.py` (17 casos) + `tests/unit/test_correio_cifra.py`
   (5) + `tests/unit/test_correio_cliente.py` (4) — **23/23 passam** rodando de verdade contra o schema
   `plat` de produção (`venv/bin/pytest tests/api/test_smtp_convites.py tests/unit/test_correio_cifra.py
   tests/unit/test_correio_cliente.py tests/api/test_docs.py -q`). `test_docs.py` incluso só para conferir
   que a mudança de nome de modelo (achado 7) não quebrou Swagger.
2. **Verificação manual contra o serviço REAL** (`https://plat.iagrointel.com`, fora do TestClient, sem
   mock nenhum): dois scripts em `/tmp/.../scratchpad/verificacao_manual_l0_07_d.py` e `verif2.py` (não
   fazem parte do repositório — só evidência desta sessão), cobrindo os MESMOS 27 pontos do portão + a
   refutação, incluindo grep direto no `journalctl` real do `plat-worker`/`plat-api` para a cláusula da
   senha. **Todas as verificações passam** nas duas rodadas finais (depois das correções).

## Pendência nomeada (por isso "parcial", não "entregue")

**`tests/e2e/test_convite.py` (Playwright) não foi executado.** O arquivo existe, passa `ruff check`, e a
lógica espelha exatamente o fluxo já provado passar via API (convite → `/aceitar-convite` → formulário →
conta criada → login). Não rodei porque, no fechamento deste turno, `free -h` mediu swap em 7,7/8,0 GiB
(múltiplas sessões concorrentes no laço) — a casa já teve pelo menos um incidente de OOM documentado por
lançar Chromium sob pressão de memória parecida (ver `CLAUDE.md`/skill, "regras que já custaram caro").
Rodar `make e2e` (ou só `pytest tests/e2e/test_convite.py -m lento --base-url https://plat.iagrointel.com`,
sob o mesmo flock) assim que `free -h` mostrar folga real resolve isto sem tocar em código.

## Fora do portão literal deste turno (registrado no ADR 0017 §D5, não fingido)

Avisos de expiração de token de serviço (90/30/7/1 dia, como a Esri) e notificação de grupo por e-mail —
a hipótese original do item citava os dois, mas nenhum está no texto literal do portão. Exigiriam um
periódico CROSS-TENANT (hoje a infraestrutura de periódicos só roda sob o inquilino técnico `plataforma`,
ADR 0003 §7) ou mexer na tela de grupos (outra trilha). O job `correio.enviar` já está pronto para os dois
— falta só o gatilho.

## Para quem continuar

- Rodar `tests/e2e/test_convite.py` quando houver RAM livre (é o único item realmente pendente).
- `docs/openapi.json` está desatualizado (não só por este item — geocodificador e outras trilhas também
  faltam); quando alguém regenerar, vai puxar tudo junto. Não é bloqueio deste item.
- Hipótese não construída (avisos de expiração/notificação de grupo) pode virar sub-item novo
  (`L0-07-d-e-avisos-expiracao`, por exemplo) se o dono quiser — o job já serve.
