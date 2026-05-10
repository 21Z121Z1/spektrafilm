#!/usr/bin/env python3
import os
import sys
import subprocess
import venv

def main():
    print("========================================")
    print("    Spektrafilm 一键启动脚本 (macOS)    ")
    print("========================================")
    
    # 1. 切换工作目录到脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"[*] 当前工作目录: {os.getcwd()}")
    
    # 2. 检查 Python 版本 (需强制为 3.13.x 因为项目依赖)
    if sys.version_info.major != 3 or sys.version_info.minor != 13:
        import shutil
        py313_path = shutil.which("python3.13")
        if py313_path:
            print(f"[*] 当前使用 {sys.version_info.major}.{sys.version_info.minor}，发现 Python 3.13，尝试重新启动脚本...")
            os.execv(py313_path, ["python3.13", __file__] + sys.argv[1:])
        else:
            print("\n[错误] 环境不满足条件:")
            print(f"项目要求 Python 3.13.x，但当前脚本使用的是 {sys.version_info.major}.{sys.version_info.minor}")
            print(f"当前 Python 解释器路径: {sys.executable}")
            print("请在系统上安装 Python 3.13，并确保其在环境变量中可用。")
            input("\n按回车键退出...")
            sys.exit(1)
        
    print(f"[*] Python 版本检查通过: {sys.version_info.major}.{sys.version_info.minor}")

    # 3. 检查并创建虚拟环境
    venv_dir = os.path.join(script_dir, ".venv")
    is_new_venv = False
    if not os.path.exists(venv_dir):
        print("[*] 正在创建虚拟环境 `.venv` ...")
        # 使用 subprocess 调用模块，以保证 macOS 下正确使用符号链接而非复制
        subprocess.check_call([sys.executable, "-m", "venv", ".venv"])
        print("[*] 虚拟环境创建完成.")
        is_new_venv = True
    else:
        print("[*] 虚拟环境已存在, 跳过创建步骤.")
        
    # 定义可执行文件路径
    pip_exe = os.path.join(venv_dir, "bin", "pip")
    py_exe = os.path.join(venv_dir, "bin", "python")
    app_exe = os.path.join(venv_dir, "bin", "spektrafilm")
    
    if not os.path.exists(pip_exe):
        print(f"\n[错误] 在虚拟环境中找不到 pip: {pip_exe}")
        input("\n按回车键退出...")
        sys.exit(1)

    # 4. 安装/更新项目依赖 (pip install -e .)
    if is_new_venv or not os.path.exists(app_exe):
        print("[*] 未发现已安装的包，正在安装依赖 (pip install -e .) ...\n此过程可能需要几分钟。")
        try:
            subprocess.check_call([pip_exe, "install", "-e", "."])
        except subprocess.CalledProcessError as e:
            print("\n[错误] 安装依赖失败！")
            input("\n按回车键退出...")
            sys.exit(1)
        print("[*] 依赖就绪.")
    else:
        print("[*] 环境包似乎已安装, 跳过依赖安装流程以加速启动.")

    # 5. 拉起应用
    if not os.path.exists(app_exe):
        print(f"\n[错误] 应用程序可执行文件在此处找不到: {app_exe}")
        print("这通常是因为 package 没被正确安装导致的，请重试。")
        input("\n按回车键退出...")
        sys.exit(1)
        
    print("\n[*] 正在启动 Spektrafilm GUI ...")
    print("========================================")
    print("💡 提示 (Mac): ")
    print("1. 如果这是首次安装启动，底层引擎 (Numba) 正在进行核心处理函数的离线编译 (AOT/JIT) \n   这个过程可能需要等待 1 到 3 分钟才能弹出窗口，请耐心等待！")
    print("2. 窗口可能没有抢占焦点，请留意屏幕下方程序坞 (Dock) 最右侧是否出现了一个新的 【Python】 图标！")
    print("========================================\n")
    
    try:
        subprocess.run([app_exe])
    except Exception as e:
        print(f"\n[错误] 启动应用程序失败: {e}")
        input("\n按回车键退出...")

if __name__ == '__main__':
    main()
