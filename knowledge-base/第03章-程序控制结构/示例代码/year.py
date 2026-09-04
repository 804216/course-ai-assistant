# year.py
year=int(input("请输入年份："))
if year % 4 == 0:
    if year % 100 == 0:
        if year % 400 == 0:
            flag = 1
        else:
            flag = 0
    else:
        flag = 1
else:
    flag = 0
if flag == 1:
    print(year,"年是闰年")
else:
    print(year,"年不是闰年")
