
import React, { useEffect } from 'react';

interface MaterialProductionProps {
  onSelectModule: (mod: string) => void;
}

const MaterialProduction: React.FC<MaterialProductionProps> = ({ onSelectModule }) => {
  // 直接跳转到口播视频界面
  useEffect(() => {
    onSelectModule('口播视频');
  }, [onSelectModule]);

  return null;
};

export default MaterialProduction;
