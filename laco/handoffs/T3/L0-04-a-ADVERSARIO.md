# Adversário — L0-04-a-upload-arquivo (dado de cliente / arquivo enviado)

**Veredito: REFUTADO.** Item recém-entregue pelo agente construtor desta mesma sessão; revisão
independente feita depois, sem ver o raciocínio do construtor além do handoff público. O mecanismo
central (partes, sha256, cota, integridade, isolamento entre usuários) resiste a tudo que ataquei —
mas achei um defeito real e reproduzível que quebra a funcionalidade inteira para a maioria dos
usuários legítimos.

## O achado (severidade: alta, funcional — não é furo de segurança, é quebra de produto)

**Nenhum usuário que não seja administrador do inquilino consegue usar o upload de arquivo, nem
pela tela nem pela API**, porque a própria interface exige um token com escopo `admin:inquilino`
para começar (`web/js/uploads/*.js:25`: `escopos: ['admin:inquilino']`), e esse escopo só pode ser
emitido para um usuário com `perfil == 'admin'` (`app/auth/rotas_tokens.py`, já auditado nesta
sessão). Confirmei ao vivo: criei um editor comum, tentei todo escopo do vocabulário fechado
(`catalogo:ler`, `camada:ler/editar`, `tiles:ler`, `jobs:executar`, `rota:usar`,
`geocodificar:usar`) contra as rotas de upload — todos devolvem `403 escopo_insuficiente
"o token não tem o escopo admin:inquilino"` — e o próprio `admin:inquilino` devolve `422
escopo_fora_do_teto "admin:inquilino só para dono com perfil admin"` para o editor. Não há
combinação que funcione para um perfil `editor`.

**Causa raiz:** `app/uploads/rotas.py` chama `autenticado("conteudo.criar")` sem passar
`escopo_token=`, então cai no padrão de `autenticado()` em `app/auth/sessao.py:354`
(`escopo_token: str | None = "admin:inquilino"`). O vocabulário fechado de escopos
(`app/auth/escopos.py`) nunca ganhou uma entrada para "enviar arquivo" — só cobre
catálogo/camada/tiles/jobs/rota/geocodificar. **O mesmo padrão já existe em `app/rotas_arquivos.py`
(item L0-11-arquivos-objetos, `POST /api/arquivos`, linha 65)** — ou seja, não é um erro só deste
item novo, é uma lacuna no vocabulário de escopos que os dois itens de upload herdaram. L0-11 já
está `refutado` no estado.json por outro motivo (achado do adversário G4, DELETE/GET sem
isolamento); este achado é adicional e diferente, e vale para os dois.

## Ataques que PASSARAM (mecanismo central, com token admin:inquilino real)

1. **Isolamento entre usuários do mesmo inquilino.** Admin A inicia upload; admin B (outro usuário
   admin, MESMO inquilino, token próprio) tenta `GET`/`PUT partes/1`/`POST concluir` no upload de A
   -> `404 upload_inexistente` nos três. PASSA — `_carregar()` filtra por `usuario_id`, não só por
   `tenant_id`.
2. **Ponta a ponta com admin real.** A envia sua própria parte -> `200`; conclui -> `202` com
   `arquivo_id`/`sha256`/`bytes` corretos. PASSA.
3. **Integridade do sha256.** Concluir com `sha256` declarado divergente do conteúdo real ->
   `422 sha256_divergente` com os dois hashes na mensagem (nunca aceita o hash mentido). PASSA.

## O que ESTE laudo NÃO cobre

- Zip-bomba, path traversal, arquivo acima do limite, duas sessões no mesmo uploadId — já testados
  pelo próprio construtor no handoff do item (não refiz, para não duplicar).
- Não testei se o front-end (`web/uploads.html`) mostra algum erro amigável quando o editor tenta
  usar a tela e falha na criação do token — só confirmei a falha na API.

## Recomendação

Não é um conserto trivial de uma linha (mudar só o `escopo_token=` da rota exigiria primeiro criar
uma entrada nova no vocabulário fechado, ex. `arquivo:enviar`, e decidir o teto de privilégio —
provavelmente `conteudo.criar` deveria bastar, já que é o privilégio que a própria rota já exige).
Como isso toca os DOIS itens de upload (L0-04-a e L0-11), e a decisão de nomear/tetar um escopo
novo é uma decisão de arquitetura pequena mas real, sugiro registrar como pendência conjunta em vez
de dois consertos separados e potencialmente divergentes.
