
import React, { useState, useEffect, useMemo } from 'react';

const Icons = {
  Zap: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>,
  Server: () => <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>,
  Pause: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  Stop: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9h6v6H9V9z" /></svg>,
  Settings: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /></svg>,
  Clock: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  Link: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>,
  Step1: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>,
  Step2: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>,
  Step3: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>,
  Step4: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>,
};

const ExecutionProgress: React.FC<{ onFinish: () => void }> = ({ onFinish }) => {
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('初始化中...');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [ellipsisTick, setEllipsisTick] = useState(0);
  const [videoVariantIndex, setVideoVariantIndex] = useState(0);

  const cleanStep = (s: string) => {
    // 去掉视频等待耗时的括号信息：例如 "生成视频中... (已等待 xx分yy秒)"
    return String(s)
      .replace(/\s*\(已等待.*?\)\s*$/, '')
      .replace(/\s*（已等待.*?）\s*$/, '')
      .replace(/\s*\(已等待.*?\)\s*$/, '')
      .trim();
  };

  const phase = useMemo(() => {
    if (progress >= 100) return 'done';
    const s = currentStep || '';
    if (s.includes('发布')) return 'publish';
    if (s.includes('生成发布素材') || s.includes('内容生成')) return 'material';
    if (s.includes('合规检测')) return 'compliance';
    if (s.includes('高清') || s.includes('清晰度') || s.includes('超清') || s.includes('增强')) return 'hd';
    if (s.includes('画中画')) return 'pip';
    if (s.includes('字幕')) return 'subtitle';
    if (s.includes('BGM')) return 'bgm';
    if (s.includes('口播语音')) return 'tts';
    if (s.includes('生成视频中') || s.includes('视频生成完成')) return 'video';
    if (s.includes('生成文案') || s.includes('解析链接')) return 'copy';
    if (s.includes('文案')) return 'copy';
    if (s.includes('生成完成')) return 'copy';
    if (s.includes('链接')) return 'link';
    return 'init';
  }, [currentStep, progress]);

  const phaseInfo = useMemo(() => {
    const base = {
      title: '自动化任务执行中',
      desc: '已启动流程，请耐心等待。',
    };
    switch (phase) {
      case 'hd':
        return {
          title: '高清增强中',
          desc: '正在对口播成片进行清晰度增强并下载高清版本',
        };
      case 'video':
        return {
          title: '生成视频中',
          desc: '正在合成数字人口播与成片输出（此阶段耗时较长）',
        };
      case 'tts':
        return {
          title: '口播语音生成中',
          desc: '正在生成口播配音（TTS）',
        };
      case 'pip':
        return {
          title: '画中画匹配中',
          desc: '正在将演示画面与主轨视频对齐合成',
        };
      case 'subtitle':
        return {
          title: '字幕匹配中',
          desc: '正在根据文案烧制并对齐字幕',
        };
      case 'bgm':
        return {
          title: 'BGM匹配中',
          desc: '正在为成片匹配并合成背景音乐',
        };
      case 'material':
        return {
          title: '发布素材生成中',
          desc: '正在生成封面、标题与发布描述',
        };
      case 'copy':
        return {
          title: '生成文案中',
          desc: '正在解析链接并进行脚本二创与润色',
        };
      case 'compliance':
        return {
          title: '合规检测中',
          desc: '正在进行敏感内容检测与安全改写',
        };
      case 'publish':
        return {
          title: '发布中',
          desc: '正在将成片与文案推送到平台',
        };
      case 'link':
        return {
          title: '链接解析中',
          desc: '正在提取视频内容并生成基础文案',
        };
      case 'done':
        return {
          title: '执行完成',
          desc: '任务已完成，正在返回主界面',
        };
      case 'init':
      default:
        return base;
    }
  }, [phase]);

  useEffect(() => {
    // 从localStorage获取任务ID，并持续监听更新
    const getTaskId = () => {
      const savedTaskId = localStorage.getItem('auto_task_id');
      if (savedTaskId && savedTaskId !== taskId) {
        setTaskId(savedTaskId);
        // 不删除，保持监听
      }
    };

    // 立即获取一次
    getTaskId();

    // 每500ms检查一次localStorage，确保能获取到最新的task_id
    const checkInterval = setInterval(getTaskId, 500);

    // 轮询任务状态
    const pollInterval = setInterval(async () => {
      const currentTaskId = localStorage.getItem('auto_task_id') || taskId;
      if (!currentTaskId) return;

      try {
        const response = await fetch(`/api/task/${currentTaskId}`);
        if (response.ok) {
          const data = await response.json();
          
          setProgress(data.progress || 0);
          const stepText = data.step || '执行中...';
          setCurrentStep(stepText);
          
          // 检查是否完成
          if (data.status === 'done') {
            const publishSuccess = stepText.includes('发布成功') || stepText.includes('抖音发布成功');
            setProgress(100);
            clearInterval(pollInterval);
            clearInterval(checkInterval);
            
            // 显示完成信息
            setTimeout(() => {
              alert('自动化流程执行完成！');
            }, 1000);
          } else if (data.status === 'error') {
            clearInterval(pollInterval);
            clearInterval(checkInterval);
            alert(`执行失败: ${data.error || '未知错误'}`);
          } else if (data.status === 'cancelled') {
            clearInterval(pollInterval);
            clearInterval(checkInterval);
            setTimeout(onFinish, 300);
          }
        } else if (response.status === 404) {
          // 任务不存在，可能是task_id还没设置，继续等待
          console.log('任务ID尚未创建，等待中...');
        }
      } catch (error) {
        console.error('查询任务状态失败:', error);
      }
    }, 2000);

    return () => {
      clearInterval(pollInterval);
      clearInterval(checkInterval);
    };
  }, [taskId]);

  const animateTitlePhases = useMemo(
    () =>
      new Set([
        'video',
        'tts',
        'hd',
        'pip',
        'subtitle',
        'bgm',
        'compliance',
        'material',
        'copy',
        'publish',
      ]),
    []
  );

  const pipelineVideoBadgePhases = useMemo(
    () => new Set(['video', 'tts', 'hd', 'pip', 'subtitle', 'bgm']),
    []
  );

  // 进行中阶段做动态省略号动画（副标题始终跟随后台 step）
  useEffect(() => {
    if (!animateTitlePhases.has(phase)) return;

    const id = window.setInterval(() => {
      setEllipsisTick(t => (t + 1) % 4);
    }, 450);

    return () => window.clearInterval(id);
  }, [phase, animateTitlePhases]);

  // 仅在「生成视频中」且未完成成片时做内部说明轮换
  useEffect(() => {
    if (phase !== 'video' || currentStep.includes('视频生成完成')) {
      setVideoVariantIndex(0);
      return;
    }
    const id = window.setInterval(() => {
      setVideoVariantIndex(i => (i + 1) % 3);
    }, 2200);
    return () => window.clearInterval(id);
  }, [phase, currentStep]);

  const dots = ['', '.', '..', '...'][ellipsisTick % 4];
  const running = progress >= 0 && progress < 100;
  const stepTitle = cleanStep(currentStep) || phaseInfo.title;
  const displayMainTitle =
    running && animateTitlePhases.has(phase) ? `${stepTitle}${dots}` : stepTitle;

  const displaySubDesc = phaseInfo.desc;

  const videoVariantDesc = [
    '正在下载/解析视频并建立工程管线',
    '正在渲染画面与合成视频输出',
    '正在等待视频生成完成并进入后处理',
  ][videoVariantIndex];

  const handleStop = async () => {
    if (stopping) return;
    setStopping(true);
    try {
      if (taskId) {
        await fetch(`/api/task/${taskId}`, { method: 'DELETE' });
      }
    } catch (e) {
      console.error('停止任务失败:', e);
    } finally {
      onFinish();
    }
  };

  // 根据进度和步骤文本，计算各步骤的进度
  const getStepProgress = (stepIndex: number) => {
    // 步骤划分：0-20% 链接解析，20-40% 文案生成，40-60% 合规检测，60-80% 素材生成，80-100% 发布
    const stepRanges = [
      { start: 0, end: 20 },   // 链接解析
      { start: 20, end: 40 },  // 文案生成
      { start: 40, end: 60 },  // 合规检测
      { start: 60, end: 80 },  // 素材生成
      { start: 80, end: 100 }  // 发布
    ];

    const range = stepRanges[stepIndex];
    if (progress < range.start) return 0;
    if (progress >= range.end) return 100;
    return ((progress - range.start) / (range.end - range.start)) * 100;
  };

  const getStepStatus = (stepIndex: number) => {
    const stepRanges = [
      { start: 0, end: 20 },
      { start: 20, end: 40 },
      { start: 40, end: 60 },
      { start: 60, end: 80 },
      { start: 80, end: 100 }
    ];
    const range = stepRanges[stepIndex];
    if (progress >= range.end) return 'completed';
    if (progress >= range.start) return 'active';
    return 'waiting';
  };

  const getStepDesc = (stepIndex: number, stepTitle: string) => {
    const stepKeywords = [
      ['链接', '解析', '文案', '二创'],
      ['文案', '生成', '合规'],
      ['合规', '检测'],
      ['视频', '素材', '生成', '画中画', '字幕', 'BGM', '口播'],
      ['发布', '抖音']
    ];
    const keywords = stepKeywords[stepIndex];
    const isCurrentStep = keywords.some(keyword => currentStep.includes(keyword));
    
    if (progress >= 100 && stepIndex === 4) {
      return '抖音发布成功';
    }
    if (isCurrentStep) {
      return currentStep;
    }
    const status = getStepStatus(stepIndex);
    if (status === 'completed') return '已完成';
    if (status === 'active') return '进行中...';
    return '等待中...';
  };

  return (
    <div className="h-full">
      <style>{`
        @keyframes axonCardFlip {
          0% { opacity: 0; transform: translateY(12px) rotateX(18deg) scale(0.98); }
          55% { opacity: 1; transform: translateY(0px) rotateX(0deg) scale(1.00); }
          100% { opacity: 1; transform: translateY(0px) rotateX(0deg) scale(1.00); }
        }
        @keyframes axonGlowSweep {
          0% { transform: translateX(-30%) rotate(0deg); opacity: 0.35; }
          50% { opacity: 0.7; }
          100% { transform: translateX(30%) rotate(180deg); opacity: 0.35; }
        }
      `}</style>

      <div className="flex items-stretch gap-6 h-[calc(100vh-140px)] min-h-[560px]">
        {/* Center Card */}
        <div className="flex-1 bg-[#070b12] border border-white/10 rounded-3xl p-10 relative overflow-hidden shadow-[0_0_80px_-40px_rgba(59,130,246,0.45)]">
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute -top-28 -left-20 w-80 h-80 rounded-full bg-cyan-500/15 blur-3xl" />
            <div className="absolute -bottom-24 -right-24 w-96 h-96 rounded-full bg-indigo-500/15 blur-3xl" />
            <div className="absolute -top-40 left-1/2 w-[520px] h-[160px] bg-[radial-gradient(closest-side,rgba(99,102,241,0.35),transparent)] opacity-60 animate-[axonGlowSweep_6s_ease-in-out_infinite]" />
          </div>

          <div className="relative z-10 flex flex-col h-full">
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500/25 to-cyan-500/15 border border-white/10 flex items-center justify-center shadow-[0_0_24px_rgba(99,102,241,0.35)]">
                    <Icons.Zap />
                  </div>
                  <div>
                    <h2 className="text-lg font-black text-white tracking-tight">
                      IP智能体 5.0 全自动生成中
                    </h2>
                  </div>
                </div>
              </div>

              {/* Completion Progress (keep) */}
              <div className="min-w-[180px]">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-slate-500 uppercase tracking-widest font-black">完成进度</span>
                  <span className="text-[12px] text-indigo-200 font-black tabular-nums">{progress}%</span>
                </div>
                <div className="h-2 rounded-full bg-white/5 overflow-hidden border border-white/10">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-400 to-indigo-500 transition-all duration-500"
                    style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Rotating step panel */}
            <div className="mt-10 flex-1 flex items-center">
              <div
                key={
                  phase === 'video' && !currentStep.includes('视频生成完成')
                    ? `${phase}-${videoVariantIndex}`
                    : phase
                }
                className="w-full max-w-2xl mx-auto bg-white/5 border border-white/10 rounded-3xl p-8 relative overflow-hidden"
                style={{ animation: 'axonCardFlip 0.55s ease-out both' }}
              >
                <div className="absolute -top-24 -right-20 w-56 h-56 rounded-full bg-indigo-500/15 blur-3xl pointer-events-none" />

                <p className="text-[10px] text-slate-400 uppercase tracking-widest font-black mb-3">
                  {phase === 'done' ? '已完成' : '进行中'}
                </p>

                <div className="flex items-end justify-between gap-6 mb-4">
                  <h3 className="text-4xl font-black text-white tracking-tight drop-shadow-[0_0_18px_rgba(99,102,241,0.35)]">
                    {displayMainTitle}
                  </h3>
                  {pipelineVideoBadgePhases.has(phase) && (
                    <div className="px-4 py-2 rounded-2xl bg-cyan-500/10 border border-cyan-400/20">
                      <p className="text-[10px] text-cyan-200 font-black uppercase tracking-widest">VIDEO</p>
                    </div>
                  )}
                </div>

                <p className="text-sm text-slate-300 leading-relaxed">
                  {phase === 'video' && !currentStep.includes('视频生成完成')
                    ? videoVariantDesc
                    : phaseInfo.desc}
                </p>

                <p className="text-xs text-slate-500 uppercase tracking-[0.22em] font-black mt-4">
                  {displaySubDesc}
                </p>
              </div>
            </div>

            {/* Small note: remove any explicit long-wait parentheses */}
            <div className="relative z-10 mt-6 flex items-center justify-center text-[10px] text-slate-500 uppercase tracking-widest font-black">
              {/* keep UI minimal */}
              系统正在根据后台任务状态同步推进
            </div>
          </div>
        </div>

        {/* Right Action Buttons */}
        <div className="w-[84px] flex flex-col items-center justify-start gap-6 pt-2">
          <button
            className="w-14 h-14 bg-white/5 border border-white/10 rounded-2xl flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10 transition-all shadow-xl"
            title="暂停（当前版本仅展示按钮）"
          >
            <Icons.Pause />
          </button>

          <button
            onClick={handleStop}
            disabled={stopping}
            className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all shadow-xl ${
              stopping
                ? 'bg-rose-500/10 border border-rose-500/20 text-rose-300 cursor-not-allowed'
                : 'bg-rose-500/10 border border-rose-500/30 text-rose-500 hover:bg-rose-500 hover:text-white'
            }`}
            title="停止当前任务"
          >
            <Icons.Stop />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ExecutionProgress;
