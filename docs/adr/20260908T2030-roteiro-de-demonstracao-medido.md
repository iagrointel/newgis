# Roteiro de demonstração medido (item L7-29-roteiro-demonstracao)

Data: 08/09/2026. Estado: aceito. Par: `laco/handoffs/T8/PLANO_PLATAFORMA48.md` (seção L7); o portão
do item vive em `laco/estado.json`. Nenhuma dependência do item estava entregue quando ele foi
construído (L7-01-c refutado, L3-01/L4-02/L5-01/L6-01 pendentes na leitura do painel usada aqui), e
isso é parte da decisão, não um desvio.

## Contexto

O portão pede três coisas: um `tests/e2e/test_demo.py` que percorre os passos do roteiro com captura
por passo e tempo total de até 30 minutos medido; texto revisado por um revisor separado; e a lista
"o que não faz ainda" gerada do `PAINEL.md`. O roteiro é documento de CLIENTE (obedece à regra de
escrita de 03/09) e ao mesmo tempo promessa verificável: cada passo declara o e2e que percorre o
mesmo caminho. Com as dependências abertas, o roteiro só pode percorrer a fundação (L0) e o mapa da
L2 — e precisa dizer isso sem margem para ambiguidade na frente do público.

## Decisão

1. **O roteiro anda só onde há prova.** Nove passos, cada um amarrado a um e2e de tela que já existe
   (catálogo, upload, tarefas, mapa, construtor, auditoria, saúde). O que não tem prova vira duas
   seções de texto: "Passos que o roteiro não percorre" (com o que dizer quando o pedido vier) e a
   lista gerada do fim do documento.
2. **A fronteira é GERADA, não escrita.** O bloco entre os marcadores
   `<!-- gerado de laco/PAINEL.md:inicio/fim -->` é reprodução verbatim da seção "Fronteira" de
   `laco/PAINEL.md`. `docs/gerar_demo.py --validar` reprova o documento se o bloco commitado diverge
   da regeneração (mesmo contrato do manual: divergiu, regenere e commit); `--preencher` regrava. O
   painel é do gerente; o roteiro nunca enchere uma fronteira à mão.
3. **Cláusulas estruturais verificáveis por máquina**, no validador e nos unitários
   (`tests/unit/test_demo_roteiro.py`): passos contínuos 1..N com duração, "o que dizer", "não
   prometer" e e2e existente; tempos somando o roteiro de 30 minutos; versão de 10 minutos como
   subconjunto na ordem; regra de escrita de 03/09 com lista fechada de termos proibidos e
   reprovação de exclamação.
4. **O revisor é um agente separado, sem o contexto do autor** (regra 7 da regra de escrita). Ele
   recebe só o texto e a regra; devolve a lista de frases que violam 1-6 e a reescrita. As alterações
   dele foram aplicadas integralmente em `docs/DEMO.md` (33 pontos, nenhum fato técnico mudado, os
   blocos gerados intocados) e o validador voltou a passar por cima do texto revisado.
5. **Um único e2e percorre os 9 passos na ordem** e mede o tempo total (reprova acima de 1.800 s),
   com captura por passo (`capturas/L7-29-roteiro-demonstracao_pNN_<passo>.png`, prefixo do item —
   `Tela.capturar` usa o ITEM do módulo dela, então o teste tem capturador próprio) e medidas por
   passo em `tests/medidas/`.
6. **O e2e se adapta ao refresco da lista de tarefas, sem mudar o produto.** A lista de tarefas só
   relê a 1ª página quando o resumo (a cada 10 s) vê o contador de tarefas ativas MUDAR; a transição
   ao vivo de uma linha já listada vem por assinatura de eventos. Duas consequências medidas: um job
   de prova curto demais nasce e conclui entre dois tiques e a linha nunca aparece; e quando um job
   termina no mesmo segundo em que o próximo começa, a contagem fica 1→1 entre tiques e a segunda
   linha não é inserida (a assinatura cobre só linha que já está na lista). O teste usa job de 45 s,
   espera o resumo declarar fila vazia antes de criar o segundo e cancela pela tela. O comportamento
   está registrado aqui como característica conhecida da tela (L0-05): em demonstração com o worker
   livre ela não aparece; sob fila ocupada, linha nova pode demorar um tique a mais que o evento.
7. **Bancada de trilha com TLS autoassinado**: `tests/e2e/conftest.py` aceita certificado inválido no
   contexto do navegador (`ignore_https_errors`) — sem efeito numa instalação com certificado de
   verdade; as chamadas httpx e o driver Node recebem o certificado por `SSL_CERT_FILE`/
   `NODE_EXTRA_CA_CERTS` no ambiente da trilha.

## Consequências

Rodada final: roteiro completo em 71,2 s (limite 1.800 s), 9 passos, 15 capturas, com carga e RAM
livre registradas ao lado (`tests/medidas/L7-29-roteiro-demonstracao.json`). O roteiro citável é
`docs/DEMO.md` + `tests/e2e/test_demo.py`; quando as linhas L1/L3/L4/L6 entregarem telas, o custo de
entrada é um passo novo no documento (com e2e) e a regeneração do bloco de fronteira. A cláusula de
dependência (dado de demonstração L7-01-c, telas de L3/L4/L6) continua aberta e está dita no texto,
não escondida.
