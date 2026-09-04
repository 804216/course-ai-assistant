#func_var2.py
x,y = 2,200         #全局变量
 
def func():
    x,y = 1,100     #局部变量作用域仅在函数内部
    print("函数内部：x=%d,y=%d" % (x,y))      

print("函数外部：x=%d,y=%d" % (x,y))
func()
print("函数外部：x=%d,y=%d" % (x,y))
