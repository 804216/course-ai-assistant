# quotient.py
# 求商
def quotient(dividend,divisor):
    if (divisor == 0):
        return
    else:
        return dividend/divisor

# 函数调用
# 除数不为0
a = 99
b = 3
print( a,"/" ,b," = ",quotient(a,b))

# 除数为0
a = 99
b = 0
print( a,"/" ,b," = ",quotient(a,b))
