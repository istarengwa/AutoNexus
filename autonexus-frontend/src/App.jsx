import React, { useState, useEffect } from 'react';
import { Box, Bot, LayoutDashboard, Network, Wifi, WifiOff } from 'lucide-react';
import { api } from './services/api';

// Import des pages
import Dashboard from './pages/Dashboard';
import AgentBuilder from './pages/AgentBuilder';
import Connections from './pages/Connections';

export default function App() {
  const [activeTab, setActiveTab] = useState('connections');
  const [isBackendOnline, setIsBackendOnline] = useState(false);

  useEffect(() => {
    api.checkHealth().then(setIsBackendOnline).catch(() => setIsBackendOnline(false));
  }, []);

  // Sidebar Button Component
  const NavButton = ({ tab, label, icon: Icon }) => (
    <button 
      onClick={() => setActiveTab(tab)} 
      className={`p-3 rounded flex gap-3 w-full transition-colors ${activeTab === tab ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}
    >
      <Icon className="w-5 h-5" /> {label}
    </button>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans flex">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 border-r border-slate-800 p-4 flex flex-col gap-2">
        <div className="font-bold text-xl text-emerald-400 mb-6 flex items-center gap-2 px-2">
          <Box /> AutoNexus
        </div>
        
        <NavButton tab="builder" label="Architect" icon={Bot} />
        <NavButton tab="dashboard" label="Dashboard" icon={LayoutDashboard} />
        <NavButton tab="connections" label="Connections" icon={Network} />

        <div className="mt-auto text-xs text-slate-500 flex items-center gap-2 px-2 py-4 border-t border-slate-800">
          {isBackendOnline ? <Wifi className="text-emerald-500 w-4 h-4" /> : <WifiOff className="text-red-500 w-4 h-4" />} 
          Server: {isBackendOnline ? 'Online' : 'Offline'}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 p-8 overflow-auto">
        {activeTab === 'connections' && <Connections isBackendOnline={isBackendOnline} />}
        {activeTab === 'builder' && <AgentBuilder setActiveTab={setActiveTab} />}
        {activeTab === 'dashboard' && <Dashboard isBackendOnline={isBackendOnline} setActiveTab={setActiveTab} />}
      </main>
    </div>
  );
}