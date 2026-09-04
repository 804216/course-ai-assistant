# pi.py
from random import random
n=10000
N=0
for i in range(1,n):
    x,y=random(),random()
    dis=pow(x**2+y**2,0.5)
    if dis<=1:
        N=N+1
pi=4*N/n
print("圆周率为{}".format(pi))
