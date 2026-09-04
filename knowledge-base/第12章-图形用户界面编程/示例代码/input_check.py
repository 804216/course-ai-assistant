# -*- coding: utf-8 -*-
# 例12-5：input_check.py
from tkinter import *
import re
app = Tk()
text= StringVar() # 定义一个控制变量
def check(*arg): #控制变量的回调函数
    newval = text.get()#获取控制变量的值
    if re.match('^[a-z A-Z]*$', newval) is None:#正则表达式进行匹配
        entry.select_range(0,END) # 调用select_range框选当前输入
        output['text']="只能输入英文字符,请重新输入"
    else:
        output['text']=""
text.trace_add("write",check)#为控制变量添加回调函数进行合法性检查
entry = Entry(app,width="10",textvariable=text)# 创建单行文本框控件
entry.pack(pady=2) #对控件进行布局，pack方法将在12.4节具体介绍
output = Label(app,width=25,text="")
output.pack(pady=2)
app.mainloop()
