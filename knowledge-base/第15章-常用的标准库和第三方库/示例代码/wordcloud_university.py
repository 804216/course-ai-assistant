# wordcloud_university.py
import jieba
import wordcloud
txt="厦门大学设有研究生院、6个学部以及30个学院和16个研究院，形成了包括人文科学、社会科学、自然科学、工程与技术科学、管理科学、艺术科学、医学科学等学科门类在内的完备学科体系。学校现有18个学科进入ESI全球前1% ，拥有5个一级学科国家重点学科、9个二级学科国家重点学科。学校设有32个博士后流动站；36个博士学位授权一级学科，45个硕士学位授权一级学科；8个交叉学科；1个博士专业学位学科授权类别，28个硕士专业学位学科授权类别。"
w=wordcloud.WordCloud(width=1000,font_path="C:\\Windows\\Fonts\\msyh.ttf",height=700)
w.generate(" ".join(jieba.lcut(txt)))
w.to_file("university.png")
