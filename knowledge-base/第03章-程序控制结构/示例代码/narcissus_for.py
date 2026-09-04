# narcissus_for.py
for a in range(10):   #个位数的范围是0~9
    for b in range(10):   #十位数的范围是0~9
        for c in range(1,10):   #百位数的范围是1~9
            if(a + 10 * b + 100 * c == a ** 3 + b ** 3 + c ** 3):
	                print(a + 10 * b + 100 * c)
