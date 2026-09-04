# prime.py
#由于程序中要用到求平方根的函数sqrt()，因此需要导入math模块
import math
m = int(input("请输入一个数m："))
n = int(math.sqrt(m))
prime = 1
for i in range(2,n+1):
    if m % i == 0:
        prime = 0
if(prime == 1):
    print(m,"是素数")
else:
    print(m,"不是素数")
