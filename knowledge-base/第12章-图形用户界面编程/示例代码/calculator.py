# -*- coding: utf-8 -*-
# calculator.py
import tkinter as tk
class Calculator(tk.Tk):
    def __init__(self):
        super().__init__()# 调用父类的构造器
        self.title("Calculator")
        self.iconbitmap("python.ico")
        # 7*4布局，第一行和第二行是两个标签控件，后5行是18个按钮控件
        opts={'padx': 2, 'pady': 2,'ipadx':3,'ipady':2, 'sticky':tk.NSEW}
        buttonwidth=7
        self.exp = tk.StringVar() # 输入表达式标签的控制变量
        self.res = tk.StringVar(self,"0")# 计算结果标签的控制变量
        exp_label=tk.Label(self,anchor=tk.E,textvariable=self.exp)#输入表达式标签控件
        exp_label.grid(opts,row = 0, column = 0, columnspan = 4) 
        res_label=tk.Label(self,anchor=tk.E,textvariable=self.res) #计算结果（开始计算前用于显示待计算表达式）标签控件
        res_label.grid(opts,row = 1, column = 0, columnspan = 4)
        tk.Button(self, text = "C", width=buttonwidth, command = self.clear).grid(opts, row = 2, column = 0)
        tk.Button(self,text="/", width=buttonwidth, command = lambda:self.show("/")).grid(opts,row=2,column=1)
        tk.Button(self,text="*",width=buttonwidth, command= lambda:self.show("*")).grid(opts,row=2,column=2)
        tk.Button(self,text="BS",width=buttonwidth, command= self.backspace).grid(opts,row=2,column=3)
        tk.Button(self,text="-",width=buttonwidth, command= lambda:self.show('-')).grid(opts,row=3,column=3)
        tk.Button(self,text="+",width=buttonwidth, command= lambda:self.show('+')).grid(opts,row=4,column=3)
        tk.Button(self,text="Enter",anchor=tk.S,width=buttonwidth, command = self.calculate).grid(opts,row=5,column=3,rowspan=2)
        tk.Button(self,text=".",width=buttonwidth, command=lambda:self.show('.')).grid(opts,row=6,column=2)
        tk.Button(self,text="0",width=buttonwidth, command=lambda:self.show('0')).grid(opts,row=6,column=0,columnspan=2)
        tk.Button(self,text="7",width=buttonwidth, command=lambda:self.show("7")).grid(opts,row=3,column=0)
        tk.Button(self,text="8",width=buttonwidth, command=lambda:self.show("8")).grid(opts,row=3,column=1)
        tk.Button(self,text="9",width=buttonwidth, command=lambda:self.show("9")).grid(opts,row=3,column=2)
        tk.Button(self,text="4",width=buttonwidth, command=lambda:self.show("4")).grid(opts,row=4,column=0)
        tk.Button(self,text="5",width=buttonwidth, command=lambda:self.show("5")).grid(opts,row=4,column=1)
        tk.Button(self,text="6",width=buttonwidth, command=lambda:self.show("6")).grid(opts,row=4,column=2)
        tk.Button(self,text="1",width=buttonwidth, command=lambda:self.show("1")).grid(opts,row=5,column=0)
        tk.Button(self,text="2",width=buttonwidth, command=lambda:self.show("2")).grid(opts,row=5,column=1)
        tk.Button(self,text="3",width=buttonwidth, command=lambda:self.show("3")).grid(opts,row=5,column=2)
        # 允许除第一二行以外的各行各列等比例缩放
        for i in range(2,7):
            self.rowconfigure(i,weight=1)
        for i in range(0,4):
            self.columnconfigure(i,weight=1)
        # 添加应用程序级别键盘输入事件
        self.bind_all("<Return>",lambda e:self.calculate()) # 回车键
        self.bind_all("<Key-BackSpace>",lambda e:self.backspace()) # 退格键
        self.bind_all("<Key-Delete>",lambda e:self.clear()) # 删除键
        self.bind_all("<Key-plus>",lambda e:self.show('+'))
        self.bind_all("<Key-minus>",lambda e:self.show('-'))
        self.bind_all("<Key-asterisk>",lambda e:self.show('*'))
        self.bind_all("<Key-slash>",lambda e:self.show('/'))
        self.bind_all("<Key>",self.check_key) # 其它数字及操作符

    def check_key(self,event): # 检查数字键及操作符键事件
        if (event.char>='0') and (event.char<="9"):
            self.show(event.char)

    def calculate(self): # 调用eval函数计算表达式结果
        res = eval(self.res.get()) # 计算当前的表达式
        self.exp.set(self.res.get())
        self.res.set(str(res))

    def clear(self): # 清除当前的表达式
        self.exp.set("")
        self.res.set("0")

    def show(self,key): # 在开始计算前将当前的输入添加到待计算表达式
        content = self.res.get()
        if content == "0":
            content = ""
        self.res.set(content + key)

    def backspace(self): # 输入回撤一位
        self.res.set(str(self.res.get()[:-1]))

if __name__ == "__main__":
    app = Calculator()
    app.mainloop()
