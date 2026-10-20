"""Run PDF parsing in a disposable process, with a parent wall-clock deadline."""
import io
import json
import resource
import sys
from pypdf import PdfReader

if sys.platform.startswith('linux'):
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
try:
    raw = sys.stdin.buffer.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024 or not raw.startswith(b'%PDF-'):
        raise ValueError('Invalid file')
    pdf = PdfReader(io.BytesIO(raw))
    if pdf.is_encrypted or len(pdf.pages) > 100:
        raise ValueError('Unsupported PDF')
    parts, length = [], 0
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ''
        length += len(text)
        if length > 100000:
            raise ValueError('Text too long')
        if text.strip():
            parts.append(f'\n第 {i + 1} 页\n{text}')
    if not parts:
        raise ValueError('No text')
    print(json.dumps({'text': '\n'.join(parts)}, ensure_ascii=False))
except Exception:
    sys.exit(2)
