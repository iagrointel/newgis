# ADR — administração do inquilino: porta única, acervo com licença, diretório LDAP e evento registrado (UX-06)

Data: setembro de 2026. Estado: aceito. Trilha de interface.

## Contexto
A administração do inquilino existia em seis telas soltas (usuários, grupos, papéis, tokens, log, organização), cada
uma alcançada só pela barra lateral e sem um lugar que dissesse "como está o inquilino". Quatro rotas do backend
não tinham controle nenhum (`GET/PUT /api/org/ldap`, `POST /api/org/ldap/importar`, `GET /api/usuarios/{id}`), o
acervo da casa (`/api/acervo`, três rotas) não tinha tela, `PUT /api/papeis/{id}` aparecia como "sem controle" por
um defeito do gerador de cobertura, e uma escrita administrativa não dizia ao operador que ficara registrada.

## Decisão
1. **`/admin` é a porta única**, não uma tela que refaz as seis. Um cartão por assunto com o número que importa,
   lido da rota que já existe (`/api/usuarios?limite=1` dá o total sem trazer a lista; `/api/org` dá cota e uso;
   `/api/convites` só devolve pendentes), e o caminho da tela que gere o assunto. Cartão só com o privilégio da
   tela; a entrada na barra lateral aceita uma lista "ou" de privilégios (`qualquer` em `TELAS`). Quem não tem
   nenhum privilégio administrativo vê o `<plat-estado>` "sem permissão" com dois caminhos de volta (refutação do
   item: 403 amigável, nunca tela quebrada); as telas filhas continuam com o `semPermissao` do `exigirSessao`.
2. **Acervo é tela de administração** (`/admin/acervo`): só fontes com licença escrita chegam à API (regra D17) e
   a ficha mostra exatamente o que o registro tem — endereço, licença, método, frescor, sha256, comando de
   reexecução, endereços testados — com "não registrado" onde falta. "Adicionar ao catálogo" chama a rota que já
   existe; o `409 confirmacao_pii_exigida` vira um diálogo com o motivo e a segunda chamada leva
   `confirma_risco_pii` só depois do clique (a tela nunca confirma sozinha). Fecha UX-10.
3. **LDAP vive em `/admin/organizacao`**, como mais uma seção de configuração, não uma tela nova: a senha de bind
   só sobe quando preenchida e nunca volta (`tem_bind_senha`); "habilitar" exige endereço com esquema `ldap(s)://`;
   o mapa grupo → perfil é uma linha por grupo e é conferido no cliente antes do PUT. A importação de grupo é um
   segundo formulário e o `409 ldap_sem_configuracao` aparece nomeado nele. `POST /api/login/ldap` (a entrada do
   usuário final) fica para UX-17: `/api/login/provedores` ainda não diz se o inquilino tem LDAP, e a tela de
   entrada não deve mostrar um botão que devolve "desabilitado" para a maioria.
4. **Toda escrita administrativa mostra o evento registrado.** `comum.js::eventoRegistrado()` lê o evento mais
   recente do inquilino (`GET /api/eventos?limite=1&desde=agora-20s`) e o mostra com tipo, hora e ator e o caminho
   para `/admin/log?aba=eventos&tipo=…`; sem `org.log_ver` ou sem evento recente não mostra nada — nunca finge um
   registro. O log ganhou link profundo (`?aba=eventos&tipo=` e `?usuario_id=`) para essas setas apontarem.
5. **Estados explícitos** pelo `<plat-estado>` nas seis telas (`comum.js::estadoDeLista`): carregando antes do
   primeiro pedido, erro com referência e "tentar de novo", negado, vazio com a ação que cabe (criar, limpar
   filtros, mudar de aba). A tabela some no vazio de lista (o cabeçalho sem linha não é controle aqui, ao
   contrário de Tarefas, cujo cabeçalho ordena no servidor).
6. **Gerador de cobertura**: o método de um literal é o da chamada imediatamente anterior a ele na linha
   (`_metodo_antes_do_literal`), não o primeiro nome que aparece na linha. Com isso `PUT /api/papeis/{id}` sai da
   lista de lacunas sem mexer em `papeis.js`; teste unitário cobre o caso.

## Consequências
- `/admin` faz até dez pedidos pequenos em paralelo; todos são de leitura e cada um tem cartão de erro próprio
  (um 500 num assunto não derruba o resto).
- A refutação com perfil `visualizador` depende de criar a sessão direto no banco da trilha (`tests/jobs_sessao`),
  como já faz `test_tarefas`; o e2e pula com a razão escrita quando `PLAT_DSN` não está no ambiente.
- O aviso de evento registrado é uma leitura a mais por escrita (só com `org.log_ver`); custo desprezível e
  desligável apagando o `<p id="evento-registrado">` da página.

## Alternativas recusadas
- Uma tela única com abas que reimplementa usuários, grupos, papéis e tokens: duplicaria mil linhas testadas e
  perderia as URLs que os e2e e os favoritos dos operadores já usam.
- Ler o evento pelo id da entidade escrita: `/api/eventos` não filtra por alvo; a janela de 20 s sobre o mais
  recente é honesta o bastante e não exige rota nova.
