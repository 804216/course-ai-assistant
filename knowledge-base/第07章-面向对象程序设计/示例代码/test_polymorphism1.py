# -*- coding: utf-8 -*-
# test_polymorphism1.py
class Animal:
    kind = "动物"  # 该属性将被子类重写
    def show(self): 
        print('我是'+self.kind,',我的叫声是',sep="",end="")
        self.yell() # 将根据传入的具体子类对象调用子类的重写方法
    def yell(self): # 该方法将被子类重写
        print("???")
class Dog(Animal):
    kind = "狗"
    def yell(self):
        print("汪汪汪.")
class Cat(Animal):
    kind = "猫"
    def yell(self):
        print("喵喵喵.")
class Duck(Animal):
    kind = "鸭子"
    def yell(self):
        print("嘎嘎嘎.")
if __name__ == '__main__':
    animals = [Dog(),Cat(),Duck()]
    for animal in animals:
        animal.show()  #传入show方法的self参数为不同的子类对象
