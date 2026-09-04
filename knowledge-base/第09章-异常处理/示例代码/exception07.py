# exception07.py
while True:
    x = input("请输入整数类型的 除 数：")
    y = input("请输入整数类型的被除数：")
    try:
        x = int(x)
        y = int(y)
        val = y / x
    except TypeError:
        print("TypeError")
    except ZeroDivisionError:
        print("ZeroDivisionError")    
    except Exception as e:
        print("Error! ",e)
    else:
        print("No Error!")
        print("x=",x," y=",y, " y/x=",val,"\n")
    finally:
        print("finally子句都要执行！\n")
