"""异常类型。"""


class CancelledError(Exception):
    """任务被用户取消。"""


class PipelineError(Exception):
    """流水线中的可预期错误（会直接展示给用户）。"""
