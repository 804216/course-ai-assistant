# fibonacci.py
i, j = 0, 1
while i < 10000:
    print(i)
    i, j = j, i+j
