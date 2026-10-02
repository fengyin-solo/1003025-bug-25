"""场租合同业务规则：状态机、必填校验、到期提醒口径都收在这里。

台账列表与到期提醒读取的是同一份行数据（到期日期、状态均同源），
状态只能沿 执行中 → 即将到期 → 续租中 → 已到期 向前推进，已到期为终态。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "rental"

# 登记时缺一不可的字段，顺序即报错点名的顺序
REQUIRED_FIELDS = ["合同编号", "站点名称", "出租方", "年租金", "到期日期"]
OPTIONAL_FIELDS = ["签约日期", "续租条款"]
ENTRY_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

# 状态只能按这个次序向前走，最后一个「已到期」是终态
STATUS_ORDER = ["执行中", "即将到期", "续租中", "已到期"]
EXPIRED = STATUS_ORDER[-1]
EXPIRE_SOON_DAYS = 30

# 每个动作只允许在这些前置状态下发起；目标状态还要结合到期日期裁定
ACTION_ALLOWED_FROM: dict[str, set[str]] = {
    "登记到期": {"执行中"},
    "申请续租": {"即将到期"},
    "确认到期": {"即将到期", "续租中"},
}


def _parse_date(value: Any) -> date | None:
    """把 YYYY-MM-DD（或 date）解析成日期；空值或格式不对返回 None。"""
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


class RentalService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        # 先按到期日期校准状态，再筛选分页：列表、提醒、统计看到的口径永远一致
        for row in rows:
            self._reconcile_one(row)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("合同编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_reminders(self) -> list[dict[str, Any]]:
        """到期提醒：到期日期与状态直接取台账行，不另算一套。

        已到期的提醒「不能再续租」，即将到期的提醒尽快续租；
        执行中、续租中的合同不出现在提醒里。
        """
        reminders: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            self._reconcile_one(row)
            status = row.get("status")
            expire_text = str(row.get("到期日期") or "")
            if status == "即将到期":
                tip = f"将于 {expire_text} 到期，请尽快申请续租"
                can_renew = True
            elif status == EXPIRED:
                tip = f"已于 {expire_text} 到期，不能再续租"
                can_renew = False
            else:
                continue
            reminders.append({
                "id": row.get("id"),
                "合同编号": row.get("合同编号", ""),
                "站点名称": row.get("站点名称", ""),
                "出租方": row.get("出租方", ""),
                "到期日期": expire_text,
                "状态": status,
                "提醒": tip,
                "can_renew": can_renew,
            })
        # 已到期最紧急排最前；同档内到期日期早的在前
        reminders.sort(key=lambda item: (
            0 if item["状态"] == EXPIRED else 1,
            item["到期日期"],
        ))
        return reminders

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            self._reconcile_one(entry)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """登记合同；提交前先把必填项和日期格式校一遍，缺什么错什么都点名返回。"""
        errors = [
            f"缺少必填字段：{field}"
            for field in REQUIRED_FIELDS
            if not str(values.get(field) or "").strip()
        ]
        expire_text = str(values.get("到期日期") or "").strip()
        if expire_text and _parse_date(expire_text) is None:
            errors.append("到期日期格式不正确，应为 YYYY-MM-DD")
        if errors:
            return None, errors

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in ENTRY_FIELDS})
        # 新登记的合同先按到期日期落初始状态（临近到期直接进即将到期）
        entry["status"] = STATUS_ORDER[0]
        self._reconcile_one(entry)
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场租合同 {entry_id} 不存在或已归档"
        if action not in ACTION_ALLOWED_FROM:
            return None, f"动作「{action}」不属于场租合同可执行范围"

        # 动手前先按到期日期校准：续租和到期撞车时，到期优先
        self._reconcile_one(entry)
        current = str(entry.get("status") or "")
        contract_no = str(entry.get("合同编号") or entry_id)
        if current == EXPIRED:
            return None, f"合同 {contract_no} 已到期，不能再续租或重复确认到期"
        if current not in ACTION_ALLOWED_FROM[action]:
            allowed = "、".join(ACTION_ALLOWED_FROM[action])
            return None, f"合同 {contract_no} 当前为「{current}」，不能执行「{action}」（仅 {allowed} 状态可执行）"

        if action == "申请续租":
            expire = _parse_date(entry.get("到期日期"))
            if expire is None:
                return None, "到期日期缺失或格式不正确（应为 YYYY-MM-DD），无法判断是否已到期，请先补全合同"
            if expire <= date.today():
                self._set_status(entry, EXPIRED)
                return entry, f"合同 {contract_no} 已于 {expire.isoformat()} 到期，续租与到期撞车时按到期处理，不能再续租"
            self._set_status(entry, "续租中")
            return entry, f"场租合同 {contract_no} 已申请续租"

        target = {"登记到期": "即将到期", "确认到期": EXPIRED}[action]
        self._set_status(entry, target)
        return entry, f"场租合同已{action}"

    def _set_status(self, entry: dict[str, Any], target: str) -> None:
        """状态字段与「合同状态」展示列同步写入，保证台账只有一个事实来源。"""
        entry["status"] = target
        entry["合同状态"] = target
        entry["pending"] = target != EXPIRED
        entry["abnormal"] = False

    def _reconcile_one(self, entry: dict[str, Any]) -> None:
        """按到期日期把状态向前校准（只进不退）：

        - 已到期是终态，只同步镜像字段，绝不回退；
        - 到期日期已过：执行中/即将到期/续租中 一律落为已到期（续租撞车先算到期）；
        - 到期日期在近 {EXPIRE_SOON_DAYS} 天内：执行中 提前进入即将到期。
        """
        current = str(entry.get("status") or "")
        if current not in STATUS_ORDER:
            current = STATUS_ORDER[0]
        if current == EXPIRED:
            self._set_status(entry, EXPIRED)
            return

        expire = _parse_date(entry.get("到期日期"))
        if expire is None:
            self._set_status(entry, current)
            return
        today = date.today()
        if expire <= today:
            self._set_status(entry, EXPIRED)
        elif expire <= today + timedelta(days=EXPIRE_SOON_DAYS) and current == "执行中":
            self._set_status(entry, "即将到期")
        else:
            self._set_status(entry, current)
