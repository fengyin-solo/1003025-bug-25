"""场租合同业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "rental"
# 提交前先校必填：缺年租金、到期日期的一律拦下并点名
REQUIRED_FIELDS = ["合同编号", "站点名称", "出租方", "年租金", "到期日期"]
ALL_FIELDS = ["合同编号", "站点名称", "出租方", "年租金", "签约日期", "到期日期", "续租条款"]
STATUS_ORDER = ["执行中", "即将到期", "续租中", "已到期"]
# 动作 → (目标状态, 允许发起的当前状态)：按 执行中→即将到期→续租中→已到期 的次序走，
# 确认到期是终态收口，任何在途状态都能确认到期；已到期是终点，不能再续。
ACTION_RULES = {
    "登记到期": ("即将到期", {"执行中"}),
    "申请续租": ("续租中", {"即将到期"}),
    "确认到期": ("已到期", {"执行中", "即将到期", "续租中"}),
}
NEGATIVE_ACTIONS = []


def _parse_due_date(value: Any) -> date | None:
    """把到期日期解析成日期；填不出来就返回 None，不参与到期判定。"""
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


class RentalService:
    def _sync_entry(self, entry: dict[str, Any]) -> None:
        """对账：到期日期已过的一律先算到期，合同状态列始终跟着状态机走。

        提醒和台账读的是同一条记录、同一个到期日期，不会再各说各话。
        """
        if entry.get("status") != STATUS_ORDER[-1]:
            due = _parse_due_date(entry.get("到期日期"))
            if due is not None and due <= date.today():
                entry["status"] = STATUS_ORDER[-1]
                entry["pending"] = False
        entry["合同状态"] = entry.get("status", STATUS_ORDER[0])

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for row in rows:
            self._sync_entry(row)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("合同编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def status_counts(self) -> dict[str, int]:
        """各状态合同数：提醒卡片和台账用同一份数据、同一个到期日期口径。"""
        rows = store.rows(MODULE)
        counts = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            self._sync_entry(row)
            counts[str(row.get("status"))] = counts.get(str(row.get("status")), 0) + 1
        return counts

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            self._sync_entry(entry)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        # 先校必填再落库：校验不过什么都不写，提交失败可以原样重试，不留半张
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in ALL_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        self._sync_entry(entry)
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场租合同 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于场租合同可执行范围"
        # 续租和到期撞车时先算到期：到期日期已过的先落已到期，再走后续判断
        self._sync_entry(entry)
        current = str(entry.get("status") or STATUS_ORDER[0])
        target, allowed_sources = ACTION_RULES[action]
        if current == STATUS_ORDER[-1]:
            return None, f"场租合同已到期，不能再{action}"
        if current not in allowed_sources:
            return None, (
                f"场租合同当前为「{current}」，不能{action}；"
                f"请按 {'→'.join(STATUS_ORDER)} 的次序流转"
            )
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        self._sync_entry(entry)
        return entry, f"场租合同已{action}"
