# -*- coding: utf-8 -*-
# 例12-4：test_button.py
from tkinter import *
import time
app = Tk()
texts={'begin':'点击按钮开始计算',
'computing':'计算中...','end':'计算完成,点击按钮开始重复计算'}
def compute():
   info['text']=texts['computing'] #设置提示文本信息
   btn['state']=DISABLED # 修改按钮状态为不可点击
   app.update() # 即时刷新界面，否则要等到函数返回才刷新。
   time.sleep(5) # 延时5秒以模拟长时间计算过程
   info['text']=texts['end'] #设置提示文本信息
   btn['state']=NORMAL #恢复按钮为可点击状态
info = Label(text=texts['begin'],width = 50)
info.pack(side=TOP,pady=5) #对控件进行布局，pack方法将在12.4节具体介绍
btn = Button(text="开始",command=compute)
btn.pack(side=TOP,pady=5) #对控件进行布局，pack方法将在12.4节具体介绍
app.mainloop()
