import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { videoSrcFromLocalPath } from '../utils/videoPreviewUrl';
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

const Icons = {
  Back: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>,
  User: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>,
  Box: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>,
  Mic: () => <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7-7v4m0 0H8m4 0h4m-4-8a3 3 0 013 3V10a3 3 0 01-3 3.5m0-6.5a3 3 0 00-3 3v3.5a3 3 0 003 3.5" /></svg>,
  File: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>,
  Upload: () => <svg className="w-6 h-6 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>,
  Copy: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>,
  External: () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>,
  Play: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
};

interface ConnectionStatus {
  status: 'connected' | 'disconnected';
  pixelle_available: boolean;
  qwen_key_configured: boolean;
  runninghub_key_configured: boolean;
  message: string;
}

const OralBroadcastDetail: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [script, setScript] = useState('');
  
  // 从localStorage读取当前使用的文案（从文案生产或合规检测来的）
  useEffect(() => {
    const currentScript = localStorage.getItem('current_script');
    if (currentScript) {
      setScript(currentScript);
    }
  }, []);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [productFile, setProductFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [backgroundMusicFile, setBackgroundMusicFile] = useState<File | null>(null);
  const [materialServer, setMaterialServer] = useState<MaterialCurrentStateApi | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewKind, setPreviewKind] = useState<'image' | 'audio' | 'video' | null>(null);
  const [previewTitle, setPreviewTitle] = useState('');
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [outputUrl, setOutputUrl] = useState<string | null>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const productInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const backgroundMusicInputRef = useRef<HTMLInputElement>(null);
  const statusCheckIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const resultPreviewSrc = useMemo(() => videoSrcFromLocalPath(outputUrl), [outputUrl]);

  // 检查连接状态
  const checkConnectionStatus = async () => {
    try {
      const response = await fetch('/api/connection_status');
      if (response.ok) {
        const data: ConnectionStatus = await response.json();
        console.log('[连接检查] 后端响应:', data);
        setConnectionStatus(data);
        setIsConnected(data.status === 'connected');
        if (data.status === 'connected') {
          console.log('[连接检查] ✅ 已连接');
        } else {
          console.log('[连接检查] ❌ 未连接:', data.message);
        }
      } else {
        console.error('[连接检查] HTTP错误:', response.status);
        setIsConnected(false);
      }
    } catch (error) {
      console.error('[连接检查] 请求失败:', error);
      setIsConnected(false);
    }
  };

  // 组件挂载时开始检查连接状态
  useEffect(() => {
    // 立即检查一次
    checkConnectionStatus();
    
    // 每2秒检查一次
    statusCheckIntervalRef.current = setInterval(() => {
      checkConnectionStatus();
    }, 2000);

    return () => {
      if (statusCheckIntervalRef.current) {
        clearInterval(statusCheckIntervalRef.current);
      }
    };
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
    if (!isConnected) return;
    void refreshMaterialServer();
  }, [isConnected, refreshMaterialServer]);

  useEffect(() => {
    const id = window.setInterval(() => {
      if (isConnected) void refreshMaterialServer();
    }, 5000);
    return () => clearInterval(id);
  }, [isConnected, refreshMaterialServer]);

  const closePreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewOpen(false);
    setPreviewUrl(null);
    setPreviewKind(null);
    setPreviewTitle('');
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
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const url = URL.createObjectURL(localFile);
      setPreviewUrl(url);
      setPreviewKind(mediaKind);
      setPreviewTitle(localFile.name);
      setPreviewOpen(true);
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

  const oralMaterialReady = materialServer?.can_generate_oral === true;

  // 上传头像
  const handleAvatarUpload = async (file: File) => {
    if (!isConnected) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch('/api/avatar', {
        method: 'POST',
        body: formData,
      });
      
      if (response.ok) {
        const data = await response.json();
        setAvatarFile(file);
        console.log('头像上传成功:', data);
        await refreshMaterialServer();
      } else {
        alert('头像上传失败');
      }
    } catch (error) {
      console.error('上传头像失败:', error);
      alert('上传头像失败');
    }
  };

  // 上传产品图片
  const handleProductUpload = async (file: File) => {
    if (!isConnected) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch('/api/product', {
        method: 'POST',
        body: formData,
      });
      
      if (response.ok) {
        const data = await response.json();
        setProductFile(file);
        console.log('产品图片上传成功:', data);
        await refreshMaterialServer();
      } else {
        alert('产品图片上传失败');
      }
    } catch (error) {
      console.error('上传产品图片失败:', error);
      alert('上传产品图片失败');
    }
  };

  // 上传音频（声音克隆）
  const handleAudioUpload = async (file: File) => {
    if (!isConnected) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch('/api/audio', {
        method: 'POST',
        body: formData,
      });
      
      if (response.ok) {
        const data = await response.json();
        setAudioFile(file);
        console.log('声音克隆音频上传成功:', data);
        await refreshMaterialServer();
      } else {
        const errorText = await response.text();
        alert(`声音克隆音频上传失败: ${errorText}`);
      }
    } catch (error) {
      console.error('上传声音克隆音频失败:', error);
      alert('上传声音克隆音频失败');
    }
  };

  // 上传背景音乐
  const handleBackgroundMusicUpload = async (file: File) => {
    if (!isConnected) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch('/api/background_music', {
        method: 'POST',
        body: formData,
      });
      
      if (response.ok) {
        const data = await response.json();
        setBackgroundMusicFile(file);
        console.log('背景音乐上传成功:', data);
        await refreshMaterialServer();
      } else {
        const errorText = await response.text();
        alert(`背景音乐上传失败: ${errorText}`);
      }
    } catch (error) {
      console.error('上传背景音乐失败:', error);
      alert('上传背景音乐失败');
    }
  };

  // 设置文案
  const handleSetText = async (text: string) => {
    if (!isConnected) return;
    
    try {
      const response = await fetch('/api/text', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      });
      
      if (response.ok) {
        console.log('文案设置成功');
      } else {
        alert('文案设置失败');
      }
    } catch (error) {
      console.error('设置文案失败:', error);
      alert('设置文案失败');
    }
  };

  // 生成视频
  const handleGenerate = async () => {
    if (!isConnected) {
      alert('后台未连接，无法生成视频');
      return;
    }

    if (!script.trim()) {
      alert('请输入脚本提示词');
      return;
    }

    setGenerating(true);
    setProgress(0);

    try {
      // 先设置文案
      await handleSetText(script);

      // 调用生成接口
      console.log('[生成] 开始调用 /api/generate 接口...');
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ defer_finalize: true }),
      });

      console.log('[生成] 收到响应，状态码:', response.status);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: '未知错误' }));
        console.error('[生成] 生成失败:', errorData);
        throw new Error(errorData.detail || '生成失败');
      }

      const data = await response.json();
      console.log('[生成] 任务已创建，task_id:', data.task_id);
      if (!data.task_id) {
        throw new Error('后端未返回 task_id');
      }
      setTaskId(data.task_id);

      // 轮询任务状态（无超时限制，直到任务完成）
      const pollTaskStatus = async () => {
        try {
          const statusResponse = await fetch(`/api/task/${data.task_id}`);
          if (statusResponse.ok) {
            const statusData = await statusResponse.json();
            console.log('[任务状态]', statusData);
            setProgress(statusData.progress || 0);

            // 后端返回的状态是 'done' 而不是 'completed'
            if (statusData.status === 'done' || statusData.status === 'completed') {
              setGenerating(false);
              setProgress(100);
              if (statusData.output) {
                setOutputUrl(statusData.output);
                console.log('[任务完成] 视频路径:', statusData.output);
                const basePath = (statusData as any).base_video_path || statusData.output;
                localStorage.setItem('latest_video_path', basePath);
                localStorage.setItem('manual_base_video_path', basePath);
                localStorage.setItem('latest_script', script);
                const segs = (statusData as any).subtitle_segments;
                if (Array.isArray(segs)) {
                  localStorage.setItem('manual_subtitle_segments', JSON.stringify(segs));
                } else {
                  localStorage.removeItem('manual_subtitle_segments');
                }
              }
            } else if (statusData.status === 'error' || statusData.status === 'failed') {
              setGenerating(false);
              alert(`生成失败: ${statusData.error || statusData.message || '未知错误'}`);
            } else {
              // 继续轮询（状态为 'running' 或其他）
              setTimeout(pollTaskStatus, 1000);
            }
          } else if (statusResponse.status === 404) {
            // 任务不存在，可能是后端重启了
            console.error('[任务状态] 任务不存在 (404)，可能后端已重启');
            setGenerating(false);
            alert('任务不存在，可能后端服务已重启。请重新生成视频。');
          } else {
            console.error('[任务状态] HTTP错误:', statusResponse.status);
            setTimeout(pollTaskStatus, 1000);
          }
        } catch (error) {
          console.error('[任务状态] 请求失败:', error);
          setTimeout(pollTaskStatus, 1000);
        }
      };

      setTimeout(pollTaskStatus, 1000);
    } catch (error: any) {
      setGenerating(false);
      alert(error.message || '生成失败，请重试');
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <header className="mb-8 flex justify-between items-center">
        <div>
            <nav className="flex items-center space-x-2 text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
                <span>口播视频生成</span>
                <span className="text-slate-700">/</span>
                <span className="text-indigo-400">创作工作室</span>
            </nav>
            <h1 className="text-3xl font-bold text-white uppercase tracking-tight">口播视频生成</h1>
        </div>
        <div className="flex items-center space-x-4">
          {/* 连接状态指示器 */}
          <div className="flex items-center space-x-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`}></div>
            <span className={`text-xs font-bold uppercase tracking-widest ${isConnected ? 'text-emerald-400' : 'text-rose-400'}`}>
              {isConnected ? '已连接' : '未连接'}
            </span>
            {connectionStatus && !isConnected && connectionStatus.message && (
              <span className="text-[10px] text-rose-400/70 ml-2" title={connectionStatus.message}>
                ({connectionStatus.message})
              </span>
            )}
          </div>
          <button onClick={onBack} className="px-5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-xs font-bold uppercase tracking-widest text-slate-400 hover:bg-white/10 flex items-center space-x-2 transition-all">
              <Icons.Back />
              <span>返回中心</span>
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-6">
          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 text-center hover:border-indigo-500/30 transition-all group">
            <div className="w-10 h-10 bg-indigo-500/10 text-indigo-400 rounded-lg flex items-center justify-center mx-auto mb-3 border border-indigo-500/20">
                <Icons.User />
            </div>
            <h4 className="text-white font-bold text-xs uppercase mb-1">人物视觉素材</h4>
            <p className="text-slate-500 text-[10px] mb-3 font-bold uppercase tracking-widest">支持AI透明背景</p>
            <input
              type="file"
              ref={avatarInputRef}
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleAvatarUpload(file);
              }}
              disabled={!isConnected}
            />
            <div 
              className={`border-2 border-dashed rounded-xl p-6 flex flex-col items-center justify-center transition-all ${
                isConnected 
                  ? 'border-white/5 bg-white/2 cursor-pointer hover:bg-white/5 hover:border-indigo-500/30' 
                  : 'border-slate-800 bg-slate-900/50 cursor-not-allowed opacity-50'
              }`}
              onClick={() => {
                if (isConnected) {
                  avatarInputRef.current?.click();
                }
              }}
            >
              <Icons.Upload />
              {avatarFile || serverMaterialSlot(materialServer, 'avatar')?.uploaded ? (
                <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 mt-2">
                  {displayMaterialName(avatarFile, serverMaterialSlot(materialServer, 'avatar'))}
                </p>
              ) : (
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">拖拽图片到此处或 <span className="text-indigo-400">点击选择</span></p>
              )}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 max-w-xs mx-auto">
              <button
                type="button"
                onClick={() => void openMaterialPreview('avatar', avatarFile, 'image')}
                disabled={!canPreviewMaterial(avatarFile, serverMaterialSlot(materialServer, 'avatar'))}
                className={`py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider ${
                  canPreviewMaterial(avatarFile, serverMaterialSlot(materialServer, 'avatar'))
                    ? 'bg-indigo-600/15 border border-indigo-500/30 text-indigo-200 hover:bg-indigo-600/25'
                    : 'bg-slate-900 border border-white/5 text-slate-600 cursor-not-allowed'
                }`}
              >
                查看
              </button>
              <button
                type="button"
                onClick={() => void handleClearMaterial('avatar')}
                disabled={!avatarFile && !serverMaterialSlot(materialServer, 'avatar')?.uploaded}
                className={`py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider ${
                  avatarFile || serverMaterialSlot(materialServer, 'avatar')?.uploaded
                    ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                    : 'bg-slate-900 border border-white/5 text-slate-600 cursor-not-allowed'
                }`}
              >
                清除
              </button>
            </div>
          </div>

          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 text-center hover:border-blue-500/30 transition-all group">
            <div className="w-10 h-10 bg-blue-500/10 text-blue-400 rounded-lg flex items-center justify-center mx-auto mb-3 border border-blue-500/20">
                <Icons.Box />
            </div>
            <h4 className="text-white font-bold text-xs uppercase mb-1">产品图片素材</h4>
            <p className="text-slate-500 text-[10px] mb-3 font-bold uppercase tracking-widest">可选3D增强</p>
            <input
              type="file"
              ref={productInputRef}
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleProductUpload(file);
              }}
              disabled={!isConnected}
            />
            <div 
              className={`border-2 border-dashed rounded-xl p-6 flex flex-col items-center justify-center transition-all ${
                isConnected 
                  ? 'border-white/5 bg-white/2 cursor-pointer hover:bg-white/5 hover:border-blue-500/30' 
                  : 'border-slate-800 bg-slate-900/50 cursor-not-allowed opacity-50'
              }`}
              onClick={() => {
                if (isConnected) {
                  productInputRef.current?.click();
                }
              }}
            >
              <Icons.Upload />
              {productFile || serverMaterialSlot(materialServer, 'product')?.uploaded ? (
                <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 mt-2">
                  {displayMaterialName(productFile, serverMaterialSlot(materialServer, 'product'))}
                </p>
              ) : (
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">拖拽图片到此处或 <span className="text-indigo-400">点击选择</span></p>
              )}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 max-w-xs mx-auto">
              <button
                type="button"
                onClick={() => void openMaterialPreview('product', productFile, 'image')}
                disabled={!canPreviewMaterial(productFile, serverMaterialSlot(materialServer, 'product'))}
                className={`py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider ${
                  canPreviewMaterial(productFile, serverMaterialSlot(materialServer, 'product'))
                    ? 'bg-indigo-600/15 border border-indigo-500/30 text-indigo-200 hover:bg-indigo-600/25'
                    : 'bg-slate-900 border border-white/5 text-slate-600 cursor-not-allowed'
                }`}
              >
                查看
              </button>
              <button
                type="button"
                onClick={() => void handleClearMaterial('product')}
                disabled={!productFile && !serverMaterialSlot(materialServer, 'product')?.uploaded}
                className={`py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider ${
                  productFile || serverMaterialSlot(materialServer, 'product')?.uploaded
                    ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                    : 'bg-slate-900 border border-white/5 text-slate-600 cursor-not-allowed'
                }`}
              >
                清除
              </button>
            </div>
          </div>

          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 text-center hover:border-amber-500/30 transition-all group">
            <div className="w-10 h-10 bg-amber-500/10 text-amber-400 rounded-lg flex items-center justify-center mx-auto mb-3 border border-amber-500/20">
                <Icons.Play />
            </div>
            <h4 className="text-white font-bold text-xs uppercase mb-1">环境演示视频（画中画）</h4>
            <p className="text-slate-500 text-[10px] mb-3 font-bold uppercase tracking-widest">
              可选；最多 3 段，每段 &lt;40 秒
            </p>
            <ShowcaseEnvPanel
              variant="oral"
              isConnected={isConnected}
              materialServer={materialServer}
              onRefresh={refreshMaterialServer}
            />
            <button
              type="button"
              onClick={() => void handleClearMaterial('showcase')}
              disabled={!serverMaterialSlot(materialServer, 'showcase')?.uploaded}
              className={`mt-3 w-full max-w-xs mx-auto py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider ${
                serverMaterialSlot(materialServer, 'showcase')?.uploaded
                  ? 'bg-rose-600/15 border border-rose-500/30 text-rose-200 hover:bg-rose-600/25'
                  : 'bg-slate-900 border border-white/5 text-slate-600 cursor-not-allowed'
              }`}
            >
              清除全部环境视频
            </button>
          </div>

          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 flex items-center space-x-4">
            <div className="w-12 h-12 bg-purple-500/10 text-purple-400 rounded-xl flex items-center justify-center flex-shrink-0 border border-purple-500/20">
                <Icons.Mic />
            </div>
            <div className="flex-1">
                <h4 className="text-white font-bold text-xs uppercase mb-1">声音克隆</h4>
                <p className="text-slate-500 text-[10px] mb-2 font-bold uppercase tracking-widest">MP3, WAV, M4A (最少5秒)</p>
                <input
                  type="file"
                  ref={audioInputRef}
                  accept="audio/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleAudioUpload(file);
                  }}
                  disabled={!isConnected}
                />
                <div className="flex flex-wrap items-center gap-2">
                    <button 
                      onClick={() => {
                        if (isConnected) {
                          audioInputRef.current?.click();
                        } else {
                          alert('请等待后台连接成功后再上传音频');
                        }
                      }}
                      disabled={!isConnected}
                      className={`px-4 py-2 text-white text-xs font-bold uppercase tracking-widest rounded-lg transition-all ${
                        isConnected 
                          ? 'bg-indigo-600 hover:bg-indigo-700 shadow-lg shadow-indigo-500/20' 
                          : 'bg-slate-900 cursor-not-allowed opacity-50'
                      }`}
                    >
                      {displayMaterialName(audioFile, serverMaterialSlot(materialServer, 'audio')) === '未选择'
                        ? '选择音频文件'
                        : displayMaterialName(audioFile, serverMaterialSlot(materialServer, 'audio'))}
                    </button>
                    <button
                      type="button"
                      onClick={() => void openMaterialPreview('audio', audioFile, 'audio')}
                      disabled={!canPreviewMaterial(audioFile, serverMaterialSlot(materialServer, 'audio'))}
                      className={`px-3 py-2 text-[10px] font-bold uppercase tracking-wider rounded-lg border ${
                        canPreviewMaterial(audioFile, serverMaterialSlot(materialServer, 'audio'))
                          ? 'border-indigo-500/30 text-indigo-200 bg-indigo-600/10 hover:bg-indigo-600/20'
                          : 'border-white/5 text-slate-600 cursor-not-allowed'
                      }`}
                    >
                      查看
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleClearMaterial('audio')}
                      disabled={!audioFile && !serverMaterialSlot(materialServer, 'audio')?.uploaded}
                      className={`px-3 py-2 text-[10px] font-bold uppercase tracking-wider rounded-lg border ${
                        audioFile || serverMaterialSlot(materialServer, 'audio')?.uploaded
                          ? 'border-rose-500/30 text-rose-200 bg-rose-600/10 hover:bg-rose-600/20'
                          : 'border-white/5 text-slate-600 cursor-not-allowed'
                      }`}
                    >
                      清除
                    </button>
                    <span className="text-[10px] text-slate-600 font-bold">最大 200MB</span>
                </div>
            </div>
          </div>

          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 flex items-center space-x-4">
            <div className="w-12 h-12 bg-amber-500/10 text-amber-400 rounded-xl flex items-center justify-center flex-shrink-0 border border-amber-500/20">
                <Icons.Mic />
            </div>
            <div className="flex-1">
                <h4 className="text-white font-bold text-xs uppercase mb-1">背景音乐</h4>
                <p className="text-slate-500 text-[10px] mb-2 font-bold uppercase tracking-widest">MP3格式（可选，不选则使用默认音乐）</p>
                <input
                  type="file"
                  ref={backgroundMusicInputRef}
                  accept="audio/mp3,audio/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleBackgroundMusicUpload(file);
                  }}
                  disabled={!isConnected}
                />
                <div className="flex flex-wrap items-center gap-2">
                    <button 
                      onClick={() => {
                        if (isConnected) {
                          backgroundMusicInputRef.current?.click();
                        } else {
                          alert('请等待后台连接成功后再上传背景音乐');
                        }
                      }}
                      disabled={!isConnected}
                      className={`px-4 py-2 text-white text-xs font-bold uppercase tracking-widest rounded-lg transition-all ${
                        isConnected 
                          ? 'bg-amber-600 hover:bg-amber-700 shadow-lg shadow-amber-500/20' 
                          : 'bg-slate-900 cursor-not-allowed opacity-50'
                      }`}
                    >
                      {displayMaterialName(
                        backgroundMusicFile,
                        serverMaterialSlot(materialServer, 'background_music'),
                      ) === '未选择'
                        ? '选择背景音乐（可选）'
                        : displayMaterialName(
                            backgroundMusicFile,
                            serverMaterialSlot(materialServer, 'background_music'),
                          )}
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
                      className={`px-3 py-2 text-[10px] font-bold uppercase tracking-wider rounded-lg border ${
                        canPreviewMaterial(
                          backgroundMusicFile,
                          serverMaterialSlot(materialServer, 'background_music'),
                        )
                          ? 'border-amber-500/30 text-amber-200 bg-amber-600/10 hover:bg-amber-600/20'
                          : 'border-white/5 text-slate-600 cursor-not-allowed'
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
                      className={`px-3 py-2 text-[10px] font-bold uppercase tracking-wider rounded-lg border ${
                        backgroundMusicFile ||
                        serverMaterialSlot(materialServer, 'background_music')?.uploaded
                          ? 'border-rose-500/30 text-rose-200 bg-rose-600/10 hover:bg-rose-600/20'
                          : 'border-white/5 text-slate-600 cursor-not-allowed'
                      }`}
                    >
                      清除
                    </button>
                    <span className="text-[10px] text-slate-600 font-bold">最大 200MB</span>
                </div>
            </div>
          </div>
        </div>

        <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 flex flex-col h-full">
            <div className="flex items-center space-x-3 mb-4">
                <div className="w-8 h-8 bg-emerald-500/10 text-emerald-400 rounded-lg flex items-center justify-center border border-emerald-500/20">
                    <Icons.File />
                </div>
                <h3 className="text-lg font-bold text-white uppercase tracking-tight">脚本文案</h3>
            </div>
            <textarea 
                value={script}
                onChange={(e) => setScript(e.target.value)}
                disabled={!isConnected}
                className={`flex-1 bg-[#1a1f2a] border rounded-xl p-4 text-slate-300 text-xs outline-none resize-none mb-4 font-medium leading-relaxed ${
                  isConnected 
                    ? 'border-white/10 focus:border-indigo-500' 
                    : 'border-slate-800 opacity-50 cursor-not-allowed'
                }`}
                placeholder={isConnected ? "请输入视频生成的文案内容..." : "请等待后台连接成功..."}
            ></textarea>
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2 text-indigo-400">
                    {generating ? (
                        <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                    ) : (
                        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-rose-500'}`}></div>
                    )}
                    <span className="text-[10px] font-bold uppercase tracking-widest">
                        {generating
                          ? '生成中...'
                          : !isConnected
                            ? '等待连接中...'
                            : oralMaterialReady
                              ? '系统就绪'
                              : '请上传人物图与口播音频'}
                    </span>
                </div>
                <div className="flex-1 mx-4 h-1 bg-slate-800 rounded-full overflow-hidden">
                    <div 
                        className="h-full bg-gradient-to-r from-indigo-500 to-cyan-500 transition-all duration-300"
                        style={{ width: `${progress}%` }}
                    ></div>
                </div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{progress}%</span>
            </div>
            <button 
                onClick={handleGenerate}
                disabled={!isConnected || generating || !script.trim() || !oralMaterialReady}
                className={`w-full py-3 rounded-xl font-black text-xs uppercase tracking-widest transition-all flex items-center justify-center space-x-2 shadow-lg ${
                    isConnected && !generating && script.trim() && oralMaterialReady
                        ? 'bg-sky-500 text-slate-950 hover:bg-sky-400 shadow-sky-500/20'
                        : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                }`}
            >
                <Icons.Play />
                <span>{generating ? '生成中...' : '开始生成视频'}</span>
            </button>
        </div>
      </div>
      
      {outputUrl && (
        <div className="mt-8 bg-[#131720] border border-white/5 rounded-2xl p-6 space-y-4">
          <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-500">生成结果</h4>
          {resultPreviewSrc ? (
            <div className="bg-[#0b0e14] rounded-xl overflow-hidden border border-white/5 max-h-[min(70vh,520px)] mx-auto flex items-center justify-center">
              <video
                key={resultPreviewSrc}
                src={resultPreviewSrc}
                controls
                playsInline
                className="w-full max-h-[min(70vh,520px)] object-contain bg-black"
              />
            </div>
          ) : null}
          <div className="bg-[#0b0e14] rounded-xl p-4 flex items-center justify-between border border-white/5 gap-3">
            <span className="text-slate-400 text-xs font-mono truncate min-w-0">{outputUrl}</span>
            <div className="flex items-center space-x-3 shrink-0">
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(outputUrl);
                }}
                className="p-2 text-slate-500 hover:text-white transition-all"
              >
                <Icons.Copy />
              </button>
              <button
                type="button"
                onClick={() => {
                  if (resultPreviewSrc) window.open(resultPreviewSrc, '_blank', 'noopener,noreferrer');
                }}
                className="p-2 text-slate-500 hover:text-white transition-all"
                title="新标签页打开预览"
              >
                <Icons.External />
              </button>
            </div>
          </div>
        </div>
      )}

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
              <div className="min-w-0 text-white font-bold text-sm truncate">查看预览：{previewTitle}</div>
              <button
                type="button"
                onClick={closePreview}
                className="text-slate-400 hover:text-white shrink-0"
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
    </div>
  );
};

export default OralBroadcastDetail;
