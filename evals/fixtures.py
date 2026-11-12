"""The figures the model produced, recorded.

These are **AI outputs**, and the project's convention is that every AI
output is gated by CI: ``tests/eval`` replays them through the same
harness the live run uses, so a kernel change that breaks them is
caught before a teacher is.

They were recorded from a live run against the service the studio
would use.  Re-record them with ``scripts/record_fixtures.py`` when the
skill changes -- and when they change, say so in the changelog.
"""

from __future__ import annotations

#: The recorded answers, by the case's name.
RECORDED: dict[str, str] = {
    "锐角三角形 + 三个心": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
O = 外心(A, B, C)
H = 垂心(A, B, C)
G = 重心(A, B, C)""",
    "外接圆 + 圆上的点": """点 A(0,0) B(4,0) C(1,3)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
c = 外接圆(A, B, C)
P = 圆上的点(c, 1/4)
PA = 线段(P, A)
PB = 线段(P, B)
PC = 线段(P, C)""",
    "九点圆": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
bc = 直线(B, C)
H = 垂足(A, bc)
D = 中点(B, C)
M = 中点(A, B)
N = 中点(A, C)
断言 共圆(D, M, N, H)""",
    "等腰三角形的顶角平分线": """点 A(0,3) B(-2,0) C(2,0)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)
m = 角平分线(B, A, C)
D = 交点(BC, m)
AD = 线段(A, D)""",
    "三条中线与重心": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
D = 中点(B, C)
E = 中点(C, A)
F = 中点(A, B)
AD = 线段(A, D)
BE = 线段(B, E)
CF = 线段(C, F)
G = 重心(A, B, C)""",
    "圆上一点的切线": """点 O(0,0) A(2,0)
c = 圆(O, A)
P = 圆上的点(c, 1/4)
t = 切线(P, c)""",
    "圆外一点的切线": """点 O(0,0) A(2,0) P(5,0)
c = 圆(O, A)
t = 切线(P, c)""",
    "做不到的切线（圆内点）": """# 做不到：P 在圆内时，过 P 引不出圆 c 的切线（切线要求点在圆上或圆外）""",
    "直角三角形的斜边中点": """点 A(0,0) B(4,0) C(0,3)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
M = 中点(B, C)""",
}
