# exception05.py
try:
    val = 1/0
    pass
except FloatingPointError as ex1:       #未能捕捉到异常
    print("ex1:",ex1)
except ZeroDivisionError as ex2:        #捕捉到异常
    print("ex2:",ex2)
finally:
   print("都要处理finally子句！")
