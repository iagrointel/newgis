---
id: uploads
titulo: Uploads
titulo_en: Uploads
titulo_es: Cargas
resumo: "upload retomável de arquivo grande por partes, com retomada e confirmação por conteúdo"
resumo_en: "resumable large file upload by parts, with resume and content confirmation"
resumo_es: "carga reanudable de archivo grande por partes, con reanudación y confirmación por contenido"
classe: tela
pagina: uploads.html
caminho: /uploads
e2e: tests/e2e/test_uploads.py
captura: L0-04-a-upload-arquivo_dropzone_vazia.png
e2e_captura: capturar("dropzone_vazia")
palavras: [upload, arquivo, partes, retomar, grande, dropzone, carga]
palavras_en: [upload, file, parts, resume, large, dropzone]
palavras_es: [carga, archivo, partes, reanudar, grande, dropzone]
---

## Uploads

A tela Uploads envia arquivos grandes por partes: a conexão pode cair e o envio recomeça do ponto
em que parou. Exige privilégio de criar conteúdo.

1. Arraste o arquivo para a zona de soltura ou escolha pelo seletor.
2. A tela mostra o progresso por parte; fechar a tela não perde o que já subiu.
3. Ao terminar, confirme o tipo pelo conteúdo (o servidor confere a assinatura do arquivo, não a
   extensão) e o item entra no catálogo.

Arquivos permitidos seguem a lista da organização; o que o servidor recusa, a tela explica.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_uploads.py`) contra a versão atual.
