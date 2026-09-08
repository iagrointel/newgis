---
id: usuarios
titulo: Usuários
titulo_en: Users
titulo_es: Usuarios
resumo: "criar membros com senha temporária, convidar por e-mail, editar, desabilitar e agir em lote"
resumo_en: "create members with a temporary password, invite by e-mail, edit, disable and bulk actions"
resumo_es: "crear miembros con contraseña temporal, invitar por correo, editar, deshabilitar y acciones en lote"
classe: tela
pagina: admin/usuarios.html
caminho: /admin/usuarios
e2e: tests/e2e/test_usuarios.py
captura: L0-02-tenant-auth_usuarios.png
e2e_captura: capturar("usuarios")
palavras: [usuarios, membros, criar, convite, senha temporaria, desabilitar, lote, desbloquear, admin]
palavras_en: [users, members, create, invite, temporary password, disable, bulk, unlock, admin]
palavras_es: [usuarios, miembros, crear, invitacion, contrasena temporal, deshabilitar, lote, admin]
---

## Usuários

A tela Usuários administra os membros do inquilino. Exige o privilégio `membros.ver`; agir exige
`membros.gerir`.

### Criar

1. Escolha Novo usuário.
2. Preencha login, nome e perfil (administrador, editor ou visualizador).
3. A resposta mostra a senha temporária uma única vez: copie e passe ao usuário. O sistema pede a
   troca no primeiro acesso.

### Convidar por e-mail

Com SMTP configurado na organização, a seção Convidar por e-mail envia um convite com link
próprio, válido por 7 dias. Sem SMTP, a resposta traz o link para você repassar.

### Editar, desabilitar e apagar

Cada linha tem Editar (nome, perfil), Redefinir senha (gera nova temporária), Desligar segundo
fator e Desbloquear. Desabilitar preserva o histórico e impede o acesso; apagar remove o membro
(queda recusada para o último administrador do inquilino).

### Ação em lote

Marque várias linhas para desabilitar ou reabilitar em lote. A operação recusa desabilitar o
último administrador.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_usuarios.py`) contra a versão atual.
