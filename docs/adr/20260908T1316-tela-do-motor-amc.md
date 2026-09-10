# Recombinar no navegador, com os pesos na URL e a URL validada

Item `L3-01-g-tela-motor`. Estado: aceita.

## Contexto

A tela do motor multicritério tem de deixar o usuário mover um peso e ver o mapa mudar. A pergunta de
desenho é onde a conta acontece. Duas coisas já existiam e apontavam a resposta: a extração de fator é cara
e já roda como job (`app.amc.executor`, itens L3-01-c/L6-04), e a combinação é barata e já tem duas
implementações provadas equivalentes — `app/amc/combinacao.py` e `web/js/amc/combinacao.js`, comparadas
vetor a vetor em `tests/unit/test_amc_combinacao_equivalencia.py`.

## Decisão

1. **A parte cara fica no servidor, a barata no navegador.** `GET /api/amc/execucoes/{id}/matriz` entrega,
   por unidade, o valor bruto e a favorabilidade de CADA fator. Mover um peso não muda nenhum valor
   extraído — muda só a combinação, que o navegador refaz com `combinacao.js`. Medido: zero requisição à
   API entre mover o controle e a lista mudar.
2. **A rota da matriz não combina nada.** Se combinasse, existiriam três implementações da mesma conta e a
   prova de equivalência deixaria de cobrir o que a tela mostra.
3. **Os pesos viajam na URL e a URL é fronteira de confiança.** `web/js/amc/pesos_url.js` aplica as mesmas
   regras que `app/amc/esquema.py:validar_pesos` aplica no servidor (fator existe, peso finito e não
   negativo, soma maior que zero, percentual fecha 100), mais o teto de escala do controle deslizante, que
   é da tela e não do servidor. Link recusado não calcula, não colore e diz por quê; nunca cai para um peso
   padrão em silêncio.
4. **Com o link recusado o mapa fica vazio, não recolorido.** Mostrar um mapa colorido enquanto a barra de
   endereço diz outra coisa é exatamente a falha que a recusa existe para evitar.
5. **A rampa é declarada num lugar só** (`web/js/amc/rampa.js`), lida pelo mapa e pela legenda. Vetado é
   cinza (excluído por restrição, não "pouco favorável") e sem nota é vazado (falta de dado nunca vira 0).

## Consequências

- Duas traduções do vocabulário do modelo para o do combinador (Python e JavaScript) passam a existir; a
  trava contra elas se desencontrarem é `tests/unit/test_amc_vocabulario_js.py`.
- A explicação de uma unidade passou a delegar as funções contínuas a `app/amc/transformacoes.py`. Sem
  isso, a explicação e a matriz dariam números diferentes para o mesmo fator.
- A pré-visualização do histograma só existe depois da primeira extração: a tela diz isso em vez de
  desenhar histograma sobre valor inventado.

## Alternativas descartadas

- **Recombinar no servidor a cada movimento do controle.** Uma ida à rede por arrasto, e a tela deixaria de
  responder num appliance com rede ruim — que é o caso de uso do produto.
- **Guardar os pesos em sessão em vez da URL.** Mata o "copiar o link e mandar para alguém", que é a forma
  como esta leitura circula.
- **Assinar os pesos na URL.** Resolveria adulteração por criptografia, mas impediria a pessoa de editar o
  link à mão — e a validação declarada já entrega o que importa: nada é calculado em silêncio.
