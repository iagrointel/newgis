"""Gerador dos vídeos por tarefa (item L7-04-d-videos-por-tarefa): alvo `make videos`.

Playwright grava a sessão real de cada tarefa (webm); o ffmpeg monta o mp4 com a narração
sintética em pt-BR (voz livre piper, sem voz clonada) e as legendas WebVTT em pt-BR, en e es.
Cada legenda é escrita só depois de a ação do passo acontecer de verdade: passo que não existe
na versão instalada derruba a geração e nunca entra no vídeo. Os vídeos são regenerados quando
a versão menor do produto muda (arquivo VERSAO), ou com --forcar.

Uso (bancada da trilha no ar, com PLAT_URL_PUBLICA e PLAT_CREDENCIAIS_ARQUIVO no ambiente):
    set -a; source laco/var/trilha/<nome>.env; set +a
    venv/bin/python scripts/videos/gerar.py             # gera o que a versão pede
    venv/bin/python scripts/videos/gerar.py --forcar    # regenera todos
    venv/bin/python scripts/videos/gerar.py --validar   # confere o que existe, sem gerar nada

Saída em web/videos/ (fora do git): <tarefa>.mp4, <tarefa>.pt-BR.vtt (+ .en.vtt / .es.vtt) e
manifesto.json. Medidas em tests/medidas/L7-04-d-videos-por-tarefa.json (carga e RAM ao lado).
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from app.versao import versao  # noqa: E402
from scripts.videos.roteiros import TAREFAS  # noqa: E402

# tarefas que começam sem sessão: a própria tarefa é entrar na conta, ou a página é pública
SEM_LOGIN_PREVIO = {"saude", "entrar"}
DURACAO_LIMITE_S = 180.0  # portão: vídeo de até 3 minutos
IDIOMAS = (("pt-BR", 0), ("en", 1), ("es", 2))
SAIDA = RAIZ / "web" / "videos"
MEDIDAS = RAIZ / "tests" / "medidas" / "L7-04-d-videos-por-tarefa.json"
VAR = re.compile(r"\{(\w+)\}")


# ---------------------------------------------------------------- ferramentas externas

def _acha_ffmpeg() -> str:
    achado = shutil.which("ffmpeg")
    if not achado:
        sys.exit("ffmpeg não está no PATH; instale o pacote ffmpeg para gerar vídeos")
    return achado


def _acha_piper() -> Path:
    p = Path(os.environ.get("PLAT_PIPER") or (Path.home() / "tools" / "piper" / "piper"))
    if not p.exists():
        sys.exit(
            "piper não encontrado (procurei $PLAT_PIPER e ~/tools/piper/piper); "
            "o binário e a voz pt_BR vivem fora do git"
        )
    return p


def _piper_fala(texto: str, wav: Path, piper: Path) -> float:
    """Sintetiza uma frase em pt-BR e devolve a duração do wav em segundos."""
    voz = piper.parent / "vozes" / "pt_BR-faber-medium.onnx"
    if not voz.exists():
        sys.exit(f"voz piper ausente: {voz}")
    ambiente = dict(os.environ, LD_LIBRARY_PATH=str(piper.parent))
    subprocess.run(
        [str(piper), "-m", str(voz), "-c", str(voz) + ".json", "-f", str(wav)],
        input=texto, capture_output=True, text=True, env=ambiente, timeout=120, check=True,
    )
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "csv=p=0", str(wav)], capture_output=True, text=True, check=True,
    )
    return float(saida.stdout.strip())


# ---------------------------------------------------------------- interpolação e passos

def interpola(texto: str, var: dict[str, str]) -> str:
    def troca(m: re.Match) -> str:
        if m.group(1) not in var:
            raise KeyError(f"variável de roteiro sem valor: {m.group(1)}")
        return var[m.group(1)]

    return VAR.sub(troca, texto)


def _interpola_corpo(corpo, var: dict[str, str]):
    """Interpola {variaveis} em qualquer string do corpo de uma chamada de API (dict/lista aninhados)."""
    if isinstance(corpo, str):
        return interpola(corpo, var)
    if isinstance(corpo, dict):
        return {c: _interpola_corpo(v, var) for c, v in corpo.items()}
    if isinstance(corpo, list):
        return [_interpola_corpo(v, var) for v in corpo]
    return corpo


def secoes_do_manual() -> dict[str, str]:
    """Seções do manual GERADO (item L7-04-a): docs/manual/<id>.md, uma por tela do e2e.

    O vínculo do vídeo é com o manual gerado, não com o MANUAL.md histórico escrito à mão:
    o que o vídeo mostra é a tela da versão instalada, e é dessa tela que a seção é gerada.
    """
    pasta = RAIZ / "docs" / "manual"
    secoes: dict[str, str] = {}
    for caminho in sorted(pasta.glob("*.md")):
        ident = titulo = ""
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if linha.startswith("id:"):
                ident = linha[3:].strip()
            elif linha.startswith("titulo:"):
                titulo = linha[7:].strip().strip('"')
            if ident and titulo:
                break
        if ident:
            secoes[ident] = titulo or ident
    return secoes


def confere_secoes_manual() -> None:
    """Cada tarefa declara o id de uma seção de docs/manual/<id>.md; divergência derruba a geração."""
    secoes = secoes_do_manual()
    if not secoes:
        sys.exit("docs/manual está vazio: gere o manual (make manual) antes de gerar os vídeos")
    for tarefa in TAREFAS:
        ident = tarefa.get("manual_id")
        if not ident:
            sys.exit(f"tarefa {tarefa['id']}: sem campo manual_id (seção de docs/manual)")
        if ident not in secoes:
            sys.exit(
                f"tarefa {tarefa['id']}: a seção do manual gerado "
                f"'docs/manual/{ident}.md' não existe"
            )


# ---------------------------------------------------------------- execução do roteiro

def executa_passos(tela, var: dict[str, str], passos: list[dict]) -> list[dict]:
    """Roda os passos de uma tarefa na sessão gravada; devolve os passos com janelas de tempo.

    A janela [inicio, fim] de cada passo é medida com relógio desde a criação do contexto — a mesma
    referência de tempo do webm gravado pelo playwright."""
    t0 = time.perf_counter()
    anotados: list[dict] = []
    fim_anterior = 0.0
    for numero, passo in enumerate(passos, start=1):
        inicio = time.perf_counter() - t0
        for acao in passo["acoes"]:
            executa_acao(tela, acao, var)
        fim = time.perf_counter() - t0
        inicio = max(inicio, fim_anterior)
        fim_anterior = fim
        anotados.append({
            "numero": numero,
            "inicio_s": round(inicio, 2),
            "fim_s": round(fim, 2),
            "texto": passo["texto"],
        })
    return anotados


def executa_acao(tela, acao: dict, var: dict[str, str]) -> None:
    page = tela.page
    if "ir" in acao:
        tela.ir(interpola(acao["ir"], var))
    elif "clique" in acao:
        page.click(interpola(acao["clique"], var), timeout=20000)
        page.wait_for_timeout(350)
    elif "preencher" in acao:
        seletor, texto = acao["preencher"]
        page.fill(interpola(seletor, var), interpola(texto, var), timeout=20000)
    elif "selecionar" in acao:
        seletor, valor = acao["selecionar"]
        page.select_option(interpola(seletor, var), interpola(valor, var), timeout=20000)
    elif "teclar" in acao:
        seletor, tecla = acao["teclar"]
        page.press(interpola(seletor, var), tecla, timeout=20000)
    elif "esperar" in acao:
        page.wait_for_selector(interpola(acao["esperar"], var), timeout=25000)
    elif "esperar_js" in acao:
        page.wait_for_function(f"() => ({interpola(acao['esperar_js'], var)})", timeout=25000)
    elif "pausa" in acao:
        page.wait_for_timeout(int(acao["pausa"] * 1000))
    elif "api" in acao:
        metodo, caminho, corpo = acao["api"]
        r = tela.api(metodo, interpola(caminho, var), _interpola_corpo(corpo, var))
        if r.status not in (200, 201):
            raise RuntimeError(f"API {metodo} {caminho} devolveu {r.status}: {r.text()}")
        if acao.get("guardar_como"):
            corpo_resp = r.json()
            valor = corpo_resp.get("id", corpo_resp) if isinstance(corpo_resp, dict) else corpo_resp
            var[acao["guardar_como"]] = str(valor)
    else:
        raise KeyError(f"ação de roteiro desconhecida: {sorted(acao)}")


# ---------------------------------------------------------------- montagem do vídeo

def monta_video(ffmpeg: str, webm: Path, wavs: list[tuple[float, Path]], destino: Path) -> float:
    """Webm + narrações deslocadas -> mp4 h264+aac. Estende o último quadro se a narração passar do vídeo."""
    dur_video = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(webm)],
        capture_output=True, text=True, check=True).stdout.strip())
    fim_audio = max((inicio + _duracao_wav(w) for inicio, w in wavs), default=0.0)
    total = max(dur_video, fim_audio + 0.8)
    filtros = []
    entradas = ["-i", str(webm)]
    for i, (inicio, wav) in enumerate(wavs, start=1):
        entradas += ["-i", str(wav)]
        filtros.append(f"[{i}:a]volume=1.8,adelay={int(inicio * 1000)}:all=1[a{i}]")
    mistura = "".join(f"[a{i}]" for i in range(1, len(wavs) + 1))
    if wavs:
        filtros.append(f"{mistura}amix=inputs={len(wavs)}:normalize=0,apad,atrim=0:{total:.2f}[a]")
    else:
        filtros.append(f"anullsrc=channel_layout=mono:sample_rate=22050,atrim=0:{total:.2f}[a]")
    ext = f",tpad=stop_mode=clone:stop_duration={(total - dur_video + 0.5):.2f}" if total > dur_video else ""
    filtros.insert(0, f"[0:v]fps=12,scale=1280:800{ext},format=yuv420p[v]")
    comando = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *entradas,
               "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[a]",
               "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
               "-c:a", "aac", "-b:a", "96k", "-ar", "22050", "-movflags", "+faststart", str(destino)]
    subprocess.run(comando, check=True, timeout=300)
    return total


def _duracao_wav(wav: Path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
        capture_output=True, text=True, check=True).stdout.strip())


def escreve_vtt(passos: list[dict], destino: Path, indice_idioma: int) -> None:
    linhas = ["WEBVTT", ""]
    for p in passos:
        ini, fim = p["inicio_s"], max(p["fim_s"], p["inicio_s"] + 1.5)
        def marca(seg: float) -> str:
            ms = int(round(seg * 1000))
            h, resto = divmod(ms, 3600000)
            m, resto = divmod(resto, 60000)
            s, mil = divmod(resto, 1000)
            return f"{h:02d}:{m:02d}:{s:02d}.{mil:03d}"
        linhas += [f"{marca(ini)} --> {marca(fim)}", p["texto"][indice_idioma], ""]
    destino.write_text("\n".join(linhas), encoding="utf-8")


# ---------------------------------------------------------------- geração

def variveis_da_tarefa(tarefa_id: str, sufixo: str, cred: tuple[str, str]) -> dict[str, str]:
    login, senha = cred
    return {
        "usuario": login,
        "senha": senha,
        "novo_login": f"video_{sufixo}",
        "grupo": f"grupo do video {sufixo}",
        "token": f"token do video {sufixo}",
        "conexao_nome": f"conexao do video {sufixo}",
        "job": "",
        "conexao": "",
    }


def limpar(tela, tarefa_id: str, var: dict[str, str]) -> list[str]:
    """Apaga por API o que a demonstração criou; devolve o que não conseguiu apagar."""
    restou = []
    if tarefa_id == "usuarios":
        r = tela.api("GET", f"/api/usuarios?busca={var['novo_login']}&limite=50")
        for u in (r.json().get("itens", []) if r.status == 200 else []):
            if u.get("login") == var["novo_login"]:
                if tela.api("DELETE", f"/api/usuarios/{u['id']}").status not in (204, 200):
                    restou.append(f"usuario {var['novo_login']}")
    elif tarefa_id == "grupos":
        r = tela.api("GET", "/api/grupos?meus=1&limite=100")
        for g in (r.json().get("itens", []) if r.status == 200 else []):
            if g.get("nome") == var["grupo"]:
                if tela.api("DELETE", f"/api/grupos/{g['id']}").status not in (204, 200):
                    restou.append(f"grupo {var['grupo']}")
    elif tarefa_id == "conexoes" and var["conexao"]:
        if tela.api("DELETE", f"/api/conexoes/{var['conexao']}").status not in (204, 200):
            restou.append(f"conexao {var['conexao']}")
    return restou


def pre_limpar(tela) -> list[str]:
    """Apaga resíduos de rodadas anteriores interrompidas (a rodada só limpa o que criou se chega ao fim).

    Nomes com prefixo do vídeo nunca são de dados reais: usuario video_*, grupo/token/conexão
    "do video". Tolerante: devolve o que não conseguiu apagar e nunca derruba a geração."""
    restou: list[str] = []
    try:
        r = tela.api("GET", "/api/usuarios?busca=video_&limite=100")
        for u in (r.json().get("itens", []) if r.status == 200 else []):
            if str(u.get("login", "")).startswith("video_") and tela.api(
                "DELETE", f"/api/usuarios/{u['id']}"
            ).status not in (204, 200):
                restou.append(f"usuario {u.get('login')}")
        r = tela.api("GET", "/api/grupos?meus=1&limite=100")
        for g in (r.json().get("itens", []) if r.status == 200 else []):
            if str(g.get("nome", "")).startswith("grupo do video") and tela.api(
                "DELETE", f"/api/grupos/{g['id']}"
            ).status not in (204, 200):
                restou.append(f"grupo {g.get('nome')}")
        for pagina in range(1, 6):
            r = tela.api("GET", f"/api/conexoes?limite=100&pagina={pagina}")
            if r.status != 200:
                break
            itens = r.json().get("itens", [])
            for c in itens:
                nome_c = str(c.get("nome", ""))
                resido = nome_c.startswith("conexao do video") or nome_c == "{conexao_nome}"
                if resido and tela.api(
                    "DELETE", f"/api/conexoes/{c['id']}"
                ).status not in (204, 200):
                    restou.append(f"conexao {nome_c}")
            if pagina * 100 >= r.json().get("total", 0):
                break
    except Exception as e:  # higiene não pode derrubar a geração
        restou.append(f"pre-limpeza: {e}")
    return restou


def gerar(base_url: str, forcar: bool) -> int:
    from playwright.sync_api import sync_playwright

    from tests.e2e.apoio import Tela, credenciais

    ffmpeg = _acha_ffmpeg()
    piper = _acha_piper()
    confere_secoes_manual()
    creds = credenciais()
    if "demo" not in creds:
        sys.exit("credenciais do inquilino demo ausentes (PLAT_CREDENCIAIS_ARQUIVO)")
    slug, login, senha = "demo", *creds["demo"]

    manifesto_cam = SAIDA / "manifesto.json"
    if manifesto_cam.exists() and not forcar:
        atual = json.loads(manifesto_cam.read_text(encoding="utf-8"))
        if atual.get("versao") == versao() and all(
            (SAIDA / f"{t['id']}.mp4").exists() for t in TAREFAS
        ):
            print(f"vídeos atuais para a versão {versao()}; use --forcar para regenerar")
            return 0

    SAIDA.mkdir(parents=True, exist_ok=True)
    sufixo = os.urandom(2).hex()
    resultados: dict[str, dict] = {}
    restantes: list[str] = []
    print(f"vídeos por tarefa da versão {versao()} contra {base_url}")

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        # resíduos de rodadas anteriores interrompidas saem antes de a câmera ligar
        ctx_hig = navegador.new_context(
            locale="pt-BR", viewport={"width": 1280, "height": 800},
            base_url=base_url, ignore_https_errors=True)
        tela_hig = Tela(ctx_hig.new_page(), base_url)
        tela_hig.entrar(slug, login, senha)
        restantes += pre_limpar(tela_hig)
        ctx_hig.close()
        for tarefa in TAREFAS:
            var = variveis_da_tarefa(tarefa["id"], sufixo, (login, senha))
            with tempfile.TemporaryDirectory(prefix=f"video-{tarefa['id']}-") as grav_tmp:
                gravacao = Path(grav_tmp)
                contexto = navegador.new_context(
                    locale="pt-BR", viewport={"width": 1280, "height": 800},
                    record_video_dir=str(gravacao), record_video_size={"width": 1280, "height": 800},
                    base_url=base_url,  # goto relativo (Tela.entrar/ir navegam por caminho)
                    ignore_https_errors=True,  # bancada de trilha com cert autoassinado
                )
                page = contexto.new_page()
                tela = Tela(page, base_url)
                if tarefa["id"] not in SEM_LOGIN_PREVIO:
                    tela.entrar(slug, login, senha)
                passos = executa_passos(tela, var, tarefa["passos"])
                restantes += limpar(tela, tarefa["id"], var)
                tela.verificar()
                contexto.close()
                webm = next(gravacao.glob("*.webm"))
                # a voz e a montagem ficam DENTRO do diretório da gravação: fora dele o
                # TemporaryDirectory apaga o webm antes de o ffmpeg ler
                wavs: list[tuple[float, Path]] = []
                with tempfile.TemporaryDirectory(prefix=f"voz-{tarefa['id']}-") as voz_tmp:
                    voz = Path(voz_tmp)
                    for passo in passos:
                        wav = voz / f"passo_{passo['numero']:02d}.wav"
                        _piper_fala(passo["texto"][0], wav, piper)
                        wavs.append((passo["inicio_s"], wav))
                    destino = SAIDA / f"{tarefa['id']}.mp4"
                    duracao = monta_video(ffmpeg, webm, wavs, destino)
            for rotulo, indice in IDIOMAS:
                escreve_vtt(passos, SAIDA / f"{tarefa['id']}.{rotulo}.vtt", indice)
            resultados[tarefa["id"]] = {
                "titulo": tarefa["titulo"],
                "manual": tarefa["manual"],
                "arquivo": destino.name,
                "duracao_s": round(duracao, 1),
                "bytes": destino.stat().st_size,
                "passos": len(passos),
                "passos_s": [[p["inicio_s"], p["fim_s"]] for p in passos],
                "idiomas_legenda": [r for r, _ in IDIOMAS],
                "tem_audio": True,
                "sha256": hashlib_arquivo(destino),
            }
            print(f"  {tarefa['id']}.mp4: {duracao:.1f} s, {len(passos)} passos")
        navegador.close()

    if restantes:
        print("AVISO: a limpeza não apagou:", ", ".join(restantes))
    manifesto = {
        "versao": versao(),
        "gerado_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "idioma_narracao": "pt-BR",
        "voz": "piper pt_BR-faber-medium (sintética, livre)",
        "limite_duracao_s": DURACAO_LIMITE_S,
        "tarefas": resultados,
    }
    manifesto_cam.write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    grava_medidas(resultados)
    return 0


def hashlib_arquivo(caminho: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(caminho.read_bytes())
    return h.hexdigest()


def grava_medidas(resultados: dict[str, dict]) -> None:
    carga = os.getloadavg()[0]
    ram_livre = round(_ram_livre_gb(), 1)
    medidas = {
        "item": "L7-04-d-videos-por-tarefa",
        "medido_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "versao": versao(),
        "videos": len(resultados),
        "limite_duracao_s": DURACAO_LIMITE_S,
        "maior_duracao_s": max(v["duracao_s"] for v in resultados.values()),
        "duracoes_s": {k: v["duracao_s"] for k, v in resultados.items()},
        "bytes_total": sum(v["bytes"] for v in resultados.values()),
        "carga_1min": round(carga, 2),
        "ram_livre_gb": ram_livre,
        "comando": "make videos (scripts/videos/gerar.py)",
    }
    MEDIDAS.write_text(json.dumps(medidas, ensure_ascii=False, indent=1), encoding="utf-8")


def _ram_livre_gb() -> float:
    com = subprocess.run(["free", "-g"], capture_output=True, text=True, check=True).stdout
    linha = [x for x in com.splitlines() if x.startswith("Mem:")][0].split()
    return float(linha[-1])


# ---------------------------------------------------------------- validação (sem gerar nada)

def validar() -> int:
    manifesto_cam = SAIDA / "manifesto.json"
    if not manifesto_cam.exists():
        print("VALIDOU NÃO: web/videos/manifesto.json não existe (rode make videos)")
        return 1
    manifesto = json.loads(manifesto_cam.read_text(encoding="utf-8"))
    falhas: list[str] = []
    if len(manifesto.get("tarefas", {})) < 10:
        falhas.append(f"só {len(manifesto.get('tarefas', {}))} vídeos, o portão pede 10 ou mais")
    for tarefa in TAREFAS:
        id_t = tarefa["id"]
        mp4 = SAIDA / f"{id_t}.mp4"
        if not mp4.exists():
            falhas.append(f"{id_t}: mp4 ausente")
            continue
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
            capture_output=True, text=True, check=True).stdout.strip())
        if dur > DURACAO_LIMITE_S:
            falhas.append(f"{id_t}: {dur:.0f} s passa de {DURACAO_LIMITE_S:.0f} s")
        fluxos = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mp4)],
            capture_output=True, text=True, check=True).stdout.split()
        if "video" not in fluxos or "audio" not in fluxos:
            falhas.append(f"{id_t}: mp4 sem fluxo de vídeo ou de áudio ({fluxos})")
        for rotulo, _ in IDIOMAS:
            vtt = SAIDA / f"{id_t}.{rotulo}.vtt"
            if not vtt.exists() or "-->" not in vtt.read_text(encoding="utf-8"):
                falhas.append(f"{id_t}: legenda {rotulo} ausente ou vazia")
    confere_secoes_manual()
    if manifesto.get("versao") != versao():
        falhas.append(f"manifesto é da versão {manifesto.get('versao')}, o repositório está em {versao()}")
    if falhas:
        print("VALIDOU NÃO:")
        for f in falhas:
            print(" -", f)
        return 1
    n = len(manifesto["tarefas"])
    maior = max(v["duracao_s"] for v in manifesto["tarefas"].values())
    print(f"VALIDOU: {n} vídeos com vídeo+áudio e 3 legendas, maior duração {maior} s "
          f"(limite {DURACAO_LIMITE_S:.0f} s), seções do manual conferidas")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forcar", action="store_true", help="regenera mesmo com a versão igual")
    parser.add_argument("--validar", action="store_true", help="só confere o que existe")
    parser.add_argument("--base-url", default=os.environ.get("PLAT_URL_PUBLICA"))
    args = parser.parse_args()
    if args.validar:
        return validar()
    if not args.base_url:
        sys.exit("sem PLAT_URL_PUBLICA no ambiente nem --base-url")
    return gerar(args.base_url.rstrip("/"), args.forcar)


if __name__ == "__main__":
    raise SystemExit(main())
