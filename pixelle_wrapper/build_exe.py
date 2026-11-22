"""
打包 FastAPI Wrapper 为 EXE
使用 PyInstaller
"""
import os
import sys
import shutil
from pathlib import Path

def build_exe():
    """打包为 EXE"""
    print("=" * 60)
    print("Pixelle-Video Wrapper EXE 打包工具")
    print("=" * 60)
    
    # 检查 PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("\n[错误] PyInstaller 未安装")
        print("请运行: pip install pyinstaller")
        return False
    
    # 获取当前目录
    current_dir = Path(__file__).parent
    main_file = current_dir / "main.py"
    
    if not main_file.exists():
        print(f"\n[错误] 找不到主文件: {main_file}")
        return False
    
    # 清理旧的构建文件
    print("\n[清理] 清理旧的构建文件...")
    for dir_name in ["build", "dist", "__pycache__"]:
        dir_path = current_dir / dir_name
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"   已删除: {dir_name}/")
    
    # 清理 .spec 文件
    spec_file = current_dir / "main.spec"
    if spec_file.exists():
        spec_file.unlink()
        print(f"   已删除: main.spec")
    
    # PyInstaller 命令
    print("\n[打包] 开始打包...")
    print("   这可能需要几分钟，请耐心等待...\n")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=PixelleWrapper",
        "--onefile",  # 单文件模式
        "--console",  # 显示控制台
        "--clean",
        "--noconfirm",
        # 隐藏导入
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=uvicorn.lifespan.off",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.http.h11_impl",
        "--hidden-import=uvicorn.protocols.http.httptools_impl",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.loops.asyncio",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=fastapi",
        "--hidden-import=pydantic",
        "--hidden-import=multipart",
        # 添加数据文件（如果需要）
        # "--add-data=config;config",
        str(main_file)
    ]
    
    # 执行打包
    import subprocess
    result = subprocess.run(cmd, cwd=current_dir)
    
    if result.returncode == 0:
        exe_path = current_dir / "dist" / "PixelleWrapper.exe"
        if exe_path.exists():
            print("\n" + "=" * 60)
            print("[成功] 打包成功！")
            print("=" * 60)
            print(f"\n[文件] EXE 文件位置: {exe_path}")
            print(f"   文件大小: {exe_path.stat().st_size / 1024 / 1024:.2f} MB")
            print("\n[运行] 运行方式:")
            print(f"   双击运行: {exe_path}")
            print(f"   或命令行: {exe_path}")
            return True
        else:
            print("\n[错误] 打包完成但找不到 EXE 文件")
            return False
    else:
        print("\n[错误] 打包失败")
        return False

if __name__ == "__main__":
    success = build_exe()
    if not success:
        sys.exit(1)

