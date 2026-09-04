# docstr.py
# 函数定义
def docstr_demo(n):
    '''函数的简要描述

    函数参数n：传递函数的参数的描述'''
    return

# 打印函数文档字符串的两种方式
help(docstr_demo)
print("-------------------------------")
print(docstr_demo.__doc__)
