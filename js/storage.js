const KEY='knowpage.original.v1';
export function loadLocal(samples) {
  const raw=localStorage.getItem(KEY);
  if(raw===null) {const initial={version:1,documents:samples,history:[]}; saveLocal(initial); return initial;}
  const state=JSON.parse(raw);
  if(state.version!==1||!Array.isArray(state.documents)||!Array.isArray(state.history)) throw new Error('本机数据格式不支持，未覆盖原数据。请备份后清理本站数据。');
  return state;
}
export function saveLocal(state) {localStorage.setItem(KEY,JSON.stringify(state));}
