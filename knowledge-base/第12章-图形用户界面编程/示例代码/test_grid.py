# -*- coding: utf-8 -*-
# 例12-11:test_grid.py
from tkinter import *
app = Tk()
pading = {'padx': 2, 'pady': 2,'ipadx':10,'ipady':10}
A_label = Label(app,text="Label A", bg="red" )
B_label = Label(app,text="Label B", bg="green")
C_label = Label(app,text="Label C", bg="blue")
D_label = Label(app,text="Label D", bg="yellow")
E_label = Label(app,text="Label E", bg="purple")
F_label = Label(app,text="Label F", bg="pink")
A_label.grid(pading, row=0, column=0, columnspan=3, sticky = NW+SE) #占据第0行，第0-2列。sticky的取值表示拉伸以填充单元格。
B_label.grid(pading, row=1, column=0, columnspan=3, sticky = NW+SE) #占据第1行，第0-2列。
C_label.grid(pading, row=2, column=0, rowspan=2, sticky = NW+SE) #占据第2-3行，第0列。
D_label.grid(pading,row=3,column=1,columnspan=2,sticky=NW+SE) #占据第3行，第1-2列。
E_label.grid(pading,row=2,column=2,sticky= NW+SE) #占据第2行，第1列。
F_label.grid(pading,row=2,column=1,sticky= NW+SE) #占据第2行，第2列。
app.mainloop()
