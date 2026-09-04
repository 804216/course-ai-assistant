# sum_seq.py
# 定义函数
def sum_seq(a1,a2):
    val = (a1 + a2) * (abs(a2 - a1)+1)/2
    return val
#调用函数
print(sum_seq(1,9))
print(sum_seq(3,4))
print(sum_seq(2,11))
