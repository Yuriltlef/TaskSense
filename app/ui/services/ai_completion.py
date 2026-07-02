# -*- coding: utf-8 -*-
"""AI 驱动的表单补全 — 跨字段上下文推理。

两层体系：
1. 快速层：关键词 + 业务规则映射（< 1ms）— 立即出结果
2. 深度层：LLM Agent 调用（600ms 防抖）— 增强/替换快速结果

跨字段推理（AGENT_TOOLS.md 内联工具 #1）：
- 标题 → ATA + 描述 + 任务类型
- ATA → 标题 + 描述 + 区域
- 描述 → 标题 + ATA
- 员工 ID → 姓名（EmployeeService 查表）
- 全字段上下文 → 缺失字段补全

上下文格式（ctx）：{field_name: value, ...}  from get_context()
"""

import threading
import json
import re
from typing import Callable

from app.core.logging import log


class AICompletionService:
    """AI 表单补全。"""

    def __init__(self, on_ready: Callable):
        self._on_ready = on_ready
        self._debounce_timer: threading.Timer | None = None
        self._debounce_ms: float = 600.0

    def on_input_changed(self, text: str, field: str, ctx: dict | None = None):
        """字段值变化 / 获得焦点时调用。"""
        ctx = ctx or {}
        text = (text or "").strip()

        # 即使当前字段为空，也可能从其他字段推断出建议
        if not text and not ctx:
            self._on_ready([], "empty")
            return

        # 第一层：即时匹配
        quick = self._infer_all(text, field, ctx)
        if quick:
            self._on_ready(quick, "keyword")

        # 第二层：LLM Agent 防抖
        if self._debounce_timer:
            self._debounce_timer.cancel()

        self._debounce_timer = threading.Timer(
            self._debounce_ms / 1000,
            lambda: self._run_agent(text, field, ctx),
        )
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def cancel(self):
        if self._debounce_timer:
            self._debounce_timer.cancel()

    # ═══════════════════════════════════════════
    # 第一层：跨字段推理引擎
    # ═══════════════════════════════════════════

    def _infer_all(self, text: str, field: str, ctx: dict) -> list[dict]:
        """综合推理：从当前字段值 + 上下文中推导所有可补全字段。"""
        result = []

        # ── 选择主要分析文本 ──
        main_text = text or ctx.get("title") or ctx.get("description") or ""

        # ── 已有 ATA（含当前字段值）──
        existing_ata = ctx.get("ata_chapter") or (text if field == "ata_chapter" else "")
        # 如果当前字段就是 ATA，直接用它推理
        if not existing_ata and field == "ata_chapter" and text:
            existing_ata = text

        # ── 1. ATA 章节（从文本推断 or 从已有 ATA 验证）──
        ata = self._infer_ata(main_text, ctx)
        if not ata and existing_ata:
            ata = existing_ata  # 用户已经填了 ATA，用它推理其他
        if ata and not ctx.get("ata_chapter") and field != "ata_chapter":
            result.append(self._sug("ata_chapter", ata, f"ATA {ata}", self._ata_label(ata)))

        # ── 2. 任务类型 ──
        tt = self._infer_task_type(main_text, ctx)
        tt_labels = {"troubleshoot":"排故","inspection":"检查","servicing":"勤务",
                      "removal_install":"拆装","test":"测试","repair":"修复"}
        if tt:
            result.append(self._sug("task_type", tt, tt_labels.get(tt, tt), ""))

        # 纯 ID 类型字段不触及其他推理
        if field in ("employee_id", "employee_name", "zone", "aircraft_reg"):
            return result

        # ── 3. 描述（ATA 输入也生成描述）──
        if not ctx.get("description") and field != "description":
            desc = self._infer_description(main_text, ata, tt)
            if desc:
                result.append(self._sug("description", desc,
                                        f"填入描述: {desc[:35]}...", ""))

        # ── 4. 标题反推 ──
        if not ctx.get("title") and field != "title":
            title_hint = self._infer_title(text or main_text, ata, tt)
            if title_hint:
                result.append(self._sug("title", title_hint, title_hint[:40], ""))

        # ── 5. 区域（从 ATA 推断）──
        if not ctx.get("zone") and field != "zone":
            zone = self._infer_zone(ata, main_text)
            if zone:
                result.append(self._sug("zone", zone, f"区域: {zone}", ""))

        # ── 6. 员工 ID → 姓名 ──
        emp_id = text if field == "employee_id" else ctx.get("employee_id", "")
        if emp_id and not ctx.get("employee_name") and field != "employee_name":
            emp = self._lookup_employee(emp_id)
            if emp:
                result.append(self._sug("employee_name", emp["name"],
                                        f"姓名: {emp['name']}", emp.get("trade", "")))

        return result

    # ── 各字段推理器 ──

    _ATA_MAP = {
        "起落架收放": ("32-31-01", "起落架收放"), "起落架转向": ("32-41-03", "前轮转向"),
        "起落架": ("32-10-00", "起落架总成"), "landing gear retract": ("32-31-01", "LG Retraction"),
        "landing gear steer": ("32-41-03", "Nose Wheel Steering"),
        "landing gear": ("32-10-00", "Landing Gear"),
        "N1": ("77-11-01", "N1 振动指示"), "N2": ("77-11-01", "N2 振动指示"),
        "振动指示": ("77-11-01", "发动机振动指示"), "振动": ("77-11-01", "发动机振动"),
        "发动机滑油": ("79-00-01", "发动机滑油系统"), "发动机燃油": ("73-11-03", "发动机燃油滤"),
        "发动机点火": ("74-11-03", "发动机点火"), "发动机控制": ("76-00-00", "发动机控制"),
        "发动机起动": ("80-00-00", "发动机起动"), "发动机指示": ("77-00-00", "发动机指示"),
        "发动机": ("72-00-00", "发动机总成"),
        "engine vibration": ("77-11-01", "Engine Vibration"),
        "engine oil": ("79-00-01", "Engine Oil"), "engine fuel": ("73-11-01", "Engine Fuel"),
        "engine ignition": ("74-00-00", "Engine Ignition"), "engine start": ("80-00-00", "Starting"),
        "engine": ("72-00-00", "Engine"),
        "燃油泵": ("28-21-01", "燃油泵"), "燃油滤": ("28-11-01", "燃油滤"),
        "燃油": ("28-10-00", "燃油系统"),
        "fuel pump": ("28-21-01", "Fuel Pump"), "fuel filter": ("28-11-01", "Fuel Filter"),
        "fuel": ("28-10-00", "Fuel"),
        "空调出口": ("21-51-01", "空调出风口"), "空调": ("21-00-00", "空调系统"),
        "air conditioning": ("21-00-00", "Air Conditioning"),
        "飞行控制面": ("27-10-00", "飞控面"), "飞行控制": ("27-00-00", "飞控系统"),
        "flight control": ("27-00-00", "Flight Controls"),
        "APU 启动": ("49-11-01", "APU 起动"), "APU 滑油": ("49-91-01", "APU 滑油"),
        "APU 进气": ("49-11-01", "APU 进气门"), "APU": ("49-00-00", "APU 总成"),
        "apu": ("49-00-00", "APU"),
        "滑油消耗": ("79-21-01", "滑油消耗"), "滑油更换": ("79-00-01", "滑油更换"),
        "滑油": ("79-00-00", "滑油系统"),
        "oil": ("79-00-00", "Oil"),
        "电源": ("24-00-00", "电源系统"), "electrical": ("24-00-00", "Electrical"),
        "液压泵": ("29-11-01", "液压泵"), "液压": ("29-00-00", "液压系统"),
        "hydraulic": ("29-00-00", "Hydraulic"),
        "防冰管路": ("30-11-01", "防冰管路"), "防冰": ("30-00-00", "防冰系统"),
        "anti-ice": ("30-11-01", "Anti-Ice"),
        "机翼前缘": ("57-40-01", "机翼前缘"), "机翼": ("57-00-00", "机翼"),
        "wing": ("57-00-00", "Wing"),
        "机身结构": ("53-10-01", "机身结构"), "机身": ("53-00-00", "机身"),
        "fuselage": ("53-00-00", "Fuselage"),
        "舱门": ("52-00-00", "舱门"), "door": ("52-00-00", "Door"),
        "灯光检查": ("33-11-01", "驾驶舱灯光"), "灯光": ("33-00-00", "灯光"),
        "light": ("33-00-00", "Light"),
        "仪表": ("31-10-00", "指示/记录"), "instrument": ("31-10-00", "Instrument"),
        "通信": ("23-00-00", "通信"), "communication": ("23-00-00", "Communication"),
        "导航": ("34-00-00", "导航"), "navigation": ("34-00-00", "Navigation"),
        "防火": ("26-00-00", "防火"), "fire": ("26-00-00", "Fire"),
        "氧气": ("35-00-00", "氧气"), "oxygen": ("35-00-00", "Oxygen"),
        "气源": ("36-00-00", "气源"), "pneumatic": ("36-00-00", "Pneumatic"),
        "水/废水": ("38-00-00", "水/废水"), "water/waste": ("38-00-00", "Water/Waste"),
        "设备/装饰": ("25-00-00", "设备/装饰"), "刹车": ("32-40-00", "刹车系统"),
        "brake": ("32-40-00", "Brake"),
        "排气": ("78-00-00", "排气"), "exhaust": ("78-00-00", "Exhaust"),
        "引气": ("75-00-00", "引气"), "bleed air": ("75-00-00", "Bleed Air"),
        "反推": ("78-00-00", "反推"),
    }

    def _infer_ata(self, text: str, ctx: dict) -> str:
        # 从上下文已有的 ATA 优先
        if ctx.get("ata_chapter"):
            return ""
        # 关键词匹配（长关键词优先）
        tl = (text or "").lower()
        sorted_kw = sorted(self._ATA_MAP.keys(), key=len, reverse=True)
        for kw in sorted_kw:
            if kw.lower() in tl:
                return self._ATA_MAP[kw][0]
        return ""

    def _infer_task_type(self, text: str, ctx: dict) -> str:
        t = (text or "").lower()
        if any(w in t for w in ["检查", "inspect", "check", "examine"]): return "inspection"
        if any(w in t for w in ["更换", "拆装", "replace", "remove", "install"]): return "removal_install"
        if any(w in t for w in ["测试", "test", "function"]): return "test"
        if any(w in t for w in ["勤务", "保养", "润滑", "清洁", "service", "lubricat", "clean"]): return "servicing"
        if any(w in t for w in ["修复", "修理", "repair", "fix"]): return "repair"
        if any(w in t for w in ["排故", "故障", "异常", "trouble", "fault", "fail", "异响", "偏高", "超限", "振动"]): return "troubleshoot"
        return ""

    def _infer_description(self, text: str, ata: str, tt: str) -> str:
        if not text:
            return ""
        templates = {
            "troubleshoot": f"排故：{text}。检查故障原因，确认部件状态，按需更换或修理。",
            "inspection": f"检查：{text}。按工卡逐项执行检查程序，记录测量值和发现的问题。",
            "removal_install": f"拆装：{text}。按 AMM {ata} 拆卸故障件并安装新件，执行功能测试。",
            "test": f"测试：{text}。执行系统功能测试，确认所有参数在容差范围内。",
            "servicing": f"勤务：{text}。按维护计划执行例行保养工作。",
            "repair": f"修复：{text}。按 SRM/AMM 手册执行结构或部件修理。",
        }
        return templates.get(tt, f"{text}。ATA {ata}。")

    def _infer_title(self, text: str, ata: str, tt: str) -> str:
        """从描述/ATA 反推标题。"""
        if not text:
            return ""
        # 取前 40 字符作为简洁标题
        short = text[:40].strip()
        if ata:
            return short
        return short

    def _infer_zone(self, ata: str, text: str) -> str:
        """根据 ATA 章节推断维护区域。"""
        zone_map = {
            "32": "710",  # 起落架 → 主起区域
            "49": "310",  # APU → 尾椎区域
            "72": "420",  # 发动机 → 右发区域
            "73": "420",
            "74": "420",
            "77": "420",
            "79": "420",
            "21": "510",  # 空调 → 客舱区域
            "53": "100",  # 机身 → 前机身
            "57": "610",  # 机翼 → 左大翼
            "30": "610",  # 防冰 → 机翼
            "27": "210",  # 飞控 → 主轮舱
            "33": "110",  # 灯光 → 驾驶舱
            "28": "420",  # 燃油 → 发动机
        }
        if ata:
            chapter = ata.split("-")[0]
            return zone_map.get(chapter, "")
        return ""

    def _lookup_employee(self, emp_id: str) -> dict | None:
        """从 EmployeeService 查员工（自动加载）。"""
        try:
            from app.core.services.employee_service import employee_service
            employee_service._ensure_loaded()
            return employee_service.get_employee(emp_id.strip())
        except Exception:
            return None

    @staticmethod
    def _sug(field: str, value: str, label: str, detail: str) -> dict:
        return {"field": field, "value": value, "label": label, "detail": detail, "source": "keyword"}

    @staticmethod
    def _ata_label(ata: str) -> str:
        for kw, (code, desc) in AICompletionService._ATA_MAP.items():
            if code == ata:
                return desc
        return ""

    # ═══════════════════════════════════════════
    # 第二层：LLM Agent
    # ═══════════════════════════════════════════

    def _run_agent(self, text: str, field: str, ctx: dict):
        log.begin("ai.agent", field=field, text=text[:30])
        try:
            suggestions = self._call_agent(text, field, ctx)
            if suggestions:
                self._on_ready(suggestions, "agent")
                log.result("ai.agent", f"{len(suggestions)} suggestions")
        except Exception as e:
            log.warn("ai.agent", f"failed: {e}")
        finally:
            log.end("ai.agent")

    def _call_agent(self, text: str, field: str, ctx: dict) -> list[dict]:
        from app.agent.llm_client import llm
        if not llm.is_available:
            return []

        ctx_str = "\n".join(f"  {k}: {v}" for k, v in ctx.items() if v) or "(无)"
        prompt = f"""分析以下航空维修任务表单输入，补全缺失字段。

当前字段: {field}
输入值: "{text}"

表单上下文:
{ctx_str}

返回 JSON，可为空的字段不输出：
{{"ata_chapter": "XX-XX-XX", "task_type": "troubleshoot|inspection|...",
  "description": "专业中文描述", "title": "建议标题", "zone": "区域编号"}}

只输出 JSON："""

        response = llm.chat(
            system_prompt="你是航空维修专家。根据表单上下文推理补全缺失字段。只输出 JSON。",
            user_message=prompt,
        )
        return self._parse(response)

    def _parse(self, raw: str) -> list[dict]:
        if not raw:
            return []
        m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return []

        _TT_MAP = {"troubleshoot":"排故","inspection":"检查","servicing":"勤务",
                    "removal_install":"拆装","test":"测试","repair":"修复"}
        result = []
        for key, label_prefix in [("ata_chapter","ATA"),("task_type",""),("description","描述"),
                                  ("title","标题"),("zone","区域")]:
            v = data.get(key, "")
            if v:
                display = _TT_MAP.get(v, v) if key == "task_type" else v
                lbl = display if key == "task_type" else f"{label_prefix}: {display}"
                result.append({"field":key,"value":v,"label":lbl,
                               "detail":"Agent 建议","source":"agent"})
        return result
