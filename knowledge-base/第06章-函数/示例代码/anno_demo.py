# anno_demo.py
# 函数定义
def anno_demo(p1:str,p2:str = "is my favorite!")->str :
    s = p1 + " " + p2
    print("函数标注：",anno_demo.__annotations__)
    print("传递的参数：",p1,p2)
    return s

# 函数调用
print(anno_demo("Python"))
