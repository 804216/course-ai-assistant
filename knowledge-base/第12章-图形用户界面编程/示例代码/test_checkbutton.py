# -*- coding: utf-8 -*-
# 例12-6：test_checkbutton.py
from tkinter import *
app = Tk()
options = [IntVar() for _ in range(4)]#每个复选框所绑定的控制变量
def check():
    for opt in options:
        if (opt.get()!=1): #正确答案是每个候选项都应该被选择
            info['text']="请再想想!"
            return
    info['text']="你真棒!"
def hint():
    cb1.select()# 选择相应的复选框
    cb2.select()
    cb3.select()
    cb4.select()
Label(app,width=35,text="下面哪些是计算机编程语言的名字:").pack()
cb1 = Checkbutton(app,variable=options[0],text="Python")
cb1.pack()
cb2 = Checkbutton(app,variable=options[1],text="Java")
cb2.pack()
cb3 = Checkbutton(app,variable=options[2],text="Ruby")
cb3.pack()
cb4 = Checkbutton(app,variable=options[3],text="Scala")
cb4.pack()
frm = Frame(app) # 创建一个框架用于容纳后面的按钮控件，将在12.3.8介绍
frm.pack() # 对框架进行布局
Button(frm,text="检查",command=check).pack(side=LEFT,padx=2)
Button(frm,text="提示",command=hint).pack(side=LEFT,padx=2)
info = Label(app,width=10,text="")
info.pack(pady=2)
app.mainloop()
