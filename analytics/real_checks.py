"""B가 만든 실제 확인 도구 모음. A의 가짜 도구와 바꿔 끼운다.

from agent.fake_checks import FAKE_TOOLS
from analytics.real_checks import REAL_TOOLS
tools = {**FAKE_TOOLS, **REAL_TOOLS}
"""

from analytics.check_budget import check_budget
from analytics.check_timing import check_timing

REAL_TOOLS = {"check_timing": check_timing, "check_budget": check_budget}
