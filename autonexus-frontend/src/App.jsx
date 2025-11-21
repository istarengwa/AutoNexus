import React, { useState, useEffect, useRef } from 'react';
import { 
  LayoutDashboard, Network, Bot, Settings, Terminal, Send, Cpu, 
  CheckCircle, AlertCircle, Activity, Play, Pause, Trash2, Box, Server, Wifi, WifiOff, Key, X, Mail, MessageSquare
} from 'lucide-react';

const API_URL = "http://localhost:8000/api";

const StatusBadge = ({ status }) => {
  const colors = {
    active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    paused: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    offline: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  };
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium border ${colors[status] || colors.offline}`}>
      {status.toUpperCase()}
    </span>
  );
};

const ConnectionsTab = ({ isBackendOnline }) => {
  const [services, setServices] = useState([
    // Mise à jour visuelle pour Discord
    { id: 'discord', name: 'Discord Bot', icon: '🤖', configured: false, desc: 'Read Channels & Send Messages', placeholder: 'Bot Token (M.xxxx...)' },
    { id: 'twitter', name: 'X (Twitter)', icon: '🐦', configured: false, desc: 'Bearer Token', placeholder: 'AAAA...' },
    { id: 'notion', name: 'Notion', icon: '📝', configured: false, desc: 'Integration Secret', placeholder: 'secret_...' },
    { id: 'gmail', name: 'Gmail SMTP', icon: '📧', configured: false, desc: 'Email:AppPassword', placeholder: 'me@gmail.com:xxxx xxxx xxxx xxxx' },
    { id: 'openai', name: 'OpenAI', icon: '🧠', configured: false, desc: 'Agent Intelligence', placeholder: 'sk-...' },
  ]);

  const [selectedService, setSelectedService] = useState(null);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [statusMsg, setStatusMsg] = useState('');

  useEffect(() => {
    if (isBackendOnline) {
      services.forEach(async (s) => {
        try {
          const res = await fetch(`${API_URL}/credentials/check/${s.id}`);
          const data = await res.json();
          if (data.configured) setServices(prev => prev.map(item => item.id === s.id ? { ...item, configured: true } : item));
        } catch (e) {}
      });
    }
  }, [isBackendOnline]);

  const handleSave = async () => {
    if (!apiKeyInput) return;
    try {
      const res = await fetch(`${API_URL}/credentials`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ serviceId: selectedService.id, apiKey: apiKeyInput })
      });
      if (res.ok) {
        setServices(prev => prev.map(item => item.id === selectedService.id ? { ...item, configured: true } : item));
        setSelectedService(null); setApiKeyInput(''); setStatusMsg('Credential Saved!');
        setTimeout(() => setStatusMsg(''), 3000);
      }
    } catch (e) { setStatusMsg('Save Error'); }
  };

  return (
    <div className="space-y-6 relative">
      {statusMsg && <div className="absolute top-0 right-0 bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm animate-bounce">{statusMsg}</div>}
      {selectedService && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 p-6 rounded-xl w-full max-w-md shadow-2xl">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold text-white flex items-center gap-2">{selectedService.icon} Configure {selectedService.name}</h3>
              <button onClick={() => setSelectedService(null)} className="text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-slate-400 mb-1 uppercase">
                  {selectedService.id === 'gmail' ? 'Email : App Password' : 'API Key / Token'}
                </label>
                <input type="password" value={apiKeyInput} onChange={(e) => setApiKeyInput(e.target.value)} placeholder={selectedService.placeholder} className="w-full bg-slate-800 border border-slate-700 rounded p-3 text-white outline-none font-mono text-sm" />
                {selectedService.id === 'gmail' && <p className="text-[10px] text-emerald-400 mt-1">Required format: email@gmail.com:abcd efgh ijkl mnop</p>}
                {selectedService.id === 'discord' && <p className="text-[10px] text-emerald-400 mt-1">Use a Bot Token (not a webhook) to read channels.</p>}
              </div>
              <button onClick={handleSave} className="w-full bg-blue-600 hover:bg-blue-500 text-white py-2 rounded-lg font-medium transition-colors">Save Credential</button>
            </div>
          </div>
        </div>
      )}
      <div className="bg-slate-800 p-6 rounded-xl border border-slate-700">
        <h2 className="text-xl font-bold text-white mb-2">Connection Hub</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
          {services.map((service) => (
            <div key={service.id} className={`p-4 rounded-xl border transition-all flex items-center justify-between ${service.configured ? 'bg-emerald-900/10 border-emerald-500/30' : 'bg-slate-800 border-slate-700'}`}>
              <div className="flex items-center gap-4">
                <div className="text-2xl bg-slate-900 w-12 h-12 flex items-center justify-center rounded-lg border border-slate-700">{service.icon}</div>
                <div><h3 className="font-bold text-white">{service.name}</h3><p className="text-xs text-slate-400">{service.desc}</p></div>
              </div>
              <button onClick={() => { setSelectedService(service); setApiKeyInput(''); }} className={`px-4 py-2 rounded-lg text-xs font-bold transition-colors border ${service.configured ? 'bg-slate-800 text-emerald-400 border-emerald-500/30' : 'bg-blue-600 text-white border-transparent'}`}>{service.configured ? 'Edit' : 'Connect'}</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const DashboardTab = ({ setActiveTab, isBackendOnline }) => {
  const [workflows, setWorkflows] = useState([]);
  useEffect(() => {
    if (isBackendOnline) fetch(`${API_URL}/workflows`).then(r => r.json()).then(data => setWorkflows(data)).catch(e => console.error(e));
  }, [isBackendOnline]);

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="p-6 border-b border-slate-700 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Active Agents</h2>
        <button onClick={() => setActiveTab('builder')} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm flex items-center"><Bot className="w-4 h-4 mr-2" /> Create</button>
      </div>
      <div className="divide-y divide-slate-700">
        {workflows.map((wf) => (
          <div key={wf.id} className="p-6 flex items-center justify-between">
            <div><h3 className="font-medium text-white">{wf.name}</h3><p className="text-slate-400 text-sm">{wf.description || `Source: ${wf.source}`}</p></div>
            <StatusBadge status={wf.status} />
          </div>
        ))}
        {workflows.length === 0 && <div className="p-8 text-center text-slate-500">No agents configured.</div>}
      </div>
    </div>
  );
};

const AgentBuilderTab = ({ setActiveTab }) => {
  const [chatHistory, setChatHistory] = useState([{ role: 'agent', content: "Describe your automation need (e.g., 'Listen to Discord channel for \"react\" and email me').", type: 'text' }]);
  const [userInput, setUserInput] = useState('');
  const [formData, setFormData] = useState({});
  const [formMeta, setFormMeta] = useState({ source: '', dest: '' });

  const sendMessage = async () => {
    if (!userInput.trim()) return;
    const newHist = [...chatHistory, { role: 'user', content: userInput, type: 'text' }];
    setChatHistory(newHist);
    setUserInput('');

    try {
      const res = await fetch(`${API_URL}/agent/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userInput, history: [] })
      });
      const data = await res.json();
      setChatHistory(prev => [...prev, data]);
      
      if (data.type === 'form') {
        setFormMeta({ source: data.formData.serviceSource, dest: data.formData.serviceDest });
        setFormData({});
      }
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'agent', content: "Backend Error.", type: 'error' }]);
    }
  };

  const deploy = async () => {
    try {
      const payload = { serviceSource: formMeta.source, serviceDest: formMeta.dest, settings: formData };
      const res = await fetch(`${API_URL}/agent/deploy`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      setChatHistory(prev => [...prev, { role: 'agent', content: data.message, type: 'success' }]);
    } catch (e) {}
  };

  return (
    <div className="h-[600px] flex flex-col bg-slate-900 rounded-xl border border-slate-700">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.map((msg, i) => (
          <div key={i} className={`p-4 rounded-xl max-w-[80%] ${msg.role === 'user' ? 'ml-auto bg-blue-600' : 'bg-slate-800 border border-slate-700'}`}>
            <div className="whitespace-pre-wrap">{msg.content}</div>
            {msg.type === 'form' && (
              <div className="mt-4 space-y-3 bg-slate-900/50 p-3 rounded-lg border border-slate-700/50">
                {msg.formData.fields.map((f, idx) => (
                  <div key={idx}>
                    <label className="text-xs text-slate-400 block mb-1">{f.label}</label>
                    <input 
                      type={f.type} 
                      placeholder={f.placeholder}
                      className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white outline-none focus:border-blue-500"
                      onChange={e => { setFormData(prev => ({ ...prev, [f.key]: e.target.value })); }}
                    />
                  </div>
                ))}
                <button onClick={deploy} className="w-full bg-emerald-600 hover:bg-emerald-500 py-2 rounded text-sm font-bold mt-2 transition-colors">Activate Agent</button>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="p-4 border-t border-slate-700 flex gap-2">
        <input value={userInput} onChange={e => setUserInput(e.target.value)} className="flex-1 bg-slate-800 rounded-lg px-4 outline-none text-white" onKeyDown={e => e.key === 'Enter' && sendMessage()} placeholder="Type your request..." />
        <button onClick={sendMessage} className="bg-blue-600 p-2 rounded-lg text-white"><Send className="w-5 h-5" /></button>
      </div>
    </div>
  );
};

export default function AutoNexus() {
  const [activeTab, setActiveTab] = useState('connections');
  const [isBackendOnline, setIsBackendOnline] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/system/stats`).then(r => r.ok && setIsBackendOnline(true)).catch(() => setIsBackendOnline(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans flex">
      <aside className="w-64 bg-slate-900 border-r border-slate-800 p-4 flex flex-col gap-2">
        <div className="font-bold text-xl text-emerald-400 mb-6 flex items-center gap-2"><Box /> AutoNexus</div>
        <button onClick={() => setActiveTab('builder')} className={`p-3 rounded flex gap-3 ${activeTab === 'builder' ? 'bg-blue-600' : 'hover:bg-slate-800'}`}><Bot /> Architect</button>
        <button onClick={() => setActiveTab('dashboard')} className={`p-3 rounded flex gap-3 ${activeTab === 'dashboard' ? 'bg-slate-800' : 'hover:bg-slate-800'}`}><LayoutDashboard /> Dashboard</button>
        <button onClick={() => setActiveTab('connections')} className={`p-3 rounded flex gap-3 ${activeTab === 'connections' ? 'bg-slate-800 border border-blue-500/30' : 'hover:bg-slate-800'}`}><Network /> Connections</button>
        <div className="mt-auto text-xs text-slate-500 flex items-center gap-2">
          {isBackendOnline ? <Wifi className="text-emerald-500 w-4 h-4" /> : <WifiOff className="text-red-500 w-4 h-4" />} Server: {isBackendOnline ? 'Online' : 'Offline'}
        </div>
      </aside>
      <main className="flex-1 p-8 overflow-auto">
        {activeTab === 'connections' && <ConnectionsTab isBackendOnline={isBackendOnline} />}
        {activeTab === 'builder' && <AgentBuilderTab setActiveTab={setActiveTab} isBackendOnline={isBackendOnline} />}
        {activeTab === 'dashboard' && <DashboardTab setActiveTab={setActiveTab} isBackendOnline={isBackendOnline} />}
      </main>
    </div>
  );
}