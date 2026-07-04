# -*- coding: utf-8 -*-
"""JSON 提取器 — 从 LLM 响应中多策略提取 JSON 数组。"""

import json
import re


def extract_json_array(text: str) -> list[dict]:
    """从 LLM 响应文本中提取 JSON 数组（4 级策略回退）。

    策略 1: ```json ... ``` 代码块
    策略 2: 裸 JSON 数组（贪婪匹配）
    策略 3: 整个响应即 JSON
    策略 4: 逐行提取 JSON 对象（最宽松）

    Raises:
        RuntimeError: 所有策略均失败
    """
    if len(text.strip()) < 30:
        raise RuntimeError(f"返回过短 ({len(text)} 字符): {text.strip()[:100]}")

    if text.startswith("[Error]"):
        raise RuntimeError(f"LLM 调用失败: {text}")

    # 策略 1: ```json ... ``` 代码块
    m = re.search(r'```json\s*\n(.*?)\n\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 策略 2: 裸 JSON 数组
    m = re.search(r'\[\s*\{[\s\S]*}\s*]', text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 策略 3: 整个响应即 JSON
    stripped = text.strip()
    if stripped.startswith('['):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # 策略 4: 逐行提取 JSON 对象
    obj_matches = re.findall(r'\{\s*"task_id"[\s\S]*?}', text)
    if obj_matches:
        issues = []
        for om in obj_matches:
            try:
                issues.append(json.loads(om))
            except json.JSONDecodeError:
                continue
        if issues:
            return issues

    raise RuntimeError(
        f"未找到有效 JSON（{len(text)} 字符）。\n"
        f"响应预览: {text[:300]}\n"
        f"响应尾: ...{text[-200:] if len(text) > 200 else ''}")
