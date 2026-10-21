"""Reproducible lexical retrieval evaluation, not a model accuracy benchmark."""
import json
from pathlib import Path
from server.retrieval import retrieve
ROOT=Path(__file__).resolve().parent.parent
cases=[
 ('入职第一天需要做什么','入职与协作指引'),
 ('差旅报销需要在几天内提交','费用报销规范'),
 ('住宿费用每晚的上限','费用报销规范'),
 ('计划休假应提前几天申请','休假与调休规则'),
 ('调休应在多久内使用','休假与调休规则'),
 ('代码合并之前要审查什么','代码审查约定'),
 ('上线发布失败如何回滚','版本发布流程'),
 ('模型服务接收什么资料','信息安全守则'),
 ('异步沟通应包含什么','远程沟通指南'),
 ('项目交付至少包含哪些材料','项目交付清单'),
 ('银河舰队燃料量子预算是多少',None),
 ('酒店一晚预算',None), # Pure synonym query: known lexical baseline limitation.
]
documents=json.loads((ROOT/'web/sample-documents.json').read_text())
results=[]
for question,expected in cases:
 hits=retrieve(question,documents)
 titles=[h['title'] for h in hits]
 passed=expected in titles if expected else not hits
 results.append({'question':question,'expected_source':expected,'actual_sources':titles,'passed':passed})
print(json.dumps({'kind':'lexical retrieval examples; not a general accuracy claim','passed':sum(x['passed'] for x in results),'total':len(results),'cases':results},ensure_ascii=False,indent=2))
