# -*- coding: utf-8 -*-
# 例12-8：test_listbox.py
from tkinter import *
app = Tk()
selectmode = IntVar()
modes = [BROWSE,SINGLE,MULTIPLE,EXTENDED]#表示不同选择模式
days = ["Monday", "Tuesday", "Wednesday", "Thursday","Friday", "Saturday", "Sunday"]
def check(): # 按钮的回调函数
    selected = options.curselection() # 取得选择的索引号
    info['text']= "你选择的是:"+str([options.get(i) for i in selected]) 
def change_mode(): # 单选按钮的回调函数
    options['selectmode']=modes[selectmode.get()]#改变选择模式
    options.selection_clear(0,END) # 清除已有的所有选择
options=Listbox(app,selectmode=modes[0])# 创建一个空的列表框
options.pack()
options.insert(END,*days)#在列表框中添加选项
frm = Frame(app) # 创建一个框架用于容纳后面的单选按钮控件，将在12.3.8介绍
frm.pack()
Label(frm,text="selectedmode:").pack(side=LEFT)
for i, mode in enumerate(modes):
    Radiobutton(frm, text=mode, variable=selectmode, value=i, command =change_mode).pack(side=LEFT)
Button(text="check my selections",command=check).pack()
info = Label(app,text="")
info.pack()
app.mainloop()
