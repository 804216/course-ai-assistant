# break2.py
for i in range(0,3) :
    print("此时i的值为：",i)
    for j in range(5):
        print("此时j的值为:",j)
        if j==1:
            break
    print("跳出内层循环")
