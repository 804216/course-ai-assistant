# exception10.py
def num_return():
    try:
        return 1
    except Exception as e:
        print (e)
        return 2 
    else:
        return 3
    
print(num_return())
