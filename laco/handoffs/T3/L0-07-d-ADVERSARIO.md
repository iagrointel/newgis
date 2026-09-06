# Adversário — L0-07-d-smtp-convites (convite de membro + redefinição de senha)

**Veredito: PASSA nos vetores atacados.** Item recém-entregue (`parcial`, e2e de navegador ainda
pendente por segurança de RAM) pelo agente construtor desta mesma sessão; revisão independente
feita depois, sem ver o raciocínio do construtor além do handoff público. Ataque ao vivo contra
`plat-api` real (`127.0.0.1:8150`).

## Ataques e evidência literal

1. **Convite de uso único.** Criei convite, aceitei (`200 ok`, conta criada), tentei aceitar de
   novo com o MESMO token -> `410 convite_usado`. `GET /api/convites/resolver` no mesmo token
   depois de usado -> `410 convite_usado` (não volta a dizer "ok"). PASSA.

2. **Convite cancelado não pode ser aceito.** `DELETE /api/convites/{id}` -> `204`; tentativa de
   aceitar o token cancelado -> `410 convite_cancelado`. PASSA.

3. **Token forjado.** `conv_<32 bytes aleatórios>` nunca emitido pelo servidor -> `410
   convite_invalido`. PASSA — sem distinção observável entre "nunca existiu" e "expirou/cancelado"
   (não vaza qual).

4. **"Altera o e-mail no link" — fechado por construção, confirmado por leitura e por ataque.** O
   link de convite carrega só o token (`/aceitar-convite?token=...`); não existe parâmetro de
   e-mail para adulterar. `POST /api/convites/aceitar` sempre lê o e-mail do CONVITE (via
   `convite_resolver`/`convite_aceitar`), nunca do corpo do pedido — o corpo nem aceita um campo
   `email`. Não há vetor de ataque aqui porque não há superfície.

5. **Rate limit de redefinição de senha.** 5 pedidos de `/api/senha/redefinir/solicitar` para o
   mesmo e-mail respondem `202 {"ok":true}` (resposta sempre genérica, não revela se o e-mail
   existe); o 6o -> `429 muitas_tentativas "aguarde 15 minutos"`. Bate exatamente com o que o
   handoff do construtor alegou (5/15min) — confirmado de fora, não só por leitura do código.

6. **Domínio de e-mail do convite.** `email_permitido` é permissivo por padrão quando o inquilino
   não configurou `dominios_email` (lista vazia = sem restrição) — confirmei isso por leitura
   (`app/auth/politica.py`) antes de testar, para não marcar como achado um comportamento
   default-aberto intencional. Convite para domínio externo no inquilino `demo` (sem restrição
   configurada) -> `201`, como esperado nesse caso. Não testei um inquilino COM
   `dominios_email` configurado — pendência nomeada abaixo.

## O que ESTE laudo NÃO cobre

- Inquilino com `dominios_email` configurado de verdade (só testei o caso permissivo-padrão).
- Corrida real entre duas aceitações simultâneas do mesmo convite (só sequencial).
- O e2e de navegador do próprio item continua não executado (pendência já nomeada no
  `estado.json` pelo construtor, por causa de RAM — não é escopo deste laudo de API).
- Conteúdo do e-mail de fato entregue por SMTP real (só testei o caminho sem SMTP configurado,
  via `link_manual`) — não montei um servidor SMTP de captura para conferir o texto que sairia.

## Conclusão

6 vetores atacados, 0 achados. O ponto mais forte do desenho é o convite não ter e-mail no link —
elimina uma classe inteira de ataque por construção em vez de por validação. Recomendo, antes de
promover o item a `entregue`, rodar o e2e de navegador already-written quando houver RAM, e testar
o domínio de e-mail restrito de verdade.
