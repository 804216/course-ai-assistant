# transfer_mutable.py
# 函数定义
def transfer_mutable(varlist):
    print("-------------------------函数内部-------------------------")
    print("函数内部赋值前，变量值：",varlist," --- 变量地址：",id(varlist))
    varlist += [4,5,6,7]
    print("函数内部赋值后，变量值：",varlist," --- 变量地址：",id(varlist))
    print("-------------------------函数内部-------------------------")
    return(varlist)

# 函数调用
var_a = [1,2,3]
print("函数外部调用前，变量值：",var_a," --- 变量地址：",id(var_a))
transfer_mutable(var_a)
print("函数外部调用后，变量值：",var_a," --- 变量地址：",id(var_a))
