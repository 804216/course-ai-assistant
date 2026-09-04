# -*- coding: utf-8 -*-
# 例12-3：test_anchor.py
from tkinter import *
app = Tk()
text = """伫倚危楼风细细，望极春愁，黯黯生天际。
草色烟光残照里，无言谁会凭阑意。
拟把疏狂图一醉，对酒当歌，强乐还无味。
衣带渐宽终不悔，为伊消得人憔悴。"""
label=Label(text=text,width=50, height=10)
label['justify']=LEFT # 尝试改为CENTER等值
label['wraplength']=300 # 尝试改为诸如200等更小的数值
label['anchor'] = CENTER # 尝试改为N等值
label.pack()
app.mainloop()
