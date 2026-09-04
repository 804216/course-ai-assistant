# exception06.py
try:
    val = 1/0
    pass
except FloatingPointError as ex1:       #未能捕捉到异常
    print("ex1:",ex1)
    
#except BaseException as BaseEx:        #可以捕捉到所有异常，此处注释掉
#    print("BaseEx:",BaseEx)

finally:
   print("都要处理finally子句！")
