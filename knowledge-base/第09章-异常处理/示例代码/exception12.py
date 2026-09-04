# exception12.py
def integer_return():
    try:
        return 1
    except Exception as e:
        return 2
    else:
        return 3
    finally:
        return 4
  
print(integer_return())
