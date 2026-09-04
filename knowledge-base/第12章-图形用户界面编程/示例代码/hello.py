# -*- coding: utf-8 -*-
# 例12-1：hello.py
import tkinter as tk
app = tk.Tk()
app.title("hello")
app.iconbitmap("python.ico")
label = tk.Label(app,text="欢迎开启GUI编程之旅！")
label.pack(padx=50,pady=5)
def change_button_text():
   btn.configure(text="[%s]" % btn['text'])
btn = tk.Button(app,text="点击我",command=change_button_text)
btn.pack(padx=50,pady=5)
app.mainloop()
