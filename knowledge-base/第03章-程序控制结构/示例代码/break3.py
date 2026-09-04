# break3.py
exit_flag = False
# 外层循环
for i in range(0, 5) :
    # 内层循环
    for j in range(0, 3) :
        print("i的值为: %d, j的值为: %d" % (i, j))
        if j == 1 :
            exit_flag = True
            # 跳出内层循环
            break
    # 如果exit_flag为True，跳出外层循环
    if exit_flag :
        break 
