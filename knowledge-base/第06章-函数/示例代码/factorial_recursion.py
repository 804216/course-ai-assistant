# factorial_recursion.py
def factorial_recursion(n):
    '''用递归的方法求非负整数n的阶乘'''
    if n==0:
        return 1
    else:
        return n*factorial_recursion(n-1)

# 调用函数
print(factorial_recursion(5))
