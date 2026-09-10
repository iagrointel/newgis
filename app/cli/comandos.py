"""Subcomandos da linha de comando `plat` (item L0-14-cli-admin).

Cada função aqui é um verbo do administrador e faz exatamente o que a tela faria: chama a rota da API
com a sessão de quem executou. Por isso o evento gravado, o privilégio exigido e o resultado são os
mesmos da tela — o teste do item compara os dois lado a lado.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
from pathlib import Path

from app.cli.rede import Cliente, ErroCLI, caminho_de_env, ler_credenciais, ler_totp, senha_de_entrada

RAIZ = Path(__file__).resolve().parents[2]
URL_LOCAL = "http://127.0.0.1:8150"
INQUILINO_DA_PLATAFORMA = "plataforma"
ESPERA_PADRAO_S = 180.0


# ---------------------------------------------------------------- apoio
def url(args) -> str:
    """Endereço da API: o que veio na linha de comando, senão o do ambiente, senão a instalação local."""
    return args.base_url or os.environ.get("PLAT_CLI_URL") or os.environ.get("PLAT_URL_PUBLICA") or URL_LOCAL


def arquivo_credenciais(args) -> Path:
    if args.credenciais:
        return Path(args.credenciais)
    return caminho_de_env("PLAT_CREDENCIAIS_ARQUIVO", RAIZ / "tests" / "credenciais.txt")


def arquivo_totp(args) -> Path | None:
    if args.totp_arquivo:
        return Path(args.totp_arquivo)
    return caminho_de_env("PLAT_CREDENCIAIS_TOTP_ARQUIVO", RAIZ / "tests" / "credenciais_totp.txt")


def _sessao(args, slug: str) -> Cliente:
    """Abre sessão na API como o administrador de `slug`, com as credenciais do arquivo modo 600."""
    caminho = arquivo_credenciais(args)
    credenciais = ler_credenciais(caminho)
    if slug not in credenciais:
        raise ErroCLI(f"{caminho} não tem a linha do inquilino {slug!r}")
    login, senha = credenciais[slug]
    cliente = Cliente(url(args), args.tempo_limite)
    resposta = cliente.entrar(slug, login, senha, ler_totp(arquivo_totp(args), slug))
    pendencias = ((resposta.get("usuario") or {}).get("pendencias")) or []
    if pendencias:
        _resolver_pendencia(args, cliente, slug, login, pendencias)
    return cliente


def _resolver_pendencia(args, cliente: Cliente, slug: str, login: str, pendencias: list[str]) -> None:
    """A sessão nasce limitada enquanto houver pendência (ADR 0002 seção 5.4) e nenhuma rota administrativa
    responde. Só a de segundo fator tem conserto pela linha de comando, e só quando quem executa autoriza
    com --configurar-2fa: ligar o segundo fator de uma conta é ato do dono da conta, não efeito colateral."""
    if pendencias != ["configurar_2fa"]:
        raise ErroCLI(f"a conta {slug}/{login} tem pendência {pendencias}; resolva pela tela antes de usar a CLI")
    if not getattr(args, "configurar_2fa", False):
        raise ErroCLI(
            f"a conta {slug}/{login} precisa configurar o segundo fator antes de administrar. "
            "Rode de novo com --configurar-2fa para configurá-lo agora e guardar o segredo no arquivo "
            "de --totp-arquivo (modo 600), ou configure pela tela."
        )
    from app.auth import totp

    inicio = cliente.exigir("POST", "/api/eu/2fa/iniciar", {})
    segredo = inicio["segredo"]
    cliente.exigir("POST", "/api/eu/2fa/confirmar", {"codigo": totp.codigo(segredo)})
    _guardar_totp(arquivo_totp(args), slug, login, segredo)


def _guardar_totp(caminho: Path | None, slug: str, login: str, segredo: str) -> None:
    if caminho is None:
        raise ErroCLI("--configurar-2fa exige --totp-arquivo (ou PLAT_CREDENCIAIS_TOTP_ARQUIVO) para guardar o segredo")
    linhas = [li for li in (caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else [])
              if not li.startswith(slug + " ")]
    linhas.append(f"{slug} {login} {segredo}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    caminho.chmod(0o600)


def _inquilino_do_comando(args) -> str:
    slug = args.inquilino or os.environ.get("PLAT_CLI_INQUILINO")
    if not slug:
        raise ErroCLI("este comando exige --inquilino <slug> (ou PLAT_CLI_INQUILINO no ambiente)")
    return slug


def _emitir(args, dado, linhas: list[str]) -> int:
    """`--json` imprime o corpo da API; sem ele, linhas curtas em português. Nunca imprime senha que não
    tenha sido pedida: quando há senha temporária, ela é o resultado do comando e vai só na saída padrão."""
    if args.json:
        print(json.dumps(dado, ensure_ascii=False, indent=2))
    else:
        for li in linhas:
            print(li)
    return 0


def _achar_inquilino(cliente: Cliente, alvo: str) -> dict:
    lista = cliente.exigir("GET", "/api/plataforma/inquilinos")
    for t in lista:
        if str(t["id"]) == str(alvo) or t["slug"] == alvo:
            return t
    raise ErroCLI(f"inquilino {alvo!r} não existe (procurado por id e por slug)")


def _achar_usuario(cliente: Cliente, alvo: str) -> dict:
    if alvo.isdigit():
        return cliente.exigir("GET", f"/api/usuarios/{int(alvo)}")
    pagina = cliente.exigir("GET", f"/api/usuarios?busca={alvo}&limite=200")
    for u in pagina["itens"]:
        if u["login"] == alvo:
            return u
    raise ErroCLI(f"usuário {alvo!r} não existe neste inquilino")


def _esperar_job(cliente: Cliente, job_id: str, limite_s: float) -> dict:
    fim = time.monotonic() + limite_s
    ultimo: dict = {}
    while time.monotonic() < fim:
        ultimo = cliente.exigir("GET", f"/api/jobs/{job_id}")
        if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
            return ultimo
        time.sleep(0.5)
    raise ErroCLI(f"o job {job_id} não terminou em {limite_s:.0f} s (estado {ultimo.get('estado')!r})")


# ---------------------------------------------------------------- inquilino
def inquilino_listar(args) -> int:
    cliente = _sessao(args, INQUILINO_DA_PLATAFORMA)
    lista = cliente.exigir("GET", "/api/plataforma/inquilinos")
    return _emitir(args, lista, [f"{t['id']}\t{t['slug']}\t{t['nome']}\t{'ativo' if t['ativo'] else 'suspenso'}"
                                 for t in lista])


def inquilino_criar(args) -> int:
    cliente = _sessao(args, INQUILINO_DA_PLATAFORMA)
    senha_desejada = senha_de_entrada(args)
    existentes = {t["slug"]: t for t in cliente.exigir("GET", "/api/plataforma/inquilinos")}
    if args.slug in existentes:
        if not args.se_nao_existir:
            raise ErroCLI(f"já existe um inquilino com o identificador {args.slug!r}")
        t = existentes[args.slug]
        return _emitir(args, {"id": t["id"], "slug": t["slug"], "criado": False},
                       [f"inquilino {t['slug']} já existe (id {t['id']}); nada a fazer"])
    corpo = {
        "slug": args.slug,
        "nome": args.nome,
        "admin_login": args.admin_login,
        "admin_nome": args.admin_nome,
        "config": json.loads(args.config) if args.config else {},
    }
    criado = cliente.exigir("POST", "/api/plataforma/inquilinos", corpo, esperado=(201,))
    temporaria = criado["senha_temporaria"]
    resultado = {"id": criado["id"], "slug": criado["slug"], "admin": criado["admin"], "criado": True}
    if senha_desejada:
        # troca a senha temporária pela definitiva usando a MESMA rota do primeiro acesso pela tela
        novo = Cliente(url(args), args.tempo_limite)
        novo.entrar(args.slug, args.admin_login, temporaria)
        novo.exigir("PUT", "/api/eu/senha", {"atual": temporaria, "nova": senha_desejada}, esperado=(204,))
        novo.sair()
        resultado["senha"] = "definida pelo arquivo/entrada padrão"
    else:
        resultado["senha_temporaria"] = temporaria
    linhas = [f"inquilino {criado['slug']} criado (id {criado['id']}, admin {criado['admin']['login']})"]
    if not senha_desejada:
        linhas.append(f"senha temporária do admin: {temporaria}")
    return _emitir(args, resultado, linhas)


def inquilino_suspender(args) -> int:
    cliente = _sessao(args, INQUILINO_DA_PLATAFORMA)
    t = _achar_inquilino(cliente, args.alvo)
    cliente.exigir("POST", f"/api/plataforma/inquilinos/{t['id']}/suspender", {}, esperado=(204,))
    return _emitir(args, {"id": t["id"], "slug": t["slug"], "ativo": False}, [f"inquilino {t['slug']} suspenso"])


def inquilino_reativar(args) -> int:
    cliente = _sessao(args, INQUILINO_DA_PLATAFORMA)
    t = _achar_inquilino(cliente, args.alvo)
    cliente.exigir("POST", f"/api/plataforma/inquilinos/{t['id']}/reativar", {}, esperado=(204,))
    return _emitir(args, {"id": t["id"], "slug": t["slug"], "ativo": True}, [f"inquilino {t['slug']} reativado"])


def inquilino_cota(args) -> int:
    """Lê e (quando pedido) grava a cota do inquilino pela rota da tela de configurações (`/api/org`)."""
    slug = _inquilino_do_comando(args)
    cliente = _sessao(args, slug)
    atual = cliente.exigir("GET", "/api/org")
    if args.bytes is None and args.usuarios is None:
        return _emitir(args, atual, _linhas_cota(atual))
    mapa = atual.get("mapa") or {}
    # o PUT reescreve o registro inteiro (é a mesma tela de configurações): tudo o que não muda vai de volta
    # como veio, para a linha de comando nunca apagar de lado o que a tela guardou
    corpo = {
        "nome": atual["nome"],
        "cor": atual["cor"],
        "idioma_padrao": atual["idioma_padrao"],
        "centro": mapa.get("centro"),
        "zoom": mapa.get("zoom"),
        "basemap": mapa.get("basemap"),
        "srid_padrao": mapa.get("srid_padrao"),
        "cota_bytes": args.bytes if args.bytes is not None else atual["armazenamento"]["cota_bytes"],
        "cota_usuarios": args.usuarios if args.usuarios is not None else atual["usuarios"]["cota"],
        "auth": atual.get("auth") or {},
    }
    novo = cliente.exigir("PUT", "/api/org", corpo)
    return _emitir(args, novo, _linhas_cota(novo))


def _linhas_cota(org: dict) -> list[str]:
    return [
        f"cota de armazenamento: {org['armazenamento']['cota_bytes']} bytes "
        f"(usados {org['armazenamento']['bytes_usados']})",
        f"cota de usuários: {org['usuarios']['cota']} (ativos {org['usuarios']['ativos']})",
    ]


# ---------------------------------------------------------------- usuário
def usuario_listar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    pagina = cliente.exigir("GET", f"/api/usuarios?limite={args.limite}")
    return _emitir(args, pagina, [f"{u['id']}\t{u['login']}\t{u['perfil']}\t{'ativo' if u['ativo'] else 'inativo'}"
                                  for u in pagina["itens"]])


def usuario_criar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    senha_desejada = senha_de_entrada(args)
    corpo = {"login": args.login, "nome": args.nome, "perfil": args.perfil, "email": args.email, "papel_id": None}
    criado = cliente.exigir("POST", "/api/usuarios", corpo, esperado=(201,))
    resultado = {"usuario": criado["usuario"]}
    if senha_desejada:
        novo = Cliente(url(args), args.tempo_limite)
        novo.entrar(_inquilino_do_comando(args), args.login, criado["senha_temporaria"])
        novo.exigir("PUT", "/api/eu/senha", {"atual": criado["senha_temporaria"], "nova": senha_desejada},
                    esperado=(204,))
        novo.sair()
        resultado["senha"] = "definida pelo arquivo/entrada padrão"
    else:
        resultado["senha_temporaria"] = criado["senha_temporaria"]
    linhas = [f"usuário {criado['usuario']['login']} criado (id {criado['usuario']['id']})"]
    if not senha_desejada:
        linhas.append(f"senha temporária: {criado['senha_temporaria']}")
    return _emitir(args, resultado, linhas)


def usuario_redefinir_senha(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    u = _achar_usuario(cliente, args.alvo)
    r = cliente.exigir("POST", f"/api/usuarios/{u['id']}/senha", {}, esperado=(200,))
    return _emitir(args, {"id": u["id"], "login": u["login"], **r},
                   [f"senha de {u['login']} redefinida; senha temporária: {r['senha_temporaria']}"])


def usuario_desabilitar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    u = _achar_usuario(cliente, args.alvo)
    r = cliente.exigir("PUT", f"/api/usuarios/{u['id']}", {"ativo": False})
    return _emitir(args, r, [f"usuário {u['login']} desabilitado"])


def usuario_reabilitar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    u = _achar_usuario(cliente, args.alvo)
    r = cliente.exigir("PUT", f"/api/usuarios/{u['id']}", {"ativo": True})
    return _emitir(args, r, [f"usuário {u['login']} reabilitado"])


# ---------------------------------------------------------------- token
def token_listar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    lista = cliente.exigir("GET", "/api/tokens" + ("?todos=1" if args.todos else ""))
    return _emitir(args, lista, [f"{t['id']}\t{t['prefixo']}\t{t['nome']}\t{','.join(t['escopos'])}" for t in lista])


def token_criar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    corpo = {"nome": args.nome, "escopos": args.escopo}
    if args.validade_dias is not None:
        corpo["validade_dias"] = args.validade_dias
    criado = cliente.exigir("POST", "/api/tokens", corpo, esperado=(201,))
    return _emitir(args, criado, [f"token {criado['id']} criado (prefixo {criado['prefixo']})",
                                  f"valor (só aparece agora): {criado['token']}"])


def token_revogar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    cliente.exigir("DELETE", f"/api/tokens/{args.id}", esperado=(204,))
    return _emitir(args, {"id": args.id, "revogado": True}, [f"token {args.id} revogado"])


# ---------------------------------------------------------------- camada
def camada_importar(args) -> int:
    """Sobe o arquivo, cria a importação e (por padrão) espera inspeção e carga — os mesmos quatro passos
    que a tela de importação faz, na mesma ordem e pelas mesmas rotas."""
    slug = _inquilino_do_comando(args)
    caminho = Path(args.arquivo)
    if not caminho.is_file():
        raise ErroCLI(f"arquivo {caminho} não existe")
    cliente = _sessao(args, slug)
    formato = args.formato
    token = cliente.exigir("POST", "/api/tokens",
                           {"nome": f"cli-importar-{caminho.stem[:32]}", "escopos": ["admin:inquilino"]},
                           esperado=(201,))
    try:
        envio = Cliente(url(args), args.tempo_limite)
        objeto = envio.exigir("POST", "/api/arquivos?classe=camada_arquivo", esperado=(201,),
                              bytes_corpo=caminho.read_bytes(),
                              cabecalhos={"Authorization": f"Bearer {token['token']}"})
        item = cliente.exigir("POST", "/api/itens", esperado=(201,), corpo={
            "tipo": "arquivo",
            "titulo": args.titulo or caminho.name,
            "dados": {"chave": objeto["chave"], "sha256": objeto["sha256"], "bytes": objeto["bytes"],
                      "content_type": objeto["content_type"], "nome_original": caminho.name},
        })
        criada = cliente.exigir("POST", "/api/importacoes", {"arquivo_id": item["id"], "formato": formato},
                                esperado=(202,))
    finally:
        cliente.exigir("DELETE", f"/api/tokens/{token['id']}", esperado=(204,))
    resultado = {"importacao_id": criada["importacao_id"], "job_inspecao": criada["job_id"], "formato": formato,
                 "arquivo_id": item["id"]}
    if args.sem_esperar:
        return _emitir(args, resultado, [f"importação {criada['importacao_id']} criada (inspeção {criada['job_id']})"])
    _esperar_job(cliente, criada["job_id"], args.espera)
    importacao = cliente.exigir("GET", f"/api/importacoes/{criada['importacao_id']}")
    if importacao["estado"] != "proposta":
        raise ErroCLI(f"a inspeção terminou em estado {importacao['estado']!r}: {importacao.get('erro')}")
    confirmacao: dict = {}
    perguntas = (importacao.get("proposta") or {}).get("perguntas") or []
    if "crs" in perguntas or args.crs is not None:
        srid = args.crs or ((importacao.get("proposta") or {}).get("crs") or {}).get("sugestao")
        if srid is None:
            raise ErroCLI("a inspeção não descobriu o sistema de coordenadas; passe --crs <SRID>")
        confirmacao["crs"] = {"srid": int(srid)}
    if "codificacao" in perguntas:
        confirmacao["codificacao"] = {"valor": args.codificacao}
    confirmada = cliente.exigir("PUT", f"/api/importacoes/{criada['importacao_id']}/confirmar", confirmacao,
                                esperado=(202,))
    _esperar_job(cliente, confirmada["job_id"], args.espera)
    final = cliente.exigir("GET", f"/api/importacoes/{criada['importacao_id']}")
    resultado.update({"estado": final["estado"], "item_id": final.get("item_id"), "job_carga": confirmada["job_id"]})
    if final["estado"] != "concluida":
        raise ErroCLI(f"a carga terminou em estado {final['estado']!r}: {final.get('erro')}")
    return _emitir(args, resultado, [f"camada {final['item_id']} publicada a partir de {caminho.name}"])


# ---------------------------------------------------------------- job
def job_listar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    consulta = f"/api/jobs?limite={args.limite}"
    if args.estado:
        consulta += f"&estado={args.estado}"
    pagina = cliente.exigir("GET", consulta)
    return _emitir(args, pagina, [f"{j['id']}\t{j['tipo']}\t{j['estado']}" for j in pagina["itens"]])


def job_cancelar(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    j = cliente.exigir("POST", f"/api/jobs/{args.id}/cancelar", {}, esperado=(202,))
    return _emitir(args, j, [f"job {j['id']} em estado {j['estado']}"])


def job_repetir(args) -> int:
    cliente = _sessao(args, _inquilino_do_comando(args))
    j = cliente.exigir("POST", f"/api/jobs/{args.id}/repetir", {}, esperado=(201,))
    return _emitir(args, j, [f"job {j['id']} criado a partir de {args.id}"])


# ---------------------------------------------------------------- evento
def evento_exportar(args) -> int:
    """Baixa o registro de eventos página a página (a mesma rota da tela de auditoria) em JSON ou CSV."""
    cliente = _sessao(args, _inquilino_do_comando(args))
    base = f"/api/eventos?limite={args.pagina}"
    for nome, valor in (("desde", args.desde), ("ate", args.ate), ("tipo", args.tipo)):
        if valor:
            base += f"&{nome}={valor}"
    itens: list[dict] = []
    deslocamento, total = 0, None
    while total is None or (deslocamento < total and len(itens) < args.maximo):
        pagina = cliente.exigir("GET", f"{base}&deslocamento={deslocamento}")
        total = pagina["total"]
        if not pagina["itens"]:
            break
        itens.extend(pagina["itens"])
        deslocamento += len(pagina["itens"])
    itens = itens[: args.maximo]
    texto = _csv(itens) if args.formato == "csv" else json.dumps(itens, ensure_ascii=False, indent=2)
    if args.saida:
        Path(args.saida).write_text(texto, encoding="utf-8")
        return _emitir(args, {"exportados": len(itens), "total": total, "arquivo": args.saida},
                       [f"{len(itens)} eventos de {total} escritos em {args.saida}"])
    print(texto)
    return 0


def _csv(itens: list[dict]) -> str:
    """Achata o evento da API em colunas (o ator vem aninhado; `propriedades` vira JSON numa célula)."""
    colunas = ["id", "em", "tipo", "ator_id", "ator_login", "alvo_tipo", "alvo_id", "ip", "req_id", "propriedades"]
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=colunas, extrasaction="ignore")
    escritor.writeheader()
    for e in itens:
        ator = e.get("ator") or {}
        linha = {c: e.get(c) for c in colunas}
        linha["ator_id"] = ator.get("id")
        linha["ator_login"] = ator.get("login")
        if isinstance(linha.get("propriedades"), (dict, list)):
            linha["propriedades"] = json.dumps(linha["propriedades"], ensure_ascii=False)
        escritor.writerow(linha)
    return buffer.getvalue()


# ---------------------------------------------------------------- saúde e segredo
def saude(args) -> int:
    cliente = Cliente(url(args), args.tempo_limite)
    status, corpo = cliente.pedir("GET", "/saude")
    if args.json:
        print(json.dumps({"status": status, "corpo": corpo}, ensure_ascii=False, indent=2))
    else:
        print(f"{url(args)}/saude -> {status}")
    return 0 if status == 200 else 1


def segredo(args) -> int:
    """Repassa para scripts/segredo_rotacionar.py (item L7-19), que é quem toca /etc/plat e as unidades."""
    import subprocess

    executavel = RAIZ / "venv" / "bin" / "python"
    script = RAIZ / "scripts" / "segredo_rotacionar.py"
    if not script.exists():
        raise ErroCLI(f"{script} não existe nesta árvore")
    return subprocess.call([str(executavel if executavel.exists() else sys.executable), str(script),
                            "rotacionar", *args.resto])


def documentacao(args) -> int:
    from app.cli.documentacao import escrever

    destino = Path(args.destino) if args.destino else RAIZ / "docs" / "CLI.md"
    escrever(destino)
    print(f"{destino} gerado a partir do argparse")
    return 0
