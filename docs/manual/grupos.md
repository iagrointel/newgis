---
id: grupos
titulo: Grupos
titulo_en: Groups
titulo_es: Grupos
resumo: "grupos de membros, entrada automática por regra e gerência de participantes"
resumo_en: "member groups, automatic entry by rule and membership management"
resumo_es: "grupos de miembros, entrada automática por regla y gestión de participantes"
classe: tela
pagina: admin/grupos.html
caminho: /admin/grupos
e2e: tests/e2e/test_grupos.py
captura: L0-02-tenant-auth_grupos.png
e2e_captura: capturar("grupos")
palavras: [grupos, membros, entrada, regra, participantes, admin]
palavras_en: [groups, members, entry, rule, membership, admin]
palavras_es: [grupos, miembros, entrada, regla, participantes, admin]
---

## Grupos

A tela Grupos organiza os membros em grupos. Todo membro pode ver os grupos; gerir exige o
privilégio de gerência de grupos.

1. Escolha Novo grupo e dê um nome.
2. Acrescente membros pela busca do painel de edição.
3. A entrada automática por regra (atributo do membro) pode ser configurada quando a organização
   usa LDAP: o grupo espelha um grupo do diretório.

Grupos servem para conceder papéis e compartilhamento em bloco: um item compartilhado com o grupo
fica visível a todos os seus membros.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_grupos.py`) contra a versão atual.
