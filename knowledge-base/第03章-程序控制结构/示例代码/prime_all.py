# prime_all.py
#由于程序中要用到求平方根的函数sqrt()，因此需要导入math模块
import math
i = 0
for n in range(100,201):
    prime = 1    
    k =  int(math.sqrt(n))   
    for  i in range(2,k+1):
        if n % i == 0:
            prime = 0    
    if prime ==1:
        print("%d是素数" % n)
  
    
