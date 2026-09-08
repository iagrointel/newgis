---
id: papeis
titulo: Papéis e privilégios
titulo_en: Roles and privileges
titulo_es: Paples y privilegios
resumo: "papéis personalizados sobre privilégios nomeados; o que cada perfil pode fazer"
resumo_en: "custom roles over named privileges; what each profile can do"
resumo_es: "papeles personalizados sobre privilegios nombrados; qué puede hacer cada perfil"
classe: tela
pagina: admin/papeis.html
caminho: /admin/papeis
e2e: tests/e2e/test_papeis.py
captura: L0-02-tenant-auth_papeis.png
e2e_captura: capturar("papeis")
palavras: [papeis, privilegios, perfil, administrador, editor, visualizador, personalizado, admin]
palavras_en: [roles, privileges, profile, administrator, editor, viewer, custom, admin]
palavras_es: [papeles, privilegios, perfil, administrador, editor, visualizador, personalizado, admin]
---

## Papéis e privilégios

A tela Papéis lista os privilégios nomeados da plataforma (cada um cobre uma família de rotas da
API) e deixa a organização criar papéis personalizados: um nome e um conjunto de privilégios.

Os três perfis de fábrica cobrem os casos comuns:

- administrador: tudo no inquilino;
- editor: cria e edita conteúdo e roda tarefas;
- visualizador: só leitura.

Para o caso intermediário (por exemplo, quem gerencia conteúdo mas não membros), crie um papel com
os privilégios exatos e atribua-o ao membro na tela Usuários. A lista de privilégios e o que cada
um cobre está documentada em `docs/PRIVILEGIOS.md`, gerada do banco.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_papeis.py`) contra a versão atual.
