# -*- coding: utf-8 -*-
# inheritance.py
class A:
    def __init__(self):
        self.public_value_1 = 'pulic value 1 in class A'
    def public_method(self):
        print('calling public method in class A')
    def __private_method(self):
        print('calling private method in class A')
class B1(A): 
    pass
class B2(A):
    def __init__(self):   #重写构造器，但没有显式调用父类的构造器
        self.public_value_2 = 'pulic value 2 in class B2'
    def public_method(self):   #重写父类公有方法
        print('calling public method in class B2')
    def __private_method(self):   #定义自己的私有方法
        print('calling private method in class B2')
class B3(A):
    def __init__(self):   #重写构造器，并显式调用父类的构造器
        super().__init__()
        self.public_value_2 = 'pulic value 2 in class B3'
