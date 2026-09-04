# factorial_loop.py
def factorial_loop(n):
    '''用循环的方式求非负整数n的阶乘'''
    val = 1
    if n==0:
        return val
    else:
        i = 1
        while i<=n:
            val = val * i
            i += 1
        return val

# 调用函数
print(factorial_loop(5))
