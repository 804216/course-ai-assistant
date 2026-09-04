# exception11.py
def bool_return():
    try:
        return True
    finally:
        return False
  
print(bool_return())
