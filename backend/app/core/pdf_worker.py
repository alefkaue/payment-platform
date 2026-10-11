"""Worker Linux de PDF sem credenciais: limite de memória/CPU e nenhum core dump."""
import sys


def aplicar_limites():
    # Docker/Azure usam Linux. Outros sistemas preservam timeout no processo pai.
    if sys.platform != 'linux':
        return
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


if __name__ == '__main__':
    aplicar_limites()
    from fastapi import HTTPException
    from app.core.arquivos import _validar_pdf_local
    # Limite absoluto independente do pai; documento no produto tem no máximo 10 MiB.
    bruto = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(bruto) > 10 * 1024 * 1024:
        print('413')
    else:
        try:
            _validar_pdf_local(bruto)
            if '--texto' in sys.argv:
                import io
                from pypdf import PdfReader
                leitor = PdfReader(io.BytesIO(bruto), strict=True)
                if len(leitor.pages) > 50:
                    raise HTTPException(status_code=413, detail='Páginas demais.')
                partes = []
                total = 0
                for pagina in leitor.pages:
                    parte = pagina.extract_text() or ''
                    total += len(parte)
                    if total > 65536:
                        raise HTTPException(status_code=413, detail='Texto demais.')
                    partes.append(parte)
                sys.stdout.buffer.write(b'texto:' + '\n'.join(partes).encode('utf-8'))
            else:
                print('ok')
        except HTTPException as e:
            print(str(e.status_code) if e.status_code in (400, 413, 415) else '400')
        except Exception:
            print('400')
