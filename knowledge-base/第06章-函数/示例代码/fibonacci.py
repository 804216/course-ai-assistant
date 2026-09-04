# fibonacci.py
def fibonacci(n):
    '''求斐波拉契数列中第n个元素'''
    fn = 0
    if n == 1:
        fn = 0
    elif n== 2:
        fn = 1
    else:
        fn = fibonacci(n-2) + fibonacci(n-1)
    return fn

# 调用函数
for i in range(1,10):
    print (fibonacci(i))
