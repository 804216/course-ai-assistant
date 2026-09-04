# five-pointed-star.pys
from turtle import Turtle
p = Turtle()
p.speed(3)
p.pensize(5)
p.color("black", "red")
p.begin_fill()
for i in range(5):
    p.forward(200)  #将箭头移到某一指定坐标 
    p.right(144)    #当前方向上向右转动角度
p.end_fill()
