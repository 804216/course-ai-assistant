# func_var3.py
x,y = 2,200         #全局变量

def func():
    global x
    x,y = 1,100     #局部变量作用域仅在函数内部
    print("函数内部：x=%d,y=%d" % (x,y)) 

print("函数外部：x=%d,y=%d" % (x,y))     #函数调用前
func()
print("函数外部：x=%d,y=%d" % (x,y))     #函数调用后
