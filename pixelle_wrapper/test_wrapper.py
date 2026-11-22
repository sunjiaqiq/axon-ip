"""
测试 Pixelle-Video Wrapper 服务
用于验证 Wrapper 是否正常工作
"""
import requests
import time
import sys

BASE_URL = "http://127.0.0.1:38887"

def test_health():
    """测试健康检查接口"""
    print("=" * 60)
    print("测试 1: 健康检查")
    print("=" * 60)
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")
        if response.status_code == 200:
            print("✅ 健康检查通过")
            return True
        else:
            print("❌ 健康检查失败")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务")
        print("   请确保 PixelleWrapper.exe 正在运行")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def test_set_key():
    """测试设置 API Key"""
    print("\n" + "=" * 60)
    print("测试 2: 设置 API Key")
    print("=" * 60)
    try:
        # 使用测试 Key（实际使用时需要真实的 Key）
        test_key = "test_key_12345"
        response = requests.post(
            f"{BASE_URL}/api/set_key",
            json={"api_key": test_key},
            timeout=5
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")
        if response.status_code == 200:
            print("✅ API Key 设置成功")
            return True
        else:
            print("❌ API Key 设置失败")
            return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def test_set_text():
    """测试设置文案"""
    print("\n" + "=" * 60)
    print("测试 3: 设置文案")
    print("=" * 60)
    try:
        test_text = "这是一段测试文案，用于验证 Wrapper 服务是否正常工作。"
        response = requests.post(
            f"{BASE_URL}/api/text",
            json={"text": test_text},
            timeout=5
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")
        if response.status_code == 200:
            print("✅ 文案设置成功")
            return True
        else:
            print("❌ 文案设置失败")
            return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def test_upload_avatar():
    """测试上传头像（需要提供图片文件）"""
    print("\n" + "=" * 60)
    print("测试 4: 上传头像（可选）")
    print("=" * 60)
    print("提示: 此测试需要提供图片文件路径")
    print("      如果跳过此测试，可以手动在 UI 中测试")
    return True

def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Pixelle-Video Wrapper 服务测试")
    print("=" * 60)
    print(f"\n服务地址: {BASE_URL}")
    print("\n请确保 PixelleWrapper.exe 正在运行！")
    print("如果未运行，请先启动: PixelleWrapper.exe")
    print("\n按回车键开始测试...")
    input()
    
    results = []
    
    # 测试 1: 健康检查
    results.append(("健康检查", test_health()))
    
    # 如果健康检查失败，停止测试
    if not results[0][1]:
        print("\n" + "=" * 60)
        print("❌ 服务未运行，请先启动 PixelleWrapper.exe")
        print("=" * 60)
        sys.exit(1)
    
    # 测试 2: 设置 API Key
    results.append(("设置 API Key", test_set_key()))
    
    # 测试 3: 设置文案
    results.append(("设置文案", test_set_text()))
    
    # 测试 4: 上传头像（可选）
    results.append(("上传头像", test_upload_avatar()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n🎉 所有测试通过！Wrapper 服务正常工作。")
        print("\n下一步: 可以在主 UI 中测试完整流程")
    else:
        print("\n⚠️ 部分测试失败，请检查服务日志")
    
    print("\n按回车键退出...")
    input()

if __name__ == "__main__":
    main()









