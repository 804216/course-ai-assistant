#param3.py
#函数定义
def userinfo(**p):
    print(p)
    for k,v in p.items():
        print(k,":",v)

#函数调用
userinfo(name = 'zhangsan' , id  = '0001' , sex= 'male')
print("====================================================")
userinfo(name = 'lisi' , id  = '0002' , sex= 'female')
print("====================================================")
userinfo(name = 'wangwu' , id  = '0003' , sex= 'female')
