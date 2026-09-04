# math_score.py
math = int(input("请输入数学成绩："))
if math >= 75:
    if math >= 90:
        print("数学成绩为优")
    else:
        print("数学成绩为良")
else:
    if math >=60:
        print("数学成绩及格了")
    else:
        print("数学成绩不及格")
