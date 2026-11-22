
import React, { useState, useEffect } from 'react';

interface ComplianceResult {
  is_compliant: boolean;
  original_script: string;
  processed_script: string;
  issues: Array<{
    type: string;
    word: string;
    position: string;
    suggestion: string;
  }>;
  replacements: Array<{
    original: string;
    replacement: string;
    type: string;
  }>;
}

const ComplianceStation: React.FC = () => {
  const [script, setScript] = useState('');
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<ComplianceResult | null>(null);
  const [error, setError] = useState('');
  const [rulesOpen, setRulesOpen] = useState(false);
  const [extraRules, setExtraRules] = useState('');

  // 从URL参数读取文案和检测结果（如果从文案生成页面跳转过来）
  useEffect(() => {
    try {
      const saved = localStorage.getItem('compliance_extra_rules');
      if (saved) setExtraRules(String(saved));
    } catch {
      /* ignore */
    }

    const urlParams = new URLSearchParams(window.location.search);
    const scriptParam = urlParams.get('script');
    const resultParam = urlParams.get('result');
    
    if (scriptParam) {
      setScript(decodeURIComponent(scriptParam));
    }
    
    if (resultParam) {
      try {
        const data = JSON.parse(decodeURIComponent(resultParam));
        setResult(data);
      } catch (e) {
        console.error('解析检测结果失败:', e);
        // 如果有文案但没有结果，自动检测
        if (scriptParam) {
          setTimeout(async () => {
            const script = decodeURIComponent(scriptParam);
            setChecking(true);
            try {
              const response = await fetch('/api/compliance/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ script, extra_rules: extraRules || undefined }),
              });
              if (response.ok) {
                const data = await response.json();
                setResult(data);
              }
            } catch (err: any) {
              setError(err.message || '检测失败');
            } finally {
              setChecking(false);
            }
          }, 500);
        }
      }
    } else if (scriptParam) {
      // 只有文案没有结果，自动检测
      setTimeout(async () => {
        const script = decodeURIComponent(scriptParam);
        setChecking(true);
        try {
          const response = await fetch('/api/compliance/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script, extra_rules: extraRules || undefined }),
          });
          if (response.ok) {
            const data = await response.json();
            setResult(data);
          }
        } catch (err: any) {
          setError(err.message || '检测失败');
        } finally {
          setChecking(false);
        }
      }, 500);
    }
  }, []);

  const handleCheck = async () => {
    if (!script.trim()) {
      setError('请输入需要检测的文案');
      return;
    }

    setChecking(true);
    setError('');
    setResult(null);

    try {
      const response = await fetch('/api/compliance/check', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ script, extra_rules: extraRules || undefined }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || '合规检测失败');
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || '检测失败，请重试');
    } finally {
      setChecking(false);
    }
  };

  // 计算健康分数（合规检测分数）
  const calculateHealthScore = () => {
    if (!result) return 0;
    const issueCount = result.issues.length;
    if (issueCount === 0) return 100;
    // 根据问题数量计算分数
    // 0个问题 = 100分
    // 1-2个问题 = 90分
    // 3-5个问题 = 80分
    // 6-10个问题 = 60分
    // 10个以上 = 40分
    if (issueCount <= 2) return 90;
    if (issueCount <= 5) return 80;
    if (issueCount <= 10) return 60;
    return 40;
  };

  const healthScore = calculateHealthScore();
  const isCompliant = result?.is_compliant ?? true;

  return (
    <div className="max-w-6xl mx-auto">
      <header className="mb-10 flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2 uppercase tracking-tight">AI 文案合规监测站</h1>
          <p className="text-slate-400">基于豆包模型的实时合规性与风险拦截系统</p>
        </div>
        <div className="bg-emerald-500/10 border border-emerald-500/20 px-4 py-2 rounded-xl flex items-center space-x-3">
            <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
            <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-widest">引擎: v4.2.0-安全版</span>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 flex flex-col space-y-4">
            <div className="bg-[#131720] border border-white/5 rounded-2xl flex-1 flex flex-col overflow-hidden">
                <div className="px-6 py-4 border-b border-white/5 flex justify-between items-center bg-white/2">
                    <div className="flex items-center space-x-3">
                        <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                        <span className="text-xs font-bold uppercase tracking-widest text-slate-400">输入文案内容</span>
                    </div>
                    <span className="text-[9px] text-slate-600 uppercase tracking-tighter font-black">限制: 2000 字</span>
                </div>
                <textarea 
                    value={script}
                    onChange={(e) => setScript(e.target.value)}
                    className="flex-1 p-8 bg-transparent text-slate-200 outline-none resize-none leading-relaxed text-lg font-medium placeholder:text-slate-700"
                    placeholder="请粘贴或输入您需要检测的文案内容..."
                ></textarea>
                <div className="p-6 border-t border-white/5 flex justify-between items-center">
                    <div className="flex space-x-2">
                        <button className="p-2.5 text-slate-600 hover:text-white transition-all bg-white/2 rounded-lg border border-white/5">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        </button>
                        <button className="p-2.5 text-slate-600 hover:text-white transition-all bg-white/2 rounded-lg border border-white/5">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                        </button>
                    </div>
                    <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => setRulesOpen(true)}
                          className="px-4 py-3 bg-indigo-600/10 border border-indigo-500/20 rounded-xl text-indigo-200 font-black text-[10px] uppercase tracking-widest hover:bg-indigo-600/20 transition-all"
                        >
                          自定义规则
                        </button>
                        <button 
                            onClick={handleCheck}
                            disabled={checking || !script.trim()}
                            className="px-8 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-xl text-white font-black text-xs uppercase tracking-widest shadow-lg shadow-indigo-500/20 hover:scale-105 transition-all flex items-center space-x-3 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {checking ? (
                                <>
                                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    <span>检测中...</span>
                                </>
                            ) : (
                                <>
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                    <span>开始检测</span>
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
            {rulesOpen && (
              <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
                <div className="bg-[#131720] border border-white/10 rounded-2xl p-6 max-w-2xl w-full">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-white font-black text-sm uppercase tracking-widest">合规检测 · 客户自定义规则</h3>
                    <button
                      type="button"
                      onClick={() => setRulesOpen(false)}
                      className="text-slate-400 hover:text-white transition-colors"
                      aria-label="关闭"
                    >
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>

                  <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                    这里填你行业里“不能出现的词/替换成什么/示例案例”。保存后，本页与自动化流程的合规检测都会一起生效。
                  </p>

                  <textarea
                    value={extraRules}
                    onChange={(e) => setExtraRules(e.target.value)}
                    placeholder="示例：\n- 禁用词：XX、YY、ZZ\n- 替换方式：XX→X某X；YY→Y某Y\n- 案例：遇到“XX保证有效”要改成“效果因人而异，建议咨询”\n"
                    className="w-full min-h-[220px] bg-[#0b0e14] border border-white/10 rounded-xl p-4 text-slate-200 outline-none focus:border-indigo-500 placeholder:text-slate-600"
                  />

                  <div className="mt-4 flex gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        setExtraRules('');
                        try { localStorage.setItem('compliance_extra_rules', ''); } catch { /* ignore */ }
                      }}
                      className="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl text-slate-300 text-xs font-black uppercase tracking-widest hover:bg-white/10 transition-all"
                    >
                      清空
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        try { localStorage.setItem('compliance_extra_rules', extraRules); } catch { /* ignore */ }
                        setRulesOpen(false);
                      }}
                      className="flex-1 py-3 bg-indigo-600 rounded-xl text-white text-xs font-black uppercase tracking-widest hover:bg-indigo-700 transition-all"
                    >
                      保存
                    </button>
                  </div>
                </div>
              </div>
            )}
            <div className="flex items-center space-x-6 px-2">
                <div className="flex items-center space-x-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                    <span className="text-[10px] text-slate-600 font-bold uppercase tracking-widest">规则: 最新版本</span>
                </div>
                <div className="flex items-center space-x-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-indigo-500"></div>
                    <span className="text-[10px] text-slate-600 font-bold uppercase tracking-widest">加密: AES-256</span>
                </div>
            </div>
        </div>

        <div className="space-y-6">
            <div className="bg-[#131720] border border-white/5 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-8">
                    <h3 className="font-black uppercase tracking-widest text-[10px] text-indigo-400">风险分析</h3>
                    <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 01-2 2h22a2 2 0 01-2-2v-6a2 2 0 00-2-2h-2a2 2 0 00-2 2v6" /></svg>
                </div>
                
                <div className="flex flex-col items-center mb-10">
                    <div className="relative w-32 h-32 flex items-center justify-center">
                        <svg className="absolute inset-0 w-full h-full transform -rotate-90">
                            <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="6" fill="transparent" className="text-slate-800" />
                            <circle 
                                cx="64" 
                                cy="64" 
                                r="58" 
                                stroke="currentColor" 
                                strokeWidth="6" 
                                fill="transparent" 
                                strokeDasharray="364.42" 
                                strokeDashoffset={364.42 * (1 - healthScore / 100)} 
                                className={healthScore >= 90 ? 'text-emerald-500' : healthScore >= 70 ? 'text-yellow-500' : 'text-rose-500'} 
                            />
                        </svg>
                        <div className="text-center">
                            <p className="text-[9px] text-slate-600 font-black uppercase mb-1">合规检测分数</p>
                            <h2 className="text-4xl font-black text-white">{healthScore}</h2>
                            <span className={`px-2 py-0.5 text-[9px] rounded font-black mt-1 inline-block uppercase tracking-wider ${
                                healthScore >= 90 
                                    ? 'bg-emerald-500/10 text-emerald-400' 
                                    : healthScore >= 80 
                                    ? 'bg-yellow-500/10 text-yellow-400'
                                    : 'bg-rose-500/10 text-rose-400'
                            }`}>
                                {healthScore >= 90 ? '优秀（可发布）' : healthScore >= 80 ? '良好（可发布）' : '需优化'}
                            </span>
                            {healthScore >= 80 && (
                                <p className="text-[8px] text-emerald-400 mt-1">可以发布</p>
                            )}
                        </div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="space-y-2">
                        <div className="flex justify-between text-[9px] font-black uppercase tracking-widest">
                            <span className="text-slate-600">金融风险</span>
                            <span className={result && result.issues.some(i => i.type.includes('finance') || i.type.includes('金融')) ? 'text-rose-400' : 'text-emerald-400'}>
                                {result && result.issues.some(i => i.type.includes('finance') || i.type.includes('金融')) ? '发现风险' : '无风险'}
                            </span>
                        </div>
                        <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                            <div className={`h-full ${
                                result && result.issues.some(i => i.type.includes('finance') || i.type.includes('金融')) ? 'bg-rose-500' : 'bg-emerald-500'
                            }`} style={{ width: result && result.issues.some(i => i.type.includes('finance') || i.type.includes('金融')) ? '85%' : '15%' }}></div>
                        </div>
                    </div>
                    <div className="space-y-2">
                        <div className="flex justify-between text-[9px] font-black uppercase tracking-widest">
                            <span className="text-slate-600">禁用词汇</span>
                            <span className={result && result.issues.length > 0 ? 'text-rose-400' : 'text-emerald-400'}>
                                {result && result.issues.length > 0 ? `发现 ${result.issues.length} 个` : '无问题'}
                            </span>
                        </div>
                        <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                            <div className={`h-full ${
                                result && result.issues.length > 0 ? 'bg-rose-500' : 'bg-emerald-500'
                            }`} style={{ width: result ? `${Math.min(result.issues.length * 20, 100)}%` : '5%' }}></div>
                        </div>
                    </div>
                    <div className="space-y-2">
                        <div className="flex justify-between text-[9px] font-black uppercase tracking-widest">
                            <span className="text-slate-600">平台封禁</span>
                            <span className={result && result.issues.some(i => i.type.includes('platform') || i.type.includes('三方')) ? 'text-rose-400' : 'text-emerald-400'}>
                                {result && result.issues.some(i => i.type.includes('platform') || i.type.includes('三方')) ? '发现风险' : '安全'}
                            </span>
                        </div>
                        <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                            <div className={`h-full ${
                                result && result.issues.some(i => i.type.includes('platform') || i.type.includes('三方')) ? 'bg-rose-500' : 'bg-emerald-500'
                            }`} style={{ width: result && result.issues.some(i => i.type.includes('platform') || i.type.includes('三方')) ? '85%' : '5%' }}></div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-[#131720] border border-white/5 rounded-2xl p-6">
                <h4 className="text-[10px] font-black text-slate-600 uppercase tracking-widest mb-4">检测结果</h4>
                {error && (
                    <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-4 text-rose-400 text-sm mb-4">
                        {error}
                    </div>
                )}
                {result && (
                    <>
                        {/* 前后对比 */}
                        {result.processed_script && result.processed_script !== result.original_script && (
                            <div className="space-y-4 mb-6">
                                <div className="bg-[#1a1f2a] border border-white/10 rounded-xl p-4">
                                    <div className="flex items-center space-x-2 mb-3">
                                        <div className="w-2 h-2 bg-slate-500 rounded-full"></div>
                                        <h5 className="text-xs font-bold text-slate-400 uppercase tracking-widest">原文案（检测前）</h5>
                                    </div>
                                    <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                                        {result.original_script}
                                    </div>
                                </div>
                                <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4">
                                    <div className="flex items-center space-x-2 mb-3">
                                        <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></div>
                                        <h5 className="text-xs font-bold text-emerald-400 uppercase tracking-widest">安全文案（检测后）</h5>
                                    </div>
                                    <div className="text-sm text-white leading-relaxed whitespace-pre-wrap">
                                        {result.processed_script}
                                    </div>
                                </div>
                            </div>
                        )}
                        
                        {/* 问题列表 */}
                        <div className="space-y-3 mb-4">
                            {result.issues.length > 0 ? (
                                result.issues.map((issue, index) => (
                                    <div key={index} className="bg-rose-500/5 border border-rose-500/10 rounded-xl p-4 flex items-start space-x-3">
                                        <div className="mt-0.5 text-rose-500">
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                                        </div>
                                        <div className="flex-1">
                                            <p className="text-[10px] text-rose-400 font-bold uppercase mb-1">
                                                {issue.type}: '{issue.word}'
                                            </p>
                                            <p className="text-[10px] text-slate-500 leading-relaxed font-medium">
                                                {issue.position}，建议替换为：{issue.suggestion}
                                            </p>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4 flex items-start space-x-3">
                                    <div className="mt-0.5 text-emerald-500">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                                    </div>
                                    <div>
                                        <p className="text-[10px] text-emerald-400 font-bold uppercase mb-1">合规通过</p>
                                        <p className="text-[10px] text-slate-500 leading-relaxed font-medium">未发现合规问题，文案可以安全使用。</p>
                                    </div>
                                </div>
                            )}
                        </div>
                        
                        {/* 操作按钮 */}
                        <div className="flex space-x-3">
                            <button 
                                onClick={() => {
                                    if (result.processed_script) {
                                        navigator.clipboard.writeText(result.processed_script);
                                    }
                                }}
                                className="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-white/10 transition-all flex items-center justify-center space-x-2"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                <span>复制安全文案</span>
                            </button>
                            <button 
                                onClick={() => {
                                    // 保存处理后的安全文案到 localStorage，供素材生产和成品素材使用
                                    const text = result.processed_script || result.original_script || '';
                                    localStorage.setItem('current_script', text);
                                    alert('安全文案已保存，可在素材生产和成品素材中使用');
                                }}
                                className="flex-1 py-3 bg-sky-600/10 border border-sky-500/20 rounded-xl text-[10px] font-black uppercase tracking-widest text-sky-400 hover:bg-sky-600/20 transition-all"
                            >
                                使用
                            </button>
                            {healthScore >= 80 && (
                                <button 
                                    onClick={() => {
                                        // 可以在这里添加发布逻辑
                                        alert('文案合规，可以发布！');
                                    }}
                                    className="flex-1 py-3 bg-emerald-600/10 border border-emerald-500/20 rounded-xl text-[10px] font-black uppercase tracking-widest text-emerald-400 hover:bg-emerald-600/20 transition-all"
                                >
                                    可以发布
                                </button>
                            )}
                        </div>
                    </>
                )}
                {!result && !error && (
                    <div className="text-slate-600 text-sm text-center py-8">
                        <p>检测结果将显示在这里</p>
                    </div>
                )}
            </div>
        </div>
      </div>
    </div>
  );
};

export default ComplianceStation;

