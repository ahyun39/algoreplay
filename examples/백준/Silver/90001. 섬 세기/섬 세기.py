import sys

sys.setrecursionlimit(10**6)
input = sys.stdin.readline

n, m = map(int, input().split())
grid = [input().strip() for _ in range(n)]
seen = [[False] * m for _ in range(n)]


def dfs(x, y):
    seen[x][y] = True
    size = 1
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < n and 0 <= ny < m and not seen[nx][ny] and grid[nx][ny] == "1":
            size += dfs(nx, ny)
    return size


count = biggest = 0
for i in range(n):
    for j in range(m):
        if grid[i][j] == "1" and not seen[i][j]:
            count += 1
            biggest = max(biggest, dfs(i, j))
print(count, biggest)
