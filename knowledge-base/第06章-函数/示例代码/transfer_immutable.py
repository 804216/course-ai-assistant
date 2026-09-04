# transfer_immutable.py
# 函数定义
def transfer_immutable(var):
    print("-------------------------函数内部-------------------------")
    print("函数内部赋值前，变量值：",var," --- 变量地址：",id(var))
    var += 77
    print("函数内部赋值后，变量值：",var," --- 变量地址：",id(var))
    print("-------------------------函数内部-------------------------")
    return(var)

# 函数调用
var_a = 11
print("函数外部调用前，变量值：",var_a," --- 变量地址：",id(var_a))
transfer_immutable(var_a)
print("函数外部调用后，变量值：",var_a," --- 变量地址：",id(var_a))
