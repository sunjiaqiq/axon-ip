
export enum ViewType {
  AUTOMATION = 'automation',
  MATERIAL = 'material',
  ORAL_BROADCAST = 'oral_broadcast',
  COPYWRITING = 'copywriting',
  COMPLIANCE = 'compliance',
  DISTRIBUTION = 'distribution',
  AVATAR_LIVE = 'avatar_live',
  FINISHED_MATERIAL = 'finished_material',
  SETTINGS = 'settings',
  EXECUTION = 'execution'
}

export interface WorkflowConfig {
  copywritingTemplate: string;
  complianceEnabled: boolean;
  materialModule: string;
  platforms: string[];
}

export interface Platform {
  id: string;
  name: string;
  icon: string;
  status: 'connected' | 'disconnected';
  followers?: string;
  likes?: string;
  accountName?: string;
}
