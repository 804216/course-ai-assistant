# param2.py
# 定义函数
def cal_sum(*a):
    sum = 0
    for ele in a:
        sum += ele
    return sum

# 调用函数
print(cal_sum(1,2))
print(cal_sum(1,2,3,4))
