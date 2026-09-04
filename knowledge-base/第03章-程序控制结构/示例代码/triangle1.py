# triangle1.py
num = int(input("请输入打印行数："))
for i in range(num):
    tab = False
    for j in range(i+1):
        print('*',end='')
        if j == i:
            tab = True
    if tab:
        print('\n' ,end = '')
