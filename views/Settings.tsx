
import React, { useState, useEffect } from 'react';
import { CUSTOMER_AUTH_KEY, CUSTOMER_AUTH_USER_KEY } from '../components/StartupLoginGate';

const Icons = {
  Key: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>,
  Check: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>,
  X: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>,
  ExternalLink: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>,
  Browser: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>,
};

interface APIKeyConfig {
  id: string;
  name: string;
  key: string;
  url: string;
  getKeyUrl: string;
  status: 'unknown' | 'testing' | 'connected' | 'failed';
  statusMessage: string;
}

const Settings: React.FC = () => {
  const [apiKeys, setApiKeys] = useState<APIKeyConfig[]>([
    {
      id: 'qwen',
      name: '通义千问（qwen3.8-max）',
      key: '',
      url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      getKeyUrl: 'https://bailian.console.aliyun.com/cn-beijing/?tab=model#/api-key',
      status: 'unknown',
      statusMessage: '未测试'
    },
    {
      id: 'siliconflow',
      name: '硅基流动（GLM-5.3）',
      key: '',
      url: 'https://api.siliconflow.cn/v1',
      getKeyUrl: 'https://siliconflow.cn/',
      status: 'unknown',
      statusMessage: '未测试'
    },
    {
      id: 'doubao',
      name: '豆包1.8（火山引擎）',
      key: '',
      url: 'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
      getKeyUrl: 'https://www.volcengine.com/product/ark',
      status: 'unknown',
      statusMessage: '未测试'
    },
    {
      id: 'runninghub',
      name: 'RunningHub',
      key: '',
      url: '',
      getKeyUrl: 'https://www.runninghub.cn/enterprise-api/consumerApi',
      status: 'unknown',
      statusMessage: '未测试'
    }
  ]);

  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [browserStatus, setBrowserStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  type BrowserPlatformId = 'douyin' | 'kuaishou' | 'xhs' | 'sph';
  const BROWSER_PLATFORM_LABEL: Record<BrowserPlatformId, string> = {
    douyin: '抖音',
    kuaishou: '快手',
    xhs: '小红书',
    sph: '视频号',
  };
  const [selectedPlatform, setSelectedPlatform] = useState<BrowserPlatformId>('douyin');

  // 加载配置
  useEffect(() => {
    loadConfig();
    checkBrowserStatus();
    // 每3秒检查一次浏览器状态
    const interval = setInterval(checkBrowserStatus, 3000);
    return () => clearInterval(interval);
  }, [selectedPlatform]);

  const loadConfig = async () => {
    try {
      const response = await fetch('/api/config/get');
      if (response.ok) {
        const config = await response.json();
        setApiKeys(prev => prev.map(item => {
          let key = '';
          if (item.id === 'qwen' && config.llm) {
            key = config.llm.api_key || '';
          } else if (item.id === 'runninghub' && config.comfyui) {
            key = config.comfyui.runninghub_api_key || '';
          } else if (item.id === 'siliconflow' && config.siliconflow) {
            key = config.siliconflow.api_key || '';
          } else if (item.id === 'doubao' && config.doubao) {
            key = config.doubao.api_key || '';
          }
          return { ...item, key };
        }));
      }
    } catch (error) {
      console.error('加载配置失败:', error);
    }
  };

  const handleKeyChange = (id: string, value: string) => {
    setApiKeys(prev => prev.map(item => 
      item.id === id 
        ? { ...item, key: value, status: 'unknown', statusMessage: '未测试' }
        : item
    ));
  };

  const handleGetKey = (url: string) => {
    window.open(url, '_blank');
  };

  const testConnection = async (id: string) => {
    const apiKey = apiKeys.find(k => k.id === id);
    if (!apiKey || !apiKey.key.trim()) {
      alert('请先填写API Key');
      return;
    }

    setApiKeys(prev => prev.map(item => 
      item.id === id 
        ? { ...item, status: 'testing', statusMessage: '正在连接，失败会自动重试（最多10次）…' }
        : item
    ));

    // 后端最多重试 10 次，前端保持“测试中”，不要提前显示失败
    const controller = new AbortController();
    const watchdog = window.setTimeout(() => controller.abort(), 180000);

    try {
      const response = await fetch('/api/config/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          api_type: id,
          api_key: apiKey.key,
          api_url: apiKey.url
        }),
        signal: controller.signal,
      });

      if (response.ok) {
        const result = await response.json();
        setApiKeys(prev => prev.map(item => 
          item.id === id 
            ? { 
                ...item, 
                status: result.success ? 'connected' : 'failed',
                statusMessage: result.message || (result.success ? '连接成功' : '连接失败，请查看具体原因')
              }
            : item
        ));
      } else {
        let detail = `服务器返回 HTTP ${response.status}`;
        try {
          const errBody = await response.json();
          if (errBody?.detail || errBody?.message) {
            detail = String(errBody.detail || errBody.message);
          }
        } catch {
          // ignore
        }
        setApiKeys(prev => prev.map(item => 
          item.id === id 
            ? { ...item, status: 'failed', statusMessage: `测试接口异常：${detail}` }
            : item
        ));
      }
    } catch (error: any) {
      const aborted = error?.name === 'AbortError';
      setApiKeys(prev => prev.map(item => 
        item.id === id 
          ? {
              ...item,
              status: 'failed',
              statusMessage: aborted
                ? '连接超时：已等待较长时间仍无结果，请检查本机网络或稍后重试'
                : `本机网络错误：无法访问本机后端（${String(error?.message || error)}）`,
            }
          : item
      ));
    } finally {
      window.clearTimeout(watchdog);
    }
  };

  const testAllConnections = async () => {
    setIsTesting(true);
    for (const apiKey of apiKeys) {
      if (apiKey.key.trim()) {
        await testConnection(apiKey.id);
        // 等待一下再测试下一个
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    setIsTesting(false);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const config: any = {};
      
      // 构建配置对象
      apiKeys.forEach(apiKey => {
        if (apiKey.id === 'qwen') {
          config.llm = {
            api_key: apiKey.key,
            base_url: apiKey.url,
            model: 'qwen3.8-max',
          };
        } else if (apiKey.id === 'runninghub') {
          config.comfyui = {
            runninghub_api_key: apiKey.key
          };
        } else if (apiKey.id === 'siliconflow') {
          config.siliconflow = {
            api_key: apiKey.key,
            api_base: apiKey.url,
            model: 'zai-org/GLM-5.3',
          };
        } else if (apiKey.id === 'doubao') {
          config.doubao = {
            api_key: apiKey.key,
            api_url: apiKey.url
          };
        }
      });

      const response = await fetch('/api/config/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config)
      });

      if (response.ok) {
        // 保存成功后自动测试所有连接
        await testAllConnections();
        alert('配置保存成功！已自动测试所有连接。');
      } else {
        alert('保存失败，请稍后重试');
      }
    } catch (error) {
      console.error('保存配置失败:', error);
      alert('保存失败，请检查网络连接');
    } finally {
      setIsSaving(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <Icons.Check className="text-emerald-400" />;
      case 'failed':
        return <Icons.X className="text-rose-400" />;
      case 'testing':
        return <svg className="w-5 h-5 text-amber-400 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>;
      default:
        return null;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected':
        return 'border-emerald-500/50 bg-emerald-500/10';
      case 'failed':
        return 'border-rose-500/50 bg-rose-500/10';
      case 'testing':
        return 'border-amber-500/50 bg-amber-500/10';
      default:
        return 'border-white/10 bg-white/5';
    }
  };

  const checkBrowserStatus = async () => {
    try {
      const response = await fetch('/api/browser/status');
      if (response.ok) {
        const result = await response.json();
        const isConnected = result.initialized && (result.platforms?.[selectedPlatform] || false);
        setBrowserStatus(isConnected ? 'connected' : 'disconnected');
      } else {
        setBrowserStatus('disconnected');
      }
    } catch (error) {
      console.error('检查浏览器状态失败:', error);
      setBrowserStatus('disconnected');
    }
  };

  const handleLogin = async () => {
    setIsLoggingIn(true);
    setBrowserStatus('connecting');
    
    try {
      const response = await fetch('/api/browser/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          platform: selectedPlatform
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        setBrowserStatus('connected');
        console.log('浏览器登录页面已打开:', result);
      } else {
        setBrowserStatus('disconnected');
        let detail = '';
        try {
          const err = await response.json();
          detail = err?.detail ? `\n\n后端返回：${String(err.detail).slice(0, 500)}` : '';
        } catch {
          // ignore non-json
        }
        alert(`打开登录页面失败，请检查后端服务${detail}`);
      }
    } catch (error) {
      setBrowserStatus('disconnected');
      console.error('登录失败:', error);
      alert('连接后端服务失败');
    } finally {
      setIsLoggingIn(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <header className="mb-10">
        <h1 className="text-3xl font-bold text-white mb-2">系统设置</h1>
        <p className="text-slate-400 font-medium">AI模型API密钥配置与管理</p>
      </header>

      <div className="space-y-6">
        {/* 浏览器登录部分 */}
        <section className="bg-[#131720] border border-white/5 rounded-2xl p-8">
          <h3 className="text-lg font-bold text-white mb-6 flex items-center space-x-3">
            <Icons.Browser />
            <span>浏览器登录</span>
          </h3>
          <div className="space-y-6">
            <div className="flex items-center justify-between p-5 bg-white/2 rounded-2xl border border-white/5">
              <div className="flex-1">
                <h4 className="text-xs font-black text-white uppercase tracking-widest mb-1">浏览器登录状态</h4>
                <p className="text-[10px] text-slate-600 font-bold uppercase">
                  {browserStatus === 'connected' ? '已连接 - 浏览器已打开并保持登录状态' : 
                   browserStatus === 'connecting' ? '连接中...' : 
                   '未连接 - 请点击登录按钮打开浏览器'}
                </p>
                <p className="text-[9px] text-slate-500 mt-2">
                  系统使用专用 Chrome（与分发中心发布共用同一用户数据目录），抖音 / 快手 / 小红书网页端在此登录；视频号将打开微信相关页，需在 PC 微信侧保持可用。
                </p>
              </div>
              <div className="ml-4">
                <div className={`w-4 h-4 rounded-full ${
                  browserStatus === 'connected' ? 'bg-green-500' : 
                  browserStatus === 'connecting' ? 'bg-yellow-500 animate-pulse' : 
                  'bg-red-500'
                }`}></div>
              </div>
            </div>
            <div className="space-y-4">
              {/* 平台选择（与分发中心一致：抖音、快手、小红书、视频号） */}
              <div className="grid grid-cols-2 gap-3">
                {(['douyin', 'kuaishou', 'xhs', 'sph'] as BrowserPlatformId[]).map((pid) => (
                  <button
                    key={pid}
                    type="button"
                    onClick={() => setSelectedPlatform(pid)}
                    className={`py-3 rounded-xl font-bold text-sm uppercase tracking-widest transition-all ${
                      selectedPlatform === pid
                        ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20'
                        : 'bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10'
                    }`}
                  >
                    {BROWSER_PLATFORM_LABEL[pid]}
                  </button>
                ))}
              </div>
              
              {/* 登录按钮 */}
              <button
                onClick={handleLogin}
                disabled={isLoggingIn || browserStatus === 'connecting'}
                className="w-full py-4 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-xl text-white font-bold text-sm uppercase tracking-widest shadow-xl shadow-indigo-500/20 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center space-x-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoggingIn ? (
                  <>
                    <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>正在打开浏览器...</span>
                  </>
                ) : (
                  <>
                    <Icons.Browser />
                    <span>打开浏览器登录 {BROWSER_PLATFORM_LABEL[selectedPlatform]}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </section>

        {/* API密钥配置区域 */}
        <section className="bg-[#131720] border border-white/5 rounded-2xl p-8">
          <h3 className="text-lg font-bold text-white mb-6 flex items-center space-x-3">
            <Icons.Key />
            <span>AI模型API密钥配置</span>
          </h3>
          
          <div className="space-y-6">
            {apiKeys.map((apiKey) => (
              <div 
                key={apiKey.id} 
                className={`border rounded-xl p-6 transition-all ${getStatusColor(apiKey.status)}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3 mb-2">
                      <h4 className="text-base font-semibold text-white">{apiKey.name}</h4>
                      {getStatusIcon(apiKey.status)}
                    </div>
                    {apiKey.url && (
                      <p className="text-xs text-slate-500 mb-2">
                        API地址：<span className="text-slate-400 font-mono">{apiKey.url}</span>
                      </p>
                    )}
                    <p className={`text-xs font-medium break-words whitespace-pre-wrap pr-2 ${
                      apiKey.status === 'connected' ? 'text-emerald-400' :
                      apiKey.status === 'failed' ? 'text-rose-400' :
                      apiKey.status === 'testing' ? 'text-amber-400' :
                      'text-slate-500'
                    }`}>
                      {apiKey.statusMessage}
                    </p>
                  </div>
                  <button
                    onClick={() => handleGetKey(apiKey.getKeyUrl)}
                    className="ml-4 px-4 py-2 bg-indigo-600/20 border border-indigo-500/50 text-indigo-400 rounded-lg text-xs font-medium hover:bg-indigo-600/30 transition-all flex items-center space-x-2 flex-shrink-0"
                  >
                    <Icons.ExternalLink />
                    <span>获取Key</span>
                  </button>
                </div>
                
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-2">
                      API密钥
                    </label>
                    <div className="flex space-x-3">
                      <input
                        type="password"
                        value={apiKey.key}
                        onChange={(e) => handleKeyChange(apiKey.id, e.target.value)}
                        placeholder={`请输入${apiKey.name}的API密钥`}
                        className="flex-1 bg-[#1a1f2a] border border-white/10 rounded-lg px-4 py-3 text-sm text-slate-300 outline-none focus:border-indigo-500 font-mono"
                      />
                      <button
                        onClick={() => testConnection(apiKey.id)}
                        disabled={!apiKey.key.trim() || apiKey.status === 'testing'}
                        className="px-6 py-3 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {apiKey.status === 'testing' ? '测试中...' : '测试连接'}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 保存 / 切换账号 */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4">
          <button
            type="button"
            onClick={() => {
              if (!confirm('确定切换账号？将返回启动登录界面。')) return;
              window.localStorage.removeItem(CUSTOMER_AUTH_KEY);
              window.localStorage.removeItem(CUSTOMER_AUTH_USER_KEY);
              window.location.reload();
            }}
            className="rounded-xl border border-white/10 bg-white/5 px-6 py-3 text-sm font-medium text-slate-300 hover:bg-white/10"
          >
            切换账号
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || isTesting}
            className="px-10 py-4 bg-indigo-600 text-white rounded-xl text-sm font-bold shadow-xl shadow-indigo-500/20 hover:bg-indigo-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? '保存中...' : isTesting ? '测试中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings;
