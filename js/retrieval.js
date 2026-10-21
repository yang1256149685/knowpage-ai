// Explainable lexical retrieval. No model calls, embeddings or hidden responses.
export function tokens(text) {
  const lower = text.toLowerCase();
  return [...(lower.match(/[a-z0-9]{2,}/g) || []), ...(lower.match(/[\u4e00-\u9fff]+/g) || []).flatMap(s => Array.from({length: Math.max(0,s.length-1)}, (_,i) => s.slice(i,i+2)))];
}
export function splitText(text) {
  const parts=[]; for(let i=0;i<text.length;i+=500) {const p=text.slice(i,i+600); if(p.trim()) parts.push(p);} return parts;
}
export function retrieve(question,documents,limit=3) {
  const query=new Set(tokens(question)); if(!query.size) return [];
  const candidates=documents.flatMap(doc => splitText(doc.text).map((part,i) => {const words=new Map(); for(const t of tokens(doc.title+' '+part)) words.set(t,(words.get(t)||0)+1); return {doc,part,i,words};}));
  const df=new Map([...query].map(t=>[t,candidates.filter(c=>c.words.has(t)).length]));
  const ranked = candidates.map(({doc,part,i,words})=>{const matched=[...query].filter(t=>words.has(t)); const score=matched.reduce((s,t)=>s+(1+Math.log((1+candidates.length)/(1+df.get(t))))*Math.min(words.get(t),3),0); return {document_id:doc.id,title:doc.title,chunk_id:`${doc.id}:${i+1}`,excerpt:part,page:null,score,coverage:matched.length/query.size};}).filter(h=>h.score>0&&h.coverage>=.08).sort((a,b)=>b.score-a.score);
  return ranked.filter(h=>h.score>=ranked[0].score*.45).slice(0,limit);
}
export function excerptAnswer(sources) {
  if(!sources.length) return '当前知识库中没有找到足够依据。请补充相关文档，或使用更具体的关键词。';
  return '以下为相关原文摘录（未调用大模型）：\n\n'+sources.map((s,i)=>{const lines=s.excerpt.split('\n').filter(l=>l.trim()&&!l.startsWith('>')).map(l=>l.trim().replace(/^#+\s*/,'')); return `[${i+1}] ${(lines.slice(2).length?lines.slice(2):lines).join('\n')}`;}).join('\n\n');
}
