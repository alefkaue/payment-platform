"""Servidor local da apresentação + app (SPA).

Uso:  python servir.py   ->  http://localhost:8777/Astro%20Apresentacao.dc.html

Arquivo que existe é servido normalmente; qualquer outra rota (ex.: /inicio,
/pix) devolve o index.html do app, para as rotas do app funcionarem no reload.
"""
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=RAIZ, **kw)

    def send_head(self):
        caminho = self.translate_path(self.path)
        if not os.path.isfile(caminho) and not os.path.isfile(os.path.join(caminho, "index.html")):
            self.path = "/index.html"
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    print("Astro: http://localhost:8777/Astro%20Apresentacao.dc.html")
    ThreadingHTTPServer(("127.0.0.1", 8777), Handler).serve_forever()
