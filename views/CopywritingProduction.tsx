
import React, { useState } from 'react';

interface PersonaConfig {
  consumptionRange: string; // 产品消费金额区间
  wechatId: string; // 微信号
  companyName: string; // 公司/团队名字
  targetMarket: string; // 目标客户群体（全国/区域）
  coreSolution: string; // 核心产品或服务解决的需求
  companyAddress: string; // 公司地址
  productYears: string; // 公司产品几年了
  productAdvantages: string; // 产品的优势
  other: string; // 其他
  /** 截流搜索词轮换，/ 或逗号分隔 */
  industryKeywords: string;
  /** 素材评论风格示例（供豆包） */
  commentExample: string;
  /** 意向词补充，与内置词合并；/ 或逗号分隔 */
  intentKeywords: string;
}

interface ScriptResult {
  original_script: {
    full_script: string;
    hook: string;
    problem: string;
    solution: string;
    cta: string;
  };
  rewritten_script: {
    hook: string;
    problem: string;
    solution: string;
    cta: string;
    full_script: string;
  };
  similarity?: {
    repetition_rate: number; // 重复率
    similarity_rate: number; // 相似度
    deduplication_rate: number; // 去重率
  };
}

const EMPTY_PERSONA: PersonaConfig = {
  consumptionRange: '',
  wechatId: '',
  companyName: '',
  targetMarket: '',
  coreSolution: '',
  companyAddress: '',
  productYears: '',
  productAdvantages: '',
  other: '',
  industryKeywords: '',
  commentExample: '',
  intentKeywords: '',
};

const CopywritingProduction: React.FC = () => {
  const [input, setInput] = useState('');
  const [inputType, setInputType] = useState<'text' | 'link' | 'keyword'>('text');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<ScriptResult | null>(null);
  const [error, setError] = useState('');
  const [showPersonaModal, setShowPersonaModal] = useState(false);
  const [personaConfig, setPersonaConfig] = useState<PersonaConfig>({ ...EMPTY_PERSONA });
  const [generateSuccess, setGenerateSuccess] = useState(false);

  const presetPrompts = [
    '短视频三秒引流',
    '短视频的生成爆款文案的方式'
  ];

  // 从 localStorage 加载人设配置（合并缺省键，兼容旧版保存）
  React.useEffect(() => {
    const saved = localStorage.getItem('personaConfig');
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as Partial<PersonaConfig>;
        setPersonaConfig({ ...EMPTY_PERSONA, ...parsed });
      } catch (e) {
        console.error('Failed to load persona config:', e);
      }
    }
  }, []);

  const handleGenerate = async (isOptimize: boolean = false) => {
    // 继续优化时，需要确保有结果和输入
    if (isOptimize) {
      if (!result || !input.trim()) {
        setError('请先生成文案后再继续优化');
        return;
      }
    } else {
      if (!input.trim()) return;
    }
    
    setGenerating(true);
    setGenerateSuccess(false);
    if (!isOptimize) {
      setResult(null);
    }
    setError('');
    
    try {
      if (inputType === 'link') {
        // 调用链接解析API，传递人设配置
        const response = await fetch('/api/copywriting/parse_link', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ 
            link: input,
            // 文案改写只使用指定字段
            persona_config: {
              companyName: personaConfig.companyName,
              targetMarket: personaConfig.targetMarket,
              coreSolution: personaConfig.coreSolution,
              productYears: personaConfig.productYears,
              productAdvantages: personaConfig.productAdvantages,
              other: personaConfig.other
            },
            optimize: isOptimize // 是否继续优化
          }),
        });
        
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || '链接解析失败');
        }
        
        const data = await response.json();
        // 确保数据结构正确
        if (data.original_script && data.rewritten_script) {
          setResult({
            original_script: {
              full_script: data.original_script.full_script || data.original_script.full_text || '',
              hook: data.original_script.hook || '',
              problem: data.original_script.problem || '',
              solution: data.original_script.solution || '',
              cta: data.original_script.cta || ''
            },
            rewritten_script: data.rewritten_script,
            similarity: data.similarity
          });
          setGenerateSuccess(true);
        } else {
          setResult(data);
          setGenerateSuccess(true);
        }
        setGenerating(false);
      } else if (inputType === 'keyword') {
        // 关键词搜索（暂时模拟）
        setTimeout(() => {
          setResult({
            original_script: {
              full_script: '',
              hook: '',
              problem: '',
              solution: '',
              cta: ''
            },
            rewritten_script: {
              hook: `针对"${input}"行业的爆款开头`,
              problem: `这个行业的核心痛点`,
              solution: `专业的解决方案`,
              cta: `立即行动，获取更多信息`,
              full_script: `针对"${input}"行业的短视频三秒引流文案...`
            },
            similarity: {
              repetition_rate: 0,
              similarity_rate: 0,
              deduplication_rate: 100
            }
          });
          setGenerateSuccess(true);
          setGenerating(false);
        }, 2000);
      } else {
        // 文案优化（暂时模拟）
        setTimeout(() => {
          setResult({
            original_script: {
              full_script: input,
              hook: input.split('。')[0] || input,
              problem: '',
              solution: '',
              cta: ''
            },
            rewritten_script: {
              hook: `${input} - 优化版本`,
              problem: '',
              solution: '',
              cta: '',
              full_script: `${input} - 经过AI优化，增加了吸引力和转化率...`
            },
            similarity: {
              repetition_rate: 0,
              similarity_rate: 0,
              deduplication_rate: 100
            }
          });
          setGenerateSuccess(true);
          setGenerating(false);
        }, 2000);
      }
    } catch (err: any) {
      setError(err.message || '生成失败，请重试');
      setGenerateSuccess(false);
      setGenerating(false);
    }
  };

  const handlePresetClick = (prompt: string) => {
    setInput(prompt);
    setInputType('keyword');
  };

  return (
    <div className="max-w-6xl mx-auto">
      <header className="mb-10 flex justify-between items-center">
            <div>
                <nav className="flex items-center space-x-2 text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
                    <span>Copy Tools</span>
                    <span className="text-slate-700">/</span>
            <span className="text-indigo-400">AI Writer</span>
                </nav>
          <h1 className="text-3xl font-bold text-white mb-2 uppercase tracking-tight">AI 文案生成与优化</h1>
          <p className="text-slate-400">支持链接解析、行业搜索、文案优化与二创</p>
        </div>
        <button
          onClick={() => setShowPersonaModal(true)}
          className="px-6 py-3 bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-indigo-600/20 transition-all flex items-center space-x-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
          <span>配置人设</span>
        </button>
      </header>

      {/* 人设配置弹窗 */}
      {showPersonaModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#131720] border border-white/10 rounded-2xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-white uppercase tracking-tight">配置人设</h2>
              <button
                onClick={() => setShowPersonaModal(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  贵公司产品消费金额通常在哪个区间?
                </label>
                <input
                  type="text"
                  value={personaConfig.consumptionRange}
                  onChange={(e) => setPersonaConfig({...personaConfig, consumptionRange: e.target.value})}
                  placeholder="如: 100-500"
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500"
                />
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  微信号具体 ID是什么?
                </label>
                <input
                  type="text"
                  value={personaConfig.wechatId}
                  onChange={(e) => setPersonaConfig({...personaConfig, wechatId: e.target.value})}
                  placeholder="如: jgksdf111"
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500"
                />
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  公司/团队名字?
                </label>
                <input
                  type="text"
                  value={personaConfig.companyName}
                  onChange={(e) => setPersonaConfig({...personaConfig, companyName: e.target.value})}
                  placeholder="如: 嘿嘿"
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500"
                />
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  目标客户群体主要是全国性还是区域性业务?
                </label>
                <select
                  value={personaConfig.targetMarket}
                  onChange={(e) => setPersonaConfig({...personaConfig, targetMarket: e.target.value})}
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500"
                >
                  <option value="">请选择</option>
                  <option value="全国">全国</option>
                  <option value="区域">区域</option>
                </select>
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  核心产品或服务主要解决客户哪些具体需求?
                </label>
                <textarea
                  value={personaConfig.coreSolution}
                  onChange={(e) => setPersonaConfig({...personaConfig, coreSolution: e.target.value})}
                  placeholder="如: 我们可以帮助客户解决获客懒的问题"
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500 min-h-[60px]"
                />
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  公司地址在哪里?
                </label>
                <input
                  type="text"
                  value={personaConfig.companyAddress}
                  onChange={(e) => setPersonaConfig({...personaConfig, companyAddress: e.target.value})}
                  placeholder="如: 山东济南"
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500"
                />
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  公司产品几年了?
                </label>
                <input
                  type="text"
                  value={personaConfig.productYears}
                  onChange={(e) => setPersonaConfig({...personaConfig, productYears: e.target.value})}
                  placeholder="如: 5年"
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500"
                />
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  产品的优势?
                </label>
                <textarea
                  value={personaConfig.productAdvantages}
                  onChange={(e) => setPersonaConfig({...personaConfig, productAdvantages: e.target.value})}
                  placeholder="如: 全面,性价比高,效果好"
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500 min-h-[60px]"
                />
              </div>
              
              <div>
                <label className="block text-red-400 text-sm font-bold mb-2">
                  其他?
                </label>
                <textarea
                  value={personaConfig.other}
                  onChange={(e) => setPersonaConfig({...personaConfig, other: e.target.value})}
                  placeholder="如: 我们的产品区别于市面上的产品..."
                  className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-indigo-500 min-h-[60px]"
                />
              </div>

              <div className="pt-2 border-t border-white/10">
                <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-3">抖音截流（与 automation 挖掘客户共用）</p>
                <div>
                  <label className="block text-cyan-300/90 text-sm font-bold mb-2">
                    行业搜索关键词（轮换）
                  </label>
                  <input
                    type="text"
                    value={personaConfig.industryKeywords}
                    onChange={(e) => setPersonaConfig({ ...personaConfig, industryKeywords: e.target.value })}
                    placeholder="如: 不锈钢门窗/系统窗/阳光房（用 / 或逗号分隔）"
                    className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-cyan-500"
                  />
                </div>
                <div className="mt-4">
                  <label className="block text-cyan-300/90 text-sm font-bold mb-2">
                    素材评论风格示例
                  </label>
                  <textarea
                    value={personaConfig.commentExample}
                    onChange={(e) => setPersonaConfig({ ...personaConfig, commentExample: e.target.value })}
                    placeholder="一句话或多行，供豆包生成评论时参考（勿含导流话术）"
                    className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-cyan-500 min-h-[56px]"
                  />
                </div>
                <div className="mt-4">
                  <label className="block text-cyan-300/90 text-sm font-bold mb-2">
                    意向词补充（与系统内置合并）
                  </label>
                  <input
                    type="text"
                    value={personaConfig.intentKeywords}
                    onChange={(e) => setPersonaConfig({ ...personaConfig, intentKeywords: e.target.value })}
                    placeholder="如: 多少钱/厂家/合作/加盟"
                    className="w-full bg-[#1a1f2a] border-b-2 border-white/20 text-white px-2 py-2 outline-none focus:border-cyan-500"
                  />
                </div>
              </div>
            </div>
            
            <div className="mt-6 flex space-x-3">
              <button
                onClick={() => setShowPersonaModal(false)}
                className="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl text-slate-400 text-sm font-bold uppercase tracking-widest hover:bg-white/10 transition-all"
              >
                取消
              </button>
              <button
                onClick={() => {
                  setShowPersonaModal(false);
                  // 保存到 localStorage
                  localStorage.setItem('personaConfig', JSON.stringify(personaConfig));
                }}
                className="flex-1 py-3 bg-indigo-600 rounded-xl text-white text-sm font-bold uppercase tracking-widest hover:bg-indigo-700 transition-all"
              >
                保存配置
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 预设提示词 */}
      <div className="mb-6">
        <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mb-3">预设提示词</p>
        <div className="flex flex-wrap gap-3">
          {presetPrompts.map((prompt, idx) => (
            <button
              key={idx}
              onClick={() => handlePresetClick(prompt)}
              className="px-4 py-2 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 rounded-xl text-sm font-medium hover:bg-indigo-500/20 transition-all"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* 输入类型选择 */}
      <div className="mb-6 flex space-x-3">
        <button
          onClick={() => setInputType('text')}
          className={`px-6 py-2.5 rounded-xl text-sm font-bold uppercase tracking-widest transition-all ${
            inputType === 'text'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20'
              : 'bg-white/5 border border-white/10 text-slate-400 hover:bg-white/10'
          }`}
        >
          文案输入
        </button>
        <button
          onClick={() => setInputType('link')}
          className={`px-6 py-2.5 rounded-xl text-sm font-bold uppercase tracking-widest transition-all ${
            inputType === 'link'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20'
              : 'bg-white/5 border border-white/10 text-slate-400 hover:bg-white/10'
          }`}
        >
          链接解析
        </button>
        <button
          onClick={() => setInputType('keyword')}
          className={`px-6 py-2.5 rounded-xl text-sm font-bold uppercase tracking-widest transition-all ${
            inputType === 'keyword'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20'
              : 'bg-white/5 border border-white/10 text-slate-400 hover:bg-white/10'
          }`}
        >
          行业/关键词
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* 左侧输入区 */}
        <div className="space-y-6">
          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center space-x-3 mb-4">
              <div className="w-10 h-10 bg-indigo-500/10 text-indigo-400 rounded-lg flex items-center justify-center border border-indigo-500/20">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </div>
              <h3 className="text-lg font-bold text-white uppercase tracking-tight">
                {inputType === 'link' ? '输入链接' : inputType === 'keyword' ? '输入行业/关键词' : '输入文案'}
              </h3>
            </div>
            
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                inputType === 'link'
                  ? '请输入视频链接（抖音、快手、小红书等）...'
                  : inputType === 'keyword'
                  ? '请输入行业或关键词，例如：美妆、科技、美食...'
                  : '请输入需要优化或二创的文案内容...'
              }
              className="w-full h-64 bg-[#1a1f2a] border border-white/10 rounded-xl p-6 text-slate-300 text-sm outline-none focus:border-indigo-500 resize-none font-medium leading-relaxed placeholder:text-slate-600"
            />
            
            <button
              onClick={() => handleGenerate(false)}
              disabled={!input.trim() || generating}
              className={`w-full mt-4 py-4 rounded-xl text-white font-black text-sm uppercase tracking-widest shadow-lg transition-all flex items-center justify-center space-x-3 disabled:opacity-50 disabled:cursor-not-allowed ${
                generateSuccess 
                  ? 'bg-gradient-to-r from-emerald-600 to-green-600 shadow-emerald-500/20' 
                  : 'bg-gradient-to-r from-indigo-600 to-purple-600 shadow-indigo-500/20 hover:scale-[1.02] active:scale-[0.98]'
              }`}
            >
              {generating ? (
                <>
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>生成中...</span>
                </>
              ) : generateSuccess ? (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>生成成功</span>
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span>生成文案</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* 右侧结果区 - 对比显示 */}
        <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 flex flex-col">
          <div className="flex items-center space-x-3 mb-4">
            <div className="w-10 h-10 bg-emerald-500/10 text-emerald-400 rounded-lg flex items-center justify-center border border-emerald-500/20">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-white uppercase tracking-tight">生成结果对比</h3>
          </div>
          
          <div className="flex-1 overflow-y-auto space-y-4">
            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm">
                {error}
              </div>
            )}
            
            {result ? (
              <div className="space-y-6">
                {/* 原文案 */}
                <div className="bg-[#1a1f2a] border border-white/10 rounded-xl p-6">
                  <div className="flex items-center space-x-2 mb-4">
                    <div className="w-2 h-2 bg-slate-500 rounded-full"></div>
                    <h4 className="text-sm font-bold text-slate-400 uppercase tracking-widest">原文案</h4>
                  </div>
                  <div className="text-slate-300 text-sm leading-relaxed whitespace-pre-wrap font-medium">
                    {result.original_script.full_script || '（从视频中提取的文案）'}
                  </div>
                  {result.original_script.hook && (
                    <div className="mt-4 pt-4 border-t border-white/5">
                      <div className="text-xs text-slate-500 mb-2">结构分析：</div>
                      <div className="space-y-2 text-xs">
                        {result.original_script.hook && (
                          <div><span className="text-slate-500">钩子：</span> <span className="text-slate-300">{result.original_script.hook}</span></div>
                        )}
                        {result.original_script.problem && (
                          <div><span className="text-slate-500">问题：</span> <span className="text-slate-300">{result.original_script.problem}</span></div>
                        )}
                        {result.original_script.solution && (
                          <div><span className="text-slate-500">方案：</span> <span className="text-slate-300">{result.original_script.solution}</span></div>
                        )}
                        {result.original_script.cta && (
                          <div><span className="text-slate-500">行动：</span> <span className="text-slate-300">{result.original_script.cta}</span></div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
                
                {/* 改写后文案 */}
                <div className="bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-2">
                      <div className="w-2 h-2 bg-indigo-400 rounded-full animate-pulse"></div>
                      <h4 className="text-sm font-bold text-indigo-400 uppercase tracking-widest">AI改写后文案</h4>
                    </div>
                    {/* 相似度显示 */}
                    {result.similarity && (
            <div className="flex items-center space-x-4">
                        <div className="flex items-center space-x-2">
                          <div className="relative w-16 h-16">
                            <svg className="w-16 h-16 transform -rotate-90">
                              <circle
                                cx="32"
                                cy="32"
                                r="28"
                                stroke="currentColor"
                                strokeWidth="4"
                                fill="none"
                                className="text-slate-700"
                              />
                              <circle
                                cx="32"
                                cy="32"
                                r="28"
                                stroke="currentColor"
                                strokeWidth="4"
                                fill="none"
                                strokeDasharray={`${2 * Math.PI * 28}`}
                                strokeDashoffset={`${2 * Math.PI * 28 * (1 - result.similarity.deduplication_rate / 100)}`}
                                className={`transition-all ${
                                  result.similarity.deduplication_rate >= 70 
                                    ? 'text-emerald-400' 
                                    : result.similarity.deduplication_rate >= 50
                                    ? 'text-yellow-400'
                                    : 'text-red-400'
                                }`}
                              />
                            </svg>
                            <div className="absolute inset-0 flex items-center justify-center">
                              <span className={`text-xs font-bold ${
                                result.similarity.deduplication_rate >= 70 
                                  ? 'text-emerald-400' 
                                  : result.similarity.deduplication_rate >= 50
                                  ? 'text-yellow-400'
                                  : 'text-red-400'
                              }`}>
                                {Math.round(result.similarity.deduplication_rate)}%
                              </span>
                            </div>
                          </div>
                          <div className="text-xs">
                            <div className="text-slate-400">去重率</div>
                            <div className={`font-bold ${
                              result.similarity.deduplication_rate >= 70 
                                ? 'text-emerald-400' 
                                : result.similarity.deduplication_rate >= 50
                                ? 'text-yellow-400'
                                : 'text-red-400'
                            }`}>
                              {result.similarity.deduplication_rate >= 70 ? '优秀' : result.similarity.deduplication_rate >= 50 ? '良好' : '需优化'}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="text-white text-sm leading-relaxed whitespace-pre-wrap font-medium">
                    {result.rewritten_script.full_script || '（改写后的完整文案）'}
                  </div>
                  {result.similarity && (
                    <div className="mt-4 pt-4 border-t border-indigo-500/20">
                      <div className="text-xs text-indigo-400 mb-2">相似度分析：</div>
                      <div className="grid grid-cols-3 gap-4 text-xs">
                        <div>
                          <div className="text-slate-400">重复率</div>
                          <div className="text-white font-bold">{result.similarity.repetition_rate.toFixed(1)}%</div>
                        </div>
                        <div>
                          <div className="text-slate-400">相似度</div>
                          <div className="text-white font-bold">{result.similarity.similarity_rate.toFixed(1)}%</div>
                        </div>
                        <div>
                          <div className="text-slate-400">去重率</div>
                          <div className={`font-bold ${
                            result.similarity.deduplication_rate >= 70 
                              ? 'text-emerald-400' 
                              : result.similarity.deduplication_rate >= 50
                              ? 'text-yellow-400'
                              : 'text-red-400'
                          }`}>
                            {result.similarity.deduplication_rate.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  <div className="mt-4 pt-4 border-t border-indigo-500/20">
                    <div className="text-xs text-indigo-400 mb-2">优化结构：</div>
                    <div className="space-y-2 text-xs">
                      {result.rewritten_script.hook && (
                        <div><span className="text-indigo-400/70">钩子：</span> <span className="text-white">{result.rewritten_script.hook}</span></div>
                      )}
                      {result.rewritten_script.problem && (
                        <div><span className="text-indigo-400/70">问题：</span> <span className="text-white">{result.rewritten_script.problem}</span></div>
                      )}
                      {result.rewritten_script.solution && (
                        <div><span className="text-indigo-400/70">方案：</span> <span className="text-white">{result.rewritten_script.solution}</span></div>
                      )}
                      {result.rewritten_script.cta && (
                        <div><span className="text-indigo-400/70">行动：</span> <span className="text-white">{result.rewritten_script.cta}</span></div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-slate-600 text-sm text-center py-20">
                <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="font-medium">生成结果将显示在这里</p>
                <p className="text-xs text-slate-600 mt-2">原文案和改写后的文案将进行对比显示</p>
              </div>
            )}
          </div>
          
          {result && (
            <div className="mt-4 flex space-x-3">
              <button 
                onClick={() => {
                  const text = result.rewritten_script.full_script || '';
                  navigator.clipboard.writeText(text);
                }}
                className="flex-1 py-2.5 bg-white/5 border border-white/10 rounded-xl text-slate-400 text-sm font-bold uppercase tracking-widest hover:bg-white/10 transition-all"
              >
                复制文案
              </button>
              <button 
                onClick={() => {
                  // 保存文案到 localStorage，供素材生产和成品素材使用
                  const text = result.rewritten_script.full_script || '';
                  localStorage.setItem('current_script', text);
                  alert('文案已保存，可在素材生产和成品素材中使用');
                }}
                className="flex-1 py-2.5 bg-sky-600/10 border border-sky-500/20 text-sky-400 rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-sky-600/20 transition-all"
              >
                使用
              </button>
              <button 
                onClick={() => handleGenerate(true)}
                disabled={generating}
                className="flex-1 py-2.5 bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-indigo-600/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                继续优化
              </button>
              <button 
                onClick={() => {
                  // 导航到合规检测页面，并传递文案
                  const text = result.rewritten_script.full_script || '';
                  // 可以通过路由或状态管理传递文案
                  window.location.href = '/compliance?script=' + encodeURIComponent(text);
                }}
                className="flex-1 py-2.5 bg-emerald-600/10 border border-emerald-500/20 text-emerald-400 rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-emerald-600/20 transition-all"
              >
                合规检测
              </button>
            </div>
          )}
        </div>
        </div>
    </div>
  );
};

export default CopywritingProduction;
