def solution(s):
    answer = []
    for i in range(len(s)):
        distance = -1
        for j in range(i - 1, -1, -1):
            if s[j] == s[i]:
                distance = i - j
                break
        answer.append(distance)
    return answer
