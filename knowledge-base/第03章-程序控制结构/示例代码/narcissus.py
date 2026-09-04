# narcissus.py
for i in range(100,1000):
    a = i % 10  #个位数
    b = i // 10 % 10  #十位数
    c = i // 100  #百位数
    if(i == a ** 3 + b ** 3 + c ** 3):
        print(i)
