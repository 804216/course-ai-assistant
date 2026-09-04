# -*- coding: utf-8 -*-
# 例12-10：test_pack.py
from tkinter import *
app = Tk()
frame = Frame(app)
frame.pack(fill=BOTH,expand=True)#允许框架随着主窗体大小自动拉伸
pading = {'padx': 2, 'pady': 2,'ipadx':10,'ipady':10}
A_label = Label(frame,text="Label A", bg="red" )
B_label = Label(frame,text="Label B", bg="green")
C_label = Label(frame,text="Label C", bg="blue")
D_label = Label(frame,text="Label D", bg="yellow")
E_label = Label(frame,text="Label E", bg="purple")
F_label = Label(frame,text="Label F", bg="pink")
labels = (A_label,B_label,C_label,D_label,E_label,F_label)
# 可以尝试调整下面三个参数的不同组合，测试不同的排版结果
sides=(TOP,TOP,LEFT,BOTTOM,RIGHT,TOP)#每个标签的放置方向不一样
fills=(BOTH,BOTH,BOTH,BOTH,BOTH,BOTH)
expands=(False,False,True,True,True,True)
i = 0
def pack_next(): # 回调函数
    global i
    if i<6: # 依次布局下一个标签
        labels[i].pack(pading, side=sides[i], fill=fills[i], expand =expands[i])
        i+=1
def forget_pre():# 回调函数
    global i
    if i>0: # 依次移除上一个标签
        labels[i-1].forget()
        i-=1
btn1 = Button(text="pack next",command=pack_next)
btn2 = Button(text="forget previous",command = forget_pre)
btn1.pack(pading,ipadx=5,ipady=2,side=LEFT,expand=True)
btn2.pack(pading,ipadx=5,ipady=2,side=LEFT,expand=True)
app.mainloop()
