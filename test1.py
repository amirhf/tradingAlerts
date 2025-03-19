class iter1():
    def __init__(self, n):
        self.n = n
        self.c1 = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.c1 < self.n:
            self.c1 += 1
            return self.c1*self.c1
        else:
            raise StopIteration
print([x for x in iter1(10)])

#define a singletons class
class Singleton:
    _instance = None
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Singleton, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        print("init called")
        self.var = 0
    def get_var(self):
        return self.var


    def __del__(self):
        print("del called")

a = Singleton()
a.var=1
b = Singleton()
b.var=2
print(a.get_var())
print(b.get_var())

'''
import heapq
print(int(" 1"))
que=[]
heapq.heappush(que,3)
heapq.heappush(que,1)
heapq.heappush(que,2)
print([heapq.heappop(que) for _ in range(3)])
def gen1(n):
    c1 = 0
    while c1<n:
        c1 += 1
        yield c1

def test1():
    generator = gen1(10)
    print([next(generator) for _ in range(5)])
    print([x for x in gen1(10)])


test1()
'''