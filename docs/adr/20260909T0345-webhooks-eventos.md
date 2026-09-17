# ADR — Webhooks de eventos por inquilino (L7-08-a-webhooks-eventos)

Estado: aceito (turno plataforma-48, setembro de 2026). Base: `laco/estado.json` item
`L7-08-a-webhooks-eventos` (hipótese, portão de pronto e refutação). Migração
`db/migracoes/20260909T0345_webhooks.sql`; código em `app/webhooks/`.

## 1. Contexto

O item pede: o receptor de teste recebe o evento em ≤ 5 s com assinatura verificável pela biblioteca
de referência do Standard Webhooks; receptor que devolve 500 vê 5 tentativas com intervalos
crescentes e depois desativação com aviso; reenvio manual funciona; entrega idempotente pelo mesmo
`webhook-id`; nenhuma entrega para URL privada (SSRF); log de entregas por inquilino com RLS. A
refutação: forjar entrega sem assinatura e com segredo alheio (o receptor recusa), cadastrar URL
interna e repetir entrega antiga (replay: timestamp fora de 5 min cai na tolerância da biblioteca).

A plataforma já tinha a metade difícil disso: `plat.evento` (migração 003) grava os fatos de domínio
DENTRO da transação da mudança, por `plat.evento_registrar` (SECURITY DEFINER; INSERT direto revogado
a `plat_app`). O que faltava era o consumidor externo: assinatura, retentativa, desativação, reenvio
e log.

## 2. Decisões

1. **Despacho é gatilho AFTER INSERT no PAI particionado de `plat.evento`, não código de rota.** O
   gatilho (`plat.webhook_despachar_evento`) roda com os privilégios de quem efetivamente insere —
   dentro de `evento_registrar`, o dono da função, com RLS contornado — e por isso filtra SEMPRE por
   `NEW.tenant_id` explícito, nunca por GUC de sessão. Toda fonte de evento (hoje `registrar_evento`
   de `app/auth/comum.py` e `app/catalogo/comum.py`) despacha sem que rota nenhuma mude, e a entrega
   nasce atômica com o fato: ou o inquilino vê os dois (evento + entrega agendada) ou nenhum.
2. **A entrega é uma linha em `plat.webhook_entrega` + um job `webhooks.entregar` por entrega.** Quem
   executa é o worker que já existe (L0-05), com retentativa própria (5 tentativas, espera
   `2**tentativa` s em `job_devolver`, migração 006). Não se inventa segundo executador nem segundo
   relógio. O job é `somente_sistema` (o mesmo racional de `correio.enviar`): `POST /api/jobs` com
   este tipo é 403.
3. **`webhook-id` do Standard Webhooks = id da ENTREGA.** Reenvio manual repõe a MESMA entrega em
   'pendente' com o MESMO payload e reenfileira — o receptor deduplica pelo id (idempotência do
   portão) e a resposta da biblioteca de referência verifica de novo sem surpresa.
4. **O corpo sai EXATAMENTE como foi assinado.** A tarefa assina os bytes e os envia sem re-serializar
   (`content=corpo`), porque a assinatura cobre o corpo cru; a verificação do receptor usa o corpo
   recebido verbatim.
5. **Segredo nunca dorme em claro**: AES-GCM com chave derivada de `PLAT_SECRET` + AAD próprio
   (`encwebhook:v1:`), leitura com rotação (`PLAT_SECRET_ANTERIOR`), o mesmo padrão de
   `app/conexao/credencial.py`. O segredo sai da API UMA vez (criar e rotacionar, resposta
   `WebhookSegredo`); listar/detalhe/log/evento nunca o carregam.
6. **Desativação automática é regra de aplicação (tarefa), não gatilho**: precisa ler
   `tenant.config.webhooks.desativar_apos` (clamp 2-100, padrão 20) e enfileirar aviso por e-mail —
   coisas de Python. A conta é de ENTREGAS seguidas falhadas (não de tentativas), incrementada uma
   única vez por entrega (só é chamada quando a entrega passa a 'falhou'); entrega pendente em curso
   adia a desativação (pode ainda entregar e zerar a conta). Desativar narra `webhooks/desativar` e
   avisa os admins com e-mail pela MESMA fila (`correio.enviar`, melhor-esforço).
7. **SSRF: a URL é recusada JÁ na entrada e revalidada no despacho.** Mesma guarda de
   `app/conexao/seguranca.py` (resolução + recusa de loopback/privado/link-local, conexão pinada no
   IP validado, sem redirect), mais a lista de esquemas admitidos
   (`PLAT_WEBHOOK_ESQUEMAS`, padrão só `https` — trilha/homologação pode declarar `https,http` para
   receptor local de teste; a proteção de IP vale para qualquer esquema).
8. **Replay**: a tolerância de ±5 min é da biblioteca de referência, checada ANTES da conferência da
   assinatura — o teste de unidade prova recusa a ±10 min e aceitação a −4 min. A casa não inventa
   tolerância própria; quem quiser replay-proof além disso deduplica por `webhook-id` no receptor.
9. **Assinatura por NOME DE TIPO em `plat.evento_tipo`**: o webhook assina a lista `eventos`
   conferida contra os tipos existentes. Eventos de feição (API do L2-03, pendente) e de qualquer
   outro item futuro entram por configuração, sem código novo. O payload segue o formato de evento da
   Esri (FeatureServer): `id`, `name`, `type`, `op` (created/updated/deleted pelo verbo do tipo),
   `when`, `source` = "plataforma", `alvo`, `ator_id`, `properties`.

## 3. O que não é desta decisão

- **Entrega em tempo real garantida**: a fila tem cota diária, teto de pendentes e espera exponencial;
  webhook aqui é "entrega logo, com rastro", não SLA de streaming.
- **Dupla assinatura na rotação**: o segredo novo vale na PRÓXIMA entrega, sem janela em que os dois
  assinam — quem coordenar a troca no receptor coordena o momento.
- **Repetição de eventos retroativos**: não há replay de histórico de `plat.evento`; o webhook vive do
  futuro dele.

## 4. Provas (a suíte)

`tests/unit/test_webhooks_unidade.py` (10) e `tests/api/test_webhooks.py` (8, um marcado `lento`
porque segura o worker ~2 min). Contra o worker REAL da trilha e receptor `http.server` no IP global
da máquina (nunca loopback: a guarda recusa por definição). Refutação coberta: sem assinatura, com
segredo alheio, corpo forjado, replay ±10 min, URL interna (loopback, link-local, RFC 1918) na criação
e no PATCH, job pela API 403, RLS entre inquilinos, 500 → 5 tentativas (2/4/8/16 s medidos no
receptor) → desativação + evento + aviso SMTP → reativar zera a conta.
