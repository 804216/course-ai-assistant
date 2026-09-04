# variance.py
# 计算两个数的平方差
  
# 以普通函数方式定义
def variance1(a,b):
    return b**2 - a**2

# 以匿名函数方式定义
variance2 = lambda a,b: b**2 - a**2

x,y = 4,5

# 普通函数调用
print("以普通函数方式定义的函数计算：")
print("{}*{} - {}*{} = {}".format(y,y ,x ,x,variance1(x,y)))

#匿名函数调用
print("============================")
print("以匿名函数方式定义的函数计算：")
print("{}*{} - {}*{} = {}".format(y,y ,x ,x,variance2(x,y)))
