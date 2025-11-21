import React from 'react';

const StatusBadge = ({ status }) => {
  const colors = {
    active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    paused: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    offline: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  };
  
  const safeStatus = status ? status.toLowerCase() : 'offline';

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium border ${colors[safeStatus] || colors.offline}`}>
      {status ? status.toUpperCase() : 'UNKNOWN'}
    </span>
  );
};

export default StatusBadge;