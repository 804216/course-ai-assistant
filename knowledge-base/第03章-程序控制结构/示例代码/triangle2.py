# triangle2.py
num = int(input("请输入打印行数："))
for i in range(num):
    tab = False
    for j in range(i + 1):
        # 判断是否最后一行
        if i != num-1:
            # 循环完成，修改标识符
            if j == i :
                tab = True
            # 判断打印空格还是*
            if (i == j or j == 0):
                print('*',end='')
            else :
                print(' ',end='')
        # 最后一行，全部打印星号
        else :
            print('*', end='')
    if tab:
        print('\n', end='')
