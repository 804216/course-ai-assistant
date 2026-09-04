# drunk-driving.py
alcohol = int(input("请输入驾驶员每100ml血液酒精的含量："))
if alcohol < 20:
    print("驾驶员不构成酒驾")
else:
    if alcohol < 80:
        print("驾驶员已构成酒驾")
    else:
        print("驾驶员已构成醉驾")
