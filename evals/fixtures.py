"""The figures the model produced, recorded.

These are **AI outputs**, and the project's convention is that every AI
output is gated by CI: ``tests/eval`` replays them through the same
harness the live run uses, so a kernel change that breaks them is
caught before a teacher is.

Four tables:

- ``RECORDED_CASES`` and ``RECORDED_STATEMENTS`` -- the answers
  themselves, by name;
- ``OUTCOMES_CASES`` and ``OUTCOMES_STATEMENTS`` -- what each answer
  achieved, so the gate can tell a failure that has not moved from one
  that has.

They were recorded from a live run against the service the studio
would use.  Re-record them with ``scripts/record_fixtures.py`` when the
skill changes -- and when they change, say so in the changelog.
"""

from __future__ import annotations

#: The recorded answers to the contract cases, by the case's name.
RECORDED_CASES: dict[str, str] = {
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
AH = 线段(A, H)
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

#: The recorded answers to the problem statements, by the statement's name.
RECORDED_STATEMENTS: dict[str, str] = {
    "直角三角形（3-4-5）+ 垂足": """点 A(0,0) B(3,0) C(0,4)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
bc = 直线(B, C)
H = 垂足(A, bc)
AH = 线段(A, H)""",
    "平行四边形（边长 + 角）": """点 A(0,0) B(5,0)
D = 旋转(B, 60, A)
D = 位似(D, 3/5, A)
C = 平移(B, D)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)""",
    "矩形（边长）": """点 A(0,0) B(3,0) C(3,4) D(0,4)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)""",
    "菱形（对角线）": """点 A(0,0) B(3,4) C(6,0) D(3,-4)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)
AC = 线段(A, C)
BD = 线段(B, D)""",
    "等边三角形 + 外接圆 + 内切圆": """点 A(0,0) B(4,0)
C = 旋转(B, 60, A)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
w = 外接圆(A, B, C)
c = 内切圆(A, B, C)""",
    "圆外一点的切线（带长度）": """点 O(0,0) P(5,0)
c = 圆(O, 2)
t = 切线(P, c)""",
    "等腰三角形 + 中点 + 高": """点 A(0,3) B(-2,0) C(2,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
D = 中点(B, C)
AD = 线段(A, D)""",
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
    "锐角三角形 + 三个心": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
O = 外心(A, B, C)
H = 垂心(A, B, C)
G = 重心(A, B, C)""",
    "三条高交于垂心": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
bc = 直线(B, C)
ad = 垂直(A, bc)
D = 交点(ad, bc)
AD = 线段(A, D)
ac = 直线(A, C)
be = 垂直(B, ac)
E = 交点(be, ac)
BE = 线段(B, E)
ab = 直线(A, B)
cf = 垂直(C, ab)
F = 交点(cf, ab)
CF = 线段(C, F)
H = 交点(ad, be)""",
    "内心与角平分线": """点 A(0,3) B(-2,0) C(2,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
I = 内心(A, B, C)
m = 角平分线(A, B, C)
D = 交点(m, CA)
BD = 线段(B, D)""",
    "九点圆（用户的那道题）": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
bc = 直线(B, C)
H = 垂足(A, bc)
D = 中点(B, C)
M = 中点(A, B)
N = 中点(A, C)
AH = 线段(A, H)
断言 共圆(D, M, N, H)""",
    "圆上的点与三条连线": """点 A(0,0) B(4,0) C(1,3)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
c = 外接圆(A, B, C)
P = 圆上的点(c, 1/4)
PA = 线段(P, A)
PB = 线段(P, B)
PC = 线段(P, C)""",
    "圆上一点的切线": """点 O(0,0) A(2,0)
c = 圆(O, A)
P = 圆上的点(c, 1/4)
t = 切线(P, c)
OP = 线段(O, P)""",
    "平行四边形的对角线互相平分": """点 A(0,0) B(4,0) C(5,3) D(1,3)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)
AC = 线段(A, C)
BD = 线段(B, D)
O = 交点(AC, BD)""",
    "直角三角形的外接圆（斜边中点）": """点 A(0,0) B(4,0) C(0,3)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
c = 外接圆(A, B, C)
M = 中点(B, C)""",
    "三角形的外接圆与内切圆": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
c = 外接圆(A, B, C)
n = 内切圆(A, B, C)""",
    "两条中线的交点是重心": """点 A(0,4) B(-3,0) C(3,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
D = 中点(B, C)
E = 中点(C, A)
AD = 线段(A, D)
BE = 线段(B, E)
G = 交点(AD, BE)""",
    "四点在同一圆上": """点 O(0,0) P(2,0)
c = 圆(O, P)
A = 圆上的点(c, 0)
B = 圆上的点(c, 1/4)
C = 圆上的点(c, 1/2)
D = 圆上的点(c, 3/4)
AB = 线段(A, B)
BC = 线段(B, C)
CD = 线段(C, D)
DA = 线段(D, A)""",
    "等腰三角形（另一种说法）": """点 A(0,0) B(5,0)
C = 旋转(B, 40, A)
AB = 线段(A, B)
AC = 线段(A, C)
BC = 线段(B, C)""",
    "中点（另一种说法）": """点 A(2,3) B(0,0) C(5,0)
AB = 线段(A, B)
BC = 线段(B, C)
CA = 线段(C, A)
D = 中点(B, C)
AD = 线段(A, D)""",
}

#: What each recorded case answer achieved: "satisfied" or "unsatisfied".
OUTCOMES_CASES: dict[str, str] = {
    "锐角三角形 + 三个心": "satisfied",
    "外接圆 + 圆上的点": "satisfied",
    "九点圆": "satisfied",
    "等腰三角形的顶角平分线": "satisfied",
    "三条中线与重心": "satisfied",
    "圆上一点的切线": "satisfied",
    "圆外一点的切线": "satisfied",
    "做不到的切线（圆内点）": "satisfied",
    "直角三角形的斜边中点": "satisfied",
}

#: What each recorded statement answer achieved: "satisfied",
#: "unsatisfied", "refused" or "parse-failure".
OUTCOMES_STATEMENTS: dict[str, str] = {
    "直角三角形（3-4-5）+ 垂足": "satisfied",
    "平行四边形（边长 + 角）": "parse-failure",
    "矩形（边长）": "satisfied",
    "菱形（对角线）": "satisfied",
    "等边三角形 + 外接圆 + 内切圆": "satisfied",
    "圆外一点的切线（带长度）": "satisfied",
    "等腰三角形 + 中点 + 高": "satisfied",
    "等腰三角形的顶角平分线": "satisfied",
    "三条中线与重心": "satisfied",
    "锐角三角形 + 三个心": "satisfied",
    "三条高交于垂心": "satisfied",
    "内心与角平分线": "satisfied",
    "九点圆（用户的那道题）": "satisfied",
    "圆上的点与三条连线": "satisfied",
    "圆上一点的切线": "satisfied",
    "平行四边形的对角线互相平分": "satisfied",
    "直角三角形的外接圆（斜边中点）": "satisfied",
    "三角形的外接圆与内切圆": "satisfied",
    "两条中线的交点是重心": "satisfied",
    "四点在同一圆上": "satisfied",
    "等腰三角形（另一种说法）": "satisfied",
    "中点（另一种说法）": "satisfied",
}
