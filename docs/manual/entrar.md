---
id: entrar
titulo: Entrar
titulo_en: Sign in
titulo_es: Entrar
resumo: "login por inquilino, senha e segundo fator; bloqueio depois de erros seguidos"
resumo_en: "sign in by tenant, password and second factor; lockout after repeated failures"
resumo_es: "inicio de sesión por inquilino, contraseña y segundo factor; bloqueo tras errores repetidos"
classe: tela
pagina: login.html
caminho: /entrar
e2e: tests/e2e/test_login.py
captura: L0-02-tenant-auth_login.png
e2e_captura: capturar("login")
palavras: [entrar, login, senha, inquilino, segundo fator, bloqueio, ldap]
palavras_en: [sign in, login, password, tenant, second factor, lockout, ldap]
palavras_es: [entrar, inicio de sesion, contrasena, inquilino, segundo factor, bloqueo, ldap]
---

## Entrar

A tela de entrada pede três coisas: o inquilino (slug), o login e a senha.

1. Abra `/entrar?inquilino=<slug>` (o link já vem preenchido quando a página inicial conhece o
   inquilino).
2. Digite login e senha e escolha Entrar.
3. Se a conta tem segundo fator (TOTP), digite os 6 dígitos do aplicativo na mesma tela.

Depois de 5 erros seguidos de senha a conta fica bloqueada por um tempo crescente; o administrador
pode desbloquear na tela Usuários. Quem entra por Active Directory usa o mesmo formulário: a
organização decide por configuração se a autenticação vai ao LDAP.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_login.py`) contra a versão atual.
