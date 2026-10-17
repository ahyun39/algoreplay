def solution(s):
    prev = None
    while prev != s:
        prev = s
        s = s.replace('()', '').replace('[]', '').replace('{}', '')
    return s == ''
