# -*- coding: utf-8 -*-
# test_polymorphism2.py
def show_object(obj):  #只要传入的obj对象具有kind属性和show方法
    print('我是'+obj.kind,',我的生活是',sep="",end="")
    obj.show()
# 以下三个类都具有kind属性和show方法
# 因此相应实例可以作为show_object的参数
class Professor:
    kind = "人"
    def show(self):
        print("吃饭、工作、睡觉.")
class Machine:
    kind = "机器"
    def show(self):
        print("工作、工作、工作.")
class Pig:
    kind = "猪"
    def show(self):
        print("吃饭、睡觉.")
if __name__ == '__main__':
    objs = [Professor(),Machine(),Pig()]
    for obj in objs: 
        show_object(obj)
