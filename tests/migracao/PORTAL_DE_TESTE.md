# Portal de teste do inventário (item L2-08-a-leitor-portal-inventario)

Setembro de 2026.

## O que o portão do item pede, e o que foi entregue

O portão pede a prova "contra um Portal público de teste (organização AGOL pública com itens abertos,
registrada com URL e data em `tests/migracao/`)". **Essa cláusula NÃO foi entregue.** O que existe é a prova
contra um servidor de teste desta casa, que devolve respostas gravadas no formato público documentado pela
Esri. As duas coisas não são a mesma, e este arquivo existe para que ninguém confunda uma com a outra.

## Por que a prova contra portal real ficou pendente

1. **Credencial do parceiro = decisão D20 do dono, em aberto.** O portal do parceiro é o único Portal real ao
   qual esta casa teria acesso legítimo hoje, e a credencial depende de uma decisão que ainda não foi tomada.
   Sem ela não há como ler um Portal com token.
2. **Organização pública de terceiro exige autorização.** Existem organizações do ArcGIS Online com conteúdo
   aberto, e ler o inventário de uma delas seria tecnicamente possível sem credencial. Não foi feito: apontar
   um varredor automatizado para o portal de um terceiro sem autorização é uso de serviço alheio, e a regra
   desta casa é não fazer isso. Quando o dono autorizar uma organização específica, a URL, a data da leitura e
   o número de itens lidos entram AQUI, nesta seção, e o teste correspondente deixa de ser pulado.

## O que foi usado no lugar

`tests/migracao/portal_falso.py` — servidor HTTP que responde os caminhos do ArcGIS REST usados pelo leitor,
com o acervo gravado em `tests/migracao/respostas/portal.json`.

- **O formato** (nomes de campo, tipos, unidades, `nextStart`, tempo em milissegundos, erro dentro do corpo
  com HTTP 200) foi copiado da referência pública da Esri; a lista de páginas lidas, com o endereço de cada
  uma, está no cabeçalho de `tests/migracao/respostas/gerar.py` e no de `app/migracao/portal.py`.
- **O conteúdo** é fictício, de uma organização inventada ("SIG de teste interno"). Nenhum dado, nome, URL ou
  credencial de cliente ou parceiro aparece no arquivo.
- **O acervo tem 59 itens** (o portão pede ≥ 50), 19 serviços com contagem de feições por camada, 3 grupos e
  4 usuários, cobrindo 21 tipos de item Esri — inclusive um tipo que a tabela de classificação NÃO conhece,
  para provar que o leitor responde `desconhecido` em vez de chutar.
- O servidor escuta no IP público da máquina, nunca em `127.0.0.1`: a defesa de SSRF do L6-02-a recusa
  loopback, e um servidor em loopback provaria só que a defesa funciona.

## O que a prova contra o servidor de mentira SUSTENTA

- o leitor paga o formato certo em cada caminho (`portals/self`, `search` paginado, `item`, `item/data`,
  `item/resources`, `relatedItems`, grupos, membros, usuários, `FeatureServer` e `query?returnCountOnly=true`);
- o modelo de dado grava o que o portão lista: tipo, contagem por camada, tamanho declarado, dono, último
  acesso, dependências (web map → camada, aplicativo → web map), classificação prévia;
- o token nunca vai para log, banco, URL ou CSV;
- nenhum dado pessoal de usuário é gravado, mesmo quando o portal o devolve;
- a leitura retoma do ponto onde parou depois de um corte de rede;
- o limite de uso (429) é respeitado com espera;
- uma URL que não é Portal vira erro nomeado, nunca 500;
- 10 mil itens paginam e terminam.

## O que ela NÃO sustenta

- que um Portal for ArcGIS ou um ArcGIS Online REAL responda exatamente assim. Portais reais têm variação de
  versão (10.8.1, 11.x), campos ausentes, `typeKeywords` diferentes do documentado, serviços que recusam
  `returnCountOnly`, redirecionamento de autenticação e limites de uso próprios;
- nenhum número de desempenho medido aqui vale como desempenho contra portal real: a rede é local.

## O que falta para fechar a cláusula

1. decisão D20 do dono (credencial do parceiro) **ou** autorização escrita para ler uma organização pública
   nomeada;
2. rodar o inventário contra ela, anotar nesta página a URL, a data e o total de itens;
3. conferir à mão uma amostra do JSON devolvido por ela, como já se faz com o acervo gravado
   (`tests/api/test_migracao_inventario.py::test_inventario_lista_itens_tipos_contagens_e_dependencias`).
