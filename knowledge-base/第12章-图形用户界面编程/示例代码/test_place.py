# -*- coding: utf-8 -*-
# 例12-12:test_place.py
from tkinter import *
app = Tk()
pading = {'padx': 10, 'pady': 10}
A_label = Label(app,pading,text="Label A", bg="red" )
B_label = Label(app,pading,text="Label B", bg="green")
A_label.place(x=0,y=0) # 采用绝对坐标固定在窗口左上角
B_label.place(relx=0.5,rely=0.5,anchor=CENTER)# 采用相对坐标放置在容器中间
app.mainloop()
