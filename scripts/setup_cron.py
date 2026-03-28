#!/usr/bin/env python3
"""
定时任务配置脚本

一键配置 Bitable 消息轮询的定时任务

使用方法:
    python scripts/setup_cron.py --help
    
    # 交互式配置
    python scripts/setup_cron.py --interactive
    
    # 自动配置（需提供所有参数）
    python scripts/setup_cron.py \
        --bot-id "ou_xxx" \
        --app-token "DIDybsDewa1pjnsSFkLcq3eonLh" \
        --table-id-relay "tbllWOJleehmXMVw" \
        --table-id-registry "tblm482wYr6GZIW9" \
        --interval 30
"""

import argparse
import os
import sys
import subprocess
import json
from pathlib import Path


def get_script_dir():
    """获取脚本所在目录"""
    return Path(__file__).parent.absolute()


def get_workspace_dir():
    """获取工作目录"""
    script_dir = get_script_dir()
    return script_dir.parent


def check_openclaw():
    """检查是否安装了 OpenClaw"""
    try:
        result = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def list_cron_jobs():
    """列出当前的定时任务"""
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout
        return f"Error: {result.stderr}"
    except Exception as e:
        return f"Error: {e}"


def add_cron_job(name, every_duration, task):
    """添加定时任务
    
    Args:
        name: 任务名称
        every_duration: 执行间隔，格式如 "30s", "1m", "5m"
        task: 要执行的命令
    """
    try:
        result = subprocess.run(
            ["openclaw", "cron", "add", "--name", name, "--every", every_duration, "--task", task],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def remove_cron_job(name):
    """删除定时任务"""
    try:
        result = subprocess.run(
            ["openclaw", "cron", "remove", "--name", name],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def interactive_setup():
    """交互式配置"""
    print("=" * 60)
    print("🚀 Feishu Bot Relay - 定时任务配置向导")
    print("=" * 60)
    print()
    
    # 检查 OpenClaw
    if not check_openclaw():
        print("❌ 错误：未检测到 OpenClaw")
        print("   请确保已安装 OpenClaw 并添加到 PATH")
        return False
    print("✅ OpenClaw 已安装")
    print()
    
    # 显示当前任务
    print("📋 当前定时任务：")
    print(list_cron_jobs())
    print()
    
    # 输入配置
    print("📝 请输入配置信息：")
    print("-" * 60)
    
    bot_id = input("你的 Bot open_id (格式: ou_xxx): ").strip()
    if not bot_id.startswith("ou_"):
        print(f"⚠️ 警告: open_id 格式可能不正确 (应为 ou_ 开头)")
    
    app_token = input("Bitable app_token [DIDybsDewa1pjnsSFkLcq3eonLh]: ").strip()
    if not app_token:
        app_token = "DIDybsDewa1pjnsSFkLcq3eonLh"
    
    table_id_relay = input("消息队列表 ID [tbllWOJleehmXMVw]: ").strip()
    if not table_id_relay:
        table_id_relay = "tbllWOJleehmXMVw"
    
    table_id_registry = input("Bot注册表 ID [tblm482wYr6GZIW9]: ").strip()
    if not table_id_registry:
        table_id_registry = "tblm482wYr6GZIW9"
    
    interval = input("轮询间隔(秒) [30]: ").strip()
    if not interval:
        interval = "30"
    
    print()
    print("📋 配置确认：")
    print(f"   Bot ID: {bot_id}")
    print(f"   App Token: {app_token[:10]}...")
    print(f"   消息表: {table_id_relay}")
    print(f"   注册表: {table_id_registry}")
    print(f"   轮询间隔: {interval}秒")
    print()
    
    confirm = input("确认创建定时任务? [Y/n]: ").strip().lower()
    if confirm and confirm not in ['y', 'yes']:
        print("❌ 已取消")
        return False
    
    return setup_cron(bot_id, app_token, table_id_relay, table_id_registry, int(interval))


def setup_cron(bot_id, app_token, table_id_relay, table_id_registry, interval=30):
    """配置定时任务"""
    workspace = get_workspace_dir()
    poll_script = workspace / "scripts" / "poll_messages.py"
    
    # 构建任务命令
    task = (
        f"python {poll_script} "
        f"--bot-id '{bot_id}' "
        f"--app-token '{app_token}' "
        f"--table-id-relay '{table_id_relay}' "
        f"--table-id-registry '{table_id_registry}' "
        f"--interval {interval}"
    )
    
    # 生成 duration 格式（OpenClaw --every 参数格式）
    if interval < 60:
        # 每 N 秒
        every_duration = f"{interval}s"
    elif interval < 3600:
        # 每 N 分钟
        minutes = interval // 60
        every_duration = f"{minutes}m"
    else:
        # 每 N 小时
        hours = interval // 3600
        every_duration = f"{hours}h"
    
    job_name = f"feishu-relay-{bot_id[:8]}"
    
    print(f"⏰ 定时任务配置：")
    print(f"   名称: {job_name}")
    print(f"   间隔: {every_duration}")
    print(f"   命令: {task[:80]}...")
    print()
    
    # 先删除已存在的同名任务
    remove_cron_job(job_name)
    
    # 添加新任务
    success, stdout, stderr = add_cron_job(job_name, every_duration, task)
    
    if success:
        print("✅ 定时任务创建成功！")
        print()
        print("📋 验证命令：")
        print(f"   openclaw cron list")
        print()
        print("📝 查看日志：")
        print(f"   openclaw cron logs --name {job_name}")
        return True
    else:
        print("❌ 定时任务创建失败")
        if stderr:
            print(f"   错误: {stderr}")
        return False


def check_existing_relay_jobs():
    """检查是否已有 relay 相关的定时任务"""
    jobs = list_cron_jobs()
    if "relay" in jobs.lower() or "feishu" in jobs.lower():
        return True, jobs
    return False, jobs


def main():
    parser = argparse.ArgumentParser(
        description="配置 Feishu Bot Relay 定时轮询任务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式配置
  python scripts/setup_cron.py --interactive
  
  # 自动配置
  python scripts/setup_cron.py \\
    --bot-id "ou_xxx" \\
    --app-token "xxx" \\
    --table-id-relay "xxx" \\
    --table-id-registry "xxx"
        """
    )
    
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="交互式配置模式")
    parser.add_argument("--bot-id", help="Bot 的 open_id (格式: ou_xxx)")
    parser.add_argument("--app-token", 
                        default="DIDybsDewa1pjnsSFkLcq3eonLh",
                        help="Bitable app_token")
    parser.add_argument("--table-id-relay",
                        default="tbllWOJleehmXMVw",
                        help="消息队列表 ID")
    parser.add_argument("--table-id-registry",
                        default="tblm482wYr6GZIW9",
                        help="Bot注册表 ID")
    parser.add_argument("--interval", type=int, default=30,
                        help="轮询间隔(秒), 默认 30")
    parser.add_argument("--check", action="store_true",
                        help="检查当前定时任务状态")
    
    args = parser.parse_args()
    
    # 检查模式
    if args.check:
        print("📋 当前定时任务状态：")
        print(list_cron_jobs())
        
        exists, jobs = check_existing_relay_jobs()
        if exists:
            print("\n✅ 检测到已有 relay 相关定时任务")
        else:
            print("\n⚠️ 未检测到 relay 定时任务，请运行配置")
        return
    
    # 交互式模式
    if args.interactive:
        success = interactive_setup()
        sys.exit(0 if success else 1)
    
    # 检查必要参数
    if not args.bot_id:
        print("❌ 错误: 必须提供 --bot-id")
        print("   使用 --interactive 进入交互式配置")
        print("   或使用 --help 查看帮助")
        sys.exit(1)
    
    # 检查 OpenClaw
    if not check_openclaw():
        print("❌ 错误：未检测到 OpenClaw")
        print("   请确保已安装 OpenClaw 并添加到 PATH")
        sys.exit(1)
    
    # 执行配置
    success = setup_cron(
        args.bot_id,
        args.app_token,
        args.table_id_relay,
        args.table_id_registry,
        args.interval
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
