import time
import sys
import os 
from multiprocessing import Queue
import signal
import atexit
from platform import system
from config_server import ServerConfig as Config
from util.server.server_cosmic import console
from util.server.providers import create_provider
from util.tools.empty_working_set import empty_current_working_set

from . import logger

# 全局变量，用于跟踪资源状态
_resources_initialized = False


def cleanup_recognizer_resources():
    """清理识别器资源"""
    global _resources_initialized

    if not _resources_initialized:
        return

    logger.debug("识别子进程资源清理完成")


def signal_handler(signum, frame):
    """
    识别子进程的信号处理器

    优雅地退出识别进程。
    """
    signal_name = signal.Signals(signum).name
    logger.info(f"识别子进程收到信号 {signal_name} ({signum})，准备退出...")

    # 清理资源
    cleanup_recognizer_resources()

    # 退出进程
    logger.debug("识别子进程退出")
    exit(0)





def init_recognizer(queue_in: Queue, queue_out: Queue, sockets_id, stdin_fn):
    global _resources_initialized

    logger.info("识别子进程启动")
    logger.debug(f"系统平台: {system()}")
    sys.stdin=os.fdopen(stdin_fn)

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.debug("识别子进程信号处理器已注册")

    # 注册 atexit 处理器
    atexit.register(cleanup_recognizer_resources)

    provider_type = Config.provider_type.lower()
    provider = create_provider()
    provider_name = getattr(provider, 'name', provider.__class__.__name__)

    console.print('[yellow]STT Provider 载入中', end='\r')
    t1 = time.time()
    logger.info(f"开始加载 STT Provider，类型: {provider_type}")

    try:
        provider.load()
    except Exception as e:
        logger.error(f"STT Provider 加载失败: {e}", exc_info=True)
        raise

    console.print(f'[green4]STT Provider 载入完成 ({provider_name})', end='\n\n')
    logger.info(f"STT Provider 加载完成 ({provider_name})，耗时: {time.time() - t1:.2f}s")
    console.print(f'Provider 加载耗时 {time.time() - t1 :.2f}s', end='\n\n')


    queue_out.put(True)  # 通知主进程加载完了
    logger.info("识别器初始化完成，开始处理任务")

    # 清空物理内存工作集
    if system() == 'Windows':
        empty_current_working_set()

    # 标记资源已初始化
    _resources_initialized = True

    while True:
        # 从队列中获取任务消息
        # 阻塞最多1秒，便于中断退出
        try:
            task = queue_in.get(timeout=1)
        except:
            continue

        # 检查退出信号
        if task is None:
            logger.info("收到退出信号，识别子进程正在停止...")
            break

        if task.socket_id not in sockets_id:    # 检查任务所属的连接是否存活
            logger.debug(f"任务所属连接已断开，跳过处理，任务ID: {task.task_id}")
            continue

        result = provider.recognize(task)   # 执行识别
        queue_out.put(result)      # 返回结果

    # 清理完成
    try:
        provider.close()
    except Exception as e:
        logger.warning(f"关闭 STT Provider 失败: {e}")
    logger.info("识别子进程已退出")
