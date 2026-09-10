# ADR 0018 — Portal de API e chaves de API

Estado: aceito · Item `L7-08-d-portal-api-chaves` · 06/09/2026 · Interno, análise / beta privado.

## Contexto

A plataforma já tinha `token_servico` (item L0-02-d): chave com escopos fechados, restrição por origem e
IP, prazo padrão de 90 dias e revogação. Faltava a parte que faz a chave ser usável por gente de fora:
uma página que mostre o que existe na API, com que escopo, e deixe experimentar; e faltava fechar dois
buracos que só aparecem quando alguém tenta abusar da chave.

## Decisão 1 — portal próprio, não Scalar nem Redoc

O enunciado do item sugeria vendorizar Scalar ou Redoc. Não foi feito. Três razões, em ordem de peso:

1. **Identidade visual é regra de build da casa** (item L0-14, decisão do dono: "instrumento", e tela sem
   identidade é erro). Scalar e Redoc trazem o desenho deles; a tela pareceria de outro produto.
2. **"Nenhum recurso externo" fica mais fácil de garantir do que de auditar.** Um pacote de terceiro pode
   buscar fonte ou ícone em tempo de execução; para provar que não busca, é preciso auditar o pacote
   inteiro. A página da casa faz três requisições, todas para a própria origem, e a CSP `default-src
   'none'` recusa qualquer outra.
3. **Já existe Swagger UI vendorizada** em `/api/docs` (`web/vendor/swagger-ui-*`, sha256 em
   `VERSOES.txt`), que continua sendo a referência crua do esquema. Somar um terceiro leitor de OpenAPI
   ao repositório seria de 2 a 3 MB de bundle repetindo o que já está lá, num disco a 92 %.

O que se perde: o portal não desenha esquema de corpo recursivamente como o Redoc. Quem precisa disso
abre `/api/docs`. O que se ganha: a tela é do produto, e o "experimentar" é código nosso de 40 linhas.

## Decisão 2 — `x-plat-escopo` derivado do código, nunca declarado à mão

Cada operação do OpenAPI passa a trazer `x-plat-escopo`. O valor **não** é escrito em `openapi_extra`
rota a rota: é lido da dependência `autenticado(...)` que a própria rota instalou
(`app/portal/openapi.py`, atributos postos em `app/auth/sessao.py`).

Motivo: `x-auth` e `x-privilegio`, que já eram escritos à mão, envelheceram. A varredura que este item
trouxe achou duas etiquetas erradas no primeiro dia — `GET /api/uploads/tipos` e
`GET /api/importacoes/formatos` dizem `x-auth: S/T` e respondem 200 a quem não tem credencial nenhuma
(são vocabulários estáticos, sem dado de inquilino, mas a etiqueta estava errada), e o descritor do
GeocodeServer compatível Esri dizia exigir escopo e não exige (é metadado, por decisão do ADR 0013).

Uma etiqueta que não é a mesma coisa que o servidor confere é pior do que nenhuma: o adversário varre a
etiqueta e mede a etiqueta. Derivada, ela não tem como divergir. As únicas rotas que declaram o valor à
mão são as do GeocodeServer, que autenticam dentro do handler e por isso não têm dependência de onde
derivar — e a declaração delas é conferida contra o servidor pela varredura.

Vocabulário fechado: `publico`, `sessao`, `superadmin`, `token:qualquer`, ou um escopo de
`app/auth/escopos.py`.

## Decisão 3 — perfis de chave são apelidos, não escopos novos

O enunciado falava em escopos "leitura, edição, admin, tiles". Eles entram como `PERFIS_DE_CHAVE` em
`app/auth/escopos.py`: conjuntos nomeados dos escopos que já existem. O vocabulário de `ESCOPO` não muda,
porque é ele que `exigir_escopo` confere. Dois eixos de nome para a mesma chave dariam duas verdades.

## Decisão 4 — prazo da chave passa a ser garantido pelo banco

`plat.token_servico.expira_em` nasceu anulável (migração 002) e `plat.auth_token` aceitava
`expira_em IS NULL OR expira_em > now()`. A API nunca gravou NULL, mas o banco admitia: uma carga, um
script de migração ou um defeito futuro criaria uma chave eterna. A migração
`20260906T1617_chaves_api.sql` põe `NOT NULL`, um `CHECK (expira_em <= criado_em + 366 dias)` e tira o
ramo do NULL da função. Também acrescenta `usos bigint`, incrementado na mesma linha de UPDATE que já
gravava `ultimo_uso` — nenhuma consulta nova.

## Decisão 5 — o erro passa a ser Problem Details da RFC 9457, por acréscimo

`app/erros.py` responde `application/problem+json` e acrescenta `type`, `title`, `status`, `detail` e
`instance`. `erro`, `mensagem`, `detalhe` e `req_id` continuam exatamente onde estavam, como membros de
extensão (RFC 9457 seção 3.2 os admite). Nenhum cliente da casa mudou; nenhum teste da suíte lia o tipo
de conteúdo do erro. `type` é uma URN estável (`urn:plat:erro:<codigo>`), nunca uma URL a buscar.

Motivo de fazer isto agora: a chave de API é consumida por programa de terceiro, e biblioteca de cliente
sabe ler `type`/`status` sem conhecer o vocabulário da casa. A decisão D18 (contrato `erro`/`mensagem`)
não foi revogada — foi embrulhada.

## Divergência assumida em relação ao portão de pronto

O portão dizia "revogar → 403 em ≤ 5 s". A plataforma responde **401 `token_revogado`**, não 403, e é o
certo: credencial que deixou de existir é 401 (autenticação), não 403 (autorização). O contrato é do item
L0-02 e já está provado em `tests/e2e/test_tokens.py`; trocá-lo por 403 quebraria o cliente que existe.
O prazo é o que foi medido e cumprido. A medida gravada nomeia o código de fato.

## Consequências

- Toda rota nova nasce com `x-plat-escopo` sem ninguém escrever nada, e
  `tests/api/test_portal_chaves.py` reprova se o valor sair do vocabulário.
- A varredura de escopo errado (`test_varredura_escopo_errado_nao_devolve_200`) é o teste de regressão
  permanente da refutação deste item: rota nova mal fechada aparece ali como 200 indevido.
- Os 20 exemplos de `exemplos/` são executados pela suíte contra a API viva. Exemplo que apodrecer com
  mudança de contrato reprova o e2e, em vez de virar documentação errada.
