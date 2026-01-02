import os
import sys

def check_env_vars():
    print("=" * 60)
    print("环境变量代理配置检查")
    print("=" * 60)
    
    proxy_vars = [
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", 
        "http_proxy", "https_proxy", "all_proxy",
        "NO_PROXY", "no_proxy"
    ]
    
    found = False
    for var in proxy_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ 发现环境变量: {var} = {value}")
            found = True
        else:
            print(f"⚪ 未设置: {var}")
            
    print("-" * 60)
    if found:
        print("结论: 系统环境变量中存在代理设置。")
        print("如果这些设置不正确或指向了错误的端口，可能会导致软件无法连接网络。")
        print("云登浏览器可能会继承这些环境变量。")
    else:
        print("结论: 系统环境变量中【没有】显式的代理设置。")
        print("云登浏览器的'本机网络'连接失败不是由环境变量强制代理造成的。")
    print("=" * 60)

if __name__ == "__main__":
    check_env_vars()
