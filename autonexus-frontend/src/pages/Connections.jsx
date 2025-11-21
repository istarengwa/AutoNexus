import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { api } from '../services/api';

const SERVICES_CONFIG = [
  { id: 'discord', name: 'Discord Bot', icon: '🤖', desc: 'Read Channels & Send Messages', placeholder: 'Bot Token (M.xxxx...)' },
  { id: 'twitter', name: 'X (Twitter)', icon: '🐦', desc: 'Bearer Token', placeholder: 'AAAA...' },
  { id: 'notion', name: 'Notion', icon: '📝', desc: 'Integration Secret', placeholder: 'secret_...' },
  { id: 'gmail', name: 'Gmail SMTP', icon: '📧', desc: 'Email:AppPassword', placeholder: 'me@gmail.com:xxxx xxxx xxxx xxxx' },
  { id: 'openai', name: 'OpenAI', icon: '🧠', desc: 'Agent Intelligence', placeholder: 'sk-...' },
];

export default function Connections({ isBackendOnline }) {
  const [services, setServices] = useState(SERVICES_CONFIG.map(s => ({ ...s, configured: false })));
  const [selectedService, setSelectedService] = useState(null);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [statusMsg, setStatusMsg] = useState('');

  useEffect(() => {
    if (isBackendOnline) {
      // Check status for all services
      services.forEach(async (s) => {
        try {
          const data = await api.checkCredential(s.id);
          if (data.configured) {
            setServices(prev => prev.map(item => item.id === s.id ? { ...item, configured: true } : item));
          }
        } catch (e) {}
      });
    }
  }, [isBackendOnline]);

  const handleSave = async () => {
    if (!apiKeyInput) return;
    try {
      await api.saveCredential(selectedService.id, apiKeyInput);
      setServices(prev => prev.map(item => item.id === selectedService.id ? { ...item, configured: true } : item));
      setSelectedService(null);
      setApiKeyInput('');
      setStatusMsg('Credential Saved!');
      setTimeout(() => setStatusMsg(''), 3000);
    } catch (e) {
      setStatusMsg('Save Error');
    }
  };

  return (
    <div className="space-y-6 relative">
      {statusMsg && <div className="absolute top-0 right-0 bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm animate-bounce">{statusMsg}</div>}
      
      {/* Modal */}
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
              </div>
              <button onClick={handleSave} className="w-full bg-blue-600 hover:bg-blue-500 text-white py-2 rounded-lg font-medium transition-colors">Save Credential</button>
            </div>
          </div>
        </div>
      )}

      {/* Grid */}
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
}