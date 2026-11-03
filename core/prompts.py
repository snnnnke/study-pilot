"""提示词模板：决定报告质量的核心。

分两个阶段：
  Map    —— 逐块提炼知识点
  Reduce —— 合并成完整的学习报告结构
"""

MAP_SYSTEM = """你是一位资深的学习教练、知识工程师，擅长从教材、课件、讲义、视频文字稿中提炼知识结构。
你的任务：阅读学习资料的一个片段，提炼其中的知识点，并严格按 JSON 输出。
要求：
1. 只输出 JSON，不要输出任何解释文字、不要用 Markdown 代码块包裹。
2. 只提炼片段中真实出现的内容，绝不编造。
3. 尽量保留原文中的定义、公式、结论、例子。
4. 使用简体中文。"""

MAP_USER = """【资料名称】{name}
【片段位置】第 {index}/{total} 段
【片段内容】
{chunk}

请提炼这个片段，严格输出如下 JSON：
{{
  "topic": "本片段的主题（一句话）",
  "points": [
    {{
      "title": "知识点标题",
      "detail": "清晰准确的解释，1-3 句话",
      "importance": 3,
      "source": "页码或时间戳，如 第12页 / [03:20]；没有则留空"
    }}
  ],
  "concepts": ["关键概念、术语"],
  "difficulties": ["初学者容易出错或难以理解的点"],
  "questions": ["值得思考或可能被考到的问题"]
}}

补充要求：
- importance 取 1-5 的整数，5 表示最重要、最核心；
- points 建议 3-12 条，覆盖该片段的主要知识；
- 如果片段是目录、封面、过渡页等低信息内容，points 可以为空数组；
- source 优先使用片段中出现的「第 x 页」或「[mm:ss]」标记。"""


REDUCE_SYSTEM = """你是一位资深学习规划师和职业规划顾问，擅长把零散的知识点整理成系统化的学习方案。
你将收到同一份（或一组）学习资料各个片段的提炼结果（JSON 数组）。
你的任务：合并、去重、重组，生成一份完整、可执行的学习报告结构。

严格要求：
1. 只输出 JSON，不要输出解释文字、不要用 Markdown 代码块包裹。
2. 内容必须基于输入材料，不能凭空编造知识点。
3. 就业与薪资相关判断，要写成基于公开常识的参考性描述，不做绝对化承诺。
4. 使用简体中文。"""

REDUCE_USER = """【资料名称】{name}
【报告档位】{profile_desc}
【片段提炼结果】
{map_json}

请生成完整的学习报告，严格输出如下 JSON（字段一个都不能少，没有内容用空数组或空字符串）：
{{
  "title": "报告的标题，概括这份资料的核心主题",
  "overview": "资料概述，150-250 字，讲清楚这份资料讲什么、适合谁学",
  "outline": [
    {{"level": 1, "title": "第 1 章 / 第一部分 标题", "summary": "这一部分讲什么（30字内）", "source": "对应页码或时间戳"}}
  ],
  "highlights": [
    {{"title": "核心重点标题", "explain": "为什么重要、核心结论是什么", "importance": 5, "source": "出处", "exam_tip": "常见考法或面试考点"}}
  ],
  "study_methods": [
    {{"method": "学习方法名称", "why": "为什么适合这份资料", "how": "具体怎么做，可执行的步骤"}}
  ],
  "review_plan": {{
    "principles": "复习总原则（间隔重复、主动回忆等）",
    "schedule": [
      {{"day": "第 1 天", "focus": "这一天复习什么", "tasks": ["具体任务1", "具体任务2"]}}
    ],
    "daily_routine": ["每天 30 分钟可以做什么"]
  }},
  "career": {{
    "roles": ["这份知识对应的岗位方向"],
    "skills": [{{"name": "技能名称", "why": "为什么重要", "level": "入门/熟练/精通"}}],
    "interview_topics": ["面试高频考点"],
    "note": "就业与薪资信息为 AI 基于公开常识的推断，仅供参考，请以实际招聘信息为准。"
  }},
  "priority": {{
    "urgent_important": [{{"item": "知识点", "reason": "为什么必须立刻掌握"}}],
    "important_not_urgent": [{{"item": "知识点", "reason": "为什么长期重要"}}],
    "urgent_not_important": [{{"item": "知识点", "reason": "为什么紧急但不重要"}}],
    "not_important": [{{"item": "知识点", "reason": "为什么可以跳过"}}],
    "advice": "整体投入建议（先学什么、后学什么、时间怎么分配）"
  }},
  "quiz": [
    {{"q": "题目", "options": ["A. 选项", "B. 选项", "C. 选项", "D. 选项"], "answer": "A", "explain": "解析"}}
  ],
  "keywords": ["关键词"]
}}

档位要求：
- quick（快速）：outline 5-10 条，highlights 5-8 条，quiz 可为空数组；
- standard（标准）：outline 8-15 条，highlights 8-15 条，quiz 3-5 题；
- deep（深度）：outline 10-20 条，highlights 12-20 条，quiz 至少 5 题，study_methods 至少 4 条。

质量要求：
- outline 要体现知识层级（level 用 1 或 2），按资料真实结构组织；
- highlights 按 importance 从高到低排列；
- review_plan.schedule 至少包含第 1/3/7/15/30 天；
- priority 四个象限都要有内容，尽量具体到知识点，不要空泛；
- 所有 source 尽量保留输入中的页码/时间戳；
- 输出必须是合法 JSON，字符串内不要出现未转义的控制字符。"""


def profile_desc(profile: str) -> str:
    return {
        "quick": "quick（快速）：篇幅精简，优先核心概念，适合快速浏览",
        "standard": "standard（标准）：平衡深度与篇幅，适合系统学习",
        "deep": "deep（深度）：最详细，覆盖细节、难点、自测题，适合备考",
    }.get(profile, "standard（标准）")


MERGE_SYSTEM = """你是一位知识整理专家。你会收到同一份学习资料分批生成的若干份报告片段（JSON）。
请把它们合并成一份完整报告，严格输出 JSON，不要输出解释文字。
合并时：outline 按资料逻辑排序、highlights 去重并按重要度排序、quiz 合并去重。"""

MERGE_USER = """下面是若干份报告片段：
{parts_json}

请合并为一份完整报告，字段结构与单份报告完全一致（title, overview, outline, highlights, study_methods, review_plan, career, priority, quiz, keywords）。
严格只输出 JSON。"""
