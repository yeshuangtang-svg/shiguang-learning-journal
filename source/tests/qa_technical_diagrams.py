"""Render every new tool, archive into MD/PDF, and retain QA images outside user data."""
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Application
from test_technical_diagrams import GRAPH,MATRIX,TENSOR,CHART

OUT=Path(__file__).resolve().parents[2]/'build'/'qa-technical'
OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='technical-qa-') as tmp:
    app=Application(tmp)
    try:
        results=[]
        for name,args in [('create_architecture_diagram',GRAPH),('create_matrix_diagram',MATRIX),('create_tensor_diagram',TENSOR),('create_data_chart',CHART),('create_data_chart',{**CHART,'kind':'line','title':'含负数的变化（示例）','series':[{'name':'差值','values':[-3,0,5]}]})]:
            result=app.run_tool(name,args)
            asset=app.store.get_asset(result['id'])
            (OUT/(str(len(results)+1)+'-'+name+'.png')).write_bytes(asset['data'])
            results.append(result)
        content='# 技术图工具验收\n\n以下为虚构的教学示例与测试数据。\n\n'+'\n\n'.join('## '+result['title']+'\n\n'+result['markdown'] for result in results)
        doc=app.run_tool('create_document',{'name':'技术图工具验收.md','content':content})
        pdf=app.run_tool('generate_document_pdf',{'id':doc['id']})
        assert pdf['pdf_current']
        shutil.copytree(pdf['directory'],OUT/'document',dirs_exist_ok=True)
        assert len(list((Path(pdf['directory'])/'assets').glob('*.png')))==5
        print(json.dumps({'ok':True,'images':5,'pdf_current':pdf['pdf_current'],'output':str(OUT)},ensure_ascii=True))
    finally: app.store.close()
