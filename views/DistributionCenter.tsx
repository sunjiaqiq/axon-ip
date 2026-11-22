
import React, { useState, useEffect } from 'react';
import { Platform } from '../types';

const Icons = {
  Douyin: () => <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-5.2 1.74 2.89 2.89 0 012.31-4.64 2.93 2.93 0 01.88.13V9.4a6.84 6.84 0 00-1-.05A6.33 6.33 0 005 20.1a6.34 6.34 0 0010.86-4.43v-7a8.16 8.16 0 004.77 1.52v-3.4a4.85 4.85 0 01-1.04-.1z"/></svg>,
  XHS: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>,
  Generic: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>,
  Browser: () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>,
  // 微信视频号（绿色风格）
  Sph: () => <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 01.213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.328.328 0 00.167-.054l1.903-1.114a.864.864 0 01.717-.098 10.16 10.16 0 002.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-3.691-6.348-7.444-6.348zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 01-1.162 1.178A1.17 1.17 0 014.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 01-1.162 1.178 1.17 1.17 0 01-1.162-1.178c0-.651.52-1.18 1.162-1.18zm5.34 2.867c-1.797-.052-3.746.512-5.28 1.786-1.72 1.428-2.687 3.72-1.78 6.22.942 2.453 3.666 4.229 6.884 4.229.826 0 1.622-.12 2.361-.336a.722.722 0 01.598.082l1.584.926a.272.272 0 00.14.047c.134 0 .24-.111.24-.247 0-.06-.023-.12-.038-.177l-.327-1.233a.49.49 0 01.177-.557C23.324 18.25 24 16.64 24 14.98c0-3.21-2.931-5.837-6.656-6.088V8.89c-.135-.01-.27-.027-.407-.03zm-2.53 3.274c.535 0 .969.44.969.982a.976.976 0 01-.969.983.976.976 0 01-.969-.983c0-.542.434-.982.97-.982zm4.844 0c.535 0 .969.44.969.982a.976.976 0 01-.969.983.976.976 0 01-.969-.983c0-.542.434-.982.969-.982z"/></svg>,
};

const DistributionCenter: React.FC = () => {
  const [publishing, setPublishing] = useState<{ [key: string]: boolean }>({});
  const [showPublishModal, setShowPublishModal] = useState<{ [key: string]: boolean }>({});
  const [publishForm, setPublishForm] = useState<{ [key: string]: { title: string; description: string; videoPath: string } }>({});
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [platformStatus, setPlatformStatus] = useState<{ [key: string]: boolean }>({
    douyin: false,
    kuaishou: false,
    xhs: false,
    sph: false
  });
  
  // 抖音、快手、小红书、视频号（视频号依赖 PC 微信，登录状态由后端/用户自行保证）
  const platforms: (Platform & { Icon: () => React.ReactElement })[] = [
    { id: 'douyin', name: '抖音', accountName: '', Icon: Icons.Douyin, status: 'connected', icon: '' },
    { id: 'kuaishou', name: '快手', accountName: '', Icon: Icons.Generic, status: 'connected', icon: '' },
    { id: 'xhs', name: '小红书', accountName: '', Icon: Icons.XHS, status: 'connected', icon: '' },
    { id: 'sph', name: '视频号', accountName: '', Icon: Icons.Sph, status: 'connected', icon: '' },
  ];

  // 检查平台登录状态
  const checkPlatformStatus = async () => {
    try {
      const response = await fetch('/api/browser/status');
      if (response.ok) {
        const data = await response.json();
        if (data.platforms) {
          setPlatformStatus(data.platforms);
        }
      }
    } catch (error) {
      console.error('检查平台状态失败:', error);
      // 网络错误时，所有平台显示为未连接
      setPlatformStatus({
        douyin: false,
        kuaishou: false,
        xhs: false,
        sph: false
      });
    }
  };

  // 实时检测平台状态
  useEffect(() => {
    checkPlatformStatus();
    // 每3秒检查一次状态
    const interval = setInterval(checkPlatformStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  // 登录处理
  const handleLogin = async (platformId?: string) => {
    setIsLoggingIn(true);
    try {
      const response = await fetch('/api/browser/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          platform: platformId || 'douyin'  // 默认打开抖音登录
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log('浏览器登录页面已打开:', result);
        // 等待一下后检查状态
        setTimeout(() => {
          checkPlatformStatus();
        }, 2000);
      } else {
        alert('打开登录页面失败，请检查后端服务');
      }
    } catch (error) {
      console.error('登录失败:', error);
      alert('连接后端服务失败');
    } finally {
      setIsLoggingIn(false);
    }
  };

  // 获取最新生成的视频路径（如果找不到，使用默认测试视频）
  const getLatestVideo = async (): Promise<string | null> => {
    try {
      // 获取所有任务
      const response = await fetch('/api/tasks');
      if (response.ok) {
        const data = await response.json();
        const tasks = data.tasks || {};
        
        // 找到最新的已完成任务
        let latestTask = null;
        let latestTime = 0;
        for (const [taskId, task] of Object.entries(tasks)) {
          const taskData = task as any;
          if (taskData.status === 'done' && taskData.output) {
            const createdAt = new Date(taskData.created_at).getTime();
            if (createdAt > latestTime) {
              latestTime = createdAt;
              latestTask = taskData;
            }
          }
        }
        
        if (latestTask && latestTask.output) {
          return latestTask.output;
        }
      }
    } catch (error) {
      console.error('获取最新视频失败:', error);
    }
    
    // 如果找不到最新视频，使用默认测试视频
    // 默认视频路径：使用素材生产里最新的视频文件
    const defaultVideos = [
      'F:\\shuziren\\pixelle_wrapper\\output\\20260314_193109_1a06fb65\\final.mp4',
      'F:\\shuziren\\pixelle_wrapper\\output\\20260314_192402_e7f416be\\final.mp4',
      'F:\\shuziren\\pixelle_wrapper\\output\\20260209_102225_07046dbe\\final.mp4'
    ];
    
    // 直接返回第一个默认视频（让后端去检查文件是否存在）
    console.log('未找到最新任务视频，使用默认测试视频:', defaultVideos[0]);
    return defaultVideos[0];
  };

  // 直接发布视频（使用成品素材的内容），与抖音共用同一路径、标题、描述
  const handlePublish = async (platformId: string) => {
    const supportedPlatforms = ['douyin', 'kuaishou', 'xhs', 'sph'];
    if (!supportedPlatforms.includes(platformId)) {
      alert('该平台发布功能开发中，目前支持：抖音、快手、小红书、视频号');
      return;
    }

    // 优先从localStorage读取成品素材的内容
    const finishedMaterialData = localStorage.getItem('finished_material_data');
    let videoPath: string | null = null;
    let title = '';
    let description = '';
    let coverText = '';
    
    if (finishedMaterialData) {
      try {
        const materialData = JSON.parse(finishedMaterialData);
        videoPath = materialData.videoPath || null;
        title = materialData.title || '';
        description = materialData.description || '';
        coverText = materialData.coverText || '';
      } catch (error) {
        console.error('解析成品素材数据失败:', error);
      }
    }
    
    // 如果成品素材中没有视频路径，尝试获取最新生成的视频
    if (!videoPath) {
      videoPath = await getLatestVideo();
    }
    
    if (!videoPath) {
      alert('未找到视频文件，请先在成品素材中保存视频路径');
      return;
    }
    
    // 如果没有标题，提示用户
    if (!title.trim()) {
      alert('请先在成品素材中填写标题并保存');
      return;
    }
    
    console.log('使用成品素材内容发布:', { videoPath, title, description, coverText });
    
    setPublishing({ ...publishing, [platformId]: true });

    const apiPath =
      platformId === 'sph'
        ? '/api/publish/sph'
        : platformId === 'xhs'
          ? '/api/publish/xhs'
          : platformId === 'kuaishou'
            ? '/api/publish/kuaishou'
            : '/api/publish/douyin';
    try {
      const response = await fetch(apiPath, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          video_path: videoPath,
          platform: platformId,
          title: title,
          description: description,
          cover_text: coverText || null
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        alert('发布任务已启动！浏览器将自动执行发布流程。');
      } else {
        const error = await response.json();
        alert(`发布失败: ${error.detail || '未知错误'}`);
      }
    } catch (error: any) {
      alert(`发布失败: ${error.message || '网络错误'}`);
    } finally {
      setPublishing({ ...publishing, [platformId]: false });
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <header className="mb-10 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2 uppercase tracking-tight">多平台分发中心</h1>
          <p className="text-slate-400">管理您的账号矩阵，实现内容一键全网分发</p>
        </div>
        <p className="text-slate-500 text-xs max-w-md text-right">
          请在下方各平台卡片内点击「浏览器登录」，打开与发布共用的 Chrome（抖音、小红书、快手等同套浏览器配置）。
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {platforms.map(p => {
          const isLoggedIn = platformStatus[p.id] || false;
          return (
            <div key={p.id} className="bg-[#131720] border border-white/5 rounded-2xl p-6 hover:bg-white/5 transition-all group">
              <div className="flex justify-between items-start mb-6">
                <div className="w-12 h-12 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center text-slate-300 group-hover:scale-110 transition-transform">
                  <p.Icon />
                </div>
                <div className={`w-3 h-3 rounded-full ${
                  isLoggedIn ? 'bg-green-500' : 'bg-red-500'
                }`} title={isLoggedIn ? '已登录' : '未登录'}></div>
              </div>
              <h3 className="text-lg font-bold text-white mb-4 uppercase tracking-tight">{p.name}</h3>
              
              <div className="space-y-4">
                <button
                  type="button"
                  onClick={() => handleLogin(p.id)}
                  disabled={isLoggingIn}
                  className="w-full py-2.5 bg-white/5 border border-white/10 text-sm font-bold uppercase tracking-widest rounded-lg hover:bg-white/10 transition-all text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Icons.Browser />
                  <span>{isLoggingIn ? '正在打开…' : '浏览器登录'}</span>
                </button>
                <button 
                  onClick={() => handlePublish(p.id)}
                  className="w-full py-3 bg-indigo-600 text-sm font-black uppercase tracking-widest rounded-lg hover:bg-indigo-500 transition-all text-white disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={publishing[p.id]}
                >
                  {publishing[p.id] ? '发布中...' : '发布'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

    </div>
  );
};

export default DistributionCenter;
