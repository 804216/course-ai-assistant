# -*- coding: utf-8 -*-
# testclassmethod.py
from datetime import date
class Member:
    def __init__(self,name,age):
        self.name = name
        self.age = age
    @classmethod
    def from_birthyear(cls,name,birthyear):
        age = date.today().year - birthyear
        return cls(name,age)
    def hello(self):
        print('I am %s. I am %d years old'%(self.name,self.age))

    
