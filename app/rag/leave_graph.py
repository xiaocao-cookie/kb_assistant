from __future__ import annotations

import json
import uuid
import re

from datetime import datetime
from typing import Any, Dict

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage

from app.deps import get_llm
from app.model.leave_model import LeaveState
from app.utils.leave_rules import validate_leave
from app.prompts.leave_prompt import SLOT_SYSTEM, SLOT_USER
from app.prompts.parse_date_prompt import TIME_USER, TIME_SYSTEM
from app.db_ops.leave_sql import (
    get_leave_balance,
    get_leave_request,
    cancel_leave_request,
    insert_leave_request,
    get_recent_leave_requests,
    update_leave_request,
    approve_leave_request,
    reject_leave_request,
    insert_annual_leave_request
)
from app.constants.rbac import Permission


def _safe_json_load(s: str) -> Dict[str , Any]:
    """
    将大模型返回的 json 转换为字典
    :param s: json 字符串
    :return: 字典
    """
    if not s:
        return {}
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].strip()
    try:
        return json.loads(s)            # 将 json 字符串转换为字典
    except Exception:
        return {}


def _safe_iso(s: Any) -> str | None:
    """
    将ISO格式的时间转为datetime对象
    :param s: 时间
    :return: datetime对象 或 None
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    try:
        datetime.fromisoformat(s)
        return s
    except Exception:
        print(f"e: {Exception.__name__}")

def _extract_leave_id(text: str) -> str:
    """
    从 text 中匹配 Leave_id(LV-...)
    """
    if not text:
        return None
    m = re.search(r"\bLV-[0-9a-fA-F]{6,12}\b", text)
    return m.group(0) if m else None

def _extract_limit(text: str, default: int = 5) -> int:
    """ 提取最近的 default 条请假记录 """

    # 中文数字映射
    CN_NUM_MAP = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    if not text:
        return default

    # 1. 数字：3条 / 最近3
    m = re.search(r"(\d+)\s*条", text)
    if not m:
        m = re.search(r"最近\s*(\d+)", text)
    if m:
        return int(m.group(1))

    # 2. 中文：三条 / 最近三
    m = re.search(r"最近\s*([一二三四五六七八九十])", text)
    if not m:
        m = re.search(r"([一二三四五六七八九十])\s*条", text)
    if m:
        return CN_NUM_MAP.get(m.group(1), default)

    return default


def _perms(state: LeaveState) -> set[str]:
    """
    获取 state 中的权限并将其转换为 set
    """
    return set(state.get("permissions") or [])


def _has_perm(state: LeaveState, code: str) -> bool:
    """
    判断 code 是否在 state 中的 permission 集合里
    """
    if state.get("is_super_admin"):
        return True
    return code in _perms(state)


def _deny(code: str) -> dict:
    """ 权限拒绝 """
    return {"answer": f"你没有 {code} 权限，请联系管理员"}


def intent_node(state: LeaveState) -> dict:
    return {}


def decide_intent(state: LeaveState) -> str:
    """
    路由分发，查询请假单/解析时间/取消请假单
    """
    text = (state.get("text") or state.get("question") or "").lower()

    if any(k in text for k in ["取消", "撤销", "作废"]):
        return "cancel"

    if any(k in text for k in ["查询", "查", "状态", "进度", "结果"]):
        if any(k in text for k in ["请假", "年假", "病假", "事假", "休假", "调休", "假期", "申请", "单"]):
            return "query"

    if any(k in text for k in ["最近", "列表", "我的请假", "请假记录", "历史请假"]) and \
       any(k in text for k in ["请假", "年假", "病假", "事假", "休假", "假期", "记录"]):
        return "list"

    if any(k in text for k in ["修改", "变更", "调整", "改期", "改到", "改为"]):
        return "modify"

    if any(k in text for k in ["批准", "同意", "通过", "审批通过"]):
        return "approve"

    if any(k in text for k in ["驳回", "拒绝", "不通过", "审批拒绝"]):
        return "reject"

    return "apply"


def query_leave_node(state: LeaveState) -> dict:
    """
    请假单查询
    """
    text = state.get("text") or state.get("question") or ""
    leave_id = state.get("leave_id") or _extract_leave_id(text)

    if not leave_id:
        return {"answer": "请提供请假单编号，我才能帮你查询"}

    row = get_leave_request(leave_id)
    if not row:
        return {"answer": f"未找到编号为 {leave_id} 的请假申请"}

    me = state.get("requester", "anonymous")
    owner = row.get("requester")

    if owner == me:
        if not _has_perm(state, Permission.PERM_LEAVE_VIEW_SELF):
            return _deny(Permission.PERM_LEAVE_VIEW_SELF)
    else:
        if not _has_perm(state, Permission.PERM_LEAVE_VIEW_ALL):
            return _deny(Permission.PERM_LEAVE_VIEW_ALL)

    return {
        "leave_id": leave_id,
        "answer": (
            f"请假单 {leave_id} 当前状态：{row['status']}\n"
            f"申请人：{row['requester']}\n"
            f"类型：{row['leave_type']}\n"
            f"开始：{row['start_time']}\n"
            f"结束：{row['end_time']}\n"
            f"时长：{row['duration_days']} 天\n"
            f"原因：{row.get('reason') or '无'}"
        ),
    }


def cancel_leave_node(state: LeaveState) -> dict:
    """
    取消请假单
    """
    if _has_perm(state, Permission.PERM_LEAVE_CANCEL):
        return _deny(Permission.PERM_LEAVE_CANCEL)

    text = state.get("text") or state.get("question") or ""
    leave_id = state.get("leave_id") or _extract_leave_id(text)

    if not leave_id:
        return {"answer": "请提供要取消的请假单编号。"}

    row = get_leave_request(leave_id)
    if not row:
        return {"answer": f"未找到编号为 {leave_id} 的请假申请"}

    me = state.get("requester", "anonymous")
    if not state.get("is_super_admin") and row.get("requester") != me:
        return {"answer": "只能取消自己的请假单"}

    ok = cancel_leave_request(leave_id)
    if not ok:
        return {"answer": "取消失败：单据不是待审批状态（PENDING）。"}

    return {"leave_id": leave_id, "answer": f"已取消请假申请 {leave_id}。"}


def list_leave_node(state: LeaveState) -> dict:
    """ 列出最近的请假记录 """
    if not _has_perm(state, Permission.PERM_LEAVE_VIEW_SELF):
        return _deny(Permission.PERM_LEAVE_VIEW_SELF)

    text = state.get("text") or state.get("question") or ""
    requester = state.get("requester", "anonymous")
    limit = _extract_limit(text, default=5)

    rows = get_recent_leave_requests(requester, limit=limit)
    if not rows:
        return {"answer": "你还没有请假记录。"}

    lines = [f"最近 {len(rows)} 条请假记录："]
    for r in rows:
        lines.append(
            f"- {r['leave_id']} | {r['leave_type']} | "
            f"{r['start_time']} ~ {r['end_time']} | "
            f"{r['duration_days']}天 | {r['status']}"
        )
    return {"answer": "\n".join(lines)}


def modify_leave_node(state: LeaveState) -> dict:
    """ 修改请假单 """
    if _has_perm(state, Permission.PERM_LEAVE_MODIFY):
        return _deny(Permission.PERM_LEAVE_MODIFY)

    text = state.get("text") or state.get("question") or ""
    requester = state.get("requester", "anonymous")

    leave_id = state.get("leave_id") or _extract_leave_id(text)
    if not leave_id:
        return {"answer": "请提供要修改的请假单号，例如 LV-xxxxxxxx"}

    old = get_leave_request(leave_id)
    if not old:
        return {"answer": f"未找到编号为 {leave_id} 的请假申请"}
    if old["status"] != "PENDING":
        return {"answer": f"{leave_id} 不是待审批状态，无法修改！当前的状态为: {old['status']}"}

    if not state.get("is_super_admin") and old.get("requester") != requester:
        return {"answer": "你只能修改自己的请假单"}

    base_req = {
        "leave_type": old["leave_type"],
        "start_time": old["start_time"].strftime("%Y-%m-%d %H:%M"),
        "end_time": old["end_time"].strftime("%Y-%m-%d %H:%M"),
        "reason": old.get("reason"),
        "requester": old["requester"]
    }

    llm = get_llm()

    # 抽槽
    raw_slots = llm.invoke([
        SystemMessage(content=SLOT_SYSTEM),
        HumanMessage(content=SLOT_USER.format(text=text))
    ]).content
    slots = _safe_json_load(raw_slots)

    # 解析时间
    raw_time = llm.invoke([
        SystemMessage(content=TIME_SYSTEM),
        HumanMessage(content=TIME_USER.format(
            now=datetime.now().strftime("%Y-%m-%d %H:%M"),
            text=text
        )),
    ]).content
    tdata = _safe_json_load(raw_time)

    new_req = dict(base_req)

    new_req["leave_type"] = slots.get("leave_type") or new_req["leave_type"]
    st = _safe_iso(slots.get("start_time")) or _safe_iso(tdata.get("start_time"))
    et = _safe_iso(slots.get("end_time")) or _safe_iso(tdata.get("end_time"))
    if st:
        new_req["start_time"] = st
    if et:
        new_req["end_time"] = et

    new_req["reason"] = slots.get("reason") or new_req["reason"]

    # 规则校验
    balance = get_leave_balance(requester) or {}
    annual_balance = float(balance.get("annual_days", 0))
    missing, violations = validate_leave(new_req, balance_days=annual_balance)
    if missing or violations:
        tips = []
        if missing:
            tips.append("缺少信息：" + "、".join(missing))
        if violations:
            tips.append("规则问题：" + "；".join(violations))
        return {"answer": "；".join(tips) + "。请重新描述修改内容。"}

    # 防止 duration_days 没有计算
    if not new_req.get("duration_days") and new_req.get("start_time") and new_req.get("end_time"):
        st_dt = datetime.fromisoformat(new_req["start_time"])
        et_dt = datetime.fromisoformat(new_req["end_time"])
        new_req["duration_days"] = round((et_dt - st_dt).total_seconds() / 3600 / 8, 2)

    # 更新
    ok = update_leave_request(leave_id,
                              {
                                  "leave_type": new_req["leave_type"],
                                  "start_time": new_req["start_time"],
                                  "end_time": new_req["end_time"],
                                  "duration_days": new_req.get("duration_days"),
                                  "reason": new_req.get("reason")
                              })

    if not ok:
        return {"answer": "修改失败，该单可能已被审批或取消"}

    return {
        "leave_id": leave_id,
        "answer": (
            f"已修改请假单 {leave_id}：\n"
            f"- 类型：{new_req['leave_type']}\n"
            f"- 开始：{new_req['start_time']}\n"
            f"- 结束：{new_req['end_time']}\n"
            f"- 时长：{new_req.get('duration_days')} 天\n"
            f"- 原因：{new_req.get('reason') or '无'}"
        )
    }



def approve_leave_node(state: LeaveState) -> dict:
    """
    批准请假
    """
    if not _has_perm(state, Permission.PERM_LEAVE_APPROVE):
        return _deny(Permission.PERM_LEAVE_APPROVE)

    text = state.get("text") or state.get("question") or ""
    leave_id = state.get("leave_id") or _extract_leave_id(text)
    if not leave_id:
        return {"answer": "请提供要审批的请假编号，例如 LV-xxxxxxxx"}

    ok = approve_leave_request(leave_id, approver=state.get("requester", "admin"))
    if not ok:
        return {"answer": "审批失败：未找到该请假单，或单据不是 PENDING 状态"}

    return {"leave_id": leave_id, "answer": f"请假单 {leave_id} 已审批通过"}


def reject_leave_node(state: LeaveState) -> dict:
    """
    驳回请假
    """
    if not _has_perm(state, Permission.PERM_LEAVE_REJECT):
        return _deny(Permission.PERM_LEAVE_REJECT)

    text = state.get("text") or state.get("question") or ""
    leave_id = state.get("leave_id") or _extract_leave_id(text)
    if not leave_id:
        return {"answer": "请提供要驳回的请假编号, 例如 LV-xxxxxxxx"}

    reason = None
    m = re.search(r"(因为|理由|原因)[:： ]?(.*)$", text)
    if m:
        reason = (m.group(2) or "").strip()[:200] or None

    ok = reject_leave_request(
        leave_id,
        approver=state.get("requester", "admin"),
        reason=reason
    )
    if not ok:
        return {"answer": "驳回失败： 未找到该单，或请假单不是 PENDING 状态"}

    return {"leave_id": leave_id, "answer": f"已驳回请假单 {leave_id}, 理由：{reason or '未填写'}"}


def parse_time_node(state: LeaveState) -> dict:
    """
    从文本中解析时间
    """
    req = state.get("req") or {}
    if _safe_iso(req.get("start_time")) and _safe_iso(req.get("end_time")):
        return {}

    llm = get_llm()
    text = state.get("text") or state.get("question") or ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    messages = [
        SystemMessage(content=TIME_SYSTEM),
        HumanMessage(content=TIME_USER.format(now=now, text=text))
    ]
    raw = llm.invoke(messages).content
    data = _safe_json_load(raw)

    start = _safe_iso(data.get("start_time"))
    end = _safe_iso(data.get("end_time"))

    if start or end:
        req.update({
            "start_time": start or req.get("start_time"),
            "end_time": end or req.get("end_time"),
        })
        return {"req": req}
    return {}

def extract_slots_node(state: LeaveState) -> dict:
    """
    抽取槽位
    :param state:
    :return:
    """
    llm = get_llm()
    text = state.get("text", "") or state.get("question", "") or ""

    messages = [
        SystemMessage(content=SLOT_SYSTEM),
        HumanMessage(content=SLOT_USER.format(text=text)),
    ]
    raw = llm.invoke(messages).content
    data = _safe_json_load(raw)

    req = state.get("req") or {}
    req.update({
        "leave_type": data.get("leave_type") or req.get("leave_type"),
        "start_time": _safe_iso(data.get("start_time")) or req.get("start_time"),
        "end_time": _safe_iso(data.get("end_time")) or req.get("end_time"),
        "reason": data.get("reason") or req.get("reason"),
    })
    req["requester"] = state.get("requester", "anonymous")
    return {"req": req}


def validate_node(state: LeaveState) -> dict:
    """
    请假的规则校验
    """
    req = state.get("req") or {}
    requester = req.get("requester") or state.get("requester", "anonymous")

    bal = get_leave_balance(requester) or {}  # 看看数据库里还有几天假期可以用
    annual_balance = float(bal.get("annual_days", 0))

    missing, violations = validate_leave(req, balance_days=annual_balance)
    return {"missing_fields": missing, "violations": violations, "req": req}


def decide_next(state: LeaveState) -> str:
    """
    决定走信息补充还是确认请假信息
    """
    if state.get("missing_fields") or state.get("violations"):
        return "need_info"

    req = state.get("req")
    if req.get("leave_type") == "annual":
        return "annual"

    return "confirm"


def annual_approve_node(state: LeaveState) -> dict:
    """ 年假自动审批 """
    req = state.get("req") or {}
    leave_id = "LV-" + uuid.uuid4().hex[:8]
    req_to_save = {
        "leave_id": leave_id,
        "requester": req["requester"],
        "leave_type": req["leave_type"],
        "start_time": req["start_time"],
        "end_time": req["end_time"],
        "duration_days": req["duration_days"],
        "reason": req.get("reason"),
    }
    insert_annual_leave_request(req_to_save)
    return {"leave_id": leave_id, "answer": "审批通过"}

def need_info_node(state: LeaveState) -> dict:
    """
    补充信息的提示
    """
    missing = state.get("missing_fields") or []
    violations = state.get("violations") or []

    tips = []
    if missing:
        tips.append("缺少信息：" + "、".join(missing))
    if violations:
        tips.append("规则问题：" + "；".join(violations))

    return {"answer": "；".join(tips) + "。请补充/修正后再说一次。"}


def confirm_node(state: LeaveState) -> dict:
    """
    请假信息确认
    """
    req = state.get("req") or {}
    ans = (
        "请确认你的请假信息：\n"
        f"- 类型：{req.get('leave_type')}\n"
        f"- 开始：{req.get('start_time')}\n"
        f"- 结束：{req.get('end_time')}\n"
        f"- 时长：{req.get('duration_days')} 天\n"
        f"- 原因：{req.get('reason') or '无'}\n"
        "回复“确认”提交，或直接回复修改后的信息。"
    )
    return {"answer": ans}


def decide_confirm(state: LeaveState) -> str:
    """
    是否确认请假
    """
    text = (state.get("text") or "").strip().lower()
    if text in {"确认", "确定", "yes", "ok", "submit"}:
        return "create"
    return "end"


def create_leave_node(state: LeaveState) -> dict:
    """
    生成请假单（这里是虚拟的请假单，并没有连接数据库）
    :param state:
    :return:
    """
    if not _has_perm(state, Permission.PERM_LEAVE_APPLY):
        return _deny(Permission.PERM_LEAVE_APPLY)

    req = state.get("req") or {}
    leave_id = "LV-" + uuid.uuid4().hex[:8]
    req_to_save = {
        "leave_id": leave_id,
        "requester": req["requester"],
        "leave_type": req["leave_type"],
        "start_time": req["start_time"],
        "end_time": req["end_time"],
        "duration_days": req["duration_days"],
        "reason": req.get("reason"),
    }
    insert_leave_request(req_to_save)
    return {"leave_id": leave_id, "answer": f"已为你提交请假申请，编号 {leave_id}，等待审批。"}


def build_leave_graph():
    """
    构建请假图
    :return: 已编译的图对象
    """
    g = StateGraph(LeaveState)

    g.add_node("intent", intent_node)

    g.add_node("cancel", cancel_leave_node)
    g.add_node("query", query_leave_node)
    g.add_node("list", list_leave_node)
    g.add_node("create", create_leave_node)
    g.add_node("modify", modify_leave_node)
    g.add_node("approve", approve_leave_node)
    g.add_node("reject", reject_leave_node)


    g.add_node("parse_time", parse_time_node)
    g.add_node("extract", extract_slots_node)
    g.add_node("validate", validate_node)
    g.add_node("need_info", need_info_node)
    g.add_node("confirm", confirm_node)
    g.add_node("annual", annual_approve_node)


    g.add_edge(START, "intent")
    g.add_conditional_edges(
        "intent",
        decide_intent,
        {
            "apply": "parse_time",
            "query": "query",
            "cancel": "cancel",
            "list": "list",
            "modify": "modify",
            "approve": "approve",
            "reject": "reject"
        }
    )

    g.add_edge("parse_time", "extract")
    g.add_edge("extract", "validate")

    g.add_conditional_edges(
        "validate",
        decide_next,
        {
            "need_info": "need_info",
            "confirm": "confirm",
            "annual": "annual"
        }
    )

    g.add_conditional_edges(
        "confirm",
        decide_confirm,
        {
            "create": "create",
            "end": END
        }
    )

    g.add_edge("query", END)
    g.add_edge("cancel", END)
    g.add_edge("modify", END)
    g.add_edge("list", END)
    g.add_edge("approve", END)
    g.add_edge("reject", END)

    g.add_edge("need_info", END)
    g.add_edge("create", END)
    g.add_edge("annual", END)


    return g.compile()