
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { WorkflowConfig } from '../types';
import {
  fetchMaterialCurrentState,
  clearMaterialOnServer,
  fetchMaterialPreviewBlob,
  displayMaterialName,
  canPreviewMaterial,
  serverMaterialSlot,
  type MaterialKind,
  type MaterialCurrentStateApi,
} from '../utils/materialAssets';
import ShowcaseEnvPanel from '../components/ShowcaseEnvPanel';

interface AutomationWorkflowProps {
  onStart: (config: WorkflowConfig, keyword?: string) => void;
  config: WorkflowConfig;
  setConfig: React.Dispatch<React.SetStateAction<WorkflowConfig>>;
}

/** 从文案页人设读取；立即执行与定时任务共用同一份 persona，保证 AI 提示词与人设一致。 */
function buildHfDmPersonaFromStorage(): Record<string, string> {
  let p: Record<string, string> = {};
  try {
    const raw = localStorage.getItem('personaConfig');
    if (raw) {
      const o = JSON.parse(raw) as Record<string, unknown>;
      if (o && typeof o === 'object') {
        p = Object.fromEntries(
          Object.entries(o).map(([k, v]) => [k, v == null ? '' : String(v)])
        ) as Record<string, string>;
      }
    }
  } catch {
    /* ignore */
  }
  return {
    consumptionRange: p.consumptionRange ?? '',
    wechatId: p.wechatId ?? '',
    companyName: p.companyName ?? '',
    targetMarket: p.targetMarket ?? '',
    coreSolution: p.coreSolution ?? '',
    companyAddress: p.companyAddress ?? '',
    productYears: p.productYears ?? '',
    productAdvantages: p.productAdvantages ?? '',
    other: p.other ?? '',
    industryKeywords: p.industryKeywords ?? '',
    commentExample: p.commentExample ?? '',
    intentKeywords: p.intentKeywords ?? '',
  };
}

/** 与产品默认一致：每步 3～7s 随机、首次搜索前不额外等待、豆包二次意向判定开启；人设来自文案页 localStorage */
function buildDefaultInterceptStartPayload(): Record<string, unknown> {
  const persona = buildHfDmPersonaFromStorage();
  return {
    human_delay_min: 3,
    human_delay_max: 7,
    start_delay_seconds: 0,
    ai_intent: true,
    persona: {
      consumptionRange: persona.consumptionRange,
      wechatId: persona.wechatId,
      companyName: persona.companyName,
      targetMarket: persona.targetMarket,
      coreSolution: persona.coreSolution,
      companyAddress: persona.companyAddress,
      productYears: persona.productYears,
      productAdvantages: persona.productAdvantages,
      other: persona.other,
      industryKeywords: persona.industryKeywords,
      commentExample: persona.commentExample,
      intentKeywords: persona.intentKeywords,
    },
  };
}

async function postDefaultInterceptStart(): Promise<void> {
  const r = await fetch('/api/intercept/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildDefaultInterceptStartPayload()),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    alert(typeof j.detail === 'string' ? j.detail : `启动截流失败 HTTP ${r.status}`);
    return;
  }
  if (!j.ok && typeof j.message === 'string' && j.message.includes('已在运行')) {
    return;
  }
  if (!j.ok) {
    alert(typeof j.message === 'string' ? j.message : '启动截流失败');
  }
}

/**
 * quick：仅控制后端拟人随机停顿（立即执行短一点、定时长一点），不改变 AI 回复逻辑。
 * persona 始终同构，与 hf_auto_reply / 豆包提示词一致。
 */
function buildHfDmRunOnceBody(quick: boolean): Record<string, unknown> {
  return {
    quick,
    persona: buildHfDmPersonaFromStorage(),
  };
}

function postHfDmRunOnce(quick: boolean): Promise<Response> {
  return fetch('/api/hf_dm/run_once', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildHfDmRunOnceBody(quick)),
  });
}

interface PersonaConfig {
  consumptionRange: string;
  wechatId: string;
  companyName: string;
  targetMarket: string;
  coreSolution: string;
  companyAddress: string;
  productYears: string;
  productAdvantages: string;
  other: string;
  industryKeywords: string;
  commentExample: string;
  intentKeywords: string;
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

const AutomationWorkflow: React.FC<AutomationWorkflowProps> = ({ onStart, config, setConfig }) => {
  const [link, setLink] = useState('');
  const [showPersonaModal, setShowPersonaModal] = useState(false);
  const [personaConfig, setPersonaConfig] = useState<PersonaConfig>({ ...EMPTY_PERSONA });
  const [complianceRulesOpen, setComplianceRulesOpen] = useState(false);
  const [complianceExtraRules, setComplianceExtraRules] = useState('');
  // IP档案管理除了“文案人设字段”，还需要补齐素材生产端的形象/音频上传能力
  const [isConnected, setIsConnected] = useState(false);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [productFile, setProductFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [backgroundMusicFile, setBackgroundMusicFile] = useState<File | null>(null);

  const avatarInputRef = useRef<HTMLInputElement>(null);
  const productInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const backgroundMusicInputRef = useRef<HTMLInputElement>(null);

  // 上传文件的“查看”预览（仅使用本地 URL，不依赖后端额外接口）
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewKind, setPreviewKind] = useState<'image' | 'audio' | 'video' | null>(null);
  const [previewTitle, setPreviewTitle] = useState<string>('');
  const [materialServer, setMaterialServer] = useState<MaterialCurrentStateApi | null>(null);
  const HF_LS_KEY = 'hf_auto_reply_auto_enabled';
  const MINING_LS_KEY = 'mining_client_enabled';
  const miningInitOnceRef = useRef(false);

  const [miningEnabled, setMiningEnabled] = useState(() => {
    try {
      return localStorage.getItem(MINING_LS_KEY) === '1';
    } catch {
      return false;
    }
  });

  const [interceptRunning, setInterceptRunning] = useState(false);
  const [interceptPid, setInterceptPid] = useState<number | null>(null);
  const [interceptLogs, setInterceptLogs] = useState<string[]>([]);
  const [interceptStats, setInterceptStats] = useState<{
    today_dm: number;
    today_comment: number;
    total_dm: number;
    total_comment: number;
  } | null>(null);

  const [hfToday, setHfToday] = useState<number | null>(null);
  const [hfTotal, setHfTotal] = useState<number | null>(null);
  const [hfRunning, setHfRunning] = useState(false);
  const [hfQueued, setHfQueued] = useState(false);
  const [hfLastErr, setHfLastErr] = useState<string | null>(null);
  const [envCheck, setEnvCheck] = useState<Record<string, unknown> | null>(null);
  const [envChecking, setEnvChecking] = useState(true);
  const [hfTimerOn, setHfTimerOn] = useState(() => {
    try {
      if (localStorage.getItem(HF_LS_KEY) === '1') return true;
      if (localStorage.getItem('hf_auto_reply_timer_enabled') === '1') return true;
      return false;
    } catch {
      return false;
    }
  });

  const refreshStats = useCallback(async () => {
    try {
      const r = await fetch('/api/hf_dm/stats');
      if (!r.ok) return;
      const j = await r.json();
      setHfToday(typeof j.today_replies === 'number' ? j.today_replies : 0);
      setHfTotal(typeof j.total_replies === 'number' ? j.total_replies : 0);
    } catch {
      /* ignore */
    }
  }, []);

  const checkConnectionStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/connection_status');
      if (!r.ok) return;
      const j = await r.json();
      setIsConnected(!!j && j.status === 'connected');
    } catch {
      /* ignore */
    }
  }, []);

  const refreshMaterialServer = useCallback(async () => {
    try {
      const s = await fetchMaterialCurrentState();
      setMaterialServer(s);
    } catch {
      setMaterialServer(null);
    }
  }, []);

  useEffect(() => {
    if (!showPersonaModal) return;
    void checkConnectionStatus();
    void refreshMaterialServer();
    const id = window.setInterval(() => {
      void checkConnectionStatus();
    }, 5000);
    return () => window.clearInterval(id);
  }, [showPersonaModal, checkConnectionStatus, refreshMaterialServer]);

  const uploadFile = async (
    endpoint: string,
    file: File,
    onOk: (data: unknown) => void,
  ) => {
    if (!isConnected) {
      alert('请等待后台连接成功后再上传');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(endpoint, { method: 'POST', body: formData });
    if (!response.ok) {
      const errorText = await response.text().catch(() => '');
      alert(`上传失败: ${errorText || response.statusText}`);
      return;
    }
    const data = await response.json().catch(() => ({}));
    onOk(data);
  };

  const handleAvatarUpload = async (file: File) => {
    await uploadFile('/api/avatar', file, () => setAvatarFile(file));
    await refreshMaterialServer();
  };

  const handleProductUpload = async (file: File) => {
    await uploadFile('/api/product', file, () => setProductFile(file));
    await refreshMaterialServer();
  };

  const handleAudioUpload = async (file: File) => {
    await uploadFile('/api/audio', file, () => setAudioFile(file));
    await refreshMaterialServer();
  };

  const handleBackgroundMusicUpload = async (file: File) => {
    await uploadFile('/api/background_music', file, () => setBackgroundMusicFile(file));
    await refreshMaterialServer();
  };

  const closePreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewOpen(false);
    setPreviewUrl(null);
    setPreviewKind(null);
    setPreviewTitle('');
  };

  const openLocalPreview = (file: File | null, kind: 'image' | 'audio' | 'video') => {
    if (!file) return;
    // 切换文件时释放旧 URL，避免内存泄漏
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setPreviewKind(kind);
    setPreviewTitle(file.name);
    setPreviewOpen(true);
  };

  const openMaterialPreview = async (
    slot: MaterialKind,
    localFile: File | null,
    mediaKind: 'image' | 'audio' | 'video',
  ) => {
    if (!isConnected) {
      alert('请等待后台连接成功后再预览');
      return;
    }
    if (localFile) {
      openLocalPreview(localFile, mediaKind);
      return;
    }
    const sv = serverMaterialSlot(materialServer, slot);
    if (!canPreviewMaterial(null, sv)) {
      alert('当前没有可预览的文件，请先上传');
      return;
    }
    try {
      const blob = await fetchMaterialPreviewBlob(slot);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const url = URL.createObjectURL(blob);
      setPreviewUrl(url);
      setPreviewKind(mediaKind);
      setPreviewTitle(sv?.filename || slot);
      setPreviewOpen(true);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  };

  const handleClearMaterial = async (slot: MaterialKind) => {
    if (!window.confirm('确定清除该素材？文件将从服务器删除，可重新上传。')) return;
    try {
      await clearMaterialOnServer(slot);
      if (slot === 'avatar') setAvatarFile(null);
      if (slot === 'product') setProductFile(null);
      if (slot === 'audio') setAudioFile(null);
      if (slot === 'background_music') setBackgroundMusicFile(null);
      closePreview();
      await refreshMaterialServer();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  };

  // 如果用户关闭了“IP档案管理”弹窗，顺手关闭预览并释放 URL
  useEffect(() => {
    if (!showPersonaModal && previewOpen) closePreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showPersonaModal, previewOpen]);

  const refreshStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/hf_dm/status');
      if (!r.ok) return;
      const j = await r.json();
      setHfRunning(!!j.running);
      setHfQueued(!!j.queued);
      setHfLastErr(typeof j.last_err === 'string' ? j.last_err : null);
    } catch {
      /* ignore */
    }
  }, []);

  const refreshInterceptStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/intercept/status');
      if (!r.ok) return;
      const j = await r.json();
      setInterceptRunning(!!j.running);
      setInterceptPid(typeof j.pid === 'number' ? j.pid : null);
      if (Array.isArray(j.logs)) {
        setInterceptLogs(j.logs.map((x: unknown) => String(x)));
      }
    } catch {
      /* ignore */
    }
  }, []);

  const refreshInterceptStats = useCallback(async () => {
    try {
      const r = await fetch('/api/intercept/stats');
      if (!r.ok) return;
      const j = await r.json();
      setInterceptStats({
        today_dm: typeof j.today_dm === 'number' ? j.today_dm : 0,
        today_comment: typeof j.today_comment === 'number' ? j.today_comment : 0,
        total_dm: typeof j.total_dm === 'number' ? j.total_dm : 0,
        total_comment: typeof j.total_comment === 'number' ? j.total_comment : 0,
      });
    } catch {
      /* ignore */
    }
  }, []);

  const runEnvCheck = useCallback(async () => {
    setEnvChecking(true);
    try {
      const r = await fetch('/api/hf_dm/env_check');
      if (!r.ok) {
        setEnvCheck({ all_ok: false, error: `HTTP ${r.status}` });
        return;
      }
      setEnvCheck(await r.json());
    } catch (e) {
      setEnvCheck({ all_ok: false, error: String(e) });
    } finally {
      setEnvChecking(false);
    }
  }, []);

  useEffect(() => {
    refreshStats();
    refreshStatus();
    runEnvCheck();
    refreshInterceptStatus();
    refreshInterceptStats();
    const id = setInterval(() => {
      refreshStats();
      refreshStatus();
      refreshInterceptStatus();
      refreshInterceptStats();
    }, 5000);
    return () => clearInterval(id);
  }, [refreshStats, refreshStatus, runEnvCheck, refreshInterceptStatus, refreshInterceptStats]);

  // 加载“IP档案管理”（与文案页共用同一个 localStorage key，不改原有调用逻辑）
  useEffect(() => {
    try {
      const saved = localStorage.getItem('personaConfig');
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<PersonaConfig>;
        if (parsed && typeof parsed === 'object') {
          setPersonaConfig({ ...EMPTY_PERSONA, ...parsed });
        }
      }
    } catch {
      /* ignore */
    }
  }, []);

  // 合规补充规则（客户自定义）：与合规站/自动化共用同一个 localStorage key
  useEffect(() => {
    try {
      const saved = localStorage.getItem('compliance_extra_rules');
      if (saved) setComplianceExtraRules(String(saved));
    } catch {
      /* ignore */
    }
  }, []);

  const saveComplianceExtraRules = () => {
    try {
      localStorage.setItem('compliance_extra_rules', complianceExtraRules);
    } catch {
      /* ignore */
    }
    setComplianceRulesOpen(false);
  };

  /** 上次关闭时若开关为开，下次进入页面自动拉起截流（仅执行一次，避免 StrictMode 双调用重复启） */
  useEffect(() => {
    if (miningInitOnceRef.current) return;
    miningInitOnceRef.current = true;
    try {
      if (localStorage.getItem(MINING_LS_KEY) !== '1') return;
    } catch {
      return;
    }
    void postDefaultInterceptStart().then(() => {
      refreshInterceptStatus();
      refreshInterceptStats();
    });
  }, [refreshInterceptStatus, refreshInterceptStats]);

  useEffect(() => {
    if (!hfTimerOn) return;
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      postHfDmRunOnce(false).then(() => {
        refreshStats();
        refreshStatus();
      });
    }, 30 * 60 * 1000);
    return () => clearInterval(id);
  }, [hfTimerOn, refreshStats, refreshStatus]);

  const onHfAutoToggle = (on: boolean) => {
    setHfTimerOn(on);
    try {
      localStorage.setItem(HF_LS_KEY, on ? '1' : '0');
    } catch {
      /* ignore */
    }
  };

  const onMiningToggle = (on: boolean) => {
    setMiningEnabled(on);
    try {
      localStorage.setItem(MINING_LS_KEY, on ? '1' : '0');
    } catch {
      /* ignore */
    }
    if (on) {
      void postDefaultInterceptStart().then(() => {
        refreshInterceptStatus();
        refreshInterceptStats();
      });
    } else {
      void fetch('/api/intercept/stop', { method: 'POST' })
        .then(() => {
          refreshInterceptStatus();
          refreshInterceptStats();
        })
        .catch(() => {});
    }
  };

  const runHfOnce = async () => {
    try {
      const r = await postHfDmRunOnce(true);
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert(`执行失败: ${r.status}`);
        return;
      }
      if (j.queued) {
        alert('已在运行中，已为您排队下一轮（允许排队）');
      }
      refreshStats();
      refreshStatus();
    } catch (e) {
      alert(`请求失败: ${e}`);
    }
  };

  const togglePlatform = (id: string) => {
    setConfig(prev => ({
      ...prev,
      platforms: prev.platforms.includes(id)
        ? prev.platforms.filter(p => p !== id)
        : [...prev.platforms, id]
    }));
  };

  return (
    <div className="max-w-6xl mx-auto">
      <header className="mb-10 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">AI员全自动配置</h1>
          <p className="text-slate-400">自动化内容创作全链路编排</p>
        </div>
        <button
          type="button"
          onClick={() => setShowPersonaModal(true)}
          className="px-6 py-3 bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-indigo-600/20 transition-all flex items-center space-x-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
          <span>IP档案管理</span>
        </button>
      </header>

      {showPersonaModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#131720] border border-white/10 rounded-2xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-white uppercase tracking-tight">IP档案管理</h2>
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, consumptionRange: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, wechatId: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, companyName: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, targetMarket: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, coreSolution: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, companyAddress: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, productYears: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, productAdvantages: e.target.value })}
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
                  onChange={(e) => setPersonaConfig({ ...personaConfig, other: e.target.value })}
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

              {/* 素材生产口：仅做形象/音频上传，不包含文案区域逻辑 */}
              <div className="pt-3 border-t border-white/10">
                <p className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-3">
                  形象与素材上传（自动化共用）
                </p>

                <div className="space-y-4">
                  {/* 头像 */}
                  <div className="bg-[#1a1f2a] border border-white/5 rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="text-white font-bold text-xs uppercase">人物形象（头像）</p>
                        <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-1">透明背景图片更好</p>
                      </div>
                      <div className="text-[10px] text-indigo-300 font-bold">
                        {displayMaterialName(avatarFile, serverMaterialSlot(materialServer, 'avatar'))}
                      </div>
                    </div>
                    <input
                      type="file"
                      ref={avatarInputRef}
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void handleAvatarUpload(file);
                      }}
                    />
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => avatarInputRef.current?.click()}
                        disabled={!isConnected}
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          isConnected
                            ? 'bg-indigo-600 hover:bg-indigo-700 shadow-lg shadow-indigo-500/20 text-white'
                            : 'bg-slate-900 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        上传
                      </button>
                      <button
                        type="button"
                        onClick={() => void openMaterialPreview('avatar', avatarFile, 'image')}
                        disabled={!canPreviewMaterial(avatarFile, serverMaterialSlot(materialServer, 'avatar'))}
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          canPreviewMaterial(avatarFile, serverMaterialSlot(materialServer, 'avatar'))
                            ? 'bg-indigo-600/10 border border-indigo-500/20 hover:bg-indigo-600/20 text-indigo-200'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        查看
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleClearMaterial('avatar')}
                        disabled={
                          !avatarFile && !serverMaterialSlot(materialServer, 'avatar')?.uploaded
                        }
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          avatarFile || serverMaterialSlot(materialServer, 'avatar')?.uploaded
                            ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-500'
                        }`}
                      >
                        清除
                      </button>
                    </div>
                  </div>

                  {/* 产品图片 */}
                  <div className="bg-[#1a1f2a] border border-white/5 rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="text-white font-bold text-xs uppercase">产品图片素材</p>
                        <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-1">可选增强画面</p>
                      </div>
                      <div className="text-[10px] text-indigo-300 font-bold">
                        {displayMaterialName(productFile, serverMaterialSlot(materialServer, 'product'))}
                      </div>
                    </div>
                    <input
                      type="file"
                      ref={productInputRef}
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void handleProductUpload(file);
                      }}
                    />
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => productInputRef.current?.click()}
                        disabled={!isConnected}
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          isConnected
                            ? 'bg-indigo-600 hover:bg-indigo-700 shadow-lg shadow-indigo-500/20 text-white'
                            : 'bg-slate-900 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        上传
                      </button>
                      <button
                        type="button"
                        onClick={() => void openMaterialPreview('product', productFile, 'image')}
                        disabled={!canPreviewMaterial(productFile, serverMaterialSlot(materialServer, 'product'))}
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          canPreviewMaterial(productFile, serverMaterialSlot(materialServer, 'product'))
                            ? 'bg-indigo-600/10 border border-indigo-500/20 hover:bg-indigo-600/20 text-indigo-200'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        查看
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleClearMaterial('product')}
                        disabled={
                          !productFile && !serverMaterialSlot(materialServer, 'product')?.uploaded
                        }
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          productFile || serverMaterialSlot(materialServer, 'product')?.uploaded
                            ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-500'
                        }`}
                      >
                        清除
                      </button>
                    </div>
                  </div>

                  {/* 音频（声音克隆） */}
                  <div className="bg-[#1a1f2a] border border-white/5 rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="text-white font-bold text-xs uppercase">声音克隆（音频）</p>
                        <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-1">MP3/WAV/M4A</p>
                      </div>
                      <div className="text-[10px] text-indigo-300 font-bold">
                        {displayMaterialName(audioFile, serverMaterialSlot(materialServer, 'audio'))}
                      </div>
                    </div>
                    <input
                      type="file"
                      ref={audioInputRef}
                      accept="audio/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void handleAudioUpload(file);
                      }}
                    />
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => audioInputRef.current?.click()}
                        disabled={!isConnected}
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          isConnected
                            ? 'bg-indigo-600 hover:bg-indigo-700 shadow-lg shadow-indigo-500/20 text-white'
                            : 'bg-slate-900 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        上传
                      </button>
                      <button
                        type="button"
                        onClick={() => void openMaterialPreview('audio', audioFile, 'audio')}
                        disabled={!canPreviewMaterial(audioFile, serverMaterialSlot(materialServer, 'audio'))}
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          canPreviewMaterial(audioFile, serverMaterialSlot(materialServer, 'audio'))
                            ? 'bg-indigo-600/10 border border-indigo-500/20 hover:bg-indigo-600/20 text-indigo-200'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        查看
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleClearMaterial('audio')}
                        disabled={
                          !audioFile && !serverMaterialSlot(materialServer, 'audio')?.uploaded
                        }
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          audioFile || serverMaterialSlot(materialServer, 'audio')?.uploaded
                            ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-500'
                        }`}
                      >
                        清除
                      </button>
                    </div>
                  </div>

                  {/* 环境演示视频（可选，三槽位） */}
                  <div className="bg-[#1a1f2a] border border-white/5 rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="text-white font-bold text-xs uppercase">环境演示视频（可选）</p>
                        <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-1">
                          画中画最多 3 段，每段 &lt;40 秒
                        </p>
                      </div>
                    </div>
                    <ShowcaseEnvPanel
                      variant="automation"
                      isConnected={isConnected}
                      materialServer={materialServer}
                      onRefresh={refreshMaterialServer}
                    />
                    <button
                      type="button"
                      onClick={() => void handleClearMaterial('showcase')}
                      disabled={!serverMaterialSlot(materialServer, 'showcase')?.uploaded}
                      className={`mt-2 w-full py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                        serverMaterialSlot(materialServer, 'showcase')?.uploaded
                          ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                          : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-500'
                      }`}
                    >
                      清除全部环境视频
                    </button>
                  </div>

                  {/* 背景音乐（可选） */}
                  <div className="bg-[#1a1f2a] border border-white/5 rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="text-white font-bold text-xs uppercase">背景音乐（可选）</p>
                        <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mt-1">MP3为主</p>
                      </div>
                      <div className="text-[10px] text-indigo-300 font-bold">
                        {displayMaterialName(
                          backgroundMusicFile,
                          serverMaterialSlot(materialServer, 'background_music'),
                        )}
                      </div>
                    </div>
                    <input
                      type="file"
                      ref={backgroundMusicInputRef}
                      accept="audio/mp3,audio/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void handleBackgroundMusicUpload(file);
                      }}
                    />
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => backgroundMusicInputRef.current?.click()}
                        disabled={!isConnected}
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          isConnected
                            ? 'bg-indigo-600 hover:bg-indigo-700 shadow-lg shadow-indigo-500/20 text-white'
                            : 'bg-slate-900 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        上传
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          void openMaterialPreview('background_music', backgroundMusicFile, 'audio')
                        }
                        disabled={
                          !canPreviewMaterial(
                            backgroundMusicFile,
                            serverMaterialSlot(materialServer, 'background_music'),
                          )
                        }
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          canPreviewMaterial(
                            backgroundMusicFile,
                            serverMaterialSlot(materialServer, 'background_music'),
                          )
                            ? 'bg-indigo-600/10 border border-indigo-500/20 hover:bg-indigo-600/20 text-indigo-200'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-400'
                        }`}
                      >
                        查看
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleClearMaterial('background_music')}
                        disabled={
                          !backgroundMusicFile &&
                          !serverMaterialSlot(materialServer, 'background_music')?.uploaded
                        }
                        className={`py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${
                          backgroundMusicFile ||
                          serverMaterialSlot(materialServer, 'background_music')?.uploaded
                            ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                            : 'bg-slate-900 border border-white/10 cursor-not-allowed opacity-50 text-slate-500'
                        }`}
                      >
                        清除
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {previewOpen && previewUrl && previewKind && (
              <div
                className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4"
                onClick={closePreview}
              >
                <div
                  className="bg-[#131720] border border-white/10 rounded-2xl p-4 max-w-4xl w-full"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-between gap-4 mb-3">
                    <div className="min-w-0">
                      <div className="text-white font-bold text-sm truncate">
                        查看预览：{previewTitle}
                      </div>
                      <div className="text-slate-400 text-xs mt-1">
                        （本地上传或服务端已保存的素材均可预览）
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={closePreview}
                      className="text-slate-400 hover:text-white transition-colors"
                      aria-label="关闭预览"
                    >
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>

                  <div className="max-h-[70vh] overflow-auto flex items-center justify-center">
                    {previewKind === 'image' && (
                      <img src={previewUrl} alt={previewTitle} className="max-w-full max-h-[70vh] rounded-lg" />
                    )}
                    {previewKind === 'audio' && (
                      <audio src={previewUrl} controls className="w-full" />
                    )}
                    {previewKind === 'video' && (
                      <video
                        src={previewUrl}
                        controls
                        playsInline
                        className="w-full max-h-[70vh] rounded-lg bg-black"
                      />
                    )}
                  </div>
                </div>
              </div>
            )}

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          {/* 链接输入 */}
          <section className="bg-[#131720] border border-white/5 rounded-2xl p-6 hover:border-white/10 transition-all">
            <div className="flex items-start space-x-6">
              <div className="w-10 h-10 bg-purple-500/10 text-purple-400 rounded-lg flex items-center justify-center font-bold flex-shrink-0 border border-purple-500/20">01</div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-4">输入视频链接</h3>
                <input
                  type="text"
                  value={link}
                  onChange={(e) => setLink(e.target.value)}
                  placeholder="请输入视频链接（抖音、快手、小红书等）..."
                  className="w-full bg-[#1a1f2a] border border-white/10 rounded-lg px-4 py-3 text-sm text-slate-300 outline-none focus:border-purple-500 placeholder:text-slate-600"
                />
                <p className="text-xs text-slate-500 mt-2">
                  系统将自动解析链接并提取视频内容
                </p>
              </div>
            </div>
          </section>

          {/* 文案生成 */}
          <section className="bg-[#131720] border border-white/5 rounded-2xl p-6 hover:border-white/10 transition-all">
            <div className="flex items-start space-x-6">
              <div className="w-10 h-10 bg-blue-500/10 text-blue-400 rounded-lg flex items-center justify-center font-bold flex-shrink-0 border border-blue-500/20">02</div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-2">文案生成</h3>
                <p className="text-sm text-slate-400">
                  AI将根据选择的模板对提取的文案进行优化和二创
                </p>
              </div>
            </div>
          </section>

          {/* 合规检测（可选） */}
          <section className="bg-[#131720] border border-white/5 rounded-2xl p-6 flex items-start space-x-6 hover:border-white/10 transition-all">
            <div className="w-10 h-10 bg-emerald-500/10 text-emerald-400 rounded-lg flex items-center justify-center font-bold flex-shrink-0 border border-emerald-500/20">03</div>
            <div className="flex-1">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="text-lg font-semibold text-white">合规检测（可选）</h3>
                  <p className="text-sm text-slate-500">敏感词库实时检测与风控拦截</p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setComplianceRulesOpen(true)}
                    className="px-4 py-2 bg-indigo-600/10 border border-indigo-500/20 text-indigo-200 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-600/20 transition-all"
                    title="添加客户自定义合规补充规则"
                  >
                    自定义规则
                  </button>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config.complianceEnabled}
                      onChange={(e) => setConfig(prev => ({ ...prev, complianceEnabled: e.target.checked }))}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
                  </label>
                </div>
              </div>

              {complianceExtraRules.trim() ? (
                <p className="text-[10px] text-indigo-200/90 font-black uppercase tracking-widest mt-3">
                  已启用客户自定义合规规则（将与系统规则一起生效）
                </p>
              ) : (
                <p className="text-[10px] text-slate-600 font-black uppercase tracking-widest mt-3">
                  未设置客户自定义规则（仅使用系统合规规则）
                </p>
              )}
            </div>
          </section>

          {complianceRulesOpen && (
            <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
              <div className="bg-[#131720] border border-white/10 rounded-2xl p-6 max-w-2xl w-full">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-white font-black text-sm uppercase tracking-widest">合规检测 · 客户自定义规则</h3>
                  <button
                    type="button"
                    onClick={() => setComplianceRulesOpen(false)}
                    className="text-slate-400 hover:text-white transition-colors"
                    aria-label="关闭"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                  这里填你行业里“不能出现的词/替换成什么/示例案例”。保存后，系统每次合规检测都会把这段内容一起给 AI 做改写。
                </p>

                <textarea
                  value={complianceExtraRules}
                  onChange={(e) => setComplianceExtraRules(e.target.value)}
                  placeholder="示例：\n- 禁用词：XX、YY、ZZ\n- 替换方式：XX→X某X；YY→Y某Y\n- 案例：遇到“XX保证有效”要改成“XX效果因人而异，建议咨询”\n"
                  className="w-full min-h-[220px] bg-[#0b0e14] border border-white/10 rounded-xl p-4 text-slate-200 outline-none focus:border-indigo-500 placeholder:text-slate-600"
                />

                <div className="mt-4 flex gap-3">
                  <button
                    type="button"
                    onClick={() => setComplianceExtraRules('')}
                    className="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl text-slate-300 text-xs font-black uppercase tracking-widest hover:bg-white/10 transition-all"
                  >
                    清空
                  </button>
                  <button
                    type="button"
                    onClick={saveComplianceExtraRules}
                    className="flex-1 py-3 bg-indigo-600 rounded-xl text-white text-xs font-black uppercase tracking-widest hover:bg-indigo-700 transition-all"
                  >
                    保存
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 素材生成 */}
          <section className="bg-[#131720] border border-white/5 rounded-2xl p-6 hover:border-white/10 transition-all">
            <div className="flex items-start space-x-6">
              <div className="w-10 h-10 bg-amber-500/10 text-amber-400 rounded-lg flex items-center justify-center font-bold flex-shrink-0 border border-amber-500/20">04</div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-2">素材生成</h3>
                <p className="text-sm text-slate-400">
                  将使用素材生产中的历史头像和音频自动生成视频
                </p>
              </div>
            </div>
          </section>

          {/* 发布平台选择 */}
          <section className="bg-[#131720] border border-white/5 rounded-2xl p-6 flex items-start space-x-6 hover:border-white/10 transition-all">
            <div className="w-10 h-10 bg-rose-500/10 text-rose-400 rounded-lg flex items-center justify-center font-bold flex-shrink-0 border border-rose-500/20">05</div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-white mb-4">选择发布平台</h3>
              <p className="text-xs text-slate-500 mb-4">
                点击选择要发布到的平台，选中的平台会高亮显示。多选时将按
                <span className="text-slate-400"> 抖音 → 快手 → 小红书 → 视频号 </span>
                顺序依次发布（同一浏览器自动化串行，不会同时多路启动）。
              </p>
              <div className="flex flex-wrap gap-4">
                {[
                  { id: 'douyin', name: '抖音' },
                  { id: 'kuaishou', name: '快手' },
                  { id: 'xhs', name: '小红书' },
                  { id: 'sph', name: '视频号' }
                ].map(p => {
                  const isSelected = config.platforms.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      onClick={() => togglePlatform(p.id)}
                      className={`px-6 py-3 rounded-xl border-2 text-sm font-bold transition-all ${
                        isSelected
                          ? 'bg-rose-500/20 border-rose-500 text-rose-400 shadow-lg shadow-rose-500/20 scale-105'
                          : 'bg-white/5 border-white/10 text-slate-500 hover:border-white/30 hover:bg-white/10'
                      }`}
                    >
                      {p.name}
                    </button>
                  );
                })}
              </div>
              <p className="text-xs text-slate-500 mt-4">
                已选择 {config.platforms.length} 个平台；成片与标题、描述与抖音发布使用同一套数据，快手仅填作品描述（无单独标题栏）。
              </p>
            </div>
          </section>

          <button
            onClick={() => {
              if (!link.trim()) {
                alert('请输入视频链接');
                return;
              }
              if (config.platforms.length === 0) {
                alert('请至少选择一个发布平台');
                return;
              }
              onStart(config, link.trim());
            }}
            disabled={!link.trim() || config.platforms.length === 0}
            className="w-full py-5 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl text-white font-bold text-lg shadow-xl shadow-indigo-500/20 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center space-x-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            <span>开始自动化流程</span>
          </button>
        </div>

        <div className="space-y-6">
          {/* 挖掘客户 */}
          <div className="relative rounded-2xl p-[1px] bg-gradient-to-br from-cyan-400/50 via-blue-600/25 to-transparent shadow-[0_0_40px_-12px_rgba(34,211,238,0.45)]">
            <div className="relative rounded-2xl bg-[#070b12] border border-cyan-500/10 overflow-hidden">
              <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-cyan-500/10 blur-2xl" />
              <div className="pointer-events-none absolute -bottom-6 -left-6 h-24 w-24 rounded-full bg-blue-600/10 blur-xl" />
              <div className="relative p-5 flex flex-col min-h-[300px]">
                <h3 className="text-center text-xl font-bold tracking-tight mb-1 bg-gradient-to-r from-cyan-200 via-sky-300 to-blue-400 bg-clip-text text-transparent drop-shadow-[0_0_20px_rgba(34,211,238,0.25)]">
                  挖掘客户
                </h3>
                <p className="text-center text-[10px] uppercase tracking-[0.2em] text-cyan-500/50 mb-5">Acquisition Matrix</p>

                <div className="grid grid-cols-2 gap-3 flex-1">
                  {[
                    { label: '今日私信成功', value: interceptStats?.today_dm ?? '—' },
                    { label: '今日评论成功', value: interceptStats?.today_comment ?? '—' },
                    {
                      label: '累计私信',
                      value:
                        typeof interceptStats?.total_dm === 'number'
                          ? String(interceptStats.total_dm).padStart(2, '0')
                          : '—',
                    },
                    {
                      label: '累计评论',
                      value:
                        typeof interceptStats?.total_comment === 'number'
                          ? String(interceptStats.total_comment).padStart(2, '0')
                          : '—',
                    },
                  ].map((row) => (
                    <div
                      key={row.label}
                      className="flex flex-col items-center justify-center text-center rounded-xl bg-black/40 border border-cyan-500/15 px-2 py-4 backdrop-blur-sm"
                    >
                      <span className="text-[11px] text-slate-500 leading-tight mb-2 px-1">{row.label}</span>
                      <span className="text-2xl font-mono font-bold tabular-nums text-transparent bg-clip-text bg-gradient-to-b from-cyan-200 to-cyan-500 drop-shadow-[0_0_14px_rgba(34,211,238,0.4)]">
                        {row.value}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-[9px] text-slate-600 text-center mt-2 px-1 leading-relaxed">
                  播放量/曝光未对接页面 DOM；统计以私信与评论 jsonl 成功记录为准。
                </p>

                <p className="text-[10px] text-center text-slate-500 mt-2 mb-2">
                  {interceptRunning ? (
                    <span className="text-cyan-300">
                      截流运行中{interceptPid != null ? ` · PID ${interceptPid}` : ''}
                    </span>
                  ) : (
                    <span>空闲</span>
                  )}
                </p>

                <div className="mt-1 flex-1 min-h-[100px] flex flex-col">
                  <p className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">运行日志</p>
                  <pre className="flex-1 text-[10px] leading-relaxed text-slate-400 bg-black/50 border border-cyan-500/10 rounded-lg p-2 overflow-y-auto max-h-[140px] font-mono whitespace-pre-wrap break-all">
                    {interceptLogs.length ? interceptLogs.join('\n') : '（无）'}
                  </pre>
                </div>

                <div className="mt-5 flex items-center justify-center gap-3">
                  <span className={`text-sm font-medium ${miningEnabled ? 'text-cyan-200' : 'text-slate-500'}`}>
                    启动挖掘客户
                  </span>
                  <label className="relative inline-flex cursor-pointer items-center">
                    <input
                      type="checkbox"
                      checked={miningEnabled}
                      onChange={(e) => onMiningToggle(e.target.checked)}
                      className="peer sr-only"
                    />
                    <div className="relative peer h-8 w-[3.25rem] shrink-0 rounded-full bg-slate-800 border border-white/10 shadow-inner transition-all peer-checked:border-cyan-500/40 peer-checked:bg-gradient-to-r peer-checked:from-cyan-600 peer-checked:to-blue-600 peer-focus-visible:ring-2 peer-focus-visible:ring-cyan-400/40 after:absolute after:left-1 after:top-1 after:h-6 after:w-6 after:rounded-full after:bg-white after:shadow-md after:transition-all after:content-[''] peer-checked:after:translate-x-[1.35rem]" />
                  </label>
                </div>
                <p className="text-[9px] text-slate-600 text-center mt-2">
                  关闭开关将停止截流。人设请在「文案创作 → 配置人设」填写；节奏每步 3～7 秒随机；命中意向词后默认再走豆包二判。
                </p>
              </div>
            </div>
          </div>

          {/* 自动回复 */}
          <div className="relative rounded-2xl p-[1px] bg-gradient-to-br from-violet-500/45 via-fuchsia-600/20 to-transparent shadow-[0_0_40px_-12px_rgba(167,139,250,0.4)]">
            <div className="relative rounded-2xl bg-[#070b12] border border-violet-500/10 overflow-hidden">
              <div className="pointer-events-none absolute -right-6 -top-10 h-28 w-28 rounded-full bg-violet-500/15 blur-2xl" />
              <button
                type="button"
                disabled={envChecking}
                onClick={runEnvCheck}
                className="absolute top-4 right-4 z-10 text-[10px] px-2.5 py-1 rounded-lg border border-violet-400/25 text-violet-200/80 hover:text-white hover:border-violet-400/50 hover:bg-violet-500/10 transition-colors disabled:opacity-50 disabled:cursor-wait"
              >
                {envChecking ? '检查中…' : '环境检查'}
              </button>

              <div className="relative p-5 pt-6 flex flex-col min-h-[340px]">
                <h3 className="text-center text-xl font-bold tracking-tight mb-1 bg-gradient-to-r from-violet-200 via-fuchsia-200 to-purple-300 bg-clip-text text-transparent drop-shadow-[0_0_18px_rgba(167,139,250,0.3)]">
                  自动回复
                </h3>
                <p className="text-center text-[10px] uppercase tracking-[0.2em] text-violet-400/45 mb-5">Direct Message Engine</p>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="flex flex-col items-center rounded-xl bg-black/40 border border-violet-500/15 px-2 py-3">
                    <span className="text-[11px] text-slate-500 mb-2">今日回复</span>
                    <span className="text-2xl font-mono font-bold tabular-nums text-transparent bg-clip-text bg-gradient-to-b from-violet-200 to-fuchsia-500 drop-shadow-[0_0_12px_rgba(192,132,252,0.35)]">
                      {hfToday === null ? '—' : hfToday}
                    </span>
                  </div>
                  <div className="flex flex-col items-center rounded-xl bg-black/40 border border-violet-500/15 px-2 py-3">
                    <span className="text-[11px] text-slate-500 mb-2">累计回复</span>
                    <span className="text-2xl font-mono font-bold tabular-nums text-transparent bg-clip-text bg-gradient-to-b from-violet-200 to-fuchsia-500 drop-shadow-[0_0_12px_rgba(192,132,252,0.35)]">
                      {hfTotal === null ? '—' : hfTotal}
                    </span>
                  </div>
                </div>

                <p className="text-center text-xs text-slate-500 mb-1">
                  <span
                    className={
                      envChecking
                        ? 'text-fuchsia-300'
                        : hfRunning
                          ? 'text-fuchsia-300'
                          : 'text-slate-500'
                    }
                  >
                    {envChecking ? '环境检测中…' : hfRunning ? '运行中' : '空闲'}
                  </span>
                  {!envChecking && hfQueued ? <span className="text-amber-400/90"> · 已排队</span> : null}
                </p>
                {hfLastErr ? (
                  <p className="text-center text-[10px] text-rose-400/90 break-all px-1 mb-3">{hfLastErr}</p>
                ) : (
                  <div className="mb-3 h-4" />
                )}

                {envCheck ? (
                  <div
                    className={`text-xs rounded-lg p-3 mb-4 border leading-relaxed ${
                      envCheck.all_ok ? 'border-emerald-500/30 text-slate-200 bg-emerald-950/25' : 'border-amber-500/30 text-slate-200 bg-amber-950/20'
                    }`}
                  >
                    {typeof envCheck.error === 'string' && envCheck.error ? (
                      <p className="text-rose-300 mb-2">暂时无法完成检测，请确认软件已启动后重试。</p>
                    ) : null}
                    {(Array.isArray(envCheck.customer_messages)
                      ? (envCheck.customer_messages as string[])
                      : envCheck.all_ok
                        ? ['检测完成，当前环境正常，可以开始使用自动回复。']
                        : ['检测完成，部分项目未通过，自动回复可能无法使用，请先处理或联系技术支持。']
                    ).map((line, i) => (
                      <p key={i} className="mb-2 last:mb-0 text-slate-200/95">
                        {line}
                      </p>
                    ))}
                  </div>
                ) : envChecking ? (
                  <p className="text-center text-xs text-violet-300/90 mb-4">正在为您检测运行环境，请稍候…</p>
                ) : (
                  <p className="text-center text-[10px] text-slate-500 mb-4">点击右上角「环境检查」或等待首次加载</p>
                )}

                <div className="mt-auto flex items-center justify-center gap-3 mb-4">
                  <span className={`text-sm font-medium ${hfTimerOn ? 'text-violet-200' : 'text-slate-500'}`}>开启自动回复</span>
                  <label className="relative inline-flex cursor-pointer items-center">
                    <input
                      type="checkbox"
                      checked={hfTimerOn}
                      onChange={(e) => onHfAutoToggle(e.target.checked)}
                      className="peer sr-only"
                    />
                    <div className="relative peer h-8 w-[3.25rem] shrink-0 rounded-full bg-slate-800 border border-white/10 shadow-inner transition-all peer-checked:border-fuchsia-500/40 peer-checked:bg-gradient-to-r peer-checked:from-violet-600 peer-checked:to-fuchsia-600 peer-focus-visible:ring-2 peer-focus-visible:ring-violet-400/40 after:absolute after:left-1 after:top-1 after:h-6 after:w-6 after:rounded-full after:bg-white after:shadow-md after:transition-all after:content-[''] peer-checked:after:translate-x-[1.35rem]" />
                  </label>
                </div>

                <button
                  type="button"
                  onClick={runHfOnce}
                  className="w-full py-3 rounded-xl font-bold text-sm text-white bg-gradient-to-r from-violet-600 via-fuchsia-600 to-purple-600 hover:from-violet-500 hover:via-fuchsia-500 hover:to-purple-500 shadow-[0_0_24px_-4px_rgba(168,85,247,0.55)] border border-white/10 transition-all active:scale-[0.99]"
                >
                  立即执行一次
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AutomationWorkflow;
