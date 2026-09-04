# -*- coding: utf-8 -*-
# jieba_test.py
import jieba
#全模式
text ="我来到厦门大学数据库实验室"
seg_list = jieba.cut(text, cut_all=True)
print(u"[全模式]: ","/ ".join(seg_list))

#精确模式
seg_list = jieba.cut(text, cut_all=False)
print(u"精确模式]: ", "/ ".join(seg_list))

#默认是精确模式
seg_list = jieba.cut(text)
print(u"[默认模式]: ", "/ ".join(seg_list))

#搜索引擎模式
seg_list = jieba.cut_for_search(text)
print(u"[搜索引擎模式]: ", "/ ".join(seg_list))
