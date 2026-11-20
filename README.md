# video-timeline-marker

长视频章节标记的时间线工具：8 个桩函数位于 `marker/timeline.py`，15 个验收测试位于 `tests/test_timeline.py`。

## 题面

给长视频自动加章节标记后，同一时刻的标记顺序乱、最后一章还丢了片尾：产品要求用毫秒时间轴维护标记 `{"t", "label", "color"}`，插入时同刻保持插入顺序，移动后按时间重排，相邻过近按阈值合并并保留较早标签，按 fps 吸附到最近帧（误差不超过 0.5 帧），按左闭右开区间查询，导出章节首尾相接且最后一章到片尾，校验越界、重复与空标签，批量处理多轨时任一轨非法整体回滚。marker/timeline.py 是核心，tests/test_timeline.py 15个红。要修的是：插入用 `sort(key=t)`，同时间顺序不稳定；移动后不重排，时间线错乱；合并用固定 1 秒，阈值不生效；吸附向下取整，偏半帧；范围查询闭区间，边界重复；章节最后一章结束时间用最后一个标记，片尾丢失；校验允许标记超出时长；重复标签不报错，导出后重名；批量共用标记列表，轨道之间串；`fps=0` 不校验，除零。

## 运行方式

```bash
python -m pytest tests -q
```

初始状态应恰好输出 `15 failed`，且没有 collection error、import error 或 syntax error：15 个测试全部调用 `marker/timeline.py` 中的桩，桩统一抛 `NotImplementedError`。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 音视频处理 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 约束

- `tests/test_timeline.py` 是验收测试，不可修改；只允许修改 `marker/timeline.py`。
- 只使用标准库（`bisect`、`math`）与 pytest，离线运行，不使用随机数。
- 8 个函数目前全部为 `raise NotImplementedError` 的桩，完整契约见各函数 docstring。
