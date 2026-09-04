# money.py
for i in range(100 // 1 + 1):
    for j in range((100 - i * 1) // 5 + 1):
        for k in range ((100 - i * 1 - j * 5) // 10 + 1):
            if i * 1 + j * 5 + k * 10 == 100:
                print("1元%d张，5元%d张，10元%d张" % (i,j,k))
                
