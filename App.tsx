
import React, { useState } from 'react';
import { ViewType, WorkflowConfig } from './types';
import Sidebar from './components/Sidebar';
import StartupLoginGate, { isCustomerAuthed } from './components/StartupLoginGate';
import AutomationWorkflow from './views/AutomationWorkflow';
import MaterialProduction from './views/MaterialProduction';
import OralBroadcastDetail from './views/OralBroadcastDetail';
import CopywritingProduction from './views/CopywritingProduction';
import ComplianceStation from './views/ComplianceStation';
import DistributionCenter from './views/DistributionCenter';
import AvatarLiveModule from './views/AvatarLiveModule';
import FinishedMaterial from './views/FinishedMaterial';
import Settings from './views/Settings';
import ExecutionProgress from './views/ExecutionProgress';

const App: React.FC = () => {
  const [showStartupGate, setShowStartupGate] = useState(() => !isCustomerAuthed());
  const [currentView, setCurrentView] = useState<ViewType>(ViewType.AUTOMATION);
  const [workflow, setWorkflow] = useState<WorkflowConfig>({
    copywritingTemplate: '爆款钩子 (Hook) 模型',
    complianceEnabled: true,
    materialModule: 'AI 真人口播',
    platforms: ['douyin', 'kuaishou', 'xhs', 'sph']
  });

  const handleStartAutomation = async (config: WorkflowConfig, link?: string) => {
    // 如果有链接，先调用API获取任务ID，然后再切换视图
    if (link) {
      try {
        // 先清理旧的task_id，确保获取到新的ID
        localStorage.removeItem('auto_task_id');
        
        // 读取文案生成页面保存的人设配置（只读取文案需要的字段）
        let personaConfig = null;
        try {
          const savedPersonaConfig = localStorage.getItem('personaConfig');
          if (savedPersonaConfig) {
            const fullPersonaConfig = JSON.parse(savedPersonaConfig);
            // 只提取文案需要的字段：公司名字、目标市场、核心解决方案、产品年限、产品优势、其他
            personaConfig = {
              companyName: fullPersonaConfig.companyName || '',
              targetMarket: fullPersonaConfig.targetMarket || '',
              coreSolution: fullPersonaConfig.coreSolution || '',
              productYears: fullPersonaConfig.productYears || '',
              productAdvantages: fullPersonaConfig.productAdvantages || '',
              other: fullPersonaConfig.other || ''
            };
            // 如果所有字段都为空，则不传递
            if (Object.values(personaConfig).every(v => !v)) {
              personaConfig = null;
            }
          }
        } catch (e) {
          console.error('读取人设配置失败:', e);
        }
        
        const requestBody: any = {
          link: link,
          compliance_enabled: config.complianceEnabled,
          platforms: config.platforms
        };

        // 合规检测补充规则（与合规站/自动化共用；只做增强，不影响现有逻辑）
        try {
          const extra = localStorage.getItem('compliance_extra_rules');
          if (extra && extra.trim()) {
            requestBody.compliance_extra_rules = extra;
          }
        } catch {
          /* ignore */
        }

        // 挖掘客户/自动回复状态（用于发布期调度：发布期间互斥，让其它模块让路）
        try {
          const hf_auto_enabled = localStorage.getItem('hf_auto_reply_auto_enabled') === '1';
          const hf_timer_enabled = localStorage.getItem('hf_auto_reply_timer_enabled') === '1';
          requestBody.hf_enabled = Boolean(hf_auto_enabled || hf_timer_enabled);
          requestBody.mining_enabled = localStorage.getItem('mining_client_enabled') === '1';
        } catch {
          requestBody.hf_enabled = false;
          requestBody.mining_enabled = false;
        }
        
        // 如果有人设配置，添加到请求中
        if (personaConfig) {
          requestBody.persona_config = personaConfig;
        }
        
        const response = await fetch('/api/auto_generate_full', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody)
        });
        
        if (response.ok) {
          const result = await response.json();
          console.log('自动化流程启动成功:', result);
          // 将task_id保存到localStorage，供ExecutionProgress使用
          if (result.task_id) {
            localStorage.setItem('auto_task_id', result.task_id);
            // 确保task_id保存后再切换视图
            setWorkflow(config);
            setCurrentView(ViewType.EXECUTION);
          } else {
            alert('启动失败：未获取到任务ID');
          }
        } else {
          const errorText = await response.text();
          console.error('自动化流程启动失败:', errorText);
          alert(`启动失败: ${errorText}`);
        }
      } catch (error) {
        console.error('调用自动化流程接口出错:', error);
        alert(`启动失败: ${error}`);
      }
    } else {
      // 没有链接，直接切换视图
      setWorkflow(config);
      setCurrentView(ViewType.EXECUTION);
    }
  };

  const renderView = () => {
    switch (currentView) {
      case ViewType.AUTOMATION:
        return <AutomationWorkflow onStart={handleStartAutomation} config={workflow} setConfig={setWorkflow} />;
      case ViewType.MATERIAL:
        return <MaterialProduction onSelectModule={(mod) => mod === '口播视频' ? setCurrentView(ViewType.ORAL_BROADCAST) : null} />;
      case ViewType.ORAL_BROADCAST:
        return <OralBroadcastDetail onBack={() => setCurrentView(ViewType.MATERIAL)} />;
      case ViewType.COPYWRITING:
        return <CopywritingProduction />;
      case ViewType.COMPLIANCE:
        return <ComplianceStation />;
      case ViewType.DISTRIBUTION:
        return <DistributionCenter />;
      case ViewType.AVATAR_LIVE:
        return <AvatarLiveModule />;
      case ViewType.FINISHED_MATERIAL:
        return <FinishedMaterial />;
      case ViewType.SETTINGS:
        return <Settings />;
      case ViewType.EXECUTION:
        return <ExecutionProgress onFinish={() => setCurrentView(ViewType.AUTOMATION)} />;
      default:
        return <AutomationWorkflow onStart={handleStartAutomation} config={workflow} setConfig={setWorkflow} />;
    }
  };

  if (showStartupGate) {
    return <StartupLoginGate onSuccess={() => setShowStartupGate(false)} />;
  }

  return (
    <div className="flex h-screen bg-[#0b0e14] text-slate-200 overflow-hidden">
      <Sidebar activeView={currentView} onViewChange={setCurrentView} />
      <main className="flex-1 overflow-y-auto p-8 relative">
        {renderView()}
      </main>
    </div>
  );
};

export default App;
