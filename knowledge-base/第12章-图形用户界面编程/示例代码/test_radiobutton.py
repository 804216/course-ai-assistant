# -*- coding: utf-8 -*-
# 例12-7：test_radiobutton.py
from tkinter import *
app = Tk()
favorite = IntVar()
favorite.set(-1) # -1不同于任何选项的value，表示默认没有选项被选中
languages = ['Python','Java','Ruby','Scala']
def greet():#单选按钮的回调函数，通过共享控制变量的值获取已选择的选项
    info['text']="你是一个{}控".format(languages[favorite.get()])
Label(app,width=35,text="你最喜欢的计算机编程是:").pack()
frm = Frame(app) # 创建一个框架用于容纳后面的单选按钮控件，将在12.3.8介绍
frm.pack()
for i, language in enumerate(languages):#创建多个单选按钮，共享同一个variable,但value的值不同
    Radiobutton(frm, text=language,  variable=favorite, value=i, command=greet).pack(side=LEFT)
info = Label(app,text="")
info.pack()
app.mainloop()
