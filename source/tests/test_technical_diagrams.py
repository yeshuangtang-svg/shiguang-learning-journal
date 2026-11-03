"""Validate semantic drawing invariants independently of the browser renderer."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from technical_diagrams import graph,matrix,tensor,chart


GRAPH = {'title':'残差连接与分支', 'nodes':[
    {'id':'input','label':'输入 X','detail':'形状 B × N × D','row':0,'column':0},
    {'id':'attention','label':'注意力分支','detail':'沿序列聚合特征','row':1,'column':0},
    {'id':'gate','label':'门控分支','detail':'产生逐元素门控值','row':1,'column':1},
    {'id':'merge','label':'合并输出','detail':'合并两个分支并加入原输入','row':2,'column':0}],
    'edges':[{'source':'input','target':'attention','label':'输入特征'},
             {'source':'input','target':'gate','label':'并行输入'},
             {'source':'attention','target':'merge','label':'注意力输出'},
             {'source':'gate','target':'merge','label':'门控权重'},
             {'source':'input','target':'merge','label':'残差跳连','style':'dashed'}]}
MATRIX={'title':'矩阵乘法：行列内积','operation':'multiply','matrices':[{'name':'A','values':[[1,2,3],[4,5,6]]},{'name':'B','values':[[1,0],[0,1],[1,1]]}]}
TENSOR={'title':'图像 token 到多头注意力','tensors':[
    {'name':'输入特征','dimensions':['B','N','D'],'detail':'B 是批次，N 是 token 数，D 是隐藏维度。'},
    {'name':'拆分注意力头','dimensions':['B','N','H','d'],'detail':'D = H × d。此处只改变形状，不改变元素总数。'},
    {'name':'交换轴顺序','dimensions':['B','H','N','d'],'detail':'把注意力头放到序列轴之前，方便每个头独立计算。'}],
    'operations':['reshape：将 D 分解为 H × d','transpose：交换 N 与 H 两个轴']}
CHART={'title':'两种配置的吞吐量（示例数据）','kind':'bar','labels':['短序列','中序列','长序列'],'y_label':'吞吐量（token/s）','series':[{'name':'配置 A','values':[120,88,51]},{'name':'配置 B','values':[132,96,60]}]}


class TechnicalDiagramChecks(unittest.TestCase):
    def test_branch_skip_and_feedback_connections(self):
        html,w,h,meta=graph(**GRAPH)
        self.assertEqual(meta,{'nodes':4,'edges':5})
        self.assertEqual(html.count('marker-end='),5)
        self.assertIn('stroke-dasharray',html)
        self.assertLess(h,4000)
        back={**GRAPH,'edges':GRAPH['edges']+[{'source':'merge','target':'input','label':'反馈'}]}
        self.assertEqual(graph(**back)[3]['edges'],6)

    def test_bad_graph_cannot_silently_drop_an_edge(self):
        for edges in ([{'source':'missing','target':'input','label':'x'}],[]):
            with self.assertRaises(ValueError): graph(**{**GRAPH,'edges':edges})
        with self.assertRaises(ValueError): graph(**{**GRAPH,'nodes':[GRAPH['nodes'][0]]*2})

    def test_matrix_product_and_dimension_check(self):
        meta=matrix(**MATRIX)[3]
        self.assertEqual(meta['product'],[[4,5],[10,11]])
        self.assertEqual(meta['shapes'],[[2,3],[3,2],[2,2]])
        with self.assertRaises(ValueError): matrix('不匹配',[{'name':'a','values':[[1,2]]},{'name':'b','values':[[1]]}],'multiply')
        with self.assertRaises(ValueError): matrix('不规则',[{'name':'a','values':[[1],[1,2]]}])

    def test_chart_negative_zero_and_real_summary(self):
        for values in ([0,0],[-4,-2],[-3,5]):
            meta=chart('测试','line',['a','b'],[{'name':'x','values':values}],'值')[3]
            self.assertLessEqual(meta['axis_min'],min(0,*values))
            self.assertGreater(meta['axis_max'],max(0,*values))
            self.assertEqual(meta['summary'][0]['mean'],sum(values)/2)
        with self.assertRaises(ValueError): chart('错位','bar',['a','b'],[{'name':'x','values':[1]}],'值')

    def test_untrusted_text_is_escaped_and_nonfinite_values_rejected(self):
        html=matrix('<script>x</script>',[{'name':'<image href="file:///x">','values':[[1]]}])[0]
        self.assertNotIn('<script>',html);self.assertNotIn('<image ',html)
        for value in (math.nan,math.inf,True,10**400):
            with self.assertRaises(ValueError): matrix('错误数值',[{'name':'x','values':[[value]]}])

    def test_tensor_steps_match_operations_and_long_labels_fit_bounds(self):
        html,w,h,meta=tensor(**TENSOR)
        self.assertEqual(meta['shapes'][2],['B','H','N','d'])
        with self.assertRaises(ValueError): tensor(**{**TENSOR,'operations':[]})
        long={'name':'张量名称'*8,'dimensions':['维度'*10]*6,'detail':'说明'*50}
        self.assertLess(tensor('长文字',[long]*6,['转换'*45]*5)[2],4000)


if __name__=='__main__': unittest.main()
