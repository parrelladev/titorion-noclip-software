#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor local para o site baixado com "Extrator de Sites Brave Cross".

Motivo de existir: abrir o site com file:// faz o navegador bloquear modulos ES,
fetch() de modelos .glb, texturas em WebGL e fontes. Servindo por HTTP, tudo
volta a funcionar exatamente como no site original.

Uso:
    python3 servidor.py                 # porta 8080
    python3 servidor.py 3000            # outra porta
    python3 servidor.py --isolar        # liga COOP/COEP (Draco/Basis com threads)
    python3 servidor.py --sem-navegador # nao abre o navegador sozinho

Requer apenas Python 3.7+. Nenhuma dependencia externa.
"""

import argparse
import json
import functools
import http.server
import mimetypes
import os
import socket
import socketserver
import sys
import threading
import webbrowser

# Tipos que servidores costumam nao conhecer e que sites 3D precisam.
EXTRA_TYPES = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".bin": "application/octet-stream",
    ".drc": "application/octet-stream",
    ".fbx": "application/octet-stream",
    ".obj": "text/plain",
    ".mtl": "text/plain",
    ".ply": "application/octet-stream",
    ".stl": "model/stl",
    ".usdz": "model/vnd.usdz+zip",
    ".splat": "application/octet-stream",
    ".ksplat": "application/octet-stream",
    ".hdr": "image/vnd.radiance",
    ".exr": "image/x-exr",
    ".ktx": "image/ktx",
    ".ktx2": "image/ktx2",
    ".basis": "application/octet-stream",
    ".dds": "image/vnd-ms.dds",
    ".wasm": "application/wasm",
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".cjs": "text/javascript",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".glsl": "text/plain",
    ".vert": "text/plain",
    ".frag": "text/plain",
    ".wgsl": "text/plain",
}

for ext, mime in EXTRA_TYPES.items():
    mimetypes.add_type(mime, ext)


ASSINATURAS = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF8", "image/gif"),
    (b"wOF2", "font/woff2"),
    (b"wOFF", "font/woff"),
    (b"\x00asm", "application/wasm"),
    (b"glTF", "model/gltf-binary"),
    (b"%PDF", "application/pdf"),
    (b"\x00\x01\x00\x00", "font/ttf"),
    (b"OTTO", "font/otf"),
    (b"#?RADIANCE", "image/vnd.radiance"),
]


def farejar_tipo(caminho):
    """Descobre o tipo lendo os primeiros bytes, para arquivos sem extensao."""
    try:
        with open(caminho, "rb") as fh:
            cabeca = fh.read(32)
    except OSError:
        return None

    for assinatura, mime in ASSINATURAS:
        if cabeca.startswith(assinatura):
            return mime

    # Formatos em container ISO-BMFF / RIFF trazem a marca alguns bytes adiante.
    if cabeca[4:8] == b"ftyp":
        marca = cabeca[8:12]
        if marca in (b"avif", b"avis"):
            return "image/avif"
        if marca.startswith(b"hei"):
            return "image/heic"
        return "video/mp4"
    if cabeca[:4] == b"RIFF" and cabeca[8:12] == b"WEBP":
        return "image/webp"

    inicio = cabeca.lstrip()[:14].lower()
    if inicio.startswith(b"<?xml") or inicio.startswith(b"<svg"):
        return "image/svg+xml"
    if inicio.startswith(b"<!doctype") or inicio.startswith(b"<html"):
        return "text/html"
    if inicio[:1] in (b"{", b"["):
        return "application/json"
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    isolate = False
    quiet = False

    inicial = "index.html"

    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map)
    extensions_map.update(EXTRA_TYPES)

    # ------------------------------------------------------------------
    # Navegacao de SPA
    #
    # Frameworks como Next.js, Nuxt e SvelteKit interceptam o clique num link
    # e fazem history.pushState. Quando o roteador precisa recarregar de
    # verdade, o navegador pede "/about" ao servidor, um caminho que nao existe
    # como arquivo, porque a pagina foi salva como "about.html".
    #
    # Sem este tratamento o usuario ve a pagina de erro do Python no lugar do
    # site. Entao, para requisicoes de NAVEGACAO (nao de asset), procuramos o
    # arquivo equivalente e, em ultimo caso, entregamos o index.html para o
    # roteador do proprio site resolver no cliente.
    # ------------------------------------------------------------------

    def _e_navegacao(self):
        accept = self.headers.get("Accept", "")
        if "text/html" in accept:
            return True
        # Sem Accept util: trata como navegacao se nao parece pedido de asset.
        _, ext = os.path.splitext(self.path.split("?")[0])
        return ext == ""

    def _alternativas(self, caminho):
        yield caminho + ".html"
        yield os.path.join(caminho, "index.html")
        yield caminho + "/index.html"

    # ------------------------------------------------------------------
    # Seguranca
    #
    # O servidor so escuta em 127.0.0.1, mas isso nao basta: qualquer site
    # aberto no navegador consegue mandar requisicoes para localhost. Duas
    # travas impedem que ele LEIA a copia (que pode ter paginas logadas):
    #   - sem Access-Control-Allow-Origin: outra origem nao le as respostas;
    #   - Host conferido: sem isso, um dominio que resolve para 127.0.0.1
    #     (DNS rebinding) viraria "mesma origem" e leria tudo.
    # ------------------------------------------------------------------

    HOSTS_OK = ("localhost", "127.0.0.1", "[::1]")

    def _host_valido(self):
        host = (self.headers.get("Host") or "").strip().lower()
        nome = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        return nome in self.HOSTS_OK

    def send_head(self):
        if not self._host_valido():
            self.send_error(403, "Host nao permitido")
            return None

        # Nada de listar pastas nem servir arquivos ocultos (.git, .env...).
        limpo = self.path.split("?", 1)[0].split("#", 1)[0]
        if any(p.startswith(".") and p not in (".", "..") for p in limpo.split("/")):
            self.send_error(404)
            return None

        # A raiz leva a pagina que foi capturada, nao ao index.html que veio de
        # carona: essa home nunca foi visitada e cai no proprio erro do site.
        if self.path in ("/", "") and Handler.inicial and Handler.inicial != "index.html":
            self.send_response(302)
            self.send_header("Location", "/" + Handler.inicial)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        caminho = self.translate_path(self.path)

        if not os.path.exists(caminho) and self._e_navegacao():
            escolhido = None
            for alt in self._alternativas(caminho.rstrip("/")):
                if os.path.isfile(alt):
                    escolhido = alt
                    break
            if escolhido is None:
                raiz_index = os.path.join(self.directory, "index.html")
                if os.path.isfile(raiz_index):
                    escolhido = raiz_index

            if escolhido:
                rel = os.path.relpath(escolhido, self.directory)
                novo = "/" + rel.replace(os.sep, "/")
                if not Handler.quiet:
                    sys.stderr.write("  ->  %s  servido como  %s\n"
                                     % (self.path.split("?")[0], novo))
                self.path = novo
                caminho = escolhido

        if os.path.isdir(caminho) and not os.path.isfile(os.path.join(caminho, "index.html")):
            self.send_error(404)
            return None

        return super().send_head()

    def do_POST(self):
        self.send_error(405)

    do_PUT = do_DELETE = do_PATCH = do_POST

    def end_headers(self):
        # Sem cache: reabrir a pagina sempre mostra o estado real do disco.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if Handler.isolate:
            # SharedArrayBuffer, necessario para decodificadores com threads.
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

    def guess_type(self, path):
        base, ext = os.path.splitext(path)
        if ext.lower() in EXTRA_TYPES:
            return EXTRA_TYPES[ext.lower()]
        if ext == "":
            # Sem extensao nenhuma: o conteudo decide. Acontece com URLs de
            # imagem geradas por framework (/_next/image?url=...), que
            # devolvem um JPEG por um caminho sem ponto nenhum.
            farejado = farejar_tipo(path)
            if farejado:
                return farejado
        return super().guess_type(path)

    def log_message(self, fmt, *args):
        code = args[1] if len(args) > 1 else ""
        if str(code).startswith("4") or str(code).startswith("5"):
            sys.stderr.write("  %s  %s\n" % (code, args[0] if args else ""))


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def porta_livre(inicial, tentativas=20):
    for p in range(inicial, inicial + tentativas):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return None


def raiz_do_site():
    """
    Descobre a pasta do site.

    O motor fica em __offline/ para deixar a raiz limpa: o usuario ve um
    arquivo so para executar. Entao, quando estamos dentro dessa pasta, o
    site e um nivel acima.
    """
    aqui = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(aqui) == "__offline":
        return os.path.dirname(aqui)
    return aqui


def conferir_pasta(raiz):
    """Avisa se o servidor foi aberto fora da pasta de um site capturado."""
    tem_html = any(
        f.lower().endswith((".html", ".htm"))
        for f in os.listdir(raiz)
        if os.path.isfile(os.path.join(raiz, f))
    )
    if tem_html:
        return True

    print()
    print("  Esta pasta nao parece conter um site capturado.")
    print()
    print("  Pasta atual: %s" % raiz)
    print()
    print("  Nao ha nenhum arquivo .html aqui. Provavelmente este servidor.py")
    print("  foi aberto a partir da pasta da extensao, e nao da pasta que a")
    print("  captura gerou.")
    print()
    print("  Abra a pasta que a extensao criou (a que tem index.html e")
    print("  __offline/) e rode o servidor de dentro dela.")
    print()
    return False


def liberar_execucao(raiz):
    """
    Da permissao de execucao ao atalho, e so a ele.

    A extensao grava os arquivos pela File System Access API, que nao tem como
    definir o bit de execucao. Sem ele o macOS recusa o duplo clique com
    "permission denied". Como este motor roda antes, ele conserta o atalho na
    primeira vez. Depois o duplo clique funciona.
    """
    for nome in os.listdir(raiz):
        # Nunca "qualquer .command": a pasta tem arquivos vindos do site, e
        # dar permissao de execucao a um deles seria entregar um executavel
        # de terceiro pronto para o duplo clique.
        if nome != "ABRIR SITE.command":
            continue
        caminho = os.path.join(raiz, nome)
        if not os.path.isfile(caminho):
            continue
        try:
            modo = os.stat(caminho).st_mode
            if not modo & 0o111:
                os.chmod(caminho, modo | 0o755)
                print("  Permissao de execucao concedida a %s." % nome)
        except OSError:
            pass


def pagina_inicial(raiz):
    """
    O arquivo da primeira pagina que a captura visitou de verdade.

    Importa porque capturar /work salva tambem um index.html da home. Ela e
    citada por um link, entao o HTML dela vem junto, mas essa home nunca foi
    aberta, nunca rolou, e os pedacos que ela carrega sozinha nao foram
    baixados. Abrir "/" cai exatamente nela, e o site parece quebrado quando o
    que foi capturado esta inteiro do lado.
    """
    try:
        with open(os.path.join(raiz, "__offline", "relatorio.json"), encoding="utf-8") as f:
            paginas = json.load(f).get("paginas") or []
        arquivo = (paginas[0] or {}).get("arquivo") if paginas else None
        seguro = (isinstance(arquivo, str) and not os.path.isabs(arquivo)
                  and ".." not in arquivo.replace("\\", "/").split("/")
                  and not any(c in arquivo for c in "\r\n"))
        if seguro and os.path.isfile(os.path.join(raiz, arquivo)):
            return arquivo
    except Exception:
        pass
    return "index.html"


def main():
    ap = argparse.ArgumentParser(add_help=True, description="Servidor local do site baixado.")
    ap.add_argument("porta", nargs="?", type=int, default=8080, help="porta (padrao 8080)")
    ap.add_argument("--isolar", action="store_true",
                    help="envia COOP/COEP; ative se o site usar SharedArrayBuffer")
    ap.add_argument("--sem-navegador", action="store_true", help="nao abrir o navegador")
    args = ap.parse_args()

    raiz = raiz_do_site()
    os.chdir(raiz)

    if not conferir_pasta(raiz):
        return 2
    liberar_execucao(raiz)

    porta = porta_livre(args.porta)
    if porta is None:
        print("Nenhuma porta livre a partir de %d." % args.porta)
        return 1
    if porta != args.porta:
        print("Porta %d ocupada; usando %d." % (args.porta, porta))

    Handler.isolate = args.isolar
    Handler.inicial = pagina_inicial(raiz)
    handler = functools.partial(Handler, directory=raiz)
    url = "http://localhost:%d/" % porta
    if Handler.inicial != "index.html":
        url += Handler.inicial

    print()
    print("  Servindo: %s" % raiz)
    print("  Endereco: %s" % url)
    if Handler.inicial != "index.html":
        print("  Pagina capturada: %s (a raiz redireciona para ela)" % Handler.inicial)
    if args.isolar:
        print("  Isolamento COOP/COEP ligado.")
    print()
    print("  Pare com Ctrl+C.")
    print()

    with Server(("127.0.0.1", porta), handler) as httpd:
        if not args.sem_navegador:
            threading.Timer(0.7, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Servidor encerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
