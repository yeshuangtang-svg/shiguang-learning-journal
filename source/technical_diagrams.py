"""Bounded structured diagrams. No user SVG, HTML, paths, URLs or code."""
from html import escape
import math
import unicodedata

from flow_diagram import render_image

COLORS = ('#35795c', '#b46531', '#536db0', '#9c5582')


def label(value, name='文字', maximum=80):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f'{name}须为 1–{maximum} 字。')
    return ' '.join(value.split())


def number(value):
    if type(value) not in (float, int) or abs(value) > 1e12 or not math.isfinite(value):
        raise ValueError('数值须为有限数字，绝对值不超过 10¹²。')
    return value


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError('图形对象字段不正确。')


def sequence(value, low, high, name):
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise ValueError(f'{name}须包含 {low}–{high} 项。')
    return value


def lines(value, units):
    result, current, size = [], '', 0
    for char in str(value):
        step = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if size + step > units and current:
            result.append(current); current, size = '', 0
        current += char; size += step
    return result + [current]


def text(x, y, value, size=18, color='#243d34', units=100, anchor='start', weight='normal'):
    rows = lines(value, units)
    spans = ''.join(f'<tspan x="{x}" dy="{0 if i == 0 else size * 1.4}">{escape(row)}</tspan>' for i, row in enumerate(rows))
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}" font-weight="{weight}">{spans}</text>'


def rect(x, y, width, height, fill='#ffffff', stroke='#c2d5c8'):
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10" fill="{fill}" stroke="{stroke}"/>'


def arrow(points, dashed=False, color='#557c69'):
    dash = 'stroke-dasharray="7 5"' if dashed else ''
    return f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" {dash} marker-end="url(#arrow)"/>'


def page(title, content, width, height):
    title = label(title, '标题', 80)
    if not 300 <= width <= 2400 or not 200 <= height <= 4000:
        raise ValueError('图形过大，请拆分为局部图。')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="Microsoft YaHei, sans-serif"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#557c69"/></marker></defs><rect width="100%" height="100%" fill="#f5f7f2"/>{text(36,45,title,24,units=int((width-72)/13),weight="bold")}{content}</svg>'
    return '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><style>body{margin:0}svg{display:block}</style>'+svg


def graph(title, nodes, edges):
    sequence(nodes, 2, 12, '节点'); sequence(edges, 1, 18, '连接')
    positions, occupied, labels = {}, set(), {}
    for node in nodes:
        fields(node, ('id','label','detail','row','column'))
        identity = label(node['id'], '节点 id', 24)
        if identity != node['id']: raise ValueError('节点 id 不能包含首尾空白或换行。')
        if identity in positions: raise ValueError('节点 id 不能重复。')
        row, col = node['row'], node['column']
        if type(row) is not int or type(col) is not int or not 0 <= row <= 5 or not 0 <= col <= 3:
            raise ValueError('节点 row 须为 0–5，column 须为 0–3 的整数。')
        if (row,col) in occupied: raise ValueError('两个节点不能占据相同位置。')
        occupied.add((row,col)); positions[identity] = (40+col*320,130+row*240,row,col)
        labels[identity] = label(node['label'],'节点名称',28)
        label(node['detail'],'节点说明',60)
    max_col=max(p[3] for p in positions.values()); max_row=max(p[2] for p in positions.values())
    right=40+max_col*320+240
    width=max(900,right+100+len(edges)*18)
    bottom=130+max_row*240+155
    connectors, legends = [], []
    for i, edge in enumerate(edges,1):
        fields(edge, ('source','target','label'), ('style',))
        label(edge['source'], '起点 id', 24); label(edge['target'], '终点 id', 24)
        if edge['source'] not in positions or edge['target'] not in positions:
            raise ValueError('连接引用了不存在的节点。')
        caption=label(edge['label'],'连接说明',60)
        style=edge.get('style','solid')
        if style not in ('solid','dashed'): raise ValueError('连线样式须为 solid 或 dashed。')
        x,y,r,c=positions[edge['source']]; xx,yy,rr,cc=positions[edge['target']]
        if r==rr and abs(c-cc)==1:
            sign=1 if cc>c else -1
            start=(x+(240 if sign>0 else 0),y+77); end=(xx+(0 if sign>0 else 240),yy+77)
            points=[start,end]; badge=((start[0]+end[0])/2,start[1]-12)
        elif c==cc and abs(r-rr)==1:
            sign=1 if rr>r else -1
            start=(x+120,y+(155 if sign>0 else 0)); end=(xx+120,yy+(0 if sign>0 else 155))
            points=[start,end]; badge=(x+137,(start[1]+end[1])/2)
        elif rr==r+1:
            start=(x+170,y+155); end=(xx+70,yy); middle=(start[1]+end[1])/2
            points=[start,(start[0],middle),(end[0],middle),end]
            badge=((start[0]+end[0])/2,middle-10)
        else:
            # Route skip/branch/feedback links through row gaps and outside the node grid.
            lane=right+35+i*18
            start=(x+170,y+155); end=(xx+70,yy)
            below=y+170+(i%4)*12; above=yy-15-(i%4)*12
            points=[start,(start[0],below),(lane,below),(lane,above),(end[0],above),end]
            badge=(lane+4,(below+above)/2)
        connectors.append(arrow(points,style=='dashed'))
        connectors.append(text(*badge,str(i),13,color='#52685b'))
        legends.append(f'{i}. {labels[edge["source"]]} → {labels[edge["target"]]}：{caption}'+('（虚线）' if style=='dashed' else ''))
    content=''.join(connectors)
    for node in nodes:
        x,y,_,_=positions[node['id']]
        content+=rect(x,y,240,155)+text(x+15,y+26,labels[node['id']],16,units=26,weight='bold')+text(x+15,y+94,label(node['detail'],'节点说明',60),13,units=30)
    ypos=bottom+50
    for caption in legends:
        content+=text(40,ypos,caption,15,units=int((width-80)/8))
        ypos+=len(lines(caption,int((width-80)/8)))*21+10
    return page(title,content,width,ypos+20),width,ypos+20,{'nodes':len(nodes),'edges':len(edges)}


def matrix(title, matrices, operation='display'):
    sequence(matrices,1,3,'矩阵')
    if operation not in ('display','multiply'): raise ValueError('矩阵模式须为 display 或 multiply。')
    items=[]
    for item in matrices:
        fields(item,('name','values')); name=label(item['name'],'矩阵名',24)
        rows=sequence(item['values'],1,6,'矩阵行'); width=None
        for row in rows:
            sequence(row,1,6,'矩阵列')
            if width is not None and len(row)!=width: raise ValueError('矩阵各行长度须相同。')
            width=len(row)
            for value in row: number(value)
        items.append({'name':name,'values':rows})
    result=None
    if operation=='multiply':
        if len(items)!=2 or len(items[0]['values'][0])!=len(items[1]['values']):
            raise ValueError('乘法需要两个矩阵，且左矩阵列数等于右矩阵行数。')
        a,b=items[0]['values'],items[1]['values']
        result=[[sum(a[i][k]*b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]
        for row in result:
            for value in row: number(value)
        items.append({'name':'乘积（工具计算）','values':result})
    cell=100; widths=[max(280,len(item['values'][0])*cell+40) for item in items]
    width=max(800,sum(widths)+70*(len(items)-1)+80)
    height=280+max(len(item['values']) for item in items)*cell
    content='';x=40
    for index,(item,panel_width) in enumerate(zip(items,widths)):
        data=item['values'];rows=len(data);cols=len(data[0]); max_value=max(abs(v) for row in data for v in row) or 1
        content+=text(x,130,item['name'],18,units=int(panel_width/10),weight='bold')+text(x,180,f'{rows} 行 × {cols} 列',15,color='#657c6e')
        for r,row in enumerate(data):
            for c,value in enumerate(row):
                alpha=0.08+0.34*abs(value)/max_value
                fill=f'rgba({"53,121,92" if value>=0 else "180,101,49"},{alpha:.3f})'
                displayed=f'{value:.5g}'; font_size=min(17,82/(max(1,len(displayed))*.6))
                content+=rect(x+c*cell,205+r*cell,cell-4,cell-4,fill)+text(x+c*cell+(cell-4)/2,259+r*cell,displayed,font_size,anchor='middle')
        if operation=='multiply' and index<2:
            content+=text(x+panel_width+28,230,'×' if index==0 else '=',28,anchor='middle')
        x+=panel_width+70
    content+=text(40,height-45,'绿色表示非负值，棕色表示负值；色深在各矩阵内按绝对值缩放。显示值保留 5 位有效数字。',13,units=int((width-80)/7))
    return page(title,content,width,height),width,height,{'operation':operation,'product':result,'shapes':[[len(i['values']),len(i['values'][0])] for i in items]}


def tensor(title, tensors, operations):
    sequence(tensors,2,6,'张量');sequence(operations,len(tensors)-1,len(tensors)-1,'变换说明')
    width=1100
    content=''; y=130
    for i,item in enumerate(tensors):
        fields(item,('name','dimensions','detail'))
        name=label(item['name'],'张量名',32);detail=label(item['detail'],'张量说明',100)
        dims=sequence(item['dimensions'],1,6,'维度')
        dims=[label(d,'维度',20) for d in dims]
        shape='形状：'+' × '.join(dims)
        detail_y=y+40+len(lines(shape,67))*27
        block_height=max(130,detail_y-y+len(lines(detail,92))*21+15)
        for offset in (12,6,0): content+=rect(48+offset,y+offset,230,112,'#dcebdd' if offset else '#fff')
        content+=text(65,y+28,name,17,units=24,weight='bold')+text(320,y+30,shape,19,units=67)+text(320,detail_y,detail,15,units=92)
        if i<len(tensors)-1:
            operation=label(operations[i],'变换说明',90)
            content+=arrow([(165,y+block_height),(165,y+block_height+65)])+text(205,y+block_height+28,operation,15,units=100)
        y+=block_height+80
    height=y+30
    content+=text(40,height-20,'示意图：卡片叠层不代表实际元素个数；维度以标注为准。',13,color='#657c6e')
    return page(title,content,width,height),width,height,{'shapes':[i['dimensions'] for i in tensors]}


def chart(title, kind, labels, series, y_label):
    if kind not in ('bar','line'): raise ValueError('图表须为 bar 或 line。')
    sequence(labels,2,12,'横轴标签');sequence(series,1,4,'数据系列')
    labels=[label(v,'横轴标签',20) for v in labels]; y_label=label(y_label,'纵轴名称及单位',30)
    all_values=[]; names=set();summaries=[]
    for item in series:
        fields(item,('name','values'));name=label(item['name'],'系列名',24)
        if name in names: raise ValueError('数据系列名不能重复。')
        names.add(name); sequence(item['values'],len(labels),len(labels),'数值')
        values=[number(v) for v in item['values']];all_values+=values
        summaries.append({'name':name,'count':len(values),'min':min(values),'max':max(values),'mean':sum(values)/len(values)})
    low=min(0,min(all_values)); high=max(0,max(all_values))
    if low==high: high=low+1
    # Bar charts retain zero; pad both ends so endpoints are visible.
    span=high-low; high+=span*0.08
    if low<0: low-=span*0.08
    width=1400;height=820;left=125;top=155;plotw=1220;ploth=420
    def sy(value): return top+(high-value)/(high-low)*ploth
    content=text(40,115,y_label,17)
    for i in range(6):
        value=low+(high-low)*i/5;y=sy(value)
        content+=f'<path d="M{left},{y} H{left+plotw}" stroke="#dce3db"/>'+text(left-14,y+5,f'{value:.4g}',14,anchor='end')
    content+=f'<path d="M{left},{sy(0)} H{left+plotw}" stroke="#7d9585"/>'
    slot=plotw/len(labels)
    for i,item in enumerate(series):
        color=COLORS[i];points=[]
        for j,value in enumerate(item['values']):
            x=left+(j+0.5)*slot;y=sy(value)
            if kind=='bar':
                barw=slot*0.74/len(series);bx=left+j*slot+slot*0.13+i*barw
                content+=f'<rect x="{bx}" y="{min(y,sy(0))}" width="{barw-2}" height="{max(1,abs(y-sy(0)))}" fill="{color}"/>'
            else:
                points.append(f'{x},{y}');content+=f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>'
        if kind=='line': content+=f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"/>'
        content+=rect(130+i*305,740,16,16,color,color)+text(155+i*305,754,item['name'],16,units=28)
    for j,value in enumerate(labels):
        content+=text(left+(j+.5)*slot,605,value,14,units=max(6,int(slot/8)),anchor='middle')
    content+=text(40,800,'横轴为按输入顺序排列的等距类别；数值使用原始数据，统计结果另随工具返回。',13,color='#657c6e')
    return page(title,content,width,height),width,height,{'summary':summaries,'axis_min':low,'axis_max':high}


RENDERERS={'create_architecture_diagram':graph,'create_matrix_diagram':matrix,'create_tensor_diagram':tensor,'create_data_chart':chart}


def create_technical_image(store, name, args):
    html,width,height,metadata=RENDERERS[name](**args)
    return {**render_image(store,args['title'],html,width,height),'diagram_type':name,**metadata}
