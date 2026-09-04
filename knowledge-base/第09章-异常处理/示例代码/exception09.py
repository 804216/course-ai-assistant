# exception09.py
class CustomError(Exception):
    def __init__(self, value):
        self.value = value
        self.__class__.__name__ = "【用户自定义异常】" + self.__class__.__name__
    def __GetStr__(self):
        return repr(self)

try:
    raise CustomError("hehe!")
except CustomError as e:
    print(e.__class__.__name__,'已触发，值为：', e.value )
    print(e.__GetStr__())
