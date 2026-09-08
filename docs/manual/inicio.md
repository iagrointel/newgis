---
id: inicio
titulo: Início
titulo_en: Home
titulo_es: Inicio
resumo: "página de entrada: versão, saúde dos serviços e atalhos das telas do inquilino"
resumo_en: "entry page: version, service health and shortcuts to the tenant screens"
resumo_es: "página de entrada: versión, salud de los servicios y atajos de las pantallas del inquilino"
classe: tela
pagina: index.html
caminho: /
e2e: tests/e2e/test_saude_pagina.py
captura: L0-01-repo_inicio.png
e2e_captura: L0-01-repo_inicio.png
palavras: [inicio, saude, versao, servicos, banco, worker, garage]
palavras_en: [home, health, version, services, database, worker, garage]
palavras_es: [inicio, salud, version, servicios, banco, worker, garage]
---

## Início

A página de entrada mostra o nome do produto, o aviso de análise / beta privado e dois painéis:
versão e saúde.

O painel versão mostra o número de versão do arquivo `VERSAO`, o commit em execução, o ambiente e
o endereço público. O painel saúde mostra a resposta do `/saude`: banco, migrações pendentes,
serviços auxiliares (garage e worker) e a fila de tarefas. HTTP 200 só com banco em ordem.

Sem sessão, a página oferece o link Entrar. Com sessão, mostra a barra lateral com as telas que o
seu perfil alcança e atalhos para elas.

### Como conferir a saúde

1. Abra a página inicial.
2. Leia o painel saúde: `banco: ok` e `migracoes_pendentes: 0` significam serviço em ordem.
3. Se `banco` vier `desatualizado`, há migração sem aplicar: rode a instalação de novo
   (seção Instalação do manual do administrador).
4. Se `workers_vivos` vier 0, a fila não está sendo processada: confira a unidade `plat-worker`.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_saude_pagina.py`) contra a versão atual.
