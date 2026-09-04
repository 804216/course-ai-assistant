# exception03.py
total = 100
while True:
    x = input("请输入整数：")
    try:
        x = int(x)
        val = total / x
        print("==>您输入的整数为：",x, " **** 商为：",val)
    except Exception as e:
        print("Error! ",e)
