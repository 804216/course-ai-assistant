# -*- coding: utf-8 -*-
# 例12-9：test_label_frame.py
from tkinter import *
app = Tk()
# 基本信息录入
frame_inf= LabelFrame(app,padx=60, pady=5,text="基本信息")
frame_inf.pack(padx=10, pady=5)
frame_name=Frame(frame_inf) # 包含姓名信息的子框架
frame_name.pack()
Label(frame_name, text="姓名").pack(side=LEFT,padx=3)
Entry(frame_name,width=15).pack(side=LEFT,padx=3)
frame_ph = Frame(frame_inf) # 包含电话信息的子框架
frame_ph.pack()
Label(frame_ph, text="电话").pack(side=LEFT,padx=3)
Entry(frame_ph,width=15).pack(side=LEFT,padx=3)
# 特长选择
frame_spec = LabelFrame(app, padx=5, pady=5,text="特长")
frame_spec.pack(padx=10, pady=5)
Checkbutton(frame_spec,text="篮球").pack(side=LEFT,padx=5)
Checkbutton(frame_spec,text="足球").pack(side=LEFT,padx=5)
Checkbutton(frame_spec,text="乒乓球").pack(side=LEFT,padx=5)
Checkbutton(frame_spec,text="排球").pack(side=LEFT,padx=5)
# 提交
Button(app, text="提交").pack(padx=10, pady=10)
app.mainloop()
