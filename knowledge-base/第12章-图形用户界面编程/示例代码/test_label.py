# -*- coding: utf-8 -*-
# 例12-2：test_label.py
from tkinter import *
app = Tk()
bitmaps = ['error', 'gray75', 'gray50', 'gray25', 'gray12', 'hourglass', 'info', 'questhead', 'question', 'warning']
for b in bitmaps: # 遍历bitmaps生成多个标签控件，创建标签后，同时调用pack方法对控件进行布局，pack方法将在12.4节具体介绍
    Label(text=b,bitmap=b,compound="left").pack(side=LEFT, padx=3)
img=PhotoImage(file="like.png") # 通过一个外部图片生成一个图像对象
label = Label(text="Like",image = img,compound="top")#创建标签
label.pack(side=LEFT,pady=3)#调用pack方法进行布局
app.mainloop()
