# -*- coding: utf-8 -*-
#wordcount.py
import jieba

text="学校设有研究生院、6个学部以及30个学院和16个研究院，形成了包括人文科学、社会科学、自然科学、工程与技术科学、管理科学、艺术科学、医学科学等学科门类在内的完备学科体系。学校现有18个学科进入 ESI全球前1% ，拥有5个一级学科国家重点学科、9个二级学科国家重点学科。学校设有32个博士后流动站；36个博士学位授权一级学科，45个硕士学位授权一级学科；8个交叉学科；1个博士专业学位学科授权类别，28个硕士专业学位学科授权类别。"
words = jieba.cut(text)     # 使用精确模式对文本进行分词
counts = {}     # 通过键值对的形式存储词语及其出现的次数

for word in words:
    if len(word) == 1:    # 不对单个字的词语进行统计
        continue
    else:
        counts[word] = counts.get(word, 0) + 1    # 词语每出现一次，其对应的次数加 1

items = list(counts.items())
items.sort(key=lambda x: x[1], reverse=True)    # 根据词语出现的次数进行从大到小排序

for i in range(3):
    word, count = items[i]
    print("{0:<4}{1:>4}".format(word, count))
