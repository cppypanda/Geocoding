import contextvars
import logging

# 1. 创建一个上下文变量，可以设置一个默认值
#    This will hold the prefix for the log messages.
request_context_var = contextvars.ContextVar('request_context', default='')

class ContextFilter(logging.Filter):
    """
    一个自定义的日志过滤器，它将上下文变量中的值注入到日志记录中。
    """
    def filter(self, record):
        """
        为日志记录添加一个 'context' 属性。
        如果上下文变量中有值，日志格式化器 (formatter) 就可以使用它。
        """
        record.context = request_context_var.get()
        return True 