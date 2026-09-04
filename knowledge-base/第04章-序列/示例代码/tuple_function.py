# function_example.py
tuple1 = ("hadoop", "spark", "flink", "storm")
#计算元组的大小
len_size = len(tuple1)
print("元组大小是：",len_size)
# 返回元组元素最大值和最小值
tuple_number = (1,2,3,4,5)
max_number = max(tuple_number)
min_number = min(tuple_number)
print("元组最大值是：",max_number)
print("元组最小值是：",min_number)
# 将列表转为元组
list1 = ["hadoop", "spark", "flink", "storm"]
tuple2 = tuple(list1)
# 打印tuple2数据类型
print("tuple2的数据类型是：",type(tuple2))
