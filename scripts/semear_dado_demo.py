"""Semeia o conjunto de demonstração nos inquilinos `demo` e `demo2` (item L0-13-dado-demonstracao).

Usa a PRÓPRIA plataforma pela API HTTP, no mesmo caminho de um usuário: entra como administrador do
inquilino, sobe o arquivo (POST /api/arquivos), registra o item de arquivo (POST /api/itens), pede a
importação (POST /api/importacoes), confirma a proposta e espera o job carregar a camada. Não escreve
uma linha de SQL direto e não tem caminho paralelo de carga: se a ingestão quebrar, a semeadura falha.

Os arquivos e o metadado de cada um (fonte, órgão, endereço, licença, data de acesso) vêm de
`dados_demo/catalogo.json`, comitado no repositório. Nada é baixado da rede.

Idempotente: reconhece o que já semeou pelo título do item dentro do inquilino e só cria o que falta.

Uso:
    venv/bin/python scripts/semear_dado_demo.py --base-url http://127.0.0.1:8150
    venv/bin/python scripts/semear_dado_demo.py --base-url ... --medida tests/medidas/x.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / "dados_demo" / "catalogo.json"
ARQUIVOS = RAIZ / "dados_demo" / "arquivos"
TOKEN_NOME = "semente-dado-demo"
ESPERA_JOB_S = 180.0

# categorias do inquilino (2 níveis): a árvore é reescrita inteira pela API, então a semeadura só
# ACRESCENTA o que falta ao que já existe.
CATEGORIAS_DEMO = ["Limites administrativos", "Transporte", "Água", "Clima", "Demonstração"]
GRUPOS_DEMO = [
    {"nome": "Equipe de campo (demonstração)", "resumo": "Grupo de exemplo: quem levanta dado em campo.",
     "visibilidade": "inquilino", "entrada": "convite"},
    {"nome": "Análise territorial (demonstração)", "resumo": "Grupo de exemplo: quem cruza as camadas.",
     "visibilidade": "inquilino", "entrada": "convite"},
]
TITULO_LIXEIRA = "Planta de exemplo (versão retirada do catálogo)"


class Erro(RuntimeError):
    pass


def credenciais(caminho: Path) -> dict[str, tuple[str, str]]:
    saida: dict[str, tuple[str, str]] = {}
    if not caminho.exists():
        raise Erro(f"arquivo de credenciais inexistente: {caminho} (rode o install.sh)")
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) >= 3:
            saida[partes[0]] = (partes[1], " ".join(partes[2:]))
    return saida


class Cliente:
    """Sessão de administrador de um inquilino, com um token de serviço para o envio de arquivo (o
    upload manda bytes crus, que a defesa de CSRF sob cookie recusa por não ser application/json)."""

    def __init__(self, base_url: str, slug: str, login: str, senha: str, verboso: bool = True):
        self.slug = slug
        self.verboso = verboso
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=120.0)
        # cliente separado, SEM o cookie de sessão: a API recusa (400 autenticacao_ambigua) quem manda
        # cookie e Authorization na mesma requisição, e o envio de arquivo exige token (bytes crus)
        self.http_token = httpx.Client(base_url=base_url.rstrip("/"), timeout=300.0)
        r = self.http.post("/api/login", json={"inquilino": slug, "login": login, "senha": senha})
        if r.status_code != 200 or not r.json().get("ok"):
            raise Erro(f"login de {slug} falhou: {r.status_code} {r.text[:300]}")
        if r.json().get("exige_2fa"):
            raise Erro(f"o administrador de {slug} exige 2FA; a semeadura só cobre os inquilinos de demonstração")
        self._token: str | None = None
        self._token_id: str | None = None

    def fechar(self) -> None:
        if self._token_id:
            self.http.delete(f"/api/tokens/{self._token_id}")
            self._token_id = None
        self.http.close()
        self.http_token.close()

    def token(self) -> str:
        if self._token is None:
            r = self.http.post("/api/tokens", json={"nome": TOKEN_NOME, "escopos": ["admin:inquilino"]})
            if r.status_code != 201:
                raise Erro(f"não criou token em {self.slug}: {r.status_code} {r.text[:300]}")
            self._token = r.json()["token"]
            self._token_id = r.json()["id"]
        return self._token

    def dizer(self, msg: str) -> None:
        if self.verboso:
            print(f"  [{self.slug}] {msg}", flush=True)

    # ------------------------------------------------------------------ catálogo
    def titulos(self) -> dict[str, str]:
        """{titulo: item_id} de tudo que o inquilino já tem, incluindo o que está na lixeira (sem isso a
        semeadura recriaria a cada execução o item que ela mesma mandou para a lixeira)."""
        saida: dict[str, str] = {}
        for rota in ("/api/itens", "/api/lixeira"):
            deslocamento = 0
            while True:
                r = self.http.get(rota, params={"limite": 200, "deslocamento": deslocamento})
                if r.status_code != 200:
                    raise Erro(f"listagem de {rota} falhou: {r.status_code} {r.text[:300]}")
                corpo = r.json()
                for it in corpo["itens"]:
                    saida[it["titulo"]] = it["id"]
                deslocamento += len(corpo["itens"])
                if not corpo["itens"] or deslocamento >= corpo["total"]:
                    break
        return saida

    def categorias(self, nomes: list[str]) -> dict[str, str]:
        r = self.http.get("/api/categorias")
        if r.status_code != 200:
            raise Erro(f"leitura de categorias falhou: {r.status_code} {r.text[:300]}")
        arvore = r.json()["arvore"]
        existentes = {no["nome"]: no for no in arvore}
        faltam = [n for n in nomes if n not in existentes]
        if faltam:
            nova = [{"id": no["id"], "nome": no["nome"], "codigo": no.get("codigo"), "filhas": []} for no in arvore]
            nova += [{"nome": n, "filhas": []} for n in faltam]
            r = self.http.put("/api/categorias", json={"arvore": nova})
            if r.status_code != 200:
                raise Erro(f"gravação de categorias falhou: {r.status_code} {r.text[:300]}")
            arvore = r.json()["arvore"]
        return {no["nome"]: no["id"] for no in arvore}

    def grupos(self, desejados: list[dict]) -> list[str]:
        r = self.http.get("/api/grupos", params={"limite": 200})
        existentes = {g["nome"]: g["id"] for g in r.json()["itens"]} if r.status_code == 200 else {}
        ids = []
        for g in desejados:
            if g["nome"] in existentes:
                ids.append(existentes[g["nome"]])
                continue
            r = self.http.post("/api/grupos", json=g)
            if r.status_code != 201:
                raise Erro(f"criação do grupo {g['nome']!r} falhou: {r.status_code} {r.text[:300]}")
            ids.append(r.json()["id"])
        return ids

    # ------------------------------------------------------------------ arquivo e ingestão
    def enviar_arquivo(self, caminho: Path, classe: str) -> dict:
        dados = caminho.read_bytes()
        r = self.http_token.post(
            "/api/arquivos", params={"classe": classe}, content=dados,
            headers={"authorization": f"Bearer {self.token()}", "content-type": "application/octet-stream"},
        )
        if r.status_code != 201:
            raise Erro(f"envio de {caminho.name} falhou: {r.status_code} {r.text[:300]}")
        return r.json()

    def criar_item(self, corpo: dict) -> str:
        r = self.http.post("/api/itens", json=corpo)
        if r.status_code != 201:
            raise Erro(f"criação do item {corpo['titulo']!r} falhou: {r.status_code} {r.text[:300]}")
        return r.json()["id"]

    def esperar_job(self, job_id: str) -> dict:
        fim = time.monotonic() + ESPERA_JOB_S
        ultimo = None
        while time.monotonic() < fim:
            r = self.http.get(f"/api/jobs/{job_id}")
            if r.status_code != 200:
                raise Erro(f"consulta do job {job_id} falhou: {r.status_code} {r.text[:300]}")
            ultimo = r.json()
            if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
                return ultimo
            time.sleep(0.3)
        raise Erro(f"job {job_id} não terminou em {ESPERA_JOB_S:.0f} s: {ultimo}")

    def importar(self, arquivo_item_id: str, formato: str, titulo: str, metadado: dict) -> str:
        r = self.http.post("/api/importacoes", json={"arquivo_id": arquivo_item_id, "formato": formato})
        if r.status_code != 202:
            raise Erro(f"importação de {titulo!r} recusada: {r.status_code} {r.text[:300]}")
        importacao_id = r.json()["importacao_id"]
        job = self.esperar_job(r.json()["job_id"])
        if job["estado"] != "concluido":
            raise Erro(f"inspeção de {titulo!r} falhou: {job.get('erro')}")
        r = self.http.get(f"/api/importacoes/{importacao_id}")
        proposta = r.json()["proposta"] or {}
        corpo: dict = {"titulo": titulo}
        perguntas = proposta.get("perguntas") or []
        if "crs" in perguntas:
            sugestao = (proposta.get("crs") or {}).get("sugestao") or 4674
            corpo["crs"] = {"srid": sugestao}
        if "codificacao" in perguntas:
            corpo["codificacao"] = {"valor": "UTF-8"}
        r = self.http.put(f"/api/importacoes/{importacao_id}/confirmar", json=corpo)
        if r.status_code != 202:
            raise Erro(f"confirmação de {titulo!r} recusada: {r.status_code} {r.text[:300]}")
        job = self.esperar_job(r.json()["job_id"])
        if job["estado"] != "concluido":
            raise Erro(f"carga de {titulo!r} falhou: {job.get('erro')}")
        r = self.http.get(f"/api/importacoes/{importacao_id}")
        final = r.json()
        if final["estado"] != "concluida":
            raise Erro(f"importação de {titulo!r} terminou em {final['estado']}: {final.get('erro')}")
        item_id = final["item_id"]
        r = self.http.patch(f"/api/itens/{item_id}", json=metadado)
        if r.status_code != 200:
            raise Erro(f"metadado da camada {titulo!r} falhou: {r.status_code} {r.text[:300]}")
        return item_id


def metadado_de(it: dict, categoria_id: str | None) -> dict:
    """Metadado do item a partir da linha do catálogo: crédito = órgão, termos de uso = licença lida na
    fonte, url = endereço de origem, tags e categoria. É o mesmo texto de docs/DADO_DEMO.md."""
    corpo = {
        "resumo": it["resumo"],
        "descricao": (
            f"Fonte: {it['fonte']} ({it['orgao']}).\n\n"
            f"Endereço: {it['url']}\n\n"
            f"Licença: {it['licenca']}\n\n"
            f"Data de acesso: {it['data_acesso']}\n\n"
            f"Arquivo de origem: `dados_demo/arquivos/{it['arquivo']}` (sha256 {it['sha256'][:16]}...)."
        ),
        "tags": it["tags"],
        "creditos": f"{it['orgao']} — {it['fonte']}",
        "termos_de_uso": it["licenca"],
        "origem": "hospedado",
        "url": it["url"],
    }
    if categoria_id:
        corpo["categorias"] = [categoria_id]
    return corpo


def semear_inquilino(base_url: str, slug: str, login: str, senha: str, itens: list[dict],
                     verboso: bool = True) -> dict:
    cli = Cliente(base_url, slug, login, senha, verboso)
    try:
        criados = {"arquivo": 0, "camada": 0, "reaproveitados": 0}
        tempos: dict[str, float] = {}
        cats = cli.categorias(sorted({it["categoria"] for it in itens}))
        titulos = cli.titulos()
        for it in itens:
            t0 = time.monotonic()
            titulo_arquivo = f"{it['titulo']} (arquivo de origem)"
            meta = metadado_de(it, cats.get(it["categoria"]))
            if titulo_arquivo in titulos:
                arquivo_item = titulos[titulo_arquivo]
                criados["reaproveitados"] += 1
            else:
                obj = cli.enviar_arquivo(ARQUIVOS / it["arquivo"],
                                         "camada_arquivo" if it["ingerir"] else "objeto")
                corpo = dict(meta)
                corpo.update({
                    "tipo": "arquivo", "titulo": titulo_arquivo,
                    "dados": {"chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"],
                              "content_type": obj["content_type"], "nome_original": it["arquivo"]},
                })
                arquivo_item = cli.criar_item(corpo)
                criados["arquivo"] += 1
                cli.dizer(f"arquivo {it['arquivo']} ({obj['bytes']} bytes)")
            if it["ingerir"]:
                if it["titulo"] in titulos:
                    criados["reaproveitados"] += 1
                else:
                    cli.importar(arquivo_item, it["formato"], it["titulo"], meta)
                    criados["camada"] += 1
                    cli.dizer(f"camada {it['titulo']!r} carregada pela ingestão")
            tempos[it["arquivo"]] = round(time.monotonic() - t0, 2)
        extras = {}
        if slug == "demo":
            extras = semear_extras_demo(cli, itens, cats, criados)
        return {"inquilino": slug, **criados, **extras, "segundos_por_arquivo": tempos}
    finally:
        cli.fechar()


def semear_extras_demo(cli: Cliente, itens: list[dict], cats: dict, criados: dict) -> dict:
    """O que o item pede além dos arquivos: 2 grupos, 1 link compartilhado e 1 item na lixeira."""
    grupos = cli.grupos(GRUPOS_DEMO)
    titulos = cli.titulos()
    alvo_titulo = itens[0]["titulo"]
    alvo = titulos.get(alvo_titulo)
    if alvo:
        r = cli.http.put(f"/api/itens/{alvo}/compartilhamento",
                         json={"acesso": "privado", "grupos": grupos[:1]})
        if r.status_code != 200:
            raise Erro(f"compartilhamento com grupo falhou: {r.status_code} {r.text[:300]}")
        r = cli.http.get(f"/api/itens/{alvo}/links")
        corpo_links = r.json() if r.status_code == 200 else []
        links = corpo_links if isinstance(corpo_links, list) else corpo_links.get("itens", [])
        if not links:
            r = cli.http.post(f"/api/itens/{alvo}/links",
                              json={"nome": "Link de demonstração", "permite_download": False})
            if r.status_code != 201:
                raise Erro(f"criação do link falhou: {r.status_code} {r.text[:300]}")
            cli.dizer(f"link compartilhado criado em {alvo_titulo!r}")
    if TITULO_LIXEIRA not in titulos:
        dxf = next(it for it in itens if it["arquivo"].endswith(".dxf"))
        obj = cli.enviar_arquivo(ARQUIVOS / dxf["arquivo"], "objeto")
        corpo = dict(metadado_de(dxf, cats.get(dxf["categoria"])))
        corpo.update({
            "tipo": "arquivo", "titulo": TITULO_LIXEIRA,
            "dados": {"chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"],
                      "content_type": obj["content_type"], "nome_original": dxf["arquivo"]},
        })
        iid = cli.criar_item(corpo)
        r = cli.http.delete(f"/api/itens/{iid}")
        if r.status_code != 204:
            raise Erro(f"envio à lixeira falhou: {r.status_code} {r.text[:300]}")
        criados["arquivo"] += 1
        cli.dizer("um item colocado na lixeira")
    return {"grupos": len(grupos)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="semeia o conjunto de demonstração (item L0-13)")
    p.add_argument("--base-url", default=os.environ.get("PLAT_URL_PUBLICA", "http://127.0.0.1:8150"))
    p.add_argument("--credenciais", default=os.environ.get("PLAT_CREDENCIAIS_ARQUIVO",
                                                           str(RAIZ / "tests" / "credenciais.txt")))
    p.add_argument("--medida", default=None, help="grava o resultado e o tempo neste JSON")
    p.add_argument("--silencioso", action="store_true")
    a = p.parse_args(argv)

    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    cred = credenciais(Path(a.credenciais))
    inicio = time.monotonic()
    resultados = []
    for slug in ("demo", "demo2"):
        itens = [it for it in catalogo["itens"] if it["inquilino"] == slug]
        if not itens:
            continue
        if slug not in cred:
            raise Erro(f"{a.credenciais} não tem a linha de {slug}")
        login, senha = cred[slug]
        resultados.append(semear_inquilino(a.base_url, slug, login, senha, itens, not a.silencioso))
    segundos = time.monotonic() - inicio
    resumo = {"segundos": round(segundos, 2), "inquilinos": resultados,
              "arquivos_no_catalogo": len(catalogo["itens"])}
    print(json.dumps(resumo, ensure_ascii=False), flush=True)
    if a.medida:
        Path(a.medida).write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Erro as e:
        print(f"semeadura do dado de demonstração falhou: {e}", file=sys.stderr)
        sys.exit(1)
