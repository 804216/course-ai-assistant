# create_list.py
dim2_list = []                #创建一个空列表
for i in range(3):
    dim2_list.append([])       #为空列表添加的每个元素依然是空列表
    for j in range(4):
        dim2_list[i].append(j)  #为内层列表添加元素
print(dim2_list)
