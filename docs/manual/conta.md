---
id: conta
titulo: Minha conta
titulo_en: My account
titulo_es: Mi cuenta
resumo: "dados pessoais, foto, senha, segundo fator, sessões abertas e convites recebidos"
resumo_en: "personal data, photo, password, second factor, open sessions and received invitations"
resumo_es: "datos personales, foto, contraseña, segundo factor, sesiones abiertas e invitaciones recibidas"
classe: tela
pagina: conta.html
caminho: /conta
e2e: tests/e2e/test_conta.py
captura: L0-02-tenant-auth_conta.png
e2e_captura: capturar("conta")
palavras: [conta, senha, foto, perfil, sessoes, convites, segundo fator, totp, dados pessoais]
palavras_en: [account, password, photo, profile, sessions, invitations, second factor, totp]
palavras_es: [cuenta, contrasena, foto, perfil, sesiones, invitaciones, segundo factor, totp]
---

## Minha conta

A tela Minha conta reúne o que diz respeito à sua pessoa: dados, senha, segundo fator, sessões e
convites.

### Dados e foto

O cartão Dados edita nome, foto e preferências do perfil (idioma, unidades, formato de data). A
foto aceita PNG, JPEG, GIF ou WEBP até 1 MB e é recortada num quadro de 200×200.

### Senha

O cartão Senha troca a sua senha: a atual, a nova e a confirmação da nova. A nova precisa dos
mínimos de política da organização.

### Segundo fator

O cartão Segundo fator ativa um gerador de códigos TOTP: a tela mostra o segredo em QR e em texto;
o aplicativo de autenticação lê o QR e passa a gerar 6 dígitos a cada 30 segundos. O teste do
código no ativação confirma que o relógio do aplicativo está certo. Desligar o segundo fator pede
um código válido.

### Sessões e convites

O cartão Sessões lista as sessões abertas da sua conta e permite encerrar cada uma. O cartão
Convites mostra convites pendentes para você aceitar.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_conta.py`) contra a versão atual.
