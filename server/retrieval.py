"""Small, inspectable lexical retrieval. It is not vector search or a model."""
import math
import re
from collections import Counter


def tokens(text):
    text = text.lower()
    en = re.findall(r'[a-z0-9]{2,}', text)
    cn = []
    for segment in re.findall(r'[\u4e00-\u9fff]+', text):
        cn.extend(segment[i:i + 2] for i in range(len(segment) - 1))
    return en + cn


def split_text(text, size=600, overlap=100):
    return [text[i:i + size] for i in range(0, len(text), size - overlap) if text[i:i + size].strip()]


def retrieve(question, documents, limit=3):
    query = set(tokens(question))
    if not query:
        return []
    candidates = []
    for doc in documents:
        for i, part in enumerate(split_text(doc['text'])):
            candidates.append((doc, i, part, Counter(tokens(doc['title'] + ' ' + part))))
    if not candidates:
        return []
    df = Counter(t for _, _, _, words in candidates for t in query if t in words)
    hits = []
    for doc, i, part, words in candidates:
        matched = query.intersection(words)
        # At least one meaningful bigram or English term is needed. The ratio
        # is deliberately visible: this baseline is not semantic understanding.
        score = sum((1 + math.log((1 + len(candidates)) / (1 + df[t]))) * min(words[t], 3) for t in matched)
        if score > 0 and len(matched) / len(query) >= .08:
            hits.append({'document_id': doc['id'], 'title': doc['title'], 'chunk_id': f"{doc['id']}:{i + 1}", 'excerpt': part, 'page': None, 'score': round(score, 5)})
    ranked = sorted(hits, key=lambda h: h['score'], reverse=True)
    return [h for h in ranked if h['score'] >= ranked[0]['score'] * .45][:limit] if ranked else []


def excerpt_answer(sources):
    if not sources:
        return '当前知识库中没有找到足够依据。请补充相关文档，或使用更具体的关键词。'
    pieces = []
    for i, source in enumerate(sources):
        # Strip the sample header in the response; preserve original in source.
        lines = [line.strip().lstrip('#').strip() for line in source['excerpt'].splitlines() if line.strip() and not line.startswith('>')]
        body = '\n'.join(lines[2:] or lines)
        pieces.append(f"[{i + 1}] {body}")
    return '以下为相关原文摘录（未调用大模型）：\n\n' + '\n\n'.join(pieces)
