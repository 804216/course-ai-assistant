# string_join.py
sourceDict = {
    "username": "sample",
    "code": "2002001001",
    "source": "python"
}

array = [];
for (key, value) in sourceDict.items():
    array.append(key + "=" + value)

queryString = "&".join(array)
print(queryString)
