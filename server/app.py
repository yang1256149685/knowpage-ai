import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import ai_provider
from .auth import admin, current_user, hash_password, verify
from .database import connect, initialize
from .retrieval import excerpt_answer, retrieve, split_text

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 5 * 1024 * 1024
buckets = defaultdict(deque)


def now():
    return datetime.now(timezone.utc).isoformat()


def add_document(db, title, category, filename, text):
    digest = hashlib.sha256(text.encode()).hexdigest()
    if db.execute('SELECT id FROM documents WHERE hash=?', (digest,)).fetchone():
        raise HTTPException(409, '该内容已存在，请勿重复上传')
    doc_id = uuid.uuid4().hex
    db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?)', (doc_id, title, category, filename, text, digest, now(), 'ready'))
    for i, part in enumerate(split_text(text)):
        db.execute('INSERT INTO chunks VALUES(?,?,?,?)', (f'{doc_id}:{i+1}', doc_id, i+1, part))
    return doc_id


@asynccontextmanager
async def lifespan(app):
    initialize()
    password = os.getenv('ADMIN_PASSWORD', '')
    if os.getenv('APP_ENV') == 'production' and len(password) < 16:
        raise RuntimeError('Production ADMIN_PASSWORD must contain at least 16 characters')
    with connect() as db:
        for name, role, variable in [('admin','admin','ADMIN_PASSWORD'), ('reader','reader','READER_PASSWORD')]:
            secret = os.getenv(variable, '')
            if secret and len(secret) < 12:
                raise RuntimeError(f'{variable} must contain at least 12 characters')
            if secret and not db.execute('SELECT id FROM users WHERE name=?', (name,)).fetchone():
                db.execute('INSERT INTO users VALUES(?,?,?,?)', (uuid.uuid4().hex, name, hash_password(secret), role))
        if os.getenv('SEED_SAMPLES', 'true') == 'true' and not db.execute('SELECT id FROM documents LIMIT 1').fetchone():
            # Seed only once. Deleting all documents must not resurrect them.
            marker = db.execute("SELECT value FROM metadata WHERE key='seeded'").fetchone()
            if not marker:
                for item in json.loads((ROOT / 'web/sample-documents.json').read_text()):
                    add_document(db, item['title'], item['category'], item['filename'], item['text'])
                db.execute("INSERT INTO metadata VALUES('seeded','true')")
    yield


app = FastAPI(title='知页 KnowPage API', version='1.0.0', lifespan=lifespan)


@app.middleware('http')
async def safety(request, call_next):
    if request.method in {'POST', 'DELETE', 'PUT', 'PATCH'}:
        try:
            if int(request.headers.get('content-length', '0')) > MAX_BYTES + 65536:
                return JSONResponse({'detail': '请求体过大'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail': '请求长度不合法'}, status_code=400)
        origin = request.headers.get('origin')
        expected = os.getenv('PUBLIC_ORIGIN') or f'{request.url.scheme}://{request.headers.get("host", "")}'
        if origin and origin.rstrip('/') != expected.rstrip('/'):
            return JSONResponse({'detail':'请求来源不被允许'}, status_code=403)
    if request.url.path in {'/api/login', '/api/ask'}:
        # Single-worker bounded per-process guard; use a gateway for distributed deployments.
        identity = request.client.host if request.client else 'unknown'
        key = (identity, request.url.path)
        bucket = buckets[key]
        cutoff = time.monotonic() - 60
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= (12 if request.url.path.endswith('login') else 30):
            return JSONResponse({'detail':'请求过于频繁，请稍后重试'}, status_code=429)
        bucket.append(time.monotonic())
        if len(buckets) > 4096:
            for old_key in list(buckets):
                if not buckets[old_key] or buckets[old_key][-1] < cutoff:
                    del buckets[old_key]
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


class Login(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.get('/config.json')
def runtime_config():
    return {'runtime': 'server'}


@app.get('/api/health')
def health():
    return {'status':'ok', 'runtime':'server', 'ai_mode':os.getenv('AI_MODE','retrieval')}


@app.post('/api/login')
def login(payload: Login, response: Response):
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE name=?', (payload.name,)).fetchone()
        encoded = user['password_hash'] if user else hash_password('invalid-account')
        if not verify(payload.password, encoded) or not user:
            raise HTTPException(401, '账号或密码错误')
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires<?', (int(time.time()),))
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], int(time.time()) + 8 * 3600))
    response.set_cookie('knowpage_session', token, max_age=8*3600, httponly=True, secure=os.getenv('APP_ENV') == 'production', samesite='strict')
    return {'id':user['id'], 'name':user['name'], 'role':user['role']}


@app.post('/api/logout')
def logout(request: Request, response: Response):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(request.cookies.get('knowpage_session','').encode()).hexdigest(),))
    response.delete_cookie('knowpage_session')
    return {'ok':True}


@app.get('/api/me')
def me(user=Depends(current_user)):
    return user


@app.get('/api/documents')
def documents(user=Depends(current_user)):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.document_id=d.id) AS chunk_count FROM documents d ORDER BY created_at DESC LIMIT 500')]


@app.get('/api/documents/{doc_id}')
def document(doc_id: str, user=Depends(current_user)):
    with connect() as db:
        row = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, '文档不存在')
    return dict(row)


@app.post('/api/documents', status_code=201)
async def upload(file: UploadFile = File(...), category: str = Form('自定义'), user=Depends(current_user)):
    admin(user)
    name = (file.filename or '').replace('\\', '/').rsplit('/',1)[-1]
    if not name or len(name) > 160 or len(category) > 30:
        raise HTTPException(422, '文件名或分类长度不合法')
    extension = Path(name).suffix.lower()
    if extension not in {'.txt','.md','.pdf'}:
        raise HTTPException(415, '仅支持 TXT、Markdown 和文本 PDF')
    data = await file.read(MAX_BYTES+1)
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, '文件为空或超过 5 MiB')
    try:
        if extension == '.pdf':
            if not data.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF signature')
            parsed = subprocess.run([sys.executable, '-m', 'server.parse_document'], input=data, capture_output=True, timeout=15, cwd=ROOT)
            if parsed.returncode:
                raise ValueError('PDF parse failed')
            text = json.loads(parsed.stdout)['text']
        else:
            if data.startswith(b'%PDF-') or b'\x00' in data:
                raise ValueError('Not a text file')
            text = data.decode('utf-8-sig')
        if len(text.strip()) < 8 or len(text) > 100000:
            raise ValueError('Invalid text length')
    except Exception:
        raise HTTPException(422, '文档无法解析：需 UTF-8 文本或不加密的文本 PDF；不支持扫描件，最多 100 页 / 10 万字符') from None
    with connect() as db:
        if db.execute('SELECT COUNT(*) FROM documents').fetchone()[0] >= 500:
            raise HTTPException(409, '本作品最多保存 500 份文档')
        doc_id = add_document(db, Path(name).stem, category.strip() or '自定义', name, text)
    return {'id':doc_id,'status':'ready'}


@app.delete('/api/documents/{doc_id}')
def delete_document(doc_id: str, user=Depends(current_user)):
    admin(user)
    with connect() as db:
        if not db.execute('DELETE FROM documents WHERE id=?', (doc_id,)).rowcount:
            raise HTTPException(404, '文档不存在')
        for row in db.execute('SELECT id,sources FROM history').fetchall():
            if any(s['document_id'] == doc_id for s in json.loads(row['sources'])):
                db.execute('UPDATE history SET answer=?,sources=? WHERE id=?', ('来源文档已删除，相关回答和引用已清除。', '[]', row['id']))
    return {'ok':True}


@app.post('/api/ask')
async def ask(payload: Question, user=Depends(current_user)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(422, '请输入问题')
    with connect() as db:
        docs = [dict(r) for r in db.execute("SELECT * FROM documents WHERE status='ready'")]
    sources = retrieve(question, docs)
    mode = os.getenv('AI_MODE','retrieval')
    if mode not in {'retrieval','live'}:
        raise HTTPException(503, '模型模式配置错误')
    answer = await ai_provider.generate(question, sources) if mode == 'live' and sources else excerpt_answer(sources)
    if not sources:
        mode = 'retrieval'
    row = {'id':uuid.uuid4().hex,'question':question,'answer':answer,'mode':mode,'sources':sources,'created_at':now()}
    with connect() as db:
        # Re-check sources inside the write transaction to avoid persisting a
        # deleted document if an administrator deletes it during a model call.
        db.execute('BEGIN IMMEDIATE')
        for source in sources:
            if not db.execute('SELECT id FROM documents WHERE id=?', (source['document_id'],)).fetchone():
                raise HTTPException(409, '来源文档已变化，请重新提问')
        db.execute('INSERT INTO history VALUES(?,?,?,?,?,?,?)', (row['id'],user['id'],question,answer,mode,json.dumps(sources,ensure_ascii=False),row['created_at']))
    return row


@app.get('/api/history')
def history(user=Depends(current_user)):
    with connect() as db:
        rows = [dict(r) for r in db.execute('SELECT id,question,answer,mode,sources,created_at FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT 200', (user['id'],))]
    for row in rows:
        row['sources'] = json.loads(row['sources'])
    return rows


@app.delete('/api/history/{history_id}')
def delete_history(history_id: str, user=Depends(current_user)):
    with connect() as db:
        if not db.execute('DELETE FROM history WHERE id=? AND user_id=?', (history_id,user['id'])).rowcount:
            raise HTTPException(404,'记录不存在')
    return {'ok':True}


app.mount('/', StaticFiles(directory=ROOT/'web', html=True), name='web')
