from enum import Enum
from pydantic import BaseModel
from typing import Optional, List, TypedDict

class LeaveType(str, Enum):
    """ 请假的类型 """
    annual = "annual"                  # 年假
    sick = "sick"                      # 病假
    personal = "personal"              # 事假
    other = "other"


class LeaveRequest(BaseModel):
    """ 请假单，对应数据库中的一张表 """
    requester: str
    leave_type: LeaveType = LeaveType.annual
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: Optional[float] = None
    reason: Optional[str] = None


class LeaveState(TypedDict, total=False):
    """ 请假的状态 """
    text: str
    requester: str
    user_role: str

    req: dict                       # 传 LeaveRequest 的字典
    missing_fields: List[str]
    violations: List[str]

    answer: str
    confirm: bool
    leave_id: Optional[str]
